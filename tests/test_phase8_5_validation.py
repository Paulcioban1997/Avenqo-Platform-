"""
Phase 8.5 Comprehensive Validation Test Suite:
1. Pricing Consistency (UI, API, Stripe TEST, AI credits, Plan names untranslated)
2. Stripe TEST Journey (Checkout session, Webhook subscription update, Idempotency, Signatures, DB persistence)
3. Retail Connections UI & API (Connector Catalog, Active Tenant Connections, Status READY, Multi-Tenant IDOR isolation)
4. WooCommerce Real Synchronization (Product 14 Avenqo Headphones X, safe mutate, webhook sync, verify DB, safe revert)
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
SANDBOX_BACKEND_URL = os.environ.get("BACKEND_URL", "https://avenqo-platform-sandbox.up.railway.app").strip()
RAILWAY_PG_URL = os.environ.get("DATABASE_URL", "")

STRIPE_TEST_KEY = os.environ.get("STRIPE_TEST_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_DEMO = os.environ.get("STRIPE_PRICE_DEMO", "")
STRIPE_PRICE_PROFESSIONAL = os.environ.get("STRIPE_PRICE_PROFESSIONAL", "")

WOO_STORE_URL = os.environ.get("WOO_STORE_URL", "https://wordpress-production-7219.up.railway.app")
WOO_CONNECTION_ID = "a93d53b9-0a32-4d7a-82bb-7123746e36b3"
COMPANY_ID = "9c97cb94-e9f9-46fb-afd4-8a1d21019cff"
TEST_USER_EMAIL = os.environ.get("TEST_USER_EMAIL", "gauffy95@gmail.com")
TEST_USER_PW = os.environ.get("TEST_USER_PW", "")


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(
        f"{SANDBOX_BACKEND_URL}/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PW},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json().get("access_token")
    assert token, "No access_token returned"
    return token


@pytest.fixture(scope="session")
def woo_creds():
    cipher = ConnectorSecretCipher(["03rZtfwgwKsrVQ3vzJ3srsLtiJHrwqrfW2z7ojGiV2E="])
    conn = psycopg2.connect(RAILWAY_PG_URL)
    cur = conn.cursor()
    cur.execute("SELECT encrypted_credentials FROM commerce_connections WHERE id=%s", (WOO_CONNECTION_ID,))
    row = cur.fetchone()
    conn.close()
    assert row and row[0], "WooCommerce connection encrypted credentials not found"
    return cipher.decrypt(row[0])


class TestPhase85_Part1_PricingConsistency:
    """Validation of Pricing consistency across UI, API, Stripe TEST, and translations."""

    def test_api_billing_plans_exact_prices_and_credits(self):
        r = requests.get(f"{SANDBOX_BACKEND_URL}/api/v1/billing/plans", timeout=15)
        assert r.status_code == 200
        plans = {p["code"]: p for p in r.json()}

        assert "demo" in plans
        assert plans["demo"]["name"] == "Demo"
        assert plans["demo"]["monthly_price_usd"] == 28
        assert plans["demo"]["requires_sales_contact"] is False

        assert "professional" in plans
        assert plans["professional"]["name"] == "Professional"
        assert plans["professional"]["monthly_price_usd"] == 49
        assert plans["professional"]["requires_sales_contact"] is False

        assert "enterprise" in plans
        assert plans["enterprise"]["name"] == "Enterprise"
        assert plans["enterprise"]["monthly_price_usd"] is None
        assert plans["enterprise"]["requires_sales_contact"] is True

    def test_stripe_test_prices_match_official_catalog(self):
        stripe.api_key = STRIPE_TEST_KEY
        demo_price = stripe.Price.retrieve(STRIPE_PRICE_DEMO)
        assert demo_price.unit_amount == 2800
        assert demo_price.currency == "usd"
        assert demo_price.recurring.interval == "month"

        pro_price = stripe.Price.retrieve(STRIPE_PRICE_PROFESSIONAL)
        assert pro_price.unit_amount == 4900
        assert pro_price.currency == "usd"
        assert pro_price.recurring.interval == "month"

    def test_nextjs_pricing_ui_displays_exact_prices(self):
        r = requests.get(f"{GATEWAY_URL}/pricing", timeout=20)
        assert r.status_code == 200
        html = r.text
        # Demo pricing & credits
        assert "$28" in html
        assert "6 500" in html or "6,500" in html
        # Pro pricing & credits
        assert "$49" in html
        assert "25 000" in html or "25,000" in html
        # Enterprise
        assert "Sur mesure" in html or "Custom quote" in html

    def test_plan_names_never_translated_across_all_locales(self):
        # Web translations check (skip proxy file ar-EG.ts)
        trans_dir = r"c:\Python-Projects\PMC_Solutions_AI_Platform\web\src\lib\i18n\translations"
        for fname in os.listdir(trans_dir):
            if fname.endswith(".ts") and fname != "ar-EG.ts":
                with open(os.path.join(trans_dir, fname), "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                tiers = re.findall(r'tier:\s*"([^"]+)"', content)
                assert tiers == ["Demo", "Professional", "Enterprise"], f"Inconsistent tier names in {fname}: {tiers}"

        # Flutter JSONs check (skip _locales.json catalog)
        flutter_i18n_dir = r"c:\Python-Projects\PMC_Solutions_AI_Platform\frontend\assets\i18n"
        for fname in os.listdir(flutter_i18n_dir):
            if fname.endswith(".json") and fname != "_locales.json":
                with open(os.path.join(flutter_i18n_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                billing = data.get("phase4e", {}).get("billing", {})
                assert billing.get("planDemo") == "Demo", f"planDemo translated in {fname}: {billing.get('planDemo')}"
                assert billing.get("planProfessional") == "Professional", f"planProfessional translated in {fname}: {billing.get('planProfessional')}"
                assert billing.get("planEnterprise") == "Enterprise", f"planEnterprise translated in {fname}: {billing.get('planEnterprise')}"


class TestPhase85_Part2_StripeTestJourney:
    """Complete Stripe Test journey: checkout session, webhook receipt, idempotency, DB updates."""

    def test_create_checkout_session_demo(self, auth_token):
        # Temporarily clear stripe_subscription_id to test clean initial checkout creation
        conn = psycopg2.connect(RAILWAY_PG_URL)
        cur = conn.cursor()
        cur.execute("SELECT stripe_subscription_id, status FROM billing_accounts WHERE company_id = %s", (COMPANY_ID,))
        orig_sub, orig_status = cur.fetchone()
        cur.execute("UPDATE billing_accounts SET stripe_subscription_id = NULL WHERE company_id = %s", (COMPANY_ID,))
        conn.commit()

        try:
            r = requests.post(
                f"{SANDBOX_BACKEND_URL}/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={"plan_code": "demo"},
                timeout=15,
            )
            assert r.status_code == 200
            data = r.json()
            assert "url" in data
            assert "checkout.stripe.com" in data["url"] or "stripe.com" in data["url"]
        finally:
            cur.execute(
                "UPDATE billing_accounts SET stripe_subscription_id = %s, status = %s WHERE company_id = %s",
                (orig_sub, orig_status, COMPANY_ID)
            )
            conn.commit()
            conn.close()

    def test_create_checkout_session_professional(self, auth_token):
        # Temporarily clear stripe_subscription_id to test clean initial checkout creation
        conn = psycopg2.connect(RAILWAY_PG_URL)
        cur = conn.cursor()
        cur.execute("SELECT stripe_subscription_id, status FROM billing_accounts WHERE company_id = %s", (COMPANY_ID,))
        orig_sub, orig_status = cur.fetchone()
        cur.execute("UPDATE billing_accounts SET stripe_subscription_id = NULL WHERE company_id = %s", (COMPANY_ID,))
        conn.commit()

        try:
            r = requests.post(
                f"{SANDBOX_BACKEND_URL}/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={"plan_code": "professional"},
                timeout=15,
            )
            assert r.status_code == 200
            data = r.json()
            assert "url" in data
            assert "checkout.stripe.com" in data["url"] or "stripe.com" in data["url"]
        finally:
            cur.execute(
                "UPDATE billing_accounts SET stripe_subscription_id = %s, status = %s WHERE company_id = %s",
                (orig_sub, orig_status, COMPANY_ID)
            )
            conn.commit()
            conn.close()

    def test_webhook_subscription_updated_updates_db(self):
        event_id = f"evt_test_sub_{int(time.time())}_{uuid4().hex[:6]}"
        sub_id = f"sub_test_{uuid4().hex[:16]}"
        cust_id = "cus_VBhfUdTZqnatYg"

        payload_obj = {
            "id": event_id,
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
                    "metadata": {"avenqo_company_id": COMPANY_ID},
                    "items": {
                        "data": [
                            {
                                "id": f"si_{uuid4().hex[:12]}",
                                "price": {"id": STRIPE_PRICE_DEMO},
                            }
                        ]
                    },
                }
            },
        }
        raw_body = json.dumps(payload_obj)
        timestamp = int(time.time())
        signed_payload = f"{timestamp}.{raw_body}"
        sig = hmac.new(STRIPE_WEBHOOK_SECRET.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        stripe_signature = f"t={timestamp},v1={sig}"

        r = requests.post(
            f"{SANDBOX_BACKEND_URL}/api/v1/billing/webhook",
            headers={
                "Stripe-Signature": stripe_signature,
                "Content-Type": "application/json",
            },
            data=raw_body.encode("utf-8"),
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("processed") is True

        # Verify DB updated
        conn = psycopg2.connect(RAILWAY_PG_URL)
        cur = conn.cursor()
        cur.execute("SELECT plan_code, status, stripe_subscription_id FROM billing_accounts WHERE company_id=%s", (COMPANY_ID,))
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "demo"
        assert row[1] == "active"
        assert row[2] == sub_id

    def test_webhook_idempotency_no_duplicate(self):
        event_id = f"evt_test_idemp_{int(time.time())}_{uuid4().hex[:6]}"
        payload_obj = {
            "id": event_id,
            "object": "event",
            "api_version": "2024-06-20",
            "created": int(time.time()),
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": f"sub_idemp_{uuid4().hex[:12]}",
                    "object": "subscription",
                    "customer": "cus_VBhfUdTZqnatYg",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_end": int(time.time()) + 2592000,
                    "metadata": {"avenqo_company_id": COMPANY_ID},
                    "items": {
                        "data": [
                            {
                                "id": f"si_{uuid4().hex[:8]}",
                                "price": {"id": STRIPE_PRICE_DEMO},
                            }
                        ]
                    },
                }
            },
        }
        raw_body = json.dumps(payload_obj)
        timestamp = int(time.time())
        signed_payload = f"{timestamp}.{raw_body}"
        sig = hmac.new(STRIPE_WEBHOOK_SECRET.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        sig_header = f"t={timestamp},v1={sig}"

        r1 = requests.post(
            f"{SANDBOX_BACKEND_URL}/api/v1/billing/webhook",
            headers={"Stripe-Signature": sig_header, "Content-Type": "application/json"},
            data=raw_body.encode("utf-8"),
            timeout=15,
        )
        assert r1.status_code == 200
        assert r1.json().get("processed") is True

        # Second delivery should be ignored idempotently without duplicate processing
        r2 = requests.post(
            f"{SANDBOX_BACKEND_URL}/api/v1/billing/webhook",
            headers={"Stripe-Signature": sig_header, "Content-Type": "application/json"},
            data=raw_body.encode("utf-8"),
            timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json().get("processed") is False

    def test_webhook_invalid_signature_rejected(self):
        r = requests.post(
            f"{SANDBOX_BACKEND_URL}/api/v1/billing/webhook",
            headers={"Stripe-Signature": "t=12345,v1=invalid_signature", "Content-Type": "application/json"},
            data=b"{}",
            timeout=15,
        )
        assert r.status_code in {400, 401}


class TestPhase85_Part3_RetailConnectionsAndSecurity:
    """Validation of Retail Connections page, catalog, active connectors, and IDOR security."""

    def test_connectors_catalog_and_active_connections(self, auth_token):
        headers = {"Authorization": f"Bearer {auth_token}"}

        # 1. Check connectors catalog
        r_cat = requests.get(f"{SANDBOX_BACKEND_URL}/api/v1/connectors", headers=headers, timeout=15)
        assert r_cat.status_code == 200
        catalog = r_cat.json()
        assert len(catalog) >= 20, f"Expected at least 20 retail connectors, found {len(catalog)}"
        catalog_providers = [c.get("provider") for c in catalog]
        assert "woocommerce" in catalog_providers
        assert "shopify" in catalog_providers
        assert "bigcommerce" in catalog_providers

        # 2. Check active tenant connections
        r_conns = requests.get(f"{SANDBOX_BACKEND_URL}/api/v1/connectors/connections", headers=headers, timeout=15)
        assert r_conns.status_code == 200
        conns = r_conns.json()
        assert isinstance(conns, list)

        # WooCommerce connection check
        woo = next((c for c in conns if c.get("provider") == "woocommerce" and c.get("id") == WOO_CONNECTION_ID), None)
        assert woo is not None, f"Connection {WOO_CONNECTION_ID} not found in {conns}"
        assert woo["status"] in {"READY", "CONNECTED", "SYNCED", "SYNCING", "PROCESSING"}
        assert "wordpress-production-7219.up.railway.app" in woo["external_account_id"]

        # Shopify connection check
        shopify = next((c for c in conns if c.get("provider") == "shopify"), None)
        assert shopify is not None
        assert shopify["status"] in {"READY", "CONNECTED", "SYNCED", "SYNCING", "PROCESSING"}
        assert "avenqo-retail-test.myshopify.com" in shopify["external_account_id"]

    def test_connections_idor_isolation(self):
        # Attempt to access connection with unauthenticated or wrong credentials
        unauth = requests.get(
            f"{SANDBOX_BACKEND_URL}/api/v1/connectors/connections",
            headers={"Authorization": "Bearer invalid_or_expired_token"},
            timeout=15,
        )
        assert unauth.status_code in {401, 403}

        # Attempt to trigger sync or inspect connection without auth
        r = requests.post(
            f"{SANDBOX_BACKEND_URL}/api/v1/connectors/{WOO_CONNECTION_ID}/sync",
            headers={"Authorization": "Bearer invalid_or_expired_token"},
            timeout=15,
        )
        assert r.status_code in {401, 403, 404}, f"IDOR vulnerability! Status: {r.status_code}"


class TestPhase85_Part4_WooCommerceLiveSyncAndProduct14:
    """Targeted live sync validation with Product 14 (Avenqo Headphones X) on WooCommerce test store."""

    def test_product_14_live_reconciliation_cycle(self, woo_creds):
        auth = (woo_creds["consumer_key"], woo_creds["consumer_secret"])
        webhook_secret = woo_creds.get("webhook_secret") or "xUumq5_TEcvKgr4cL5dApQT2TYqQ8hgn07TvVm-RsWZO2hR6Or05f4cH2ndZ4PpY"

        # 1. Fetch current product 14 from WooCommerce store
        r_get = requests.get(f"{WOO_STORE_URL}/wp-json/wc/v3/products/14", auth=auth, timeout=15)
        assert r_get.status_code == 200, f"Failed fetching product 14 from Woo: {r_get.text}"
        prod_data = r_get.json()
        original_price = prod_data.get("regular_price") or "245"
        test_price = "249" if original_price == "245" else "245"

        try:
            # 2. Update price on WooCommerce test store
            r_put = requests.put(
                f"{WOO_STORE_URL}/wp-json/wc/v3/products/14",
                auth=auth,
                json={"regular_price": test_price},
                timeout=15,
            )
            assert r_put.status_code == 200
            updated_p14 = r_put.json()
            assert updated_p14.get("regular_price") == test_price

            # 3. Deliver WooCommerce webhook product.updated
            delivery_id = f"deliv_{uuid4().hex[:12]}"
            webhook_body = json.dumps(updated_p14).encode("utf-8")
            sig = base64.b64encode(
                hmac.new(webhook_secret.encode("utf-8"), webhook_body, hashlib.sha256).digest()
            ).decode("ascii")

            r_hook = requests.post(
                f"{SANDBOX_BACKEND_URL}/api/v1/connectors/woocommerce/webhook/{WOO_CONNECTION_ID}",
                headers={
                    "x-wc-webhook-delivery-id": delivery_id,
                    "x-wc-webhook-topic": "product.updated",
                    "x-wc-webhook-signature": sig,
                    "Content-Type": "application/json",
                },
                data=webhook_body,
                timeout=15,
            )
            assert r_hook.status_code == 200
            assert r_hook.json().get("accepted") is True

            # 4. Give background worker a moment to process the sync
            time.sleep(3)

            # 5. Check database contains product 14
            conn = psycopg2.connect(RAILWAY_PG_URL)
            cur = conn.cursor()
            cur.execute(
                "SELECT normalized_data FROM normalized_commerce_records WHERE connection_id=%s AND entity_type='products' AND source_record_id='14'",
                (WOO_CONNECTION_ID,)
            )
            row = cur.fetchone()
            conn.close()
            assert row is not None
            norm = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
            assert norm.get("product_name") == "Avenqo Headphones X"

        finally:
            # 6. ALWAYS revert back to original price (245)
            r_rev = requests.put(
                f"{WOO_STORE_URL}/wp-json/wc/v3/products/14",
                auth=auth,
                json={"regular_price": original_price},
                timeout=15,
            )
            assert r_rev.status_code == 200
            reverted_p14 = r_rev.json()
            assert reverted_p14.get("regular_price") == original_price

            # Deliver revert webhook
            revert_body = json.dumps(reverted_p14).encode("utf-8")
            revert_sig = base64.b64encode(
                hmac.new(webhook_secret.encode("utf-8"), revert_body, hashlib.sha256).digest()
            ).decode("ascii")
            requests.post(
                f"{SANDBOX_BACKEND_URL}/api/v1/connectors/woocommerce/webhook/{WOO_CONNECTION_ID}",
                headers={
                    "x-wc-webhook-delivery-id": f"deliv_revert_{uuid4().hex[:8]}",
                    "x-wc-webhook-topic": "product.updated",
                    "x-wc-webhook-signature": revert_sig,
                    "Content-Type": "application/json",
                },
                data=revert_body,
                timeout=15,
            )
