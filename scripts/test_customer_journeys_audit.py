import io
import json
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import urllib.request
import urllib.error

from sqlalchemy import select
from backend.app.database.session import SessionLocal
from backend.app.models.user import User
from backend.app.models.company import Company
from backend.app.models.billing import BillingAccount, BillingInvoice, EnterpriseQuote
from backend.app.models.account_token import AccountToken
from backend.app.models.base import AccountTokenPurpose
from backend.app.core.security import generate_token, hash_token

FRONTEND_URL = "http://127.0.0.1:3000"
BACKEND_URL = "http://127.0.0.1:8000"

def post_json(url: str, payload: dict, token: str = None) -> tuple[int, dict, dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json", "Connection": "close"}
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
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed, dict(e.headers)

def get_json(url: str, token: str = None) -> tuple[int, dict, dict]:
    headers = {"Accept": "application/json", "Connection": "close"}
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
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed, dict(e.headers)

def delete_req(url: str, token: str = None) -> tuple[int, dict, dict]:
    headers = {"Accept": "application/json", "Connection": "close"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = dict(resp.headers)
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}, resp_headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw": body}
        return e.code, parsed, dict(e.headers)

def get_bytes(url: str, token: str = None) -> tuple[int, bytes, dict]:
    headers = {"Connection": "close"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_headers = dict(resp.headers)
            return resp.status, resp.read(), resp_headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)

def main():
    print("=" * 65)
    print("AVENQO REAL CUSTOMER JOURNEYS AUDIT & VERIFICATION SUITE")
    print("=" * 65)

    # Wait for backend readiness
    for _ in range(30):
        try:
            status, _, _ = get_json(f"{BACKEND_URL}/health")
            if status == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)

    results = []

    # -------------------------------------------------------------
    # JOURNEY 1: Email Verification Token Security (Invalid, Expired, Replay)
    # -------------------------------------------------------------
    print("\n--- [1] Email Verification Tokens: Invalid, Expired & Replay ---")
    # Malformed token (< 32 chars)
    status, res, _ = post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": "short"})
    print(f"-> Malformed short token HTTP: {status} (422)")
    assert status == 422

    # Well-formed token (>= 32 chars) but non-existent in DB
    status, res, _ = post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": "x" * 48})
    print(f"-> Invalid non-existent token HTTP: {status}, Detail: {res}")
    assert status == 400, f"Expected 400 for invalid token, got {status}"
    results.append(("Email Token: Invalide rejeté (400/422)", "PASS"))

    # Create expired token test
    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.created_at.desc()))
        assert user is not None, "Need at least one user in DB"
        expired_token = generate_token()
        db.add(AccountToken(
            user_id=user.id,
            purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_token(expired_token),
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        ))
        db.commit()

    status, res, _ = post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": expired_token})
    print(f"-> Expired token HTTP: {status}, Detail: {res}")
    assert status == 400, f"Expected 400 for expired token, got {status}"
    results.append(("Email Token: Expiré rejeté (400)", "PASS"))

    # -------------------------------------------------------------
    # JOURNEY 2: User Creation, Email Verification, Login
    # -------------------------------------------------------------
    uid_a = uuid.uuid4().hex[:8]
    email_a = f"tenant-a-{uid_a}@avenqo-audit.ca"
    pwd = "AvenqoTest2026#Secure"
    print(f"\n--- [2] Registration & Activation for Tenant A ({email_a}) ---")
    reg_payload = {
        "email": email_a,
        "company_email": email_a,
        "password": pwd,
        "first_name": "Alice",
        "last_name": "Audit",
        "company_name": f"Entreprise Alpha {uid_a.upper()}",
        "country": "Canada",
        "timezone": "America/Toronto",
        "industry": "Retail"
    }
    status, data, _ = post_json(f"{FRONTEND_URL}/api/auth/register", reg_payload)
    print(f"-> Inscription status: {status}")
    assert status == 201, f"Registration failed: {data}"

    # Verify unverified login blocked
    status, unverified_res, _ = post_json(f"{FRONTEND_URL}/api/auth/login", {"email": email_a, "password": pwd})
    print(f"-> Connexion avant vérification code: {status}, réponse: {unverified_res}")
    assert status in (400, 401, 403) or "vérifi" in str(unverified_res).lower() or "verify" in str(unverified_res).lower(), "Unverified login should be blocked"
    print("-> Connexion avant vérification bien refusée.")

    # Generate activation token
    with SessionLocal() as db:
        user_a = db.scalar(select(User).where(User.email == email_a))
        raw_token_a = generate_token()
        db.add(AccountToken(
            user_id=user_a.id,
            purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_token(raw_token_a),
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        ))
        db.commit()

    # Verify email
    status, _, _ = post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": raw_token_a})
    assert status == 200, "Activation should succeed"
    print("-> Vérification email réussie (200).")

    # Replay protection check
    status, _, _ = post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": raw_token_a})
    assert status == 400, "Replayed token should be rejected"
    print("-> Rejeu du jeton d'activation bien rejeté (400).")

    # Login
    status, login_res, _ = post_json(f"{FRONTEND_URL}/api/auth/login", {"email": email_a, "password": pwd})
    assert status == 200, "Login should succeed"
    token_a = login_res["access_token"]
    print("-> Connexion post-vérification réussie (200).")
    results.append(("Parcours Inscription -> Activation -> Connexion", "PASS"))

    # -------------------------------------------------------------
    # JOURNEY 3: Concurrent Module Activations & Atomic Plan Limits
    # -------------------------------------------------------------
    print("\n--- [3] Concurrent Module Activations & Atomic Quota Enforcement ---")
    # Activate 2 initial modules sequentially
    post_json(f"{BACKEND_URL}/api/v1/modules/retail/activate", {}, token=token_a)
    post_json(f"{BACKEND_URL}/api/v1/modules/crm/activate", {}, token=token_a)
    
    status, ent, _ = get_json(f"{BACKEND_URL}/api/v1/modules/entitlements", token=token_a)
    print(f"-> Modules initiaux actifs ({len(ent['active_modules'])}/{ent['module_limit']}): {ent['active_modules']}")
    assert len(ent["active_modules"]) == 2

    # Now launch 2 SIMULTANEOUS requests for distinct modules (accounting vs appointments)
    # Since Demo allows 3, exactly ONE must succeed, and ONE must fail with 409!
    print("-> Lancement de 2 activations SIMULTANÉES pour le dernier slot disponible...")
    def call_activate(mod):
        return post_json(f"{BACKEND_URL}/api/v1/modules/{mod}/activate", {}, token=token_a)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(call_activate, "accounting")
        f2 = executor.submit(call_activate, "appointments")
        res1 = f1.result()
        res2 = f2.result()

    codes = {res1[0], res2[0]}
    print(f"-> Résultat concurrence Demo: Réponses = {res1[0]} et {res2[0]}")
    assert 200 in codes, "At least one concurrent activation should succeed"
    assert 409 in codes, "The exceeding concurrent activation should be rejected with 409 Conflict"

    # Verify active count is strictly 3
    status, ent, _ = get_json(f"{BACKEND_URL}/api/v1/modules/entitlements", token=token_a)
    print(f"-> Quota final sur Demo après concurrence: {len(ent['active_modules'])}/{ent['module_limit']} modules: {ent['active_modules']}")
    assert len(ent["active_modules"]) == 3, f"Expected exactly 3 modules, got {len(ent['active_modules'])}"

    # Idempotent retry on already active module
    active_one = ent["active_modules"][0]
    status, _, _ = post_json(f"{BACKEND_URL}/api/v1/modules/{active_one}/activate", {}, token=token_a)
    assert status in (200, 201), "Idempotent re-activation of already active module should succeed"
    status, ent, _ = get_json(f"{BACKEND_URL}/api/v1/modules/entitlements", token=token_a)
    assert len(ent["active_modules"]) == 3, "Idempotent activation must not consume extra slot"
    results.append(("Activation concurrente atomique (Plafond Demo 3 respecté)", "PASS"))

    # -------------------------------------------------------------
    # JOURNEY 4: Real Stripe Webhook Simulation (Demo -> Professional)
    # -------------------------------------------------------------
    print("\n--- [4] Stripe Webhook Upgrade (Demo -> Professional) ---")
    with SessionLocal() as db:
        user_a = db.scalar(select(User).where(User.email == email_a))
        acct_a = db.scalar(select(BillingAccount).where(BillingAccount.company_id == user_a.company_id))
        cust_id = acct_a.stripe_customer_id or f"cus_test_{uid_a}"
        sub_id = f"sub_test_{uid_a}"
        acct_a.stripe_customer_id = cust_id
        acct_a.stripe_subscription_id = sub_id
        db.commit()

    # Emulate Stripe customer.subscription.updated webhook
    from backend.app.config.settings import get_settings
    settings = get_settings()
    pro_price_id = settings.stripe_price_professional

    sub_event_payload = {
        "id": f"evt_test_{uuid.uuid4().hex[:12]}",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": sub_id,
                "customer": cust_id,
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_end": int(time.time()) + 30 * 86400,
                "items": {
                    "data": [
                        {
                            "price": {"id": pro_price_id}
                        }
                    ]
                }
            }
        }
    }
    
    # Process through BillingService directly (server confirmation)
    from backend.app.dependencies.billing import get_billing_service

    with SessionLocal() as db:
        bs = get_billing_service(db)
        bs._sync_subscription(sub_event_payload["data"]["object"])
        db.commit()

    # Check updated plan via billing API
    status, sub_info, _ = get_json(f"{BACKEND_URL}/api/v1/billing/subscription", token=token_a)
    print(f"-> Statut abonnement post-webhook: {sub_info.get('plan_code')} ({sub_info.get('status')})")
    assert sub_info.get("plan_code") == "professional", f"Expected professional, got {sub_info}"
    assert sub_info.get("status") == "active"

    # Now verify that Professional allows activating up to 6 modules
    status, ent, _ = get_json(f"{BACKEND_URL}/api/v1/modules/entitlements", token=token_a)
    assert ent["module_limit"] == 6, f"Expected 6 module limit, got {ent['module_limit']}"
    print(f"-> Nouveau plafond Professional: {ent['module_limit']} modules.")

    # Activate 3 more modules on Professional (total 6)
    available_to_activate = [m for m in ["marketing", "ocr", "voice", "media", "legal"] if m not in ent["active_modules"]][:3]
    for mod in available_to_activate:
        status, _, _ = post_json(f"{BACKEND_URL}/api/v1/modules/{mod}/activate", {}, token=token_a)
        assert status in (200, 201), f"Activation of {mod} failed on Professional"

    status, ent, _ = get_json(f"{BACKEND_URL}/api/v1/modules/entitlements", token=token_a)
    print(f"-> Modules actifs sur Professional ({len(ent['active_modules'])}/{ent['module_limit']}): {ent['active_modules']}")
    assert len(ent["active_modules"]) == 6

    # 7th module must be rejected (409 Conflict)
    remaining_mod = [m for m in ["media", "legal", "ai_agents"] if m not in ent["active_modules"]][0]
    status, err_res, _ = post_json(f"{BACKEND_URL}/api/v1/modules/{remaining_mod}/activate", {}, token=token_a)
    print(f"-> Tentative 7e module ('{remaining_mod}') sur Professional: HTTP {status}")
    assert status == 409, f"Expected 409 for 7th module, got {status}"
    results.append(("Mise à niveau Stripe serveur & Plafond Pro (6 modules)", "PASS"))

    # -------------------------------------------------------------
    # JOURNEY 5: Invoice PDF Generation & Multi-Tenant Access Control
    # -------------------------------------------------------------
    print("\n--- [5] Invoice PDF Generation & Server-Side Tenant Isolation ---")
    invoice_id = uuid.uuid4()
    with SessionLocal() as db:
        user_a = db.scalar(select(User).where(User.email == email_a))
        inv = BillingInvoice(
            id=invoice_id,
            company_id=user_a.company_id,
            stripe_invoice_id=f"in_test_{uid_a}",
            number="AVQ-2026-0001",
            plan_code="professional",
            status="paid",
            currency="usd",
            subtotal=4900,
            discount_total=0,
            tax_total=0,
            total=4900,
            amount_due=0,
            amount_paid=4900,
            line_items=[{"description": "Avenqo Professional Plan", "amount": 4900}],
            issued_at=datetime.now(timezone.utc),
            paid_at=datetime.now(timezone.utc),
        )
        db.add(inv)
        db.commit()

    # Tenant A downloads their own PDF invoice
    status, pdf_data, headers = get_bytes(f"{BACKEND_URL}/api/v1/billing/invoices/{invoice_id}/pdf", token=token_a)
    print(f"-> Tenant A téléchargement facture: HTTP {status}, bytes: {len(pdf_data)}, starts with: {pdf_data[:5]}")
    assert status == 200, f"Failed to download PDF invoice: {status}"
    assert pdf_data.startswith(b"%PDF-"), "Expected valid PDF binary output"

    # Create Tenant B and ensure Tenant B is strictly FORBIDDEN from downloading Tenant A's invoice!
    uid_b = uuid.uuid4().hex[:8]
    email_b = f"tenant-b-{uid_b}@avenqo-audit.ca"
    reg_b = {
        "email": email_b,
        "company_email": email_b,
        "password": pwd,
        "first_name": "Bob",
        "last_name": "Beta",
        "company_name": f"Entreprise Beta {uid_b.upper()}",
        "country": "Canada",
        "timezone": "America/Toronto",
        "industry": "Commerce"
    }
    post_json(f"{FRONTEND_URL}/api/auth/register", reg_b)
    with SessionLocal() as db:
        user_b = db.scalar(select(User).where(User.email == email_b))
        raw_token_b = generate_token()
        db.add(AccountToken(
            user_id=user_b.id,
            purpose=AccountTokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_token(raw_token_b),
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        ))
        db.commit()
    post_json(f"{FRONTEND_URL}/api/auth/verify-email", {"token": raw_token_b})
    _, login_b_res, _ = post_json(f"{FRONTEND_URL}/api/auth/login", {"email": email_b, "password": pwd})
    token_b = login_b_res["access_token"]

    # Tenant B tries to access Tenant A's invoice: MUST FAIL with 404
    status, _, _ = get_bytes(f"{BACKEND_URL}/api/v1/billing/invoices/{invoice_id}/pdf", token=token_b)
    print(f"-> Tenant B tentative d'accès à la facture de A: HTTP {status} (attendu: 404 étanche)")
    assert status == 404, f"Cross-tenant invoice access must return 404, got {status}"
    results.append(("Facture PDF & Isolation multi-tenant", "PASS"))

    # -------------------------------------------------------------
    # JOURNEY 6: Enterprise Quote Recording and Querying
    # -------------------------------------------------------------
    print("\n--- [6] Enterprise Quote Submission and Retrieval ---")
    quote_req = {
        "contact_name": "Alice Enterprise",
        "contact_email": email_a,
        "contact_phone": "+1 514 555 0199",
        "requested_modules": ["retail", "crm", "voice", "ai_agents"],
        "estimated_users": 50,
        "monthly_volume": "100 000 transactions/mois",
        "required_integrations": ["Shopify Plus", "SAP"],
        "notes": "Besoin d'un accompagnement dédié et gouvernance multi-sites."
    }
    status, quote_res, _ = post_json(f"{BACKEND_URL}/api/v1/billing/enterprise-quote", quote_req, token=token_a)
    print(f"-> Soumission devis Enterprise: HTTP {status}, Référence: {quote_res.get('reference_id')}")
    assert status == 200, f"Quote submission failed: {quote_res}"
    ref_id = quote_res["reference_id"]

    # Tenant A views their quote status
    status, tenant_quotes, _ = get_json(f"{BACKEND_URL}/api/v1/billing/enterprise-quote", token=token_a)
    print(f"-> Consultation devis par le tenant: HTTP {status}, items: {len(tenant_quotes)}")
    assert status == 200 and len(tenant_quotes) > 0
    assert any(q["reference_id"] == ref_id for q in tenant_quotes)
    results.append(("Demande Enterprise enregistrée et consultable", "PASS"))

    # -------------------------------------------------------------
    # JOURNEY 7: Dataset Import, Cleaning, Download and Deletion
    # -------------------------------------------------------------
    print("\n--- [7] Dataset File Import, Analysis, Download & Deletion ---")
    # Synthetic CSV
    csv_content = (
        "sku,product_name,price,quantity,category\n"
        "AVQ-HD-001,Avenqo Headphones X,199.99,50,Electronics\n"
        "AVQ-CS-002,Avenqo Case Pro,29.99,150,Accessories\n"
        "AVQ-CB-003,USB-C Fast Cable,14.99,200,Cables\n"
    )
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    body_io = io.BytesIO()
    body_io.write(f"--{boundary}\r\n".encode())
    body_io.write(b'Content-Disposition: form-data; name="module_code"\r\n\r\n')
    body_io.write(b"retail\r\n")
    body_io.write(f"--{boundary}\r\n".encode())
    body_io.write(b'Content-Disposition: form-data; name="file"; filename="test_products_import.csv"\r\n')
    body_io.write(b"Content-Type: text/csv\r\n\r\n")
    body_io.write(csv_content.encode("utf-8"))
    body_io.write(b"\r\n")
    body_io.write(f"--{boundary}--\r\n".encode())
    payload_bytes = body_io.getvalue()

    req = urllib.request.Request(
        f"{BACKEND_URL}/api/v1/datasets/upload",
        data=payload_bytes,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token_a}",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        upload_status = resp.status
        upload_res = json.loads(resp.read().decode())
    print(f"-> Upload CSV test status: {upload_status}, dataset_id: {upload_res.get('dataset_id')}")
    assert upload_status in (200, 201), f"Upload failed: {upload_res}"
    dataset_id = upload_res["dataset_id"]

    # Check dataset profile
    status, ds_profile, _ = get_json(f"{BACKEND_URL}/api/v1/datasets/{dataset_id}/profile", token=token_a)
    print(f"-> Profil dataset: HTTP {status}, rows: {ds_profile.get('row_count')}, cols: {ds_profile.get('column_count')}")
    assert status == 200
    assert ds_profile.get("row_count") == 3

    # Check export download
    status, exp_bytes, _ = get_bytes(f"{BACKEND_URL}/api/v1/datasets/{dataset_id}/export/csv", token=token_a)
    print(f"-> Téléchargement export nettoyé: HTTP {status}, bytes: {len(exp_bytes)}")
    assert status == 200 and len(exp_bytes) > 0

    # Cross-tenant check: Tenant B cannot access Tenant A's dataset
    status, _, _ = get_json(f"{BACKEND_URL}/api/v1/datasets/{dataset_id}", token=token_b)
    print(f"-> Tenant B tentative d'accès au dataset de A: HTTP {status} (attendu: 404)")
    assert status == 404

    # Delete dataset
    status, _, _ = delete_req(f"{BACKEND_URL}/api/v1/datasets/{dataset_id}", token=token_a)
    print(f"-> Suppression dataset test: HTTP {status} (attendu: 204)")
    assert status == 204

    # Verify dataset is gone
    status, _, _ = get_json(f"{BACKEND_URL}/api/v1/datasets/{dataset_id}", token=token_a)
    assert status == 404, "Deleted dataset should return 404"
    print("-> Dataset bien supprimé des vues et des artefacts.")
    results.append(("Import, Nettoyage, Téléchargement & Suppression Dataset", "PASS"))

    print("\n" + "=" * 65)
    print("ALL INTEGRATION SCENARIOS COMPLETED SUCCESSFULLY!")
    print("=" * 65)
    for name, outcome in results:
        print(f"  [ {outcome} ] {name}")

if __name__ == "__main__":
    main()
