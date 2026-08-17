#!/usr/bin/env python3
# Groundhog D455 depth server: RGB/Depth/IR, emitter+laser, distance+obstacle,
# crosshair, plane-fit accuracy, depth near-object box, + AI person detection.
import pyrealsense2 as rs
import numpy as np
import io, os, threading, time, json, urllib.parse, socketserver, http.server
from PIL import Image, ImageDraw

try:
    from scipy import ndimage
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

MODEL = "/home/npalakurla/models/yolov8n.onnx"
CONF = 0.40
SESS = None
try:
    import onnxruntime as ort
    so = ort.SessionOptions(); so.intra_op_num_threads = 4
    SESS = ort.InferenceSession(MODEL, sess_options=so, providers=["CPUExecutionProvider"])
    INAME = SESS.get_inputs()[0].name
except Exception:
    SESS = None

W, H, FPS, PORT, BOUND = 640, 480, 15, 8090, "frame"
OBST_M = 0.8

state = {"view": "color", "emitter": 1, "laser": 150, "detect": 1, "near": 2.5, "ai": 0, "dirty": True}
latest = {"j": None}
depthbuf = {"arr": None}
colorbuf = {"arr": None}
persons = []
tele = {"center": 0.0, "min": 0.0, "obstacle": False, "fps": 0, "view": "color", "box": None,
        "people": 0, "ai_ready": SESS is not None}
lock = threading.Lock()


def nms(x0, y0, x1, y1, sc, th):
    idx = sc.argsort()[::-1]; keep = []; areas = (x1 - x0) * (y1 - y0)
    while idx.size > 0:
        i = idx[0]; keep.append(i)
        if idx.size == 1:
            break
        r = idx[1:]
        xx0 = np.maximum(x0[i], x0[r]); yy0 = np.maximum(y0[i], y0[r])
        xx1 = np.minimum(x1[i], x1[r]); yy1 = np.minimum(y1[i], y1[r])
        w = np.maximum(0, xx1 - xx0); h = np.maximum(0, yy1 - yy0); inter = w * h
        iou = inter / (areas[i] + areas[r] - inter + 1e-6)
        idx = r[iou < th]
    return keep


def find_box(arr, near):
    nm = (arr > 0.35) & (arr < near)
    if int(nm.sum()) < 800:
        return None
    if HAVE_SCIPY:
        small = nm[::2, ::2]; lbl, n = ndimage.label(small)
        if n == 0:
            return None
        sizes = ndimage.sum(np.ones_like(lbl), lbl, range(1, n + 1))
        k = int(np.argmax(sizes)) + 1; ys, xs = np.where(lbl == k)
        if xs.size < 200:
            return None
        x0, x1 = int(xs.min()) * 2, int(xs.max()) * 2
        y0, y1 = int(ys.min()) * 2, int(ys.max()) * 2
    else:
        ys, xs = np.where(nm)
        x0, x1 = int(np.percentile(xs, 4)), int(np.percentile(xs, 96))
        y0, y1 = int(np.percentile(ys, 4)), int(np.percentile(ys, 96))
    if (x1 - x0) < 25 or (y1 - y0) < 25:
        return None
    sub = arr[y0:y1 + 1, x0:x1 + 1]; sv = sub[(sub > 0.35) & (sub < near)]
    bd = round(float(np.median(sv)), 2) if sv.size else 0.0
    return [x0, y0, x1, y1, bd]


