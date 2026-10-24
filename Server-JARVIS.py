import os, json, threading
import urllib.request
from flask import Flask, Response, request, send_from_directory

MODEL = "gemma2:2b"                 # must match the name shown by `ollama list`
OLLAMA = "http://localhost:11434"
OPTIONS = {"num_predict": 80, "num_ctx": 1024}
STYLE = ("You are Jarvis, a fast, friendly voice assistant. Your reply is spoken out loud: "
         "answer in one or two short sentences, simple words, no markdown, no lists, no emojis.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))
history = []


def post(path, payload, timeout=120):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def warm_up():
    try:
        post("/api/generate", {"model": MODEL, "prompt": "hi", "stream": False,
                               "keep_alive": "60m", "options": OPTIONS}, 300).read()
        print("Jarvis is warmed up and ready")
    except Exception as e:
        print("Warm-up failed (is Ollama running? is MODEL the right name?):", e)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/ask", methods=["POST"])
def ask():
    text = (request.get_json() or {}).get("text", "").strip()[:500]

    def gen():
        if not text:
            return
        msgs = history[-6:] + [{"role": "user", "content": STYLE + "\n\n" + text}]
        full = ""
        try:
            with post("/api/chat", {"model": MODEL, "messages": msgs, "stream": True,
                                    "keep_alive": "60m", "options": OPTIONS}) as r:
                for line in r:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        full += piece
                        yield piece
                    if chunk.get("done"):
                        break
        except Exception as e:
            print("Ollama error:", e)
            yield "Sorry, I can't reach Ollama right now."
            return
        if full.strip():
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": full})

    return Response(gen(), mimetype="text/plain",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/forget", methods=["POST"])
def forget():
    history.clear()
    return ("", 204)


if __name__ == "__main__":
    threading.Thread(target=warm_up, daemon=True).start()
    app.run(host="0.0.0.0", port=8000, threaded=True)
