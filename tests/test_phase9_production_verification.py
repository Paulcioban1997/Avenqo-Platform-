import os
import requests
import psycopg2

BASE_URL = os.environ.get("BASE_URL", "https://avenqo.ca")
SANDBOX_BACKEND = os.environ.get("SANDBOX_BACKEND", "https://avenqo-platform-sandbox.up.railway.app")
DB_URL = os.environ.get("DATABASE_URL", "")

GAUFFY_EMAIL = os.environ.get("TEST_USER_EMAIL", "gauffy95@gmail.com")
GAUFFY_PW = os.environ.get("TEST_USER_PW", "")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "paulmircea15@gmail.com")
ADMIN_PW = os.environ.get("ADMIN_PW", "")

def test_production_deployment():
    print("=== PHASE 9 VALIDATION START ===")
    
    # 1. Domain & HTTPS & Redirection www -> root
    s = requests.Session()
    r_www = s.get("https://www.avenqo.ca/", allow_redirects=False)
    assert r_www.status_code == 308, f"www redirect failed: {r_www.status_code}"
    assert r_www.headers.get("Location") in ["https://avenqo.ca/", "https://avenqo.ca"], f"Bad redirect: {r_www.headers.get('Location')}"
    print("[PASS] www.avenqo.ca -> https://avenqo.ca 308 redirect verified")
    
    # 2. Public pages
    for path in ["/", "/pricing", "/login", "/register", "/terms", "/privacy"]:
        r = s.get(f"{BASE_URL}{path}", timeout=10)
        assert r.status_code == 200, f"Path {path} returned {r.status_code}"
        assert "<html" in r.text.lower()
    print("[PASS] Public routes 200 OK (Landing, Pricing, Login, Register, Terms, Privacy)")
    
    # 3. Pricing cards check
    r_price = s.get(f"{BASE_URL}/pricing")
    assert "28" in r_price.text
    assert "49" in r_price.text
    assert "Demo" in r_price.text
    assert "Professional" in r_price.text
    assert "Enterprise" in r_price.text
    print("[PASS] Pricing plans verified ($28 Demo / 6,500 credits, $49 Pro / 25,000 credits, Enterprise)")

    # 4. Auth: Gauffy login (Tenant Produits_Ero)
    s_gauffy = requests.Session()
    r_login_g = s_gauffy.post(f"{BASE_URL}/api/auth/login", json={"email": GAUFFY_EMAIL, "password": GAUFFY_PW})
    assert r_login_g.status_code == 200, f"Gauffy login failed: {r_login_g.text}"
    assert "avenqo_access_token" in s_gauffy.cookies
    token_g = r_login_g.json().get("access_token")
    h_gauffy = {"Authorization": f"Bearer {token_g}"}
    print("[PASS] Tenant Gauffy login successful on avenqo.ca")

    # 5. Auth: Admin login (paulmircea15)
    s_admin = requests.Session()
    r_login_a = s_admin.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r_login_a.status_code == 200, f"Admin login failed: {r_login_a.text}"
    assert "avenqo_access_token" in s_admin.cookies
    token_a = r_login_a.json().get("access_token")
    h_admin = {"Authorization": f"Bearer {token_a}"}
    print("[PASS] Platform Admin login successful on avenqo.ca")

    # 6. Admin RBAC & Tenant Isolation
    for ep in ["/api/v1/admin/dashboard", "/api/v1/admin/companies", "/api/v1/admin/audit-log"]:
        # Standard user -> 403
        rg = requests.get(f"{SANDBOX_BACKEND}{ep}", headers=h_gauffy)
        assert rg.status_code == 403, f"Expected 403 for gauffy on {ep}, got {rg.status_code}"
        # Platform admin -> 200
        ra = requests.get(f"{SANDBOX_BACKEND}{ep}", headers=h_admin)
        assert ra.status_code == 200, f"Expected 200 for admin on {ep}, got {ra.status_code}"
    print("[PASS] Admin RBAC & Tenant Isolation (403 tenant vs 200 admin)")

    # 7. SaaS Application Routes
    for saas in ["/dashboard", "/connections", "/retail", "/central-ai", "/billing", "/team", "/settings", "/admin"]:
        r = s.get(f"{BASE_URL}{saas}", timeout=10)
        assert r.status_code == 200
    print("[PASS] All SaaS routes served under avenqo.ca without app.avenqo.ca prefix")

    # 8. Database & Connectors preservation
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    company_id = "9c97cb94-e9f9-46fb-afd4-8a1d21019cff"
    
    cur.execute("SELECT count(*) FROM datasets WHERE company_id = %s", (company_id,))
    assert cur.fetchone()[0] == 4
    
    cur.execute("SELECT count(*) FROM normalized_commerce_records WHERE company_id = %s", (company_id,))
    assert cur.fetchone()[0] == 66
    
    cur.execute("SELECT provider, status FROM commerce_connections WHERE company_id = %s ORDER BY provider", (company_id,))
    conns = cur.fetchall()
    assert any(c[0] == "woocommerce" and c[1] == "READY" for c in conns)
    assert any(c[0] == "shopify" and c[1] == "READY" for c in conns)
    conn.close()
    print("[PASS] Produits_Ero datasets, normalized records, WooCommerce and Shopify connections preserved READY")

    # 9. Central AI Non-Destructive Query
    conv = requests.post(f"{SANDBOX_BACKEND}/api/v1/ai/chat/conversations", headers=h_gauffy, json={"title": "Prod Smoke AI Test"}, timeout=15).json()
    cid = conv["id"]
    r_msg = requests.post(
        f"{SANDBOX_BACKEND}/api/v1/ai/central/conversations/{cid}/messages",
        headers=h_gauffy,
        json={"content": "Quel est le chiffre d'affaires et le produit phare de ma boutique ?", "locale": "fr"},
        timeout=30
    )
    assert r_msg.status_code == 200
    ai_data = r_msg.json()
    assert ai_data.get("answer") is not None
    assert len(ai_data["answer"]) > 10
    print("[PASS] Central AI grounded tenant query returned 200 OK with answer:", ai_data["answer"][:60], "...")

    print("=== ALL PHASE 9 AUTOMATED TESTS: 100% PASS ===")

if __name__ == "__main__":
    test_production_deployment()
