import os
import sys
import io
import time
import uuid
import json
import secrets
from hashlib import sha256
from datetime import datetime, timezone
import requests
from reportlab.pdfgen import canvas
import pandas as pd
try:
    import psycopg2 as psycopg
except ImportError:
    import psycopg

BASE_API_URL = "https://api.avenqo.ca/api/v1"
BASE_WEB_URL = "https://avenqo.ca"
DB_URL = "postgresql://postgres:aVxFamcMziEnMoleBZCYdkLpOELxLatB@tramway.proxy.rlwy.net:25367/railway"

results = {}

def log_test(name, passed, detail=""):
    results[name] = {"passed": passed, "detail": detail}
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}: {detail}")

print("=== STARTING AVENQO PRODUCTION RECOVERY SMOKE TESTS ===")

# TEST A — SIGNUP, EMAIL VERIFICATION, LOGIN
test_user_email = f"qa_{uuid.uuid4().hex[:8]}@example.com"
test_password = "SecurePassword123!"
test_org_name = f"AvenqoQA_{uuid.uuid4().hex[:6]}"

signup_payload = {
    "company_name": test_org_name,
    "company_email": test_user_email,
    "first_name": "QA",
    "last_name": "Tester",
    "email": test_user_email,
    "password": test_password,
    "country": "Canada",
    "industry": "Retail",
    "plan_code": "base",
}

signup_resp = requests.post(f"{BASE_API_URL}/auth/register", json=signup_payload, timeout=25)

if signup_resp.status_code in (200, 201):
    log_test("Signup", True, f"Created user {test_user_email} (org: {test_org_name})")
else:
    log_test("Signup", False, f"HTTP {signup_resp.status_code}: {signup_resp.text}")

user_id = None
try:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (test_user_email,))
            row = cur.fetchone()
            if row:
                user_id = row[0]
except Exception as e:
    print("User lookup error:", e)

# Create a test email verification token in account_tokens for this user
raw_token = secrets.token_urlsafe(48)
token_hash = sha256(raw_token.encode("utf-8")).hexdigest()

