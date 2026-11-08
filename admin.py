"""Laufdaten – lokales Eingabe-Programm.

Startet einen kleinen Webserver, der NUR auf diesem PC erreichbar ist
(http://127.0.0.1:8787). Darüber trägst du Daten ein; sie werden im Ordner
"daten" gespeichert. Mit "Veröffentlichen" verschlüsselt die Seite alles mit dem
Team-Passwort, legt es in "docs/data" ab und lädt es per git auf GitHub hoch.

Start: Doppelklick auf "Eingabe starten.bat" (oder: python admin.py)
Nur Python-Standardbibliothek, keine weiteren Pakete nötig.
"""

import datetime
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
DATA_DIR = os.path.join(ROOT, "daten")
DATA_FILE = os.path.join(DATA_DIR, "laufdaten.json")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
HM_DIR = os.path.join(DATA_DIR, "heatmaps")
PUB_DIR = os.path.join(DOCS, "data")
PUB_HM = os.path.join(PUB_DIR, "hm")
HOST, PORT = "127.0.0.1", 8787
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
COLS = ("spieler", "spiele", "einsaetze")
ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,120}$")
EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
MAX_BODY = 40 * 1024 * 1024
lock = threading.Lock()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_data():
    d = read_json(DATA_FILE, {})
    for c in COLS:
        d.setdefault(c, {})
    return d


def mark_dirty():
    st = read_json(STATUS_FILE, {})
    st["dirty"] = True
    st["changed"] = now_iso()
    write_json(STATUS_FILE, st)


