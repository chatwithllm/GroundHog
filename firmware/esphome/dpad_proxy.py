#!/usr/bin/env python3
"""D-pad proxy: serves dpad.html AND relays /api/* to the ESP WITHOUT an Origin
header, dodging ESPHome's cross-origin 500. Browser <-> proxy = same-origin (OK);
proxy <-> ESP = no Origin (OK). Run: python3 dpad_proxy.py   ->  :8788
"""
import http.server, urllib.request, urllib.error, os

ESP = "http://192.168.20.119"          # target ESP32-C6
PORT = 8788
DIR = os.path.dirname(os.path.abspath(__file__))

class H(http.server.BaseHTTPRequestHandler):
    def _file(self):
        name = "dpad.html" if self.path in ("/", "") else self.path.lstrip("/").split("?")[0]
        fp = os.path.join(DIR, name)
        if os.path.isfile(fp) and fp.startswith(DIR):
            self.send_response(200)
            self.send_header("Content-Type", "text/html" if fp.endswith(".html") else "application/octet-stream")
            self.end_headers()
            with open(fp, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404); self.end_headers()

    def _proxy(self):
        target = ESP + self.path[len("/api"):]          # /api/button/Forward/press -> ESP/button/Forward/press
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n) if n else b""
        data = body if self.command == "POST" else None  # POST always carries a (possibly empty) body -> Content-Length:0
        req = urllib.request.Request(target, data=data, method=self.command)  # NB: no Origin header added
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                out, code = r.read(), r.status
        except urllib.error.HTTPError as e:
            out, code = e.read(), e.code
        except Exception as e:
            out, code = str(e).encode(), 502
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self._proxy() if self.path.startswith("/api/") else self._file()
    def do_POST(self):
        self._proxy() if self.path.startswith("/api/") else (self.send_response(404), self.end_headers())
    def log_message(self, *a):
        pass

print(f"D-pad proxy: http://<mac-ip>:{PORT}/  ->  relaying to {ESP}")
http.server.HTTPServer(("0.0.0.0", PORT), H).serve_forever()