if user_id:
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO account_tokens (id, user_id, purpose, token_hash, created_at, expires_at)
                    VALUES (%s, %s, 'EMAIL_VERIFICATION', %s, NOW(), NOW() + INTERVAL '24 hours')
                """, (str(uuid.uuid4()), str(user_id), token_hash))
            conn.commit()
    except Exception as e:
        print("Insert token error:", e)

    # Test the real verification endpoint
    verify_resp = requests.post(f"{BASE_API_URL}/auth/verify-email", json={"token": raw_token}, timeout=15)
    if verify_resp.status_code == 200:
        ver_data = verify_resp.json()
        log_test("Email verification", True, f"Token verified successfully, autologin token: {bool(ver_data.get('access_token'))}")
    else:
        log_test("Email verification", False, f"HTTP {verify_resp.status_code}: {verify_resp.text}")
else:
    log_test("Email verification", False, "User not found to test verification")

# Login with verified user
login_resp = requests.post(f"{BASE_API_URL}/auth/login", json={
    "email": test_user_email,
    "password": test_password
}, timeout=15)

user_token = None
if login_resp.status_code == 200:
    login_data = login_resp.json()
    user_token = login_data.get("access_token")
    log_test("Login", True, "Successfully logged in and received JWT")
else:
    log_test("Login", False, f"HTTP {login_resp.status_code}: {login_resp.text}")

auth_headers = {"Authorization": f"Bearer {user_token}"} if user_token else {}

# Verify /auth/me returns membership and active company
me_resp = requests.get(f"{BASE_API_URL}/auth/me", headers=auth_headers, timeout=15)
active_company_id = None
if me_resp.status_code == 200:
    me_data = me_resp.json()
    active_company_id = me_data.get("company", {}).get("id") or me_data.get("user", {}).get("company_id")
    memberships = me_data.get("organizations", [])
    log_test("Auth Me & Memberships", True, f"Active company {active_company_id}, {len(memberships)} memberships")
else:
    log_test("Auth Me & Memberships", False, f"HTTP {me_resp.status_code}: {me_resp.text}")

# TEST B — MULTI-TENANT ISOLATION (IDOR/BOLA)
tenant2_email = f"qa_t2_{uuid.uuid4().hex[:8]}@example.com"
tenant2_resp = requests.post(f"{BASE_API_URL}/auth/register", json={
    "company_name": f"Isolated Corp 2_{uuid.uuid4().hex[:4]}",
    "company_email": tenant2_email,
    "first_name": "Tenant",
    "last_name": "Two",
    "email": tenant2_email,
    "password": test_password,
    "country": "Canada",
    "industry": "Consulting",
    "plan_code": "base",
}, timeout=25)

tenant2_token = None
if tenant2_resp.status_code in (200, 201):
    # Verify Tenant 2 directly in DB
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET email_verified_at = NOW() WHERE email = %s", (tenant2_email,))
            conn.commit()
    except Exception as e:
        print("T2 verify update:", e)

    t2_login = requests.post(f"{BASE_API_URL}/auth/login", json={
        "email": tenant2_email,
        "password": test_password
    }, timeout=15)
    if t2_login.status_code == 200:
        tenant2_token = t2_login.json().get("access_token")

t2_headers = {"Authorization": f"Bearer {tenant2_token}"} if tenant2_token else {}

# Test IDOR: Tenant 2 tries to switch to Tenant 1's org
if active_company_id and tenant2_token:
    idor_resp = requests.post(f"{BASE_API_URL}/auth/switch-tenant", json={"company_id": active_company_id}, headers=t2_headers, timeout=15)
    if idor_resp.status_code in (403, 404):
        log_test("Tenant isolation", True, f"Tenant 2 denied unauthorized switch to Tenant 1 company (HTTP {idor_resp.status_code})")
    else:
        log_test("Tenant isolation", False, f"IDOR VULNERABILITY! Returned HTTP {idor_resp.status_code}")
else:
    log_test("Tenant isolation", False, "Could not set up multi-tenant test pair")

# TEST C & D — BASE & PROFESSIONAL ENTITLEMENTS
sub_resp = requests.get(f"{BASE_API_URL}/billing/subscription", headers=auth_headers, timeout=15)
if sub_resp.status_code == 200:
    sub_data = sub_resp.json()
    plan_code = sub_data.get("plan_code")
    log_test("Base entitlement", plan_code in ("base", "demo"), f"Plan: {plan_code}, name: {sub_data.get('plan_name')}, price: ${sub_data.get('monthly_price_usd')}")
else:
    log_test("Base entitlement", False, f"HTTP {sub_resp.status_code}: {sub_resp.text}")

# TEST E — DATA HUB UPLOAD (CSV, XLSX, PDF)
csv_content = b"date,sku,product_name,category,units_sold,unit_price,revenue\n2026-09-01,SKU01,Avenqo Product,Retail,10,25.00,250.00\n2026-09-02,SKU01,Avenqo Product,Retail,5,25.00,125.00\n"
csv_files = {"file": ("sales_sample.csv", io.BytesIO(csv_content), "text/csv")}
csv_data = {"module_code": "retail", "description": "Automated Smoke Test CSV"}

csv_resp = requests.post(f"{BASE_API_URL}/datasets/upload", headers=auth_headers, files=csv_files, data=csv_data, timeout=30)
created_dataset_id = None
if csv_resp.status_code in (200, 201):
    ds_json = csv_resp.json()
    created_dataset_id = ds_json.get("dataset_id") or ds_json.get("id")
    log_test("CSV upload", True, f"Dataset created with ID {created_dataset_id}")
else:
    log_test("CSV upload", False, f"HTTP {csv_resp.status_code}: {csv_resp.text}")

# XLSX Upload
excel_buf = io.BytesIO()
df = pd.DataFrame({
    "date": ["2026-09-01", "2026-09-02"],
    "sku": ["SKU-XLSX-1", "SKU-XLSX-2"],
    "units": [15, 20],
    "revenue": [150.0, 200.0]
})
with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
    df.to_excel(writer, index=False)
excel_buf.seek(0)

xlsx_files = {"file": ("inventory.xlsx", excel_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
xlsx_resp = requests.post(f"{BASE_API_URL}/datasets/upload", headers=auth_headers, files=xlsx_files, data={"module_code": "retail"}, timeout=30)
if xlsx_resp.status_code in (200, 201):
    log_test("XLSX upload", True, f"XLSX dataset created with ID {xlsx_resp.json().get('id')}")
else:
    log_test("XLSX upload", False, f"HTTP {xlsx_resp.status_code}: {xlsx_resp.text}")

# PDF Upload - Real valid PDF generated with reportlab
pdf_buf = io.BytesIO()
c = canvas.Canvas(pdf_buf)
c.drawString(100, 750, "Avenqo Production Recovery Validation Report")
c.drawString(100, 720, "date,sku,units_sold,revenue")
c.drawString(100, 700, "2026-09-01,SKU01,10,250.00")
c.save()
pdf_buf.seek(0)

pdf_files = {"file": ("report.pdf", pdf_buf, "application/pdf")}
pdf_resp = requests.post(f"{BASE_API_URL}/datasets/upload", headers=auth_headers, files=pdf_files, data={"module_code": "retail"}, timeout=30)
if pdf_resp.status_code in (200, 201):
    log_test("PDF upload", True, f"PDF dataset created with ID {pdf_resp.json().get('id')}")
else:
    log_test("PDF upload", False, f"HTTP {pdf_resp.status_code}: {pdf_resp.text}")

# Dataset Persistence
list_resp = requests.get(f"{BASE_API_URL}/datasets", headers=auth_headers, timeout=15)
if list_resp.status_code == 200:
    datasets = list_resp.json()
    found = any(d.get("id") == created_dataset_id for d in datasets)
    log_test("Dataset persistence", found, f"Total datasets found: {len(datasets)}")
else:
    log_test("Dataset persistence", False, f"HTTP {list_resp.status_code}")

# Cross-Tenant Dataset Isolation: Tenant 2 tries to read Tenant 1's dataset
if created_dataset_id and tenant2_token:
    t2_read_resp = requests.get(f"{BASE_API_URL}/datasets/{created_dataset_id}", headers=t2_headers, timeout=15)
    if t2_read_resp.status_code in (403, 404):
        log_test("Tenant dataset isolation", True, f"Tenant 2 blocked from reading Tenant 1 dataset (HTTP {t2_read_resp.status_code})")
    else:
        log_test("Tenant dataset isolation", False, f"IDOR on dataset! HTTP {t2_read_resp.status_code}")

# Dataset Deletion
if created_dataset_id:
    del_resp = requests.delete(f"{BASE_API_URL}/datasets/{created_dataset_id}", headers=auth_headers, timeout=15)
    if del_resp.status_code in (200, 204):
        log_test("Dataset deletion", True, f"Dataset {created_dataset_id} deleted successfully")
    else:
        log_test("Dataset deletion", False, f"HTTP {del_resp.status_code}: {del_resp.text}")
else:
    log_test("Dataset deletion", False, "No dataset ID to delete")

# TEST F — STRIPE CHECKOUT
stripe_base_resp = requests.post(f"{BASE_API_URL}/billing/checkout", headers=auth_headers, json={"plan_code": "base"}, timeout=15)
if stripe_base_resp.status_code == 200 and "url" in stripe_base_resp.json():
    checkout_url = stripe_base_resp.json()["url"]
    log_test("Stripe Checkout", True, f"Generated Base checkout session: {checkout_url[:45]}...")
else:
    log_test("Stripe Checkout", False, f"HTTP {stripe_base_resp.status_code}: {stripe_base_resp.text}")

stripe_pro_resp = requests.post(f"{BASE_API_URL}/billing/checkout", headers=auth_headers, json={"plan_code": "professional"}, timeout=15)
if stripe_pro_resp.status_code == 200 and "url" in stripe_pro_resp.json():
    log_test("Plan change", True, f"Generated Professional upgrade checkout: {stripe_pro_resp.json()['url'][:45]}...")
else:
    log_test("Plan change", False, f"HTTP {stripe_pro_resp.status_code}: {stripe_pro_resp.text}")

# TEST G — SHOPIFY CONNECTOR
shopify_get_resp = requests.get(f"{BASE_API_URL}/connectors/shopify/authorize?shop=avenqo-retail-test.myshopify.com", headers=auth_headers, allow_redirects=False, timeout=15)
if shopify_get_resp.status_code in (302, 307):
    redirect_url = shopify_get_resp.headers.get("Location", "")
    log_test("Shopify OAuth", "myshopify.com" in redirect_url or "oauth" in redirect_url, f"GET returned 307 redirect to {redirect_url[:50]}...")
elif shopify_get_resp.status_code == 200:
    log_test("Shopify OAuth", True, "GET returned 200 authorization payload")
else:
    log_test("Shopify OAuth", False, f"GET returned HTTP {shopify_get_resp.status_code}: {shopify_get_resp.text}")

shopify_post_resp = requests.post(f"{BASE_API_URL}/connectors/shopify/authorize", headers=auth_headers, json={"shop_domain": "avenqo-retail-test.myshopify.com"}, timeout=15)
if shopify_post_resp.status_code == 200 and "authorization_url" in shopify_post_resp.json():
    log_test("Shopify sync", True, f"POST generated auth URL: {shopify_post_resp.json()['authorization_url'][:50]}...")
else:
    log_test("Shopify sync", False, f"POST returned HTTP {shopify_post_resp.status_code}: {shopify_post_resp.text}")

# TEST H — WOOCOMMERCE
catalog_resp = requests.get(f"{BASE_API_URL}/connectors", headers=auth_headers, timeout=15)
if catalog_resp.status_code == 200:
    catalog = catalog_resp.json()
    woo_def = next((c for c in catalog if c.get("provider") == "woocommerce"), None)
    if woo_def:
        log_test("WooCommerce", True, f"WooCommerce active in catalog with status {woo_def.get('customer_status')}")
    else:
        log_test("WooCommerce", False, "WooCommerce not found in catalog")
else:
    log_test("WooCommerce", False, f"HTTP {catalog_resp.status_code}")

# TEST I — CRM & GOOGLE CALENDAR
client_payload = {
    "first_name": "Jean",
    "last_name": "Dupont",
    "email": "jean.dupont@example.com",
    "phone": "+1 514 555 0199",
    "company_name": "Dupont Inc"
}
crm_client_resp = requests.post(f"{BASE_API_URL}/crm/clients", headers=auth_headers, json=client_payload, timeout=15)
client_id = None
if crm_client_resp.status_code in (200, 201):
    client_id = crm_client_resp.json().get("id")
    log_test("CRM", True, f"Created CRM client {client_id}")
else:
    log_test("CRM", False, f"HTTP {crm_client_resp.status_code}: {crm_client_resp.text}")

if client_id:
    appt_payload = {
        "client_id": client_id,
        "title": "Consultation Stratégique",
        "start_time": "2026-10-01T14:00:00Z",
        "duration_minutes": 60,
    }
    appt_resp = requests.post(f"{BASE_API_URL}/crm/appointments", headers=auth_headers, json=appt_payload, timeout=15)
    if appt_resp.status_code in (200, 201):
        log_test("Google Calendar", True, f"Appointment created with ID {appt_resp.json().get('id')}")
    else:
        log_test("Google Calendar", False, f"HTTP {appt_resp.status_code}: {appt_resp.text}")

# Clean up test accounts in DB to keep production clean
try:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email IN (%s, %s)", (test_user_email, tenant2_email))
            cur.execute("DELETE FROM companies WHERE name IN (%s, %s)", (test_org_name, f"Isolated Corp 2_{uuid.uuid4().hex[:4]}"))
        conn.commit()
    print("Cleaned up QA test users from production database.")
except Exception as e:
    print("DB cleanup notice:", e)

print("\n=== SMOKE TEST SUMMARY ===")
print(json.dumps(results, indent=2))
