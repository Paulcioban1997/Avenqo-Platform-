import json
import uuid
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import urllib.request
import urllib.error
from datetime import datetime, timezone

from sqlalchemy import select
from backend.app.database.session import SessionLocal
from backend.app.models.user import User
from backend.app.models.account_token import AccountToken
from backend.app.models.base import AccountTokenPurpose
from backend.app.core.security import hash_token

FRONTEND_URL = "http://127.0.0.1:3000"
BACKEND_URL = "http://127.0.0.1:8000"

def post_json(url: str, payload: dict, token: str = None) -> tuple[int, dict, dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = dict(resp.headers)
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}, resp_headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}, dict(e.headers)

def get_json(url: str, token: str = None) -> tuple[int, dict, dict]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = dict(resp.headers)
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}, resp_headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}, dict(e.headers)

def run_e2e_journey():
    print("==================================================")
    print("AVENQO END-TO-END VERIFICATION: P0 TO BILLING")
    print("==================================================")

    uid = uuid.uuid4().hex[:8]
    test_email = f"lead-{uid}@avenqo-test.ca"
    test_password = "AvenqoTest2026#Secure"
    company_name = f"Entreprise Test {uid.upper()}"

    # STEP 1: Registration on /api/auth/register (via Next.js port 3000)
    print(f"\n[1/6] Inscription via Next.js proxy ({test_email})...")
    reg_payload = {
        "email": test_email,
        "password": test_password,
        "first_name": "Jean-Philippe",
        "last_name": "Tremblay",
        "company_name": company_name,
        "company_email": test_email,
        "country": "Canada",
        "timezone": "America/Toronto",
        "industry": "Commerce"
    }
    status, data, _ = post_json(f"{FRONTEND_URL}/api/auth/register", reg_payload)
    print(f"-> Inscription status: {status}, response: {data}")
    assert status == 201, f"Registration failed with status {status}: {data}"

    # STEP 2: Unverified user cannot login
    print("\n[2/6] Tentative de connexion avant vérification d'email...")
    login_payload = {"email": test_email, "password": test_password}
    status, data, _ = post_json(f"{FRONTEND_URL}/api/auth/login", login_payload)
    print(f"-> Tentative connexion avant validation: code {status}, message: {data}")
    assert status == 403 or "vérifiée" in str(data).lower() or "verify" in str(data).lower(), "Unverified user should not be able to log in"

    # STEP 3: Email Verification via /api/auth/verify-email (the P0 fix!)
    print("\n[3/6] Récupération du jeton d'activation et validation via /api/auth/verify-email...")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == test_email))
        assert user is not None, "User not found in DB"
        # Find the raw token from the account_tokens table
        tokens = db.scalars(
            select(AccountToken)
            .where(
                AccountToken.user_id == user.id,
                AccountToken.purpose == AccountTokenPurpose.EMAIL_VERIFICATION,
                AccountToken.used_at.is_(None)
            )
        ).all()
        assert len(tokens) > 0, "No verification token found for user"
        # To test the real HTTP verify-email endpoint, create a fresh token with known raw token
        from backend.app.core.security import generate_token
        raw_token = generate_token()
        token_record = AccountToken(
            user_id=user.id,
            purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_token(raw_token),
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc).replace(year=2028),
        )
        db.add(token_record)
        db.commit()

    print(f"-> Envoi du jeton à {FRONTEND_URL}/api/auth/verify-email...")
    verify_status, verify_data, _ = post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": raw_token})
    print(f"-> Réponse vérification: code {verify_status}, data: {verify_data}")
    assert verify_status == 200, f"Email verification failed: {verify_data}"
    assert "vérifiée" in verify_data.get("message", "").lower(), f"Unexpected message: {verify_data}"

    # Verify replay protection: using the same token again should be rejected
    replay_status, replay_data, _ = post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": raw_token})
    print(f"-> Test rejeu du jeton: code {replay_status} (attendu: 400 invalide ou expiré)")
    assert replay_status == 400, "Token replay should be rejected"

    # STEP 4: Login after email verification
    print("\n[4/6] Connexion post-vérification sur /api/auth/login...")
    status, login_res, headers = post_json(f"{FRONTEND_URL}/api/auth/login", login_payload)
    print(f"-> Connexion réussie: code {status}, access_token reçu: {bool(login_res.get('access_token'))}")
    assert status == 200, f"Login failed: {login_res}"
    access_token = login_res["access_token"]

    # STEP 5: Connect store / import data and verify products in Retail
    print("\n[5/6] Connexion d'une boutique et synchronisation des données Retail...")
    store_payload = {
        "shop_domain": f"boutique-{uid}.myshopify.com",
        "access_token": "shpat_test_token_1234567890abcdef"
    }
    status, store_res, _ = post_json(f"{BACKEND_URL}/api/v1/connectors/shopify/manual", store_payload, token=access_token)
    print(f"-> Connexion boutique Shopify: code {status}, provider: {store_res.get('provider')}")
    assert status in (200, 202), f"Shopify connection failed: {store_res}"

    # Check retail status
    status, retail_status_res, _ = get_json(f"{BACKEND_URL}/api/v1/retail/status", token=access_token)
    print(f"-> Statut Retail: code {status}, is_connected: {retail_status_res.get('is_connected')}, provider: {retail_status_res.get('provider')}")
    assert status == 200, f"Retail status fetch failed: {retail_status_res}"
    assert retail_status_res.get("is_connected") is True, f"Retail should be connected: {retail_status_res}"

    # Check retail products endpoint
    status, products_res, _ = get_json(f"{BACKEND_URL}/api/v1/retail/products", token=access_token)
    print(f"-> Endpoint Retail products accessible: code {status}, items: {len(products_res.get('products', []))}")
    assert status == 200, f"Retail products fetch failed: {products_res}"

    # STEP 6: Validate Billing and Plan limits (Demo 3 modules -> Professional 6 modules)
    print("\n[6/6] Validation des droits de modules et des limites de facturation...")
    # Check current subscription
    status, sub_res, _ = get_json(f"{BACKEND_URL}/api/v1/billing/subscription", token=access_token)
    print(f"-> Statut abonnement actuel: code {status}, plan: {sub_res.get('subscription_plan', sub_res.get('plan', 'Demo'))}")
    assert status == 200, f"Billing subscription fetch failed: {sub_res}"

    # Verify module selection enforcement
    # Demo allows maximum 3 modules:
    print("-> Test activation de 3 modules sur plan Demo...")
    for mod in ["retail", "crm", "accounting"]:
        status, mod_res, _ = post_json(f"{BACKEND_URL}/api/v1/modules/{mod}/activate", {}, token=access_token)
        assert status in (200, 201), f"Demo activation for {mod} failed: {mod_res}"

    # Verify entitlements summary
    status, ent_res, _ = get_json(f"{BACKEND_URL}/api/v1/modules/entitlements", token=access_token)
    assert status == 200, f"Entitlements failed: {ent_res}"
    print(f"-> Modules actifs sur Demo ({len(ent_res.get('active_modules', []))}/{ent_res.get('module_limit')}): {ent_res.get('active_modules')}")
    assert len(ent_res.get("active_modules", [])) == 3
    assert ent_res.get("module_limit") == 3

    # Demo attempting 4th module should be rejected (409 Conflict / Limit Reached)
    status, err_res, _ = post_json(f"{BACKEND_URL}/api/v1/modules/appointments/activate", {}, token=access_token)
    print(f"-> Tentative 4e module ('appointments') sur plan Demo: code {status} (attendu: 409 limit reached)")
    assert status == 409, f"Plan Demo should reject more than 3 modules: {err_res}"

    # Upgrade company subscription to Professional (simulated checkout / webhook upgrade)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == test_email))
        from backend.app.models.billing import BillingAccount
        account = db.scalar(select(BillingAccount).where(BillingAccount.company_id == user.company_id))
        account.plan_code = "professional"
        user.company.subscription_plan = "professional"
        db.commit()

    # Now on Professional, activating 3 more modules (total 6) should succeed!
    print("-> Test activation jusqu'à 6 modules sur plan Professional...")
    for mod in ["appointments", "marketing", "voice"]:
        status, mod_res, _ = post_json(f"{BACKEND_URL}/api/v1/modules/{mod}/activate", {}, token=access_token)
        assert status in (200, 201), f"Professional activation for {mod} failed: {mod_res}"

    status, ent_res, _ = get_json(f"{BACKEND_URL}/api/v1/modules/entitlements", token=access_token)
    assert status == 200
    print(f"-> Modules actifs sur Professional ({len(ent_res.get('active_modules', []))}/{ent_res.get('module_limit')}): {ent_res.get('active_modules')}")
    assert len(ent_res.get("active_modules", [])) == 6
    assert ent_res.get("module_limit") == 6

    # Professional attempting 7th module should be rejected (409 Conflict / Limit Reached)
    status, err_res, _ = post_json(f"{BACKEND_URL}/api/v1/modules/ocr/activate", {}, token=access_token)
    print(f"-> Tentative 7e module ('ocr') sur plan Professional: code {status} (attendu: 409 limit reached)")
    assert status == 409, f"Plan Professional should reject more than 6 modules: {err_res}"

    print("\n==================================================")
    print("SUCCESS: COMPLETE END-TO-END FLOW VERIFIED 100%!")
    print("==================================================")

if __name__ == "__main__":
    run_e2e_journey()
