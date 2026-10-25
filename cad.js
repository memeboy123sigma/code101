import * as THREE from "https://unpkg.com/three@0.160.0/build/three.module.js";

const act = (m) => (window.jarvisAct ? window.jarvisAct(m) : console.log(m));
const BTN = "text-decoration:none;font:inherit;font-size:15px;padding:8px 14px;background:rgba(0,40,90,.7);color:#00e5ff;border:1px solid #00e5ff;border-radius:6px";
const mount = document.getElementById("cadmount");
mount.innerHTML = `
  <h3>CAD · <span id="cadmode">OFF</span></h3>
  <div id="cadstatus" style="font-size:12px;color:#8fdcff;margin-bottom:6px">say “design a phone stand”, or type it</div>
  <canvas id="cadcanvas" style="width:100%;aspect-ratio:4/3;background:#00060f;border:1px solid #0a6a88;touch-action:none"></canvas>
  <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
    <a href="/cad/model.stl?dl=1" download style="${BTN}">STL ⬇</a>
    <a href="/cad/model.scad?dl=1" download style="${BTN}">SCAD ⬇</a>
    <button class="btn" id="cadcodebtn" type="button">code</button>
    <button class="btn" id="cadnew" type="button">new</button>
  </div>
  <pre id="cadcode" style="display:none;max-height:180px;overflow:auto;font-size:11px;color:#8fdcff;margin:8px 0 0;white-space:pre-wrap"></pre>`;
const $ = (id) => document.getElementById(id);

// ---------- viewer ----------
const canvas = $("cadcanvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(45, 4 / 3, 0.1, 100);
cam.position.set(0, 1.5, 7);
scene.add(new THREE.AmbientLight(0x88aacc, 1.4));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(3, 6, 5);
scene.add(sun);
const holder = new THREE.Group();
scene.add(holder);
let mesh = null, targetY = 0, targetX = 0.35, idleAt = 0, drag = null;

function parseStl(buf) {
  const dec = new TextDecoder();
  if (/^\s*solid/.test(dec.decode(buf.slice(0, 64))) && /facet|vertex/.test(dec.decode(buf.slice(0, 1024)))) {
    const re = /vertex\s+(\S+)\s+(\S+)\s+(\S+)/g, out = [];
    let m;
    const txt = dec.decode(buf);
    while ((m = re.exec(txt))) out.push(+m[1], +m[2], +m[3]);
    return new Float32Array(out);
  }
  const dv = new DataView(buf), n = dv.getUint32(80, true), out = new Float32Array(n * 9);
  for (let i = 0; i < n; i++) for (let j = 0; j < 9; j++) out[i * 9 + j] = dv.getFloat32(84 + i * 50 + 12 + j * 4, true);
  return out;
}
async function loadModel(v) {
  const pos = parseStl(await (await fetch("/cad/model.stl?v=" + v, { cache: "no-store" })).arrayBuffer());
  if (pos.length < 9) throw new Error("empty model");
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.computeVertexNormals();
  geo.computeBoundingBox();
  const size = new THREE.Vector3(), c = new THREE.Vector3();
  geo.boundingBox.getSize(size);
  geo.boundingBox.getCenter(c);
  geo.translate(-c.x, -c.y, -c.z);
  if (mesh) { holder.remove(mesh); mesh.children.forEach(o => o.geometry.dispose()); }
  mesh = new THREE.Group();
  mesh.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color: 0x00cfff, shininess: 90, flatShading: true, transparent: true, opacity: 0.88 })));
  mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25), new THREE.LineBasicMaterial({ color: 0xbff6ff })));
  mesh.rotation.x = -Math.PI / 2;
  mesh.scale.setScalar(3.2 / Math.max(size.x, size.y, size.z, 1e-6));
  holder.add(mesh);
  act("model loaded: " + size.x.toFixed(0) + " x " + size.y.toFixed(0) + " x " + size.z.toFixed(0) + " mm");
}
function render() {
  requestAnimationFrame(render);
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (w && (canvas.width !== w || canvas.height !== h)) {
    renderer.setSize(w, h, false);
    cam.aspect = w / h;
    cam.updateProjectionMatrix();
  }
  if (performance.now() - idleAt > 3000) targetY += 0.006;
  holder.rotation.y += (targetY - holder.rotation.y) * 0.12;
  holder.rotation.x += (targetX - holder.rotation.x) * 0.12;
  renderer.render(scene, cam);
}
render();
canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener("pointermove", (e) => {
  if (!drag) return;
  targetY += (e.clientX - drag.x) * 0.01;
  targetX += (e.clientY - drag.y) * 0.01;
  drag = { x: e.clientX, y: e.clientY };
  idleAt = performance.now();
});
canvas.addEventListener("pointerup", () => { drag = null; });
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  cam.position.z = Math.min(14, Math.max(3, cam.position.z + e.deltaY * 0.005));
}, { passive: false });
window.jarvisSwipe = (dx) => { targetY += (dx < 0 ? 1 : -1) * Math.PI / 2; idleAt = performance.now(); };

// ---------- buttons ----------
$("cadcodebtn").addEventListener("click", () => {
  const p = $("cadcode");
  p.style.display = p.style.display === "none" ? "block" : "none";
});
$("cadnew").addEventListener("click", async () => {
  await fetch("/cad/reset", { method: "POST" });
  if (mesh) { holder.remove(mesh); mesh = null; }
  $("cadcode").textContent = "";
  $("cadstatus").textContent = "new model: say or type what to design";
  act("CAD: new model");
});

// ---------- talking to the CAD maker ----------
let cadMode = false;
const setMode = () => { $("cadmode").textContent = cadMode ? "ON" : "OFF"; };

window.jarvisCad = async (text) => {
  const t = text.trim();
  if (/^(exit|leave|stop|quit)( the)? cad\b/i.test(t)) { cadMode = false; setMode(); return "Okay, leaving CAD mode."; }
  const start = /^(jarvis[,.\s]+)?(cad|design|model)\b/i.test(t);
  if (!cadMode && !start) return null;
  if (!cadMode) { cadMode = true; setMode(); act("CAD mode on"); }
  const t0 = performance.now();
  let final = null;
  try {
    const res = await fetch("/cad", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: t, fresh: start }) });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let acc = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      acc += dec.decode(value, { stream: true });
      let i;
      while ((i = acc.indexOf("\n")) >= 0) {
        const ln = acc.slice(0, i).trim();
        acc = acc.slice(i + 1);
        if (!ln) continue;
        try {
          const ev = JSON.parse(ln);
          if (ev.event === "status") { act("CAD: " + ev.msg); $("cadstatus").textContent = ev.msg; }
          else if (ev.event === "done") final = ev;
        } catch (e) {}
      }
    }
  } catch (err) {
    act("CAD error: " + (err.message || err));
  }
  const secs = ((performance.now() - t0) / 1000).toFixed(0);
  if (final && final.ok) {
    $("cadcode").textContent = final.scad;
    $("cadstatus").textContent = "built in " + secs + "s · drag to rotate";
    try { await loadModel(final.version); } catch (e) { act("viewer error: " + e.message); }
    return "Done. The model is ready in the side panel.";
  }
  act("CAD failed: " + (final ? String(final.error).slice(0, 160) : "no answer"));
  $("cadstatus").textContent = "couldn't build that. Try something simpler.";
  return "Sorry, I couldn't build that one. Try describing something simpler.";
};
