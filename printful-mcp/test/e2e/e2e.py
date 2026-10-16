# End-to-end: discovery -> DCR -> consent page (bad then good token) -> PKCE token exchange -> MCP tools.
import base64, hashlib, json, os, re, secrets, sys, urllib.error, urllib.parse, urllib.request

BASE = sys.argv[1].rstrip("/")
LOG = sys.argv[2]
REDIRECT = "http://localhost:33418/callback"
results = []

def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
opener = urllib.request.build_opener(NoRedirect)

def req(method, url, data=None, headers=None):
    headers = dict(headers or {})
    if isinstance(data, dict):
        data = json.dumps(data).encode(); headers.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        data = data.encode()
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = opener.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    return resp.status, dict(resp.headers), resp.headers.get_all("Set-Cookie") or [], resp.read().decode()

def cookies_from(set_cookies):
    return "; ".join(c.split(";", 1)[0] for c in set_cookies)

# 1. unauthenticated MCP call is challenged
s, h, _, _ = req("POST", f"{BASE}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                 {"Accept": "application/json, text/event-stream"})
check("unauthenticated /mcp -> 401 with resource metadata", s == 401 and "resource_metadata" in h.get("WWW-Authenticate", h.get("www-authenticate", "")), f"{s} {h}")

# 2. discovery
s, _, _, b = req("GET", f"{BASE}/.well-known/oauth-protected-resource/mcp")
prm = json.loads(b) if s == 200 else {}
check("protected resource metadata", s == 200 and prm.get("resource") == f"{BASE}/mcp", b[:200])
s, _, _, b = req("GET", f"{BASE}/.well-known/oauth-authorization-server")
asm = json.loads(b) if s == 200 else {}
check("authorization server metadata has DCR", s == 200 and asm.get("registration_endpoint", "").endswith("/oauth/register"), b[:300])

# 3. register a disallowed client and a loopback client
s, _, _, b = req("POST", f"{BASE}/oauth/register", {"redirect_uris": ["https://evil.example/cb"], "client_name": "Evil", "token_endpoint_auth_method": "none"})
evil = json.loads(b)["client_id"]
s, _, _, b = req("POST", f"{BASE}/oauth/register", {"redirect_uris": [REDIRECT], "client_name": "Test <script>", "token_endpoint_auth_method": "none"})
check("DCR registers loopback client", s == 201, b[:200])
client_id = json.loads(b)["client_id"]

verifier = secrets.token_urlsafe(48)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
def authorize_url(cid, redirect):
    return f"{BASE}/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect, "state": "st4te",
        "code_challenge": challenge, "code_challenge_method": "S256", "scope": "printful",
        "resource": f"{BASE}/mcp"})

s, _, _, b = req("GET", authorize_url(evil, "https://evil.example/cb"))
check("non-Claude redirect host is refused at /authorize", s == 403 and "evil.example" in b, f"{s} {b[:200]}")

# 4. consent page
s, h, sc, b = req("GET", authorize_url(client_id, REDIRECT))
check("consent page renders", s == 200 and 'name="token"' in b, f"{s} {b[:300]}")
check("client name is escaped", "<script>" not in b and "&#60;script&#62;" in b)
check("loopback warning shown", "app on your computer" in b)
check("page can't be framed", "frame-ancestors" in h.get("Content-Security-Policy", h.get("content-security-policy", "")) or h.get("X-Frame-Options", h.get("x-frame-options")), str(h))
handle = re.search(r'name="handle" value="([^"]+)"', b).group(1)
q = re.search(r'name="q" value="([^"]+)"', b).group(1).replace("&#38;", "&")
cookie = cookies_from(sc)

def post_form(fields):
    return req("POST", f"{BASE}/authorize", urllib.parse.urlencode(fields),
               {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie, "Origin": BASE})

# 5. bad token -> same form again, handle still usable
s, _, _, b = post_form({"handle": handle, "q": q, "decision": "approve", "token": "bad-token", "store_id": ""})
check("bad token re-shows the form with an error", s == 400 and "didn" in b and 'name="token"' in b, f"{s} {b[:300]}")
check("bad token isn't echoed back", "bad-token" not in b)

# 6. good token -> redirect with code
s, h, sc2, b = post_form({"handle": handle, "q": q, "decision": "approve", "token": "good-token", "store_id": ""})
loc = h.get("Location", h.get("location", ""))
check("good token redirects to the client with a code", s == 302 and loc.startswith(REDIRECT) and "code=" in loc, f"{s} {loc} {b[:200]}")
params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(loc).query))
check("state round-trips", params.get("state") == "st4te")

