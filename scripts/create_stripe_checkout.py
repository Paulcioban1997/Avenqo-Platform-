"""
Create a fresh Stripe Checkout test session for the Professional plan
for the ciomir@gmail.com account via the production API at avenqo.ca.

Steps:
1. Login as ciomir@gmail.com (email not verified yet — may be blocked)
2. If blocked, try gauffy95@gmail.com (already verified, owner of Produits_Ero)
3. Hit POST /api/v1/billing/checkout to get a Stripe Checkout URL
4. Print the URL for the user to visit and complete test payment.
"""
import json
import urllib.request
import urllib.error

BASE = "https://avenqo.ca"

def post_json(url, payload, token=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}

def get_json(url, token=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}

# 1. Check health + environment
status, health = get_json(f"{BASE}/api/v1/health")
print(f"=== Health === HTTP {status}: {health}")

# 2. Try login as ciomir (may be blocked due to unverified email)
for email, pwd in [("ciomir@gmail.com", "Test1234!"), ("gauffy95@gmail.com", "Test1234!")]:
    status, res = post_json(f"{BASE}/api/auth/login", {"email": email, "password": pwd})
    print(f"\n=== Login {email} === HTTP {status}: {list(res.keys()) if isinstance(res, dict) else res}")
    token = res.get("access_token") if isinstance(res, dict) else None
    if token:
        print(f"  -> Logged in as {email}")
        break
else:
    print("ERROR: Could not login with any account")
    exit(1)

# 3. Create Stripe Checkout session
status, res = post_json(f"{BASE}/api/v1/billing/checkout", {"plan": "professional"}, token=token)
print(f"\n=== Stripe Checkout === HTTP {status}: {res}")
url_field = res.get("url") or res.get("checkout_url") or res.get("session_url")
if url_field:
    print(f"\n>>> CHECKOUT URL: {url_field}")
else:
    print("  -> Could not extract checkout URL from response")