def detector():
    global persons
    if SESS is None:
        return
    while True:
        with lock:
            ai = state["ai"]; carr = None if colorbuf["arr"] is None else colorbuf["arr"]
        if not ai or carr is None:
            with lock:
                persons = []
            time.sleep(0.2); continue
        try:
            rgb = carr[:, :, ::-1]
            H0, W0 = rgb.shape[:2]
            scale = min(640.0 / W0, 640.0 / H0); nw, nh = int(W0 * scale), int(H0 * scale)
            px, py = (640 - nw) // 2, (640 - nh) // 2
            im = Image.fromarray(rgb).resize((nw, nh))
            canvas = np.full((640, 640, 3), 114, np.uint8); canvas[py:py + nh, px:px + nw] = np.asarray(im)
            inp = (canvas.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
            out = SESS.run(None, {INAME: inp})[0][0].T   # [8400, 84]
            ps = out[:, 4]                                # person = class 0
            m = ps > CONF
            res = []
            if m.any():
                b = out[m, :4]; sc = ps[m]
                x0 = b[:, 0] - b[:, 2] / 2; y0 = b[:, 1] - b[:, 3] / 2
                x1 = b[:, 0] + b[:, 2] / 2; y1 = b[:, 1] + b[:, 3] / 2
                x0 = (x0 - px) / scale; x1 = (x1 - px) / scale
                y0 = (y0 - py) / scale; y1 = (y1 - py) / scale
                with lock:
                    darr = None if depthbuf["arr"] is None else depthbuf["arr"]
                for i in nms(x0, y0, x1, y1, sc, 0.45):
                    xa = int(max(0, x0[i])); ya = int(max(0, y0[i]))
                    xb = int(min(W0 - 1, x1[i])); yb = int(min(H0 - 1, y1[i]))
                    dist = 0.0
                    if darr is not None and xb > xa and yb > ya:
                        sv = darr[ya:yb, xa:xb]; sv = sv[sv > 0]
                        if sv.size:
                            dist = round(float(np.median(sv)), 2)
                    res.append([xa, ya, xb, yb, round(float(sc[i]), 2), dist])
            with lock:
                persons = res
        except Exception:
            with lock:
                persons = []
        time.sleep(0.02)


def worker():
    colorizer = rs.colorizer(); colorizer.set_option(rs.option.color_scheme, 9)
    while True:
        try:
            pipe = rs.pipeline(); cfg = rs.config()
            cfg.enable_stream(rs.stream.color, W, H, rs.format.bgr8, FPS)
            cfg.enable_stream(rs.stream.depth, W, H, rs.format.z16, FPS)
            cfg.enable_stream(rs.stream.infrared, 1, W, H, rs.format.y8, FPS)
            prof = pipe.start(cfg)
            ds = prof.get_device().first_depth_sensor()
            lrange = ds.get_option_range(rs.option.laser_power)
            tframe = time.time(); fcount = 0
            while True:
                with lock:
                    view = state["view"]; detect = state["detect"]; near = state["near"]
                    if state["dirty"]:
                        try:
                            ds.set_option(rs.option.emitter_enabled, float(state["emitter"]))
                            ds.set_option(rs.option.laser_power,
                                          max(lrange.min, min(lrange.max, float(state["laser"]))))
                        except Exception:
                            pass
                        state["dirty"] = False
                fs = pipe.wait_for_frames()
                depth = fs.get_depth_frame()
                cframe = fs.get_color_frame()
                colimg = np.asanyarray(cframe.get_data()) if cframe else None
                if colimg is not None:
                    with lock:
                        colorbuf["arr"] = colimg
                cx, cy = W // 2, H // 2
                cdist = mindist = 0.0; box = None
                if depth:
                    cdist = depth.get_distance(cx, cy)
                    arr = np.asanyarray(depth.get_data()).astype(np.float32) * depth.get_units()
                    roi = arr[H // 3:2 * H // 3, W // 3:2 * W // 3]; v = roi[roi > 0]
                    mindist = float(v.min()) if v.size else 0.0
                    if detect:
                        try:
                            box = find_box(arr, near)
                        except Exception:
                            box = None
                    with lock:
                        depthbuf["arr"] = arr
                        tele["center"] = round(cdist, 2); tele["min"] = round(mindist, 2)
                        tele["obstacle"] = (0 < mindist < OBST_M); tele["box"] = box
                if view == "depth" and depth:
                    img = np.asanyarray(colorizer.colorize(depth).get_data())
                elif view == "ir":
                    irf = fs.first(rs.stream.infrared)
                    img = np.asanyarray(irf.get_data()) if irf else None
                else:
                    img = colimg
                if img is not None:
                    pim = (Image.fromarray(img, "L") if img.ndim == 2
                           else Image.fromarray(img[:, :, ::-1])).convert("RGB")
                    d = ImageDraw.Draw(pim)
                    if box:
                        bx0, by0, bx1, by1, bd = box
                        col = (255, 90, 114) if (0 < bd < OBST_M) else (90, 230, 130)
                        d.rectangle([bx0, by0, bx1, by1], outline=col, width=2)
                        d.text((bx0 + 3, by0 - 13 if by0 > 13 else by0 + 3), "object %.2f m" % bd, fill=col)
                    with lock:
                        pl = list(persons)
                    for (xa, ya, xb, yb, sc, dist) in pl:
                        d.rectangle([xa, ya, xb, yb], outline=(90, 200, 255), width=3)
                        lab = "person %.0f%%" % (sc * 100) + (" @ %.1fm" % dist if dist > 0 else "")
                        d.text((xa + 3, ya - 14 if ya > 14 else ya + 3), lab, fill=(150, 220, 255))
                    d.rectangle([W // 3, H // 3, 2 * W // 3, 2 * H // 3], outline=(255, 210, 0), width=1)
                    d.line([(cx - 18, cy), (cx + 18, cy)], fill=(255, 230, 0), width=2)
                    d.line([(cx, cy - 18), (cx, cy + 18)], fill=(255, 230, 0), width=2)
                    d.text((8, 8), "center %.2f m" % cdist, fill=(255, 255, 255))
                    d.text((8, 22), "nearest %.2f m" % mindist, fill=(255, 235, 120))
                    bio = io.BytesIO(); pim.save(bio, "JPEG", quality=68)
                    with lock:
                        latest["j"] = bio.getvalue()
                fcount += 1
                if time.time() - tframe >= 1.0:
                    with lock:
                        tele["fps"] = fcount; tele["view"] = view; tele["people"] = len(persons)
                    fcount = 0; tframe = time.time()
        except Exception:
            with lock:
                latest["j"] = None
            try:
                pipe.stop()
            except Exception:
                pass
            time.sleep(2)


def planefit():
    with lock:
        arr = None if depthbuf["arr"] is None else depthbuf["arr"].copy()
    if arr is None:
        return {"ok": False, "err": "no depth frame"}
    y0, y1, x0, x1 = int(H * 0.30), int(H * 0.70), int(W * 0.30), int(W * 0.70)
    roi = arr[y0:y1, x0:x1]; hh, ww = roi.shape
    vv, uu = np.mgrid[0:hh, 0:ww]; m = roi > 0; n = int(m.sum()); total = hh * ww
    if n < 200:
        return {"ok": False, "err": "not enough valid depth (aim at a surface, emitter on)",
                "fill_pct": round(100.0 * n / total, 1)}
    A = np.column_stack([uu[m].ravel(), vv[m].ravel(), np.ones(n)]); z = roi[m].ravel()
    coef, *_ = np.linalg.lstsq(A, z, rcond=None)
    rms = float(np.sqrt(np.mean((z - A @ coef) ** 2))); mean = float(z.mean())
    return {"ok": True, "mean_m": round(mean, 3), "rms_mm": round(rms * 1000, 1),
            "rms_pct": round(100.0 * rms / mean, 2) if mean > 0 else 0,
            "fill_pct": round(100.0 * n / total, 1), "n": n}


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Groundhog Depth Camera</title>
<style>
:root{--bg:#101216;--surf:#181b21;--surf2:#20242c;--ink:#e7eaee;--mut:#8b95a1;
--acc:#e6944b;--ok:#3fb559;--haz:#ff5a72;--blu:#5ac8ff;--line:#2a313a;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);padding:14px}
.wrap{max-width:1080px;margin:0 auto;display:grid;grid-template-columns:1fr;gap:14px}
@media(min-width:860px){.wrap{grid-template-columns:1.5fr 1fr}}
h1{font-size:16px;margin:0 0 2px}.sub{color:var(--mut);font-size:12px;font-family:var(--mono)}
.card{background:var(--surf);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card img{display:block;width:100%;background:#000;aspect-ratio:4/3;object-fit:contain}
.vbar{display:flex;gap:8px;align-items:center;padding:9px 11px;border-top:1px solid var(--line);flex-wrap:wrap}
.panel{background:var(--surf);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:16px}
.grp{display:flex;flex-direction:column;gap:10px}
.glabel{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--acc);display:flex;align-items:center;gap:8px}
.glabel::after{content:"";flex:1;height:1px;background:var(--line)}
.seg{display:flex;gap:6px}.seg button{flex:1;font-size:13px;background:var(--surf2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:9px;cursor:pointer}
.seg button.on{background:var(--acc);color:#161008;border-color:var(--acc);font-weight:650}
.sw{display:flex;align-items:center;justify-content:space-between;font-size:13px;gap:10px}.sw input{width:40px;height:22px;accent-color:var(--acc)}
.row{display:grid;grid-template-columns:74px 1fr 52px;gap:10px;align-items:center}.row output{font-family:var(--mono);font-size:12px;color:var(--mut);text-align:right}
input[type=range]{width:100%;accent-color:var(--acc)}
button.act{font-size:13px;background:var(--surf2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px;cursor:pointer}button.act:hover{border-color:var(--acc)}
.tele{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.stat{background:var(--surf2);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
.stat .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
.stat .v{font-family:var(--mono);font-size:22px;font-variant-numeric:tabular-nums;margin-top:3px}
.obst{grid-column:1/-1;display:flex;align-items:center;justify-content:center;gap:9px;font-family:var(--mono);font-size:14px;font-weight:650;padding:11px;border-radius:10px;border:1px solid var(--line)}
.obst.clear{color:var(--ok);background:color-mix(in srgb,var(--ok) 12%,transparent)}
.obst.hit{color:var(--haz);background:color-mix(in srgb,var(--haz) 15%,transparent)}
.obst .dot{width:9px;height:9px;border-radius:50%;background:currentColor}
.aibadge{font-family:var(--mono);font-size:11px;color:var(--blu);border:1px solid var(--line);border-radius:999px;padding:3px 9px}
#pfout{font-family:var(--mono);font-size:12.5px;white-space:pre-line;min-height:18px;color:var(--mut)}
</style></head><body>
<div class="wrap">
 <div>
  <h1>Groundhog &middot; D455 Depth</h1>
  <div class="sub" id="sub">starting camera &hellip;</div>
  <div class="card" style="margin-top:8px"><img id="vid" src="/stream" alt="live">
   <div class="vbar"><span class="sub" id="fps">-- fps</span><span class="aibadge" id="ppl" style="display:none">0 people</span><span style="flex:1"></span>
    <button class="act" id="snap">Snapshot</button><button class="act" id="full">Fullscreen</button></div>
  </div>
 </div>
 <div class="panel">
  <div class="grp"><div class="glabel">View</div>
   <div class="seg" id="view"><button data-v="color" class="on">RGB</button><button data-v="depth">Depth</button><button data-v="ir">IR</button></div></div>
  <div class="grp"><div class="glabel">AI person detection</div>
   <div class="sw"><label for="ai">Detect people (YOLOv8n)</label><input type="checkbox" id="ai"></div>
   <div class="sub" id="aihint">Cyan box = person + confidence + distance (depth-fused). CPU-heavy: ~3&ndash;5&nbsp;fps detection, stream stays smooth.</div></div>
  <div class="grp"><div class="glabel">Depth blob detection</div>
   <div class="sw"><label for="det">Box nearest object</label><input type="checkbox" id="det" checked></div>
   <div class="row"><label>Range (m)</label><input type="range" min="1" max="6" step="0.5" value="2.5" id="near"><output id="no">2.5</output></div></div>
  <div class="grp"><div class="glabel">Obstacle &amp; distance</div>
   <div class="tele">
    <div class="stat"><div class="k">Center (crosshair)</div><div class="v" id="tc">-- m</div></div>
    <div class="stat"><div class="k">Nearest (front)</div><div class="v" id="tm">-- m</div></div>
    <div class="obst clear" id="obst"><span class="dot"></span><span id="obtxt">CLEAR</span></div></div></div>
  <div class="grp"><div class="glabel">Accuracy check</div>
   <button class="act" id="pf">Run flat-wall test</button><div id="pfout"></div></div>
  <div class="grp"><div class="glabel">IR projector</div>
   <div class="sw"><label for="em">Emitter (depth dots)</label><input type="checkbox" id="em" checked></div>
   <div class="row"><label>Laser</label><input type="range" min="0" max="360" step="30" value="150" id="laser"><output id="lo">150</output></div></div>
 </div>
</div>
<script>
function set(k,v){fetch("/set?k="+k+"&v="+v);}
var view=document.getElementById("view");
view.querySelectorAll("button").forEach(function(b){b.addEventListener("click",function(){
 view.querySelectorAll("button").forEach(function(x){x.classList.remove("on");});b.classList.add("on");
 set("view",b.dataset.v);document.getElementById("vid").src="/stream?t="+Date.now();});});
var ai=document.getElementById("ai");ai.addEventListener("change",function(){
 set("ai",ai.checked?1:0);document.getElementById("ppl").style.display=ai.checked?"":"none";});
var det=document.getElementById("det");det.addEventListener("change",function(){set("detect",det.checked?1:0);});
var near=document.getElementById("near"),no=document.getElementById("no");
near.addEventListener("input",function(){no.textContent=near.value;set("near",near.value);});
var em=document.getElementById("em");em.addEventListener("change",function(){set("emitter",em.checked?1:0);});
var laser=document.getElementById("laser"),lo=document.getElementById("lo");
laser.addEventListener("input",function(){lo.textContent=laser.value;set("laser",laser.value);});
document.getElementById("snap").addEventListener("click",function(){window.open("/snapshot","_blank");});
document.getElementById("full").addEventListener("click",function(){var v=document.getElementById("vid");if(v.requestFullscreen)v.requestFullscreen();});
document.getElementById("pf").addEventListener("click",function(){
 var o=document.getElementById("pfout");o.textContent="measuring \\u2026";
 fetch("/planefit").then(function(r){return r.json();}).then(function(t){
  if(!t.ok){o.textContent="\\u26a0 "+t.err+(t.fill_pct!==undefined?" (fill "+t.fill_pct+"%)":"");return;}
  o.innerHTML="mean dist: <b>"+t.mean_m+" m</b>\\nnoise (RMS): <b>"+t.rms_mm+" mm</b> ("+t.rms_pct+"%)\\nfill: "+t.fill_pct+"%";
 }).catch(function(){o.textContent="test failed";});});
function poll(){fetch("/telemetry").then(function(r){return r.json();}).then(function(t){
 document.getElementById("tc").textContent=(t.center>0?t.center.toFixed(2):"--")+" m";
 document.getElementById("tm").textContent=(t.min>0?t.min.toFixed(2):"--")+" m";
 document.getElementById("fps").textContent=t.fps+" fps";
 document.getElementById("ppl").textContent=t.people+" people";
 if(!t.ai_ready){document.getElementById("aihint").textContent="\\u26a0 AI model not loaded on server.";}
 document.getElementById("sub").textContent="D455 \\u00b7 "+t.view+" \\u00b7 live";
 var o=document.getElementById("obst"),tx=document.getElementById("obtxt");
 if(t.obstacle){o.className="obst hit";tx.textContent="OBSTACLE "+t.min.toFixed(2)+" m";}
 else{o.className="obst clear";tx.textContent="CLEAR";}}).catch(function(){});}
setInterval(poll,500);poll();
</script></body></html>"""


class Hd(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); path = u.path; q = urllib.parse.parse_qs(u.query)
        if path in ("/", "/index.html"):
            b = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if path == "/telemetry":
            with lock:
                b = json.dumps(tele).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if path == "/planefit":
            b = json.dumps(planefit()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if path == "/set":
            k = q.get("k", [""])[0]; v = q.get("v", [""])[0]
            with lock:
                if k == "view" and v in ("color", "depth", "ir"):
                    state["view"] = v
                elif k == "emitter":
                    state["emitter"] = 1 if v == "1" else 0; state["dirty"] = True
                elif k == "detect":
                    state["detect"] = 1 if v == "1" else 0
                elif k == "ai":
                    state["ai"] = 1 if v == "1" else 0
                elif k == "near":
                    try:
                        state["near"] = float(v)
                    except Exception:
                        pass
                elif k == "laser":
                    try:
                        state["laser"] = int(v); state["dirty"] = True
                    except Exception:
                        pass
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b"{\"ok\":true}"); return
        if path == "/snapshot":
            with lock:
                j = latest["j"]
            if j:
                self.send_response(200); self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(j))); self.end_headers(); self.wfile.write(j)
            else:
                self.send_response(503); self.end_headers()
            return
        if path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=%s" % BOUND)
            self.send_header("Cache-Control", "no-cache"); self.end_headers()
            try:
                while True:
                    with lock:
                        j = latest["j"]
                    if j:
                        self.wfile.write(b"--" + BOUND.encode() + b"\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(("Content-Length: %d\r\n\r\n" % len(j)).encode())
                        self.wfile.write(j + b"\r\n")
                    time.sleep(1 / 15.0)
            except Exception:
                pass
            return
        self.send_response(404); self.end_headers()


class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


threading.Thread(target=worker, daemon=True).start()
threading.Thread(target=detector, daemon=True).start()
TS(("0.0.0.0", PORT), Hd).serve_forever()