# 7. token exchange
s, _, _, b = req("POST", f"{BASE}/oauth/token", urllib.parse.urlencode({
    "grant_type": "authorization_code", "code": params.get("code", ""), "redirect_uri": REDIRECT,
    "client_id": client_id, "code_verifier": verifier, "resource": f"{BASE}/mcp"}),
    {"Content-Type": "application/x-www-form-urlencoded"})
tok = json.loads(b) if s == 200 else {}
check("code exchange returns access + refresh tokens", s == 200 and tok.get("access_token") and tok.get("refresh_token"), b[:300])
at = tok.get("access_token", "")

# 8. MCP
def mcp(method, params=None, id_=1):
    s, h, _, b = req("POST", f"{BASE}/mcp", {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}},
                     {"Accept": "application/json, text/event-stream", "Authorization": f"Bearer {at}",
                      "MCP-Protocol-Version": "2025-06-18"})
    if "text/event-stream" in h.get("Content-Type", h.get("content-type", "")):
        data = [l[5:].strip() for l in b.splitlines() if l.startswith("data:")]
        b = data[-1] if data else b
    return s, json.loads(b) if b.strip().startswith("{") else b

s, r = mcp("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "e2e", "version": "1"}})
check("initialize", s == 200 and isinstance(r, dict) and r.get("result", {}).get("serverInfo", {}).get("name") == "printful", str(r)[:300])
s, r = mcp("tools/list", id_=2)
tools = {t["name"]: t for t in r.get("result", {}).get("tools", [])} if isinstance(r, dict) else {}
check("three tools listed", set(tools) == {"printful_get", "printful_request", "printful_guarded_request"}, str(r)[:300])
check("annotations: get is read-only, guarded is destructive",
      tools.get("printful_get", {}).get("annotations", {}).get("readOnlyHint") is True
      and tools.get("printful_guarded_request", {}).get("annotations", {}).get("destructiveHint") is True)

def call(name, args, id_):
    s, r = mcp("tools/call", {"name": name, "arguments": args}, id_)
    res = r.get("result", {}) if isinstance(r, dict) else {}
    return res.get("isError", False), (res.get("content") or [{}])[0].get("text", str(r))

open(LOG, "w").close()
err, t = call("printful_get", {"path": "/v2/stores"}, 3)
check("printful_get reaches Printful", not err and "Mock Store" in t, t[:200])
err, t = call("printful_get", {"path": "/v2/orders/404"}, 4)
check("Printful errors come back as tool errors with a summary", err and "HTTP 404" in t and "Order 404 not found" in t, t[:200])
err, t = call("printful_request", {"method": "POST", "path": "/v2/orders/1/confirmation"}, 5)
check("printful_request refuses confirmation", err and "printful_guarded_request" in t, t[:200])
err, t = call("printful_request", {"method": "DELETE", "path": "//v2//orders/1"}, 6)
check("printful_request refuses DELETE via path tricks", err and "Refusing" in t, t[:200])
err, t = call("printful_guarded_request", {"method": "POST", "path": "/v2/orders"}, 7)
check("printful_guarded_request refuses ordinary calls", err and "doesn't spend money" in t, t[:200])
err, t = call("printful_request", {"method": "POST", "path": "/v2/orders", "body": {"recipient": {"name": "A"}}}, 8)
check("printful_request creates a draft", not err and "POST /v2/orders" in t, t[:200])
err, t = call("printful_guarded_request", {"method": "POST", "path": "/v2/orders/1/confirmation"}, 9)
check("printful_guarded_request confirms", not err and "confirmation" in t, t[:200])
err, t = call("printful_get", {"path": "/v2/../v2/stores"}, 10)
check("dot segments refused", err and "dot segments" in t, t[:200])

log = [json.loads(l) for l in open(LOG)]
check("Printful saw the user's token on every call", log and all(e["auth"] == "Bearer good-token" for e in log), str(log)[:300])
check("Printful never saw the refused calls", [e["method"] + " " + e["path"] for e in log] ==
      ["GET /v2/stores", "GET /v2/orders/404", "POST /v2/orders", "POST /v2/orders/1/confirmation"], str([e["method"] + " " + e["path"] for e in log]))
check("draft body forwarded", any(e["body"] == '{"recipient":{"name":"A"}}' for e in log))

# 9. refresh
s, _, _, b = req("POST", f"{BASE}/oauth/token", urllib.parse.urlencode({
    "grant_type": "refresh_token", "refresh_token": tok.get("refresh_token", ""), "client_id": client_id}),
    {"Content-Type": "application/x-www-form-urlencoded"})
check("refresh token works", s == 200 and "access_token" in b, b[:200])

# 10. "Sign in with Printful"
MOCK = "http://127.0.0.1:8789"
jar = {}
def remember(set_cookies):
    for c in set_cookies:
        name, _, value = c.split(";", 1)[0].partition("=")
        jar[name] = value
def cookie_header():
    return "; ".join(f"{k}={v}" for k, v in jar.items() if v)

def start_sign_in():
    jar.clear()
    s, h, sc, b = req("GET", authorize_url(client_id, REDIRECT))
    remember(sc)
    handle = re.search(r'name="handle" value="([^"]+)"', b).group(1)
    q = re.search(r'name="q" value="([^"]+)"', b).group(1).replace("&#38;", "&")
    s2, h2, sc2, _ = req("POST", f"{BASE}/authorize",
                         urllib.parse.urlencode({"handle": handle, "q": q, "decision": "printful"}),
                         {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie_header(), "Origin": BASE})
    remember(sc2)
    return b, s2, h2.get("Location", h2.get("location", ""))

page_html, s, printful_url = start_sign_in()
check("sign-in page offers Printful sign-in with the token form as a fallback",
      'value="printful"' in page_html and "Use a private token instead" in page_html)
pq = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(printful_url).query))
check("approving redirects to Printful's authorize page", s == 302 and printful_url.startswith(f"{MOCK}/oauth/authorize")
      and pq.get("client_id") == "app-1040801" and pq.get("redirect_url") == f"{BASE}/printful/callback" and pq.get("state"), printful_url)

