#!/usr/bin/env python3
"""Stay Active: local helper. Serves the UI and nudges the cursor 1px on an interval."""
import ctypes, json, subprocess, threading, time, random, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", 8765))
# Origins allowed to control this helper from a browser (the hosted UI + local UI)
ALLOWED_ORIGINS = {"https://teams-status-keeper.vercel.app", f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}
HERE = os.path.dirname(os.path.abspath(__file__))

class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

_cg = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
_cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_cg.CGEventCreate.restype = ctypes.c_void_p
_cg.CGEventCreate.argtypes = [ctypes.c_void_p]
_cg.CGEventGetLocation.restype = CGPoint
_cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
_cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
_cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
_cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
_cf.CFRelease.argtypes = [ctypes.c_void_p]

def _move_to(x, y):
    ev = _cg.CGEventCreateMouseEvent(None, 5, CGPoint(x, y), 0)  # 5 = mouseMoved
    _cg.CGEventPost(0, ev)  # HID event tap: counts as real input
    _cf.CFRelease(ev)

def nudge():
    cur = _cg.CGEventCreate(None)
    p = _cg.CGEventGetLocation(cur)
    _cf.CFRelease(cur)
    d = random.choice([-1, 1])
    _move_to(p.x + d, p.y)
    time.sleep(0.05)
    _move_to(p.x, p.y)

class Worker:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.interval = 60
        self.stop_at = None   # epoch seconds or None
        self.started = None
        self.nudges = 0
        self.last = None
        self.log = []
        self.caff = None
        self._t = None

    def _log(self, msg):
        self.log.insert(0, {"t": time.time(), "msg": msg})
        del self.log[30:]

    def start(self, interval, hours):
        with self.lock:
            if self.running:
                return
            self.interval = max(10, min(int(interval), 600))
            self.stop_at = time.time() + hours * 3600 if hours else None
            self.started = time.time()
            self.running = True
            self.caff = subprocess.Popen(["caffeinate", "-di"])
            self._log(f"Started. Nudging every {self.interval}s")
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()

    def stop(self, why="Stopped"):
        with self.lock:
            if not self.running:
                return
            self.running = False
            if self.caff:
                self.caff.terminate()
                self.caff = None
            self._log(why)

    def _loop(self):
        while True:
            wait = self.interval + random.uniform(-0.15, 0.15) * self.interval
            end = time.time() + wait
            while time.time() < end:
                if not self.running:
                    return
                time.sleep(0.5)
            if self.stop_at and time.time() >= self.stop_at:
                self.stop("Timer finished, stopped automatically")
                return
            try:
                nudge()
                self.nudges += 1
                self.last = time.time()
            except Exception as e:
                self._log(f"Nudge failed: {e}")

    def status(self):
        return {"running": self.running, "interval": self.interval, "started": self.started,
                "stopAt": self.stop_at, "nudges": self.nudges, "last": self.last,
                "log": self.log, "now": time.time()}

W = Worker()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _cors(self):
        o = self.headers.get("Origin")
        if o in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Vary", "Origin")
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def _host_ok(self):
        return self.headers.get("Host", "").split(":")[0] in ("localhost", "127.0.0.1")
    def do_GET(self):
        if not self._host_ok(): return self._json({"error": "bad host"}, 403)
        if self.path == "/api/status": return self._json(W.status())
        if self.path in ("/", "/index.html"):
            b = open(os.path.join(HERE, "index.html"), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        self._json({"error": "not found"}, 404)
    def do_POST(self):
        if not self._host_ok() or self.headers.get("Content-Type") != "application/json":
            return self._json({"error": "forbidden"}, 403)
        o = self.headers.get("Origin")
        if o and o not in ALLOWED_ORIGINS:
            return self._json({"error": "forbidden origin"}, 403)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict): raise ValueError
            float(body.get("hours", 0)); int(body.get("interval", 60))
        except Exception:
            return self._json({"error": "bad request"}, 400)
        if self.path == "/api/start":
            W.start(body.get("interval", 60), float(body.get("hours", 0)))
        elif self.path == "/api/stop":
            W.stop()
        elif self.path == "/api/test":
            try:
                nudge()
            except Exception as e:
                W._log(f"Nudge failed: {e}")
        else:
            return self._json({"error": "not found"}, 404)
        self._json(W.status())

if __name__ == "__main__":
    print(f"Stay Active running → http://localhost:{PORT}")
    import signal
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
    except KeyboardInterrupt:
        W.stop()
