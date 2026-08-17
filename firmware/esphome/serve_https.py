#!/usr/bin/env python3
"""HTTPS static server for the Web Bluetooth page (Web Bluetooth needs a secure context).
Self-signed cert -> phone will show a one-time warning; tap Advanced -> Proceed.
Run: python3 serve_https.py   ->  https://<mac-ip>:8443/ble.html
"""
import http.server, ssl, os
DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DIR)
httpd = http.server.HTTPServer(("0.0.0.0", 8443), http.server.SimpleHTTPRequestHandler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(os.path.join(DIR, "cert.pem"), os.path.join(DIR, "key.pem"))
httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
print("HTTPS on :8443  ->  https://<mac-ip>:8443/ble.html")
httpd.serve_forever()