s, h, _, _ = req("GET", printful_url)
callback = h.get("Location", h.get("location", ""))
s, h, _, b = req("GET", callback)
check("callback without the browser's binding cookie is refused", s == 400 and "connect again" in b, f"{s} {b[:200]}")
s, h, sc, b = req("GET", callback, headers={"Cookie": cookie_header()})
loc = h.get("Location", h.get("location", ""))
params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(loc).query))
check("Printful callback finishes the authorization", s == 302 and loc.startswith(REDIRECT) and params.get("code"), f"{s} {loc} {b[:200]}")

s, _, _, b = req("POST", f"{BASE}/oauth/token", urllib.parse.urlencode({
    "grant_type": "authorization_code", "code": params.get("code", ""), "redirect_uri": REDIRECT,
    "client_id": client_id, "code_verifier": verifier, "resource": f"{BASE}/mcp"}),
    {"Content-Type": "application/x-www-form-urlencoded"})
tok = json.loads(b) if s == 200 else {}
check("our access token never outlives Printful's (2 min token -> 60 s)", s == 200 and tok.get("expires_in") == 60, b[:300])
at = tok.get("access_token", "")
open(LOG, "w").close()
err, t = call("printful_get", {"path": "/v2/stores"}, 20)
check("tools use the Printful access token", not err and "Mock Store" in t, t[:200])

s, _, _, b = req("POST", f"{BASE}/oauth/token", urllib.parse.urlencode({
    "grant_type": "refresh_token", "refresh_token": tok.get("refresh_token", ""), "client_id": client_id}),
    {"Content-Type": "application/x-www-form-urlencoded"})
tok2 = json.loads(b) if s == 200 else {}
check("refreshing our token refreshes Printful's", s == 200 and tok2.get("access_token"), b[:300])
at = tok2.get("access_token", "")
err, t = call("printful_get", {"path": "/v2/stores"}, 21)
log = [json.loads(l) for l in open(LOG)]
check("Printful saw the rotated refresh token and the new access token",
      any("grant_type=refresh_token" in e["body"] and "refresh_token=oauth-refresh-1" in e["body"] for e in log)
      and log[-1]["auth"] == "Bearer oauth-access-2" and not err, str([(e["path"], e["auth"]) for e in log]))
check("client secret only ever went to Printful's token endpoint",
      all(e["path"] == "/oauth/token" for e in log if "mock-secret" in e["body"]))

req("POST", f"{MOCK}/__revoke")
s, _, _, b = req("POST", f"{BASE}/oauth/token", urllib.parse.urlencode({
    "grant_type": "refresh_token", "refresh_token": tok2.get("refresh_token", ""), "client_id": client_id}),
    {"Content-Type": "application/x-www-form-urlencoded"})
check("revoked Printful access ends the grant with invalid_grant", s == 400 and "invalid_grant" in b, f"{s} {b[:200]}")

_, _, printful_url = start_sign_in()
st = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(printful_url).query)).get("state", "")
s, h, _, _ = req("GET", f"{BASE}/printful/callback?" + urllib.parse.urlencode({"state": st, "success": "0"}),
                 headers={"Cookie": cookie_header()})
loc = h.get("Location", h.get("location", ""))
check("declining at Printful returns access_denied to the client", s == 302 and loc.startswith(REDIRECT) and "error=access_denied" in loc, loc)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
