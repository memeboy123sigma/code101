import os, re, json, shutil, subprocess, threading
import urllib.request
from flask import Flask, Response, request, send_file, send_from_directory

MODEL = "gemma2:2b"        # must match `ollama list`
CAD_MODEL = MODEL          # for better CAD: ollama pull qwen2.5-coder:3b, then put that name here
OLLAMA = "http://localhost:11434"
OPTIONS = {"num_predict": 80, "num_ctx": 4096}
STYLE = ("You are Jarvis, a fast, friendly voice assistant. Your reply is spoken out loud: "
         "answer in one or two short sentences, simple words, no markdown, no lists, no emojis.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_DIR = os.path.join(BASE_DIR, "cad_work")
os.makedirs(CAD_DIR, exist_ok=True)
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))
history = []
cad = {"scad": "", "version": 0}


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


# ---------------- CAD ----------------
RULES = ("You are an expert OpenSCAD programmer. Write ONE complete OpenSCAD script for the part described. "
         "Rules: units are millimetres; keep the part under 150 mm; use only cube, cylinder, sphere, translate, "
         "rotate, scale, union, difference, intersection, linear_extrude, rotate_extrude; use $fn=48 on round "
         "shapes; make cuts slightly bigger than the part so holes go all the way through; "
         "output ONLY code, no explanation, no markdown.")
EXAMPLES = '''Request: a box 40 by 30 by 15 with a 6 mm hole through the middle
Code:
difference() {
  cube([40, 30, 15]);
  translate([20, 15, -1]) cylinder(h = 17, d = 6, $fn = 48);
}

Request: an L bracket 50 long, 20 wide, 3 thick, 30 tall, with a screw hole in each arm
Code:
difference() {
  union() {
    cube([50, 20, 3]);
    cube([3, 20, 30]);
  }
  translate([35, 10, -1]) cylinder(h = 5, d = 4, $fn = 48);
  translate([-1, 10, 20]) rotate([0, 90, 0]) cylinder(h = 5, d = 4, $fn = 48);
}
'''


def ask_model(prompt):
    body = {"model": CAD_MODEL, "prompt": prompt, "stream": False, "keep_alive": "60m",
            "options": {**OPTIONS, "num_predict": 700, "temperature": 0.3}}
    with post("/api/generate", body, 300) as r:
        return json.loads(r.read()).get("response", "")


def clean_code(t):
    m = re.search(r"```(?:\w+)?\n(.*?)```", t, re.S)
    t = (m.group(1) if m else t).strip()
    t = re.sub(r"^(code|openscad)\s*:\s*", "", t, flags=re.I)
    return re.sub(r"\$fn\s*=\s*(\d+)", lambda m: "$fn = %d" % min(int(m.group(1)), 64), t).strip()


def check_code(c):
    plain = re.sub(r"/\*.*?\*/", "", c, flags=re.S)
    plain = re.sub(r"//[^\n]*", "", plain)
    if not c:
        return "the answer was empty"
    if len(c) > 4000:
        return "the script was too long"
    if re.search(r"\b(include|use)\s*<|\b(import|surface|text|projection)\s*\(", plain):
        return "it used a blocked command"
    if not re.search(r"\b(cube|cylinder|sphere|linear_extrude|rotate_extrude)\b", plain):
        return "there were no shapes in the script"
    return ""


def build_stl(code):
    scad = os.path.join(CAD_DIR, "try.scad")
    stl = os.path.join(CAD_DIR, "try.stl")
    with open(scad, "w") as f:
        f.write(code)
    if os.path.exists(stl):
        os.remove(stl)
    try:
        r = subprocess.run(["openscad", "-o", stl, scad], capture_output=True, text=True,
                           timeout=90, cwd=CAD_DIR)
    except FileNotFoundError:
        return "OpenSCAD isn't installed (run: sudo apt install -y openscad)"
    except subprocess.TimeoutExpired:
        return "the build took too long"
    if r.returncode != 0 or not os.path.exists(stl) or os.path.getsize(stl) < 200:
        return (r.stderr or r.stdout or "").strip()[-400:] or "the model came out empty"
    shutil.copyfile(scad, os.path.join(CAD_DIR, "model.scad"))
    os.replace(stl, os.path.join(CAD_DIR, "model.stl"))
    return ""


@app.route("/cad", methods=["POST"])
def cad_route():
    data = request.get_json() or {}
    text = data.get("text", "").strip()[:400]
    base = "" if data.get("fresh") else cad["scad"]

    def line(**kw):
        return json.dumps(kw) + "\n"

    def gen():
        code, err = "", ""
        for attempt in range(1, 4):
            yield line(event="status", msg="writing OpenSCAD (attempt %d of 3)" % attempt)
            if attempt > 1:
                prompt = (RULES + "\n\nRequest: " + text + "\nThis script failed:\n" + code +
                          "\n\nError: " + err + "\nFix it. Output the complete corrected script only.\nCode:\n")
            elif base:
                prompt = (RULES + "\n\nCurrent OpenSCAD script:\n" + base + "\n\nChange it as requested: " +
                          text + "\nOutput the complete updated script only.\nCode:\n")
            else:
                prompt = RULES + "\n\n" + EXAMPLES + "\nRequest: " + text + "\nCode:\n"
            try:
                code = clean_code(ask_model(prompt))
            except Exception as e:
                yield line(event="done", ok=False, error="couldn't reach Ollama: %s" % e)
                return
            err = check_code(code)
            if not err:
                yield line(event="status", msg="building the 3D model")
                err = build_stl(code)
            if not err:
                break
            yield line(event="status", msg="problem: " + err[:100].replace("\n", " "))
        else:
            yield line(event="done", ok=False, error=err)
            return
        cad["scad"] = code
        cad["version"] += 1
        yield line(event="done", ok=True, version=cad["version"], scad=code)

    return Response(gen(), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/cad/model.stl")
def cad_stl():
    p = os.path.join(CAD_DIR, "model.stl")
    if not os.path.exists(p):
        return ("no model yet", 404)
    return send_file(p, mimetype="model/stl", as_attachment=bool(request.args.get("dl")),
                     download_name="jarvis-model.stl", max_age=0)


@app.route("/cad/model.scad")
def cad_scad():
    p = os.path.join(CAD_DIR, "model.scad")
    if not os.path.exists(p):
        return ("no model yet", 404)
    return send_file(p, mimetype="text/plain", as_attachment=bool(request.args.get("dl")),
                     download_name="jarvis-model.scad", max_age=0)


@app.route("/cad/reset", methods=["POST"])
def cad_reset():
    cad["scad"] = ""
    return ("", 204)


if __name__ == "__main__":
    threading.Thread(target=warm_up, daemon=True).start()
    app.run(host="0.0.0.0", port=8000, threaded=True)
