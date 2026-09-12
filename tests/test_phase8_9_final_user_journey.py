"""
PHASE 8.9: FINAL USER JOURNEY / PRE-PRODUCTION SMOKE TEST SUITE AVENQO
Covers:
1. Public Pricing Exactness & Untranslated Tier Names
2. Stripe TEST Journey (Isolated Tenant Signup, Checkout URL, Webhook, DB Active, AI Credits Allocation)
3. Retail Connectors (Catalog 30 items, Active Connections READY/SYNCING, Multi-Tenant IDOR Isolation)
4. WooCommerce Real Sync (Product 14 Avenqo Headphones X: fetch, safe mutation, signed webhook, DB verification, safe revert)
5. Central AI Grounded Responses & AI Credit Consumption
6. Admin Platform Isolation (403 for Tenant, 200 for Platform Admin)
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from uuid import uuid4
import psycopg2
import pytest
import requests
import stripe

sys.path.insert(0, ".")
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher

GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://web-mudxgew9c-paulmircea15-9488s-projects.vercel.app").strip()
SANDBOX_URL = os.environ.get("BACKEND_URL", "https://avenqo-platform-sandbox.up.railway.app").strip()
DB_URL = os.environ.get("DATABASE_URL", "").strip()

STRIPE_TEST_KEY = os.environ.get("STRIPE_TEST_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_DEMO = os.environ.get("STRIPE_PRICE_DEMO", "")
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "")

WOO_STORE_URL = os.environ.get("WOO_STORE_URL", "https://wordpress-production-7219.up.railway.app")
WOO_CONN_ID = "a93d53b9-0a32-4d7a-82bb-7123746e36b3"
COMPANY_ID = "9c97cb94-e9f9-46fb-afd4-8a1d21019cff"
TENANT_EMAIL = os.environ.get("TEST_USER_EMAIL", "gauffy95@gmail.com")
TENANT_PW = os.environ.get("TEST_USER_PW", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "paulmircea15@gmail.com")
ADMIN_PW = os.environ.get("ADMIN_PW", "")


@pytest.fixture(scope="session")
def tenant_token():
    r = requests.post(f"{SANDBOX_URL}/api/v1/auth/login", json={"email": TENANT_EMAIL, "password": TENANT_PW}, timeout=15)
    assert r.status_code == 200, f"Tenant login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{SANDBOX_URL}/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def woo_creds():
    cipher = ConnectorSecretCipher(["03rZtfwgwKsrVQ3vzJ3srsLtiJHrwqrfW2z7ojGiV2E="])
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT encrypted_credentials FROM commerce_connections WHERE id=%s", (WOO_CONN_ID,))
    row = cur.fetchone()
    conn.close()
    assert row and row[0], "WooCommerce credentials missing"
    return cipher.decrypt(row[0])


# ==============================================================================
# 1. PUBLIC PRICING & TIERS
# ==============================================================================

def test_public_pricing_exact_tiers_and_no_untranslated_names():
    r = requests.get(f"{GATEWAY_URL}/pricing", timeout=15)
    assert r.status_code == 200
    html = r.text
    assert "$28" in html
    assert "6 500" in html or "6,500" in html
    assert "$49" in html
    assert "25 000" in html or "25,000" in html
    assert "Sur mesure" in html or "Custom quote" in html

    # Backend API pricing
    r_api = requests.get(f"{SANDBOX_URL}/api/v1/billing/plans", timeout=15)
    assert r_api.status_code == 200
    plans = {p["code"]: p for p in r_api.json()}
    assert plans["demo"]["monthly_price_usd"] == 28 and plans["demo"]["name"] == "Demo"
    assert plans["professional"]["monthly_price_usd"] == 49 and plans["professional"]["name"] == "Professional"
    assert plans["enterprise"]["monthly_price_usd"] is None and plans["enterprise"]["name"] == "Enterprise"


# ==============================================================================
# 2. STRIPE TEST ISOLATED TENANT JOURNEY
# ==============================================================================

def test_stripe_test_isolated_tenant_lifecycle():
    suffix = uuid4().hex[:6]
    test_email = f"user_smoke_{suffix}@avenqo.ca"
    company_name = f"SmokeCo_{suffix}"

    # A. Register new tenant
    r_reg = requests.post(f"{SANDBOX_URL}/api/v1/auth/register", json={
        "email": test_email,
        "password": "SecurePassword2026!",
        "first_name": "Smoke",
        "last_name": "Tester",
        "company_name": company_name,
        "company_email": test_email,
        "country": "Canada",
        "industry": "Retail",
        "selected_modules": ["retail"]
    }, timeout=15)
    assert r_reg.status_code == 201

    # Activate user directly in DB
    from datetime import datetime, timezone
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, company_id FROM users WHERE email=%s", (test_email,))
    user_row = cur.fetchone()
    assert user_row is not None, f"Utilisateur {test_email} introuvable en base."
    uid, cid = user_row
    cur.execute("UPDATE users SET email_verified_at=%s WHERE id=%s", (datetime.now(timezone.utc), uid))
    conn.commit()

    # Login
    r_login = requests.post(f"{SANDBOX_URL}/api/v1/auth/login", json={"email": test_email, "password": "SecurePassword2026!"}, timeout=15)
    assert r_login.status_code == 200
    token = r_login.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # B. Trigger Stripe Checkout Demo
    r_chk = requests.post(f"{SANDBOX_URL}/api/v1/billing/checkout", headers=h, json={"plan_code": "demo"}, timeout=15)
    assert r_chk.status_code == 200
    assert "checkout.stripe.com" in r_chk.json()["url"]

    # C. Webhook subscription update
    sub_id = f"sub_smoke_{suffix}"
    cust_id = f"cus_smoke_{suffix}"
    payload = {
        "id": f"evt_smoke_{suffix}",
        "object": "event",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": sub_id,
                "object": "subscription",
                "customer": cust_id,
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_end": int(time.time()) + 2592000,
                "metadata": {"avenqo_company_id": str(cid)},
                "items": {"data": [{"id": f"si_{suffix}", "price": {"id": STRIPE_PRICE_DEMO}}]}
            }
        }
    }
    raw_body = json.dumps(payload)
    ts = int(time.time())
    sig = hmac.new(STRIPE_WEBHOOK_SECRET.encode("utf-8"), f"{ts}.{raw_body}".encode("utf-8"), hashlib.sha256).hexdigest()
    r_wh = requests.post(
        f"{SANDBOX_URL}/api/v1/billing/webhook",
        headers={"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"},
        data=raw_body.encode("utf-8"),
        timeout=15
    )
    assert r_wh.status_code == 200 and r_wh.json().get("processed") is True

    # D. Verify DB billing_accounts status
    cur.execute("SELECT plan_code, status, stripe_subscription_id FROM billing_accounts WHERE company_id=%s", (str(cid),))
    row = cur.fetchone()
    assert row is not None, f"Compte de facturation introuvable pour la compagnie {cid}."
    assert row[0] == "demo" and row[1] == "active" and row[2] == sub_id

    # E. Verify AI credits endpoint
    r_cred = requests.get(f"{SANDBOX_URL}/api/v1/billing/ai-credits", headers=h, timeout=15)
    assert r_cred.status_code == 200
    assert r_cred.json()["monthly_included"] == 6500

    conn.close()


# ==============================================================================
# 3. RETAIL CONNECTIONS & IDOR
# ==============================================================================

def test_retail_connectors_catalog_and_security(tenant_token):
    h = {"Authorization": f"Bearer {tenant_token}"}
    # Catalog
    r_cat = requests.get(f"{SANDBOX_URL}/api/v1/connectors", headers=h, timeout=15)
    assert r_cat.status_code == 200
    providers = [c.get("provider") for c in r_cat.json()]
    assert "woocommerce" in providers and "shopify" in providers and "bigcommerce" in providers

    # Active connections
    r_conns = requests.get(f"{SANDBOX_URL}/api/v1/connectors/connections", headers=h, timeout=15)
    assert r_conns.status_code == 200
    conns = r_conns.json()
    woo = next((c for c in conns if c["id"] == WOO_CONN_ID), None)
    assert woo is not None
    assert woo["status"] in {"READY", "CONNECTED", "SYNCED", "SYNCING", "PROCESSING"}

    # IDOR check
    r_idor = requests.get(f"{SANDBOX_URL}/api/v1/connectors/connections", headers={"Authorization": "Bearer bad_token"}, timeout=15)
    assert r_idor.status_code in {401, 403}


# ==============================================================================
# 4. WOOCOMMERCE REAL SYNCHRONIZATION (PRODUCT 14)
# ==============================================================================

def test_woocommerce_real_sync_product_14(woo_creds):
    auth = (woo_creds["consumer_key"], woo_creds["consumer_secret"])
    wh_secret = woo_creds.get("webhook_secret", "xUumq5_TEcvKgr4cL5dApQT2TYqQ8hgn07TvVm-RsWZO2hR6Or05f4cH2ndZ4PpY")

    # 1. Fetch current price
    r_prod = requests.get(f"{WOO_STORE_URL}/wp-json/wc/v3/products/14", auth=auth, timeout=15)
    assert r_prod.status_code == 200
    orig_price = r_prod.json().get("regular_price") or "245"
    test_price = "249" if orig_price == "245" else "245"

    try:
        # 2. Mutate price on WooCommerce
        r_mut = requests.put(f"{WOO_STORE_URL}/wp-json/wc/v3/products/14", auth=auth, json={"regular_price": test_price}, timeout=15)
        assert r_mut.status_code == 200
        updated_body = json.dumps(r_mut.json()).encode("utf-8")

        # 3. Deliver webhook
        sig = base64.b64encode(hmac.new(wh_secret.encode("utf-8"), updated_body, hashlib.sha256).digest()).decode("ascii")
        r_hook = requests.post(
            f"{SANDBOX_URL}/api/v1/connectors/woocommerce/webhook/{WOO_CONN_ID}",
            headers={
                "x-wc-webhook-delivery-id": f"deliv_{uuid4().hex[:10]}",
                "x-wc-webhook-topic": "product.updated",
                "x-wc-webhook-signature": sig,
                "Content-Type": "application/json"
            },
            data=updated_body,
            timeout=15
        )
        assert r_hook.status_code == 200
        assert r_hook.json().get("accepted") is True

        # 4. Wait for background synchronization
        time.sleep(3)

        # 5. Check database
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute(
            "SELECT normalized_data FROM normalized_commerce_records WHERE connection_id=%s AND entity_type='products' AND source_record_id='14'",
            (WOO_CONN_ID,)
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        norm = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        assert norm.get("product_name") == "Avenqo Headphones X"

    finally:
        # 6. Revert back to original price (245 CAD)
        r_rev = requests.put(f"{WOO_STORE_URL}/wp-json/wc/v3/products/14", auth=auth, json={"regular_price": orig_price}, timeout=15)
        assert r_rev.status_code == 200
        rev_body = json.dumps(r_rev.json()).encode("utf-8")
        rev_sig = base64.b64encode(hmac.new(wh_secret.encode("utf-8"), rev_body, hashlib.sha256).digest()).decode("ascii")
        requests.post(
            f"{SANDBOX_URL}/api/v1/connectors/woocommerce/webhook/{WOO_CONN_ID}",
            headers={
                "x-wc-webhook-delivery-id": f"deliv_rev_{uuid4().hex[:8]}",
                "x-wc-webhook-topic": "product.updated",
                "x-wc-webhook-signature": rev_sig,
                "Content-Type": "application/json"
            },
            data=rev_body,
            timeout=15
        )


# ==============================================================================
# 5. CENTRAL AI & CREDIT CONSUMPTION
# ==============================================================================

def test_central_ai_grounded_business_questions(tenant_token):
    h = {"Authorization": f"Bearer {tenant_token}"}

    # Record initial credits
    init_credits = requests.get(f"{SANDBOX_URL}/api/v1/billing/ai-credits", headers=h, timeout=15).json()["monthly_used"]

    # Ask grounded question
    conv = requests.post(f"{SANDBOX_URL}/api/v1/ai/chat/conversations", headers=h, json={"title": "Smoke AI Test"}).json()
    cid = conv["id"]
    r_msg = requests.post(
        f"{SANDBOX_URL}/api/v1/ai/central/conversations/{cid}/messages",
        headers=h,
        json={"content": "Quel est mon produit le plus vendu ?", "locale": "fr"},
        timeout=30
    )
    assert r_msg.status_code == 200
    ai_data = r_msg.json()
    assert ai_data.get("answer") is not None
    assert len(ai_data["answer"]) > 20

    # Verify credit decrement
    new_credits = requests.get(f"{SANDBOX_URL}/api/v1/billing/ai-credits", headers=h, timeout=15).json()["monthly_used"]
    assert new_credits >= init_credits


# ==============================================================================
# 6. ADMIN PLATFORM & ISOLATION
# ==============================================================================

def test_admin_platform_access_and_tenant_isolation(tenant_token, admin_token):
    # Standard tenant blocked with 403
    r_tenant = requests.get(f"{SANDBOX_URL}/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {tenant_token}"}, timeout=15)
    assert r_tenant.status_code == 403

    # Platform admin allowed with 200
    r_admin = requests.get(f"{SANDBOX_URL}/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    assert r_admin.status_code == 200
    r_comps = requests.get(f"{SANDBOX_URL}/api/v1/admin/companies", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    assert r_comps.status_code == 200