def hm_path(asset_id):
    if not ID_RE.match(asset_id):
        return None
    for ext in EXT.values():
        p = os.path.join(HM_DIR, asset_id + ext)
        if os.path.exists(p):
            return p
    return None


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "Laufdaten/1"

    def log_message(self, fmt, *args):
        pass

    # ---- helpers ----
    def guard(self, write=False):
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            self.send_error(403, "Host nicht erlaubt")
            return False
        if write and self.headers.get("X-Laufdaten") != "1":
            self.send_error(403, "Fehlender Header")
            return False
        return True

    def send(self, code, body=b"", ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("zu groß")
        return self.rfile.read(n) if n else b""

    def json_body(self):
        return json.loads(self.body() or b"{}")

    def doc_path(self, rest):
        parts = [unquote(p) for p in rest.split("/") if p]
        if len(parts) != 2 or parts[0] not in COLS or not ID_RE.match(parts[1]):
            return None, None
        return parts[0], parts[1]

    # ---- GET ----
    def do_GET(self):
        if not self.guard():
            return
        path = urlparse(self.path).path
        if path == "/api/ping":
            return self.send(200, {"mode": "admin"})
        if path == "/api/data":
            with lock:
                return self.send(200, {"data": load_data(), "status": read_json(STATUS_FILE, {}),
                                       "pub": read_json(os.path.join(PUB_DIR, "meta.json"), None)})
        if path.startswith("/hm/"):
            p = hm_path(unquote(path[4:]))
            if not p:
                return self.send(404, {"error": "nicht gefunden"})
            with open(p, "rb") as f:
                data = f.read()
            ctype = {v: k for k, v in EXT.items()}[os.path.splitext(p)[1]]
            return self.send(200, data, ctype)
        # statische Dateien aus docs/
        rel = unquote(path).lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(DOCS, rel))
        if not full.startswith(DOCS) or not os.path.isfile(full):
            return self.send(404, "Nicht gefunden", "text/plain; charset=utf-8")
        with open(full, "rb") as f:
            data = f.read()
        return self.send(200, data, STATIC_TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    # ---- PUT ----
    def do_PUT(self):
        if not self.guard(write=True):
            return
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/doc/"):
                col, did = self.doc_path(path[len("/api/doc/"):])
                if not col:
                    return self.send(400, {"error": "Pfad ungültig"})
                obj = self.json_body()
                if not isinstance(obj, dict):
                    return self.send(400, {"error": "Daten ungültig"})
                with lock:
                    d = load_data()
                    d[col][did] = obj
                    write_json(DATA_FILE, d)
                    mark_dirty()
                return self.send(200, {"ok": True})
            if path.startswith("/api/pub/hm/"):
                aid = unquote(path[len("/api/pub/hm/"):])
                if not ID_RE.match(aid):
                    return self.send(400, {"error": "ID ungültig"})
                os.makedirs(PUB_HM, exist_ok=True)
                with open(os.path.join(PUB_HM, aid + ".enc"), "wb") as f:
                    f.write(self.body())
                return self.send(200, {"ok": True})
        except Exception as e:  # noqa: BLE001
            return self.send(500, {"error": str(e)})
        self.send(404, {"error": "nicht gefunden"})

    # ---- POST ----
    def do_POST(self):
        if not self.guard(write=True):
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/asset":
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
                if ctype not in EXT:
                    return self.send(415, {"error": "Bildformat nicht unterstützt", "code": "unsupported_type"})
                data = self.body()
                if not data:
                    return self.send(400, {"error": "leer"})
                aid = secrets.token_hex(16)
                os.makedirs(HM_DIR, exist_ok=True)
                with open(os.path.join(HM_DIR, aid + EXT[ctype]), "wb") as f:
                    f.write(data)
                mark_dirty()
                return self.send(200, {"id": aid, "url": "/hm/" + aid, "sizeBytes": len(data), "contentType": ctype})
            if path == "/api/pub/finish":
                req = self.json_body()
                meta, enc_data, keep = req.get("meta"), req.get("data"), set(req.get("keep") or [])
                if not isinstance(meta, dict) or not isinstance(enc_data, str):
                    return self.send(400, {"error": "Daten ungültig"})
                import base64
                os.makedirs(PUB_HM, exist_ok=True)
                with open(os.path.join(PUB_DIR, "laufdaten.enc"), "wb") as f:
                    f.write(base64.b64decode(enc_data))
                write_json(os.path.join(PUB_DIR, "meta.json"), meta)
                for fn in os.listdir(PUB_HM):
                    if fn.endswith(".enc") and fn[:-4] not in keep:
                        os.remove(os.path.join(PUB_HM, fn))
                log = []
                code, out = git("add", "-A", "docs")
                log.append(out)
                code, out = git("diff", "--cached", "--quiet")
                if code != 0:
                    code, out = git("commit", "-m", f"Daten veröffentlicht ({datetime.date.today():%d.%m.%Y})")
                    log.append(out)
                    if code != 0:
                        return self.send(500, {"error": "Speichern im Git-Verlauf (commit) ist fehlgeschlagen.", "log": "\n".join(log)})
                # immer pushen: holt auch frühere, nicht hochgeladene Stände nach
                code, out = git("push")
                log.append(out)
                pushed = code == 0
                msg = "Veröffentlicht." if pushed else "Lokal gespeichert, aber das Hochladen zu GitHub ist fehlgeschlagen. Prüfe die Internetverbindung und klicke erneut auf „Veröffentlichen“."
                if pushed:
                    st = read_json(STATUS_FILE, {})
                    st.update({"dirty": False, "published": now_iso()})
                    write_json(STATUS_FILE, st)
                return self.send(200 if pushed else 502, {"ok": pushed, "message": msg, "error": None if pushed else msg,
                                                          "log": "\n".join(l for l in log if l)})
        except Exception as e:  # noqa: BLE001
            return self.send(500, {"error": str(e)})
        self.send(404, {"error": "nicht gefunden"})

    # ---- DELETE ----
    def do_DELETE(self):
        if not self.guard(write=True):
            return
        path = urlparse(self.path).path
        if path.startswith("/api/doc/"):
            col, did = self.doc_path(path[len("/api/doc/"):])
            if not col:
                return self.send(400, {"error": "Pfad ungültig"})
            with lock:
                d = load_data()
                d[col].pop(did, None)
                write_json(DATA_FILE, d)
                mark_dirty()
            return self.send(200, {"ok": True})
        if path.startswith("/api/asset/"):
            p = hm_path(unquote(path[len("/api/asset/"):]))
            if p:
                os.remove(p)
                mark_dirty()
            return self.send(200, {"deleted": bool(p)})
        self.send(404, {"error": "nicht gefunden"})


def main():
    os.makedirs(HM_DIR, exist_ok=True)
    try:
        srv = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        print(f"Port {PORT} ist belegt – läuft das Eingabe-Programm schon? Öffne http://{HOST}:{PORT}")
        webbrowser.open(f"http://{HOST}:{PORT}/#eingabe")
        return
    url = f"http://{HOST}:{PORT}/#eingabe"
    print("Laufdaten – Eingabe läuft.")
    print(f"Im Browser: {url}")
    print("Zum Beenden dieses Fenster schließen (oder Strg+C).")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
