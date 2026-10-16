# Minimal Printful stand-in for the e2e test. Logs every request.
# API: accepts the private token "good-token" and any live OAuth access token.
# OAuth: /oauth/authorize approves at once; /oauth/token issues 2-minute access
# tokens and rotates refresh tokens; POST /__revoke invalidates them all.
import json, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = sys.argv[1]
CLIENT_ID, CLIENT_SECRET = "app-1040801", "mock-secret"
lock = threading.Lock()
state = {"n": 0, "access": set(), "refresh": set()}

def issue():
    state["n"] += 1
    n = state["n"]
    state["access"].add(f"oauth-access-{n}")
    state["refresh"] = {f"oauth-refresh-{n}"}
    return {"access_token": f"oauth-access-{n}", "expires_at": str(int(time.time()) + 120),
            "token_type": "bearer", "refresh_token": f"oauth-refresh-{n}"}

class H(BaseHTTPRequestHandler):
    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        url = urllib.parse.urlparse(self.path)
        with open(LOG, "a") as f:
            f.write(json.dumps({"method": self.command, "path": self.path,
                                "auth": self.headers.get("Authorization"),
                                "store": self.headers.get("X-PF-Store-Id"), "body": body}) + "\n")
        with lock:
            if url.path == "/__revoke":
                state["access"].clear(); state["refresh"].clear()
                return self._send(200, {})
            if url.path == "/oauth/authorize":
                q = dict(urllib.parse.parse_qsl(url.query))
                if q.get("client_id") != CLIENT_ID:
                    return self._send(400, {"error": "unknown client"})
                back = q["redirect_url"] + "?" + urllib.parse.urlencode({"state": q["state"], "code": "mock-code", "success": "1"})
                self.send_response(302); self.send_header("Location", back); self.end_headers(); return
            if url.path == "/oauth/token":
                form = dict(urllib.parse.parse_qsl(body))
                if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
                    return self._send(401, {"error": "invalid_client"})
                if form.get("grant_type") == "authorization_code" and form.get("code") == "mock-code":
                    return self._send(200, issue())
                if form.get("grant_type") == "refresh_token" and form.get("refresh_token") in state["refresh"]:
                    return self._send(200, issue())
                return self._send(400, {"error": "invalid_grant"})
            auth = self.headers.get("Authorization") or ""
            if auth != "Bearer good-token" and auth.removeprefix("Bearer ") not in state["access"]:
                return self._send(401, {"code": 401, "result": "Unauthorized", "error": {"reason": "Unauthorized", "message": "Invalid token"}})
        if url.path.startswith("/v2/stores"):
            return self._send(200, {"data": [{"id": 4242, "type": "native", "name": "Mock Store"}]})
        if url.path.startswith("/v2/orders/404"):
            return self._send(404, {"type": "about:blank", "status": 404, "title": "Not Found", "detail": "Order 404 not found"})
        return self._send(200, {"data": {"echo": self.command + " " + self.path}})
    def _send(self, status, obj):
        b = json.dumps(obj).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle
    def log_message(self, *a): pass

ThreadingHTTPServer(("127.0.0.1", 8789), H).serve_forever()
