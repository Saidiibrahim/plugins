# Minimal Printful stand-in: accepts only "good-token", logs every request.
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[1]

class H(BaseHTTPRequestHandler):
    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        with open(LOG, "a") as f:
            f.write(json.dumps({"method": self.command, "path": self.path,
                                "auth": self.headers.get("Authorization"),
                                "store": self.headers.get("X-PF-Store-Id"), "body": body}) + "\n")
        if self.headers.get("Authorization") != "Bearer good-token":
            return self._send(401, {"code": 401, "result": "Unauthorized", "error": {"reason": "Unauthorized", "message": "Invalid token"}})
        if self.path.startswith("/v2/stores"):
            return self._send(200, {"data": [{"id": 4242, "type": "native", "name": "Mock Store"}]})
        if self.path.startswith("/v2/orders/404"):
            return self._send(404, {"type": "about:blank", "status": 404, "title": "Not Found", "detail": "Order 404 not found"})
        return self._send(200, {"data": {"echo": self.command + " " + self.path}})
    def _send(self, status, obj):
        b = json.dumps(obj).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle
    def log_message(self, *a): pass

ThreadingHTTPServer(("127.0.0.1", 8789), H).serve_forever()
