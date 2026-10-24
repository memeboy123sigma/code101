<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Jarvis</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; background: #000; color: #0ff;
               font-family: system-ui, sans-serif; }
  body { display: flex; flex-direction: column;
         padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  #log { flex: 1; overflow-y: auto; padding: 16px; font-size: 17px; line-height: 1.45; }
  .you { color: #7ff; margin: 10px 0 2px; }
  .jarvis { color: #ff0; margin: 2px 0 12px; white-space: pre-wrap; }
  #stage { display: flex; flex-direction: column; align-items: center; padding: 8px 0 12px; }
  #orb { width: 120px; height: 120px; border-radius: 50%; border: 0; cursor: pointer;
         background: radial-gradient(circle, #aff, #0ff 55%, #046); box-shadow: 0 0 40px #0ff; }
  #orb.listening { background: radial-gradient(circle, #cfc, #0f6 55%, #040);
                   box-shadow: 0 0 50px #0f6; animation: pulse 1.1s infinite; }
  #orb.thinking { background: radial-gradient(circle, #ffc, #fc0 55%, #640);
                  box-shadow: 0 0 44px #fc0; animation: pulse 0.5s infinite; }
  #orb.speaking { background: radial-gradient(circle, #fcf, #f0f 55%, #404);
                  box-shadow: 0 0 50px #f0f; animation: pulse 0.8s infinite; }
  @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }
  #heard { min-height: 1.4em; margin-top: 12px; padding: 0 16px; text-align: center;
           color: #7ff; font-size: 16px; }
  #status { margin-top: 6px; font-size: 13px; color: #088; text-align: center; padding: 0 16px; }
  #forget { margin-top: 6px; background: none; border: 0; color: #066; font-size: 12px; }
  form { display: flex; gap: 8px; padding: 0 12px 12px; }
  input { flex: 1; font-size: 16px; padding: 10px 12px; background: #021; color: #0ff;
          border: 1px solid #066; border-radius: 8px; }
  form button { font-size: 16px; padding: 0 16px; background: #022; color: #0ff;
                border: 1px solid #066; border-radius: 8px; }
</style>
</head>
<body>
<div id="log"></div>
<div id="stage">
  <button id="orb" aria-label="Talk to Jarvis"></button>
  <div id="heard"></div>
  <div id="status"></div>
  <button id="forget" type="button">new chat</button>
</div>
<form id="form">
  <input id="input" placeholder="or type here" autocomplete="off">
  <button>Send</button>
</form>

<script>
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const logEl = document.getElementById("log");
const orb = document.getElementById("orb");
const heardEl = document.getElementById("heard");
const statusEl = document.getElementById("status");
const form = document.getElementById("form");
const input = document.getElementById("input");

let state = "idle", notice = "";
let convo = false, isListening = false, rec = null, silentRuns = 0;
let convoGen = 0, pending = 0, streamDone = true, abortCtl = null;
let buf = "", spokenAny = false, voice = null, unlocked = false;

const labels = { idle: "Tap to talk", listening: "Listening…",
                 thinking: "Thinking…", speaking: "Speaking · tap to interrupt" };
function setState(s) {
  state = s;
  orb.className = s;
  statusEl.textContent = notice || labels[s];
}

function pickVoice() {
  const vs = speechSynthesis.getVoices();
  voice = vs.find(v => /^en[-_](US|GB)/i.test(v.lang) && /google|natural|premium|enhanced/i.test(v.name))
       || vs.find(v => /^en/i.test(v.lang)) || null;
}
pickVoice();
speechSynthesis.onvoiceschanged = pickVoice;

function unlock() {
  if (unlocked) return;
  unlocked = true;
  try { speechSynthesis.speak(new SpeechSynthesisUtterance("")); } catch (e) {}
  try { navigator.wakeLock && navigator.wakeLock.request("screen").catch(() => {}); } catch (e) {}
}

function addLine(cls, text) {
  const d = document.createElement("div");
  d.className = cls;
  d.textContent = text;
  logEl.appendChild(d);
  logEl.scrollTop = logEl.scrollHeight;
  return d;
}

function speak(text) {
  text = text.trim();
  if (!text) return;
  const gen = convoGen;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = 1.1;
  if (voice) u.voice = voice;
  pending++;
  spokenAny = true;
  setState("speaking");
  let finished = false;
  const done = () => {
    if (finished || gen !== convoGen) return;
    finished = true;
    pending--;
    maybeNext();
  };
  u.onend = done;
  u.onerror = done;
  speechSynthesis.speak(u);
}

function flushChunks(final) {
  while (true) {
    const min = spokenAny ? 25 : 10;
    let cut = -1;
    for (let i = min; i < buf.length - 1; i++) {
      if (".!?,;:".includes(buf[i]) && /\s/.test(buf[i + 1])) { cut = i + 1; break; }
    }
    if (cut < 0) break;
    speak(buf.slice(0, cut));
    buf = buf.slice(cut);
  }
  if (final && buf.trim()) { speak(buf); buf = ""; }
}

function stopSpeaking() {
  convoGen++;
  pending = 0;
  try { speechSynthesis.cancel(); } catch (e) {}
  if (abortCtl) { abortCtl.abort(); abortCtl = null; }
}

function maybeNext() {
  if (!streamDone || pending > 0 || isListening) return;
  if (convo) {
    setTimeout(() => { if (!isListening && pending <= 0) startListening(); }, 250);
  } else {
    setState("idle");
  }
}

async function send(text) {
  const myGen = convoGen;
  setState("thinking");
  addLine("you", text);
  const jEl = addLine("jarvis", "");
  buf = "";
  spokenAny = false;
  streamDone = false;
  abortCtl = new AbortController();
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: abortCtl.signal
    });
    if (!res.ok) throw new Error("server " + res.status);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let full = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const piece = dec.decode(value, { stream: true });
      full += piece;
      buf += piece;
      jEl.textContent = full;
      logEl.scrollTop = logEl.scrollHeight;
      flushChunks(false);
    }
    flushChunks(true);
  } catch (err) {
    if (err.name === "AbortError") return;
    jEl.textContent = "(couldn't reach the Pi)";
  }
  if (myGen !== convoGen) return;
  streamDone = true;
  maybeNext();
}

function startListening() {
  if (isListening) return;
  if (!SR) {
    notice = "This browser can't do speech input. Try Chrome on Android, or type below.";
    convo = false;
    setState("idle");
    return;
  }
  notice = "";
  isListening = true;
  heardEl.textContent = "";
  let finalText = "", lastHeard = "";
  rec = new SR();
  rec.lang = "en-US";
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;
  rec.onresult = (e) => {
    let finalPart = "", interim = "";
    for (let i = 0; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalPart += r[0].transcript; else interim += r[0].transcript;
    }
    finalText = finalPart;
    lastHeard = finalPart + interim;
    heardEl.textContent = lastHeard;
  };
  rec.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      notice = "Mic blocked. Allow the microphone for this site.";
      convo = false;
    } else if (e.error === "network") {
      notice = "Speech service unreachable. Check your internet.";
      convo = false;
    }
  };
  rec.onend = () => {
    isListening = false;
    const text = (finalText || lastHeard).trim();
    if (!convo) { setState("idle"); return; }
    if (text) { silentRuns = 0; heardEl.textContent = ""; send(text); }
    else if (++silentRuns >= 2) { convo = false; setState("idle"); }
    else startListening();
  };
  setState("listening");
  try { rec.start(); } catch (err) { isListening = false; setState("idle"); }
}

orb.addEventListener("click", () => {
  unlock();
  if (state === "idle") {
    convo = true;
    silentRuns = 0;
    startListening();
  } else if (state === "listening") {
    convo = false;
    try { rec.abort(); } catch (e) {}
  } else {
    stopSpeaking();
    convo = true;
    silentRuns = 0;
    startListening();
  }
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  unlock();
  stopSpeaking();
  convo = false;
  send(text);
});

document.getElementById("forget").addEventListener("click", () => {
  fetch("/forget", { method: "POST" });
  logEl.replaceChildren();
});

setState("idle");
</script>
</body>
</html>
