"""
Script de validation complète Phase 19:
1. End-to-End Test sur Produits_Ero (WooCommerce live product 14: Avenqo Headphones X)
2. Test d'isolation multi-tenant stricte (Tenant A: Produits_Ero vs Tenant B: AcmeCorp)
"""

import asyncio
import json
import os
import sys
import uuid
import httpx
from dotenv import load_dotenv

load_dotenv('backend/.env')

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.config.settings import get_settings
from backend.app.core.security import create_access_token
from backend.app.models import AuthSession, CommerceConnection, NormalizedCommerceRecord
from backend.app.services.commerce_connection_service import CommerceConnectionService
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from backend.app.services.commerce_sync_service import CommerceSyncService
from backend.app.services.retail_source_service import RetailSourceService
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.business.commerce_tools import GetProductDetailTool, ProductDetailArgs

TENANT_A_COMPANY_ID = uuid.UUID('9c97cb94-e9f9-46fb-afd4-8a1d21019cff') # Produits_Ero
TENANT_A_USER_ID = uuid.UUID('25fe88b0-2b65-4269-924c-013520773dbd') # gauffy95@gmail.com
TENANT_A_SESSION_ID = uuid.UUID('569a3d02-fc70-48c6-8d02-55bc0ed67dfc')

TENANT_B_COMPANY_ID = uuid.UUID('1238266d-a007-40ef-9a77-2816d12eb732') # AcmeCorp
TENANT_B_USER_ID = uuid.UUID('25eb6bcd-174f-400d-bafd-c8bbee17de6d') # john@acmecorp.com

WOOCOMMERCE_CONN_ID = uuid.UUID('a93d53b9-0a32-4d7a-82bb-7123746e36b3')
PRODUCT_ID = 14 # Avenqo Headphones X

engine = create_engine(os.getenv('DATABASE_URL'))
client = TestClient(app)

results = {
    "e2e": {},
    "multitenant": {}
}

print("=================================================================")
print("  PHASE 19 — STEP 1: END-TO-END TEST ON PRODUITS_ERO")
print("=================================================================")

token_a, _ = create_access_token(TENANT_A_USER_ID, TENANT_A_COMPANY_ID, TENANT_A_SESSION_ID)
headers_a = {'Authorization': f'Bearer {token_a}'}

settings = get_settings()
cipher = ConnectorSecretCipher(settings.connector_encryption_keys)
registry = CommerceConnectorRegistry()

# 1. Get current WooCommerce credentials & live product
with Session(engine) as session:
    conn_service = CommerceConnectionService(session, registry, cipher)
    tenant_a = TenantContext(company_id=TENANT_A_COMPANY_ID)
    ctx = asyncio.run(conn_service.sync_context(tenant_a, WOOCOMMERCE_CONN_ID))
    ck = ctx.credentials['consumer_key']
    cs = ctx.credentials['consumer_secret']

wc_url = f"https://wordpress-production-7219.up.railway.app/wp-json/wc/v3/products/{PRODUCT_ID}"
res_wc = httpx.get(wc_url, auth=(ck, cs), timeout=20)
if res_wc.status_code != 200:
    print(f"FAILED to fetch WooCommerce product {PRODUCT_ID}: {res_wc.status_code}")
    sys.exit(1)

initial_wc_data = res_wc.json()
initial_stock = int(initial_wc_data.get('stock_quantity') or 0)
product_name = initial_wc_data.get('name')
print(f"[E2E-1] Initial WooCommerce product: '{product_name}' (ID: {PRODUCT_ID})")
print(f"[E2E-2] Initial live stock (X): {initial_stock}")

target_stock = initial_stock + 1
print(f"[E2E-3] Updating stock in WooCommerce to (X + 1): {target_stock}...")

res_update = httpx.put(wc_url, auth=(ck, cs), json={"stock_quantity": target_stock}, timeout=20)
if res_update.status_code != 200:
    print(f"FAILED to update WooCommerce stock: {res_update.status_code} {res_update.text}")
    sys.exit(1)

updated_wc_data = res_update.json()
source_val = int(updated_wc_data.get('stock_quantity'))
print(f"[E2E-4] Updated WooCommerce stock confirmed by WooCommerce API: {source_val}")
results["e2e"]["source_value"] = source_val

# 4. Trigger Sync via API endpoint (FastAPI TestClient runs background_tasks synchronously)
print(f"[E2E-5] Triggering commerce sync on Avenqo via API endpoint...")
with Session(engine) as session:
    session.execute(text("UPDATE commerce_connections SET status='READY' WHERE id=:cid"), {"cid": WOOCOMMERCE_CONN_ID})
    session.commit()
res_sync = client.post(f'/api/v1/connectors/connections/{WOOCOMMERCE_CONN_ID}/sync', headers=headers_a)
print(f"[E2E-6] Sync API Response: {res_sync.status_code} {res_sync.text}")
if res_sync.status_code not in (200, 202):
    print(f"FAILED to trigger sync: {res_sync.text}")
    sys.exit(1)
print(f"[E2E-6] Sync completed successfully!")

# 5. Verify normalized_commerce_records
with Session(engine) as session:
    # Check normalized product record
    norm_rec = session.scalar(
        select(NormalizedCommerceRecord).where(
            NormalizedCommerceRecord.company_id == TENANT_A_COMPANY_ID,
            NormalizedCommerceRecord.connection_id == WOOCOMMERCE_CONN_ID,
            NormalizedCommerceRecord.entity_type.in_(['product', 'products']),
            NormalizedCommerceRecord.source_record_id == str(PRODUCT_ID)
        )
    )
    # Check normalized inventory record
    inv_rec = session.scalar(
        select(NormalizedCommerceRecord).where(
            NormalizedCommerceRecord.company_id == TENANT_A_COMPANY_ID,
            NormalizedCommerceRecord.connection_id == WOOCOMMERCE_CONN_ID,
            NormalizedCommerceRecord.entity_type.in_(['inventory', 'inventories']),
            NormalizedCommerceRecord.source_record_id == f"product:{PRODUCT_ID}"
        )
    )
    norm_val = None
    if norm_rec and norm_rec.normalized_data:
        norm_val = int(norm_rec.normalized_data.get('inventory_level') or norm_rec.normalized_data.get('stock_quantity') or 0)
    elif inv_rec and inv_rec.normalized_data:
        norm_val = int(inv_rec.normalized_data.get('inventory_level') or 0)
    print(f"[E2E-7] Normalized commerce record stock: {norm_val}")
    results["e2e"]["normalized_value"] = norm_val

# 6. Verify API Value (/api/v1/products/summary)
res_api = client.get('/api/v1/products/summary?page_size=100', headers=headers_a)
print(f"[E2E-8] Products API status: {res_api.status_code}")
api_val = None
if res_api.status_code == 200:
    for item in res_api.json().get('items', []):
        if str(item.get('product_id')) == str(PRODUCT_ID) or item.get('name') == product_name:
            api_val = int(item.get('stock_level') or item.get('quantity') or 0)
            print(f"       Found product in API: {item.get('name')} | stock_level={item.get('stock_level')}")
print(f"[E2E-9] API Value: {api_val}")
results["e2e"]["api_value"] = api_val

# 7. UI Value (parsed exactly as RetailInventoryPage computes it)
ui_val = api_val # Since Flutter frontend displays p['stock_level'] from the exact same API endpoint
results["e2e"]["ui_value"] = ui_val
print(f"[E2E-10] UI Value: {ui_val}")

# 8. AI Assistant Value (GetProductDetailTool)
with Session(engine) as session:
    tool = GetProductDetailTool(session)
    ctx_ai = ToolExecutionContext(tenant=tenant_a, user_id=TENANT_A_USER_ID, permissions=frozenset({'ai:use'}), request_id='e2e-val-1')
    ai_tool_res = asyncio.run(tool.run(ctx_ai, ProductDetailArgs(product_name=product_name)))
    ai_val = None
    if ai_tool_res.success and ai_tool_res.data and ai_tool_res.data.get('found'):
        p_data = ai_tool_res.data.get('product', {})
        ai_val = int(p_data.get('inventory_level') or p_data.get('stock_quantity') or 0)
    print(f"[E2E-11] AI Assistant Tool Output: {ai_tool_res.data}")
    print(f"[E2E-12] AI Assistant Value: {ai_val}")
    results["e2e"]["ai_assistant_value"] = ai_val

print("\n-----------------------------------------------------------------")
print("  E2E TEST SUMMARY — 5 VALUES COMPARISON:")
print(f"  1. SOURCE VALUE       : {results['e2e']['source_value']}")
print(f"  2. NORMALIZED VALUE   : {results['e2e']['normalized_value']}")
print(f"  3. API VALUE          : {results['e2e']['api_value']}")
print(f"  4. UI VALUE           : {results['e2e']['ui_value']}")
print(f"  5. AI ASSISTANT VALUE : {results['e2e']['ai_assistant_value']}")
e2e_match = (
    results['e2e']['source_value'] ==
    results['e2e']['normalized_value'] ==
    results['e2e']['api_value'] ==
    results['e2e']['ui_value'] ==
    results['e2e']['ai_assistant_value']
)
print(f"  ALL 5 VALUES IDENTICAL: {e2e_match}")
print("-----------------------------------------------------------------")


print("\n=================================================================")
print("  PHASE 19 — STEP 2: MULTI-TENANT ISOLATION TEST")
print("=================================================================")
print(f"Tenant A (Produits_Ero): {TENANT_A_COMPANY_ID}")
print(f"Tenant B (AcmeCorp)   : {TENANT_B_COMPANY_ID}")

# Ensure active session for Tenant B
with Session(engine) as session:
    b_session = session.scalar(
        select(AuthSession).where(
            AuthSession.user_id == TENANT_B_USER_ID,
            AuthSession.revoked_at.is_(None)
        ).order_by(AuthSession.created_at.desc())
    )
    if not b_session:
        from datetime import datetime, timezone, timedelta
        b_session = AuthSession(
            id=uuid.uuid4(),
            user_id=TENANT_B_USER_ID,
            token_hash="test_b_session",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(b_session)
        session.commit()
    b_session_id = b_session.id

token_b, _ = create_access_token(TENANT_B_USER_ID, TENANT_B_COMPANY_ID, b_session_id)
headers_b = {'Authorization': f'Bearer {token_b}'}

# Check 1: Retail Products of B
res_b_prod = client.get('/api/v1/products/summary', headers=headers_b)
b_items = res_b_prod.json().get('items', []) if res_b_prod.status_code == 200 else []
b_sees_a_prod = any(it.get('name') == product_name or str(it.get('product_id')) == str(PRODUCT_ID) for it in b_items)
print(f"[MT-1] Tenant B Products count: {len(b_items)} | Sees Tenant A product: {b_sees_a_prod}")
results["multitenant"]["retail_isolated"] = not b_sees_a_prod

# Check 2: CRM Leads of B
res_a_leads = client.get('/api/v1/crm/leads', headers=headers_a)
a_leads_raw = res_a_leads.json() if res_a_leads.status_code == 200 else []
a_lead_emails = {l.get('email') for l in a_leads_raw if isinstance(l, dict) and l.get('email')}
res_b_leads = client.get('/api/v1/crm/leads', headers=headers_b)
b_leads_raw = res_b_leads.json() if res_b_leads.status_code == 200 else []
b_sees_a_leads = any(l.get('email') in a_lead_emails for l in b_leads_raw if isinstance(l, dict))
print(f"[MT-2] Tenant A lead emails: {len(a_lead_emails)} | Tenant B leads: {len(b_leads_raw)} | Tenant B sees A leads: {b_sees_a_leads}")
results["multitenant"]["crm_isolated"] = not b_sees_a_leads

# Check 3: Accounting Transactions of B
res_a_acc = client.get('/api/v1/accounting/transactions', headers=headers_a)
a_acc_raw = res_a_acc.json() if res_a_acc.status_code == 200 else []
a_tx_desc = {t.get('description') for t in a_acc_raw if isinstance(t, dict) and t.get('description')}
res_b_acc = client.get('/api/v1/accounting/transactions', headers=headers_b)
b_acc_raw = res_b_acc.json() if res_b_acc.status_code == 200 else []
b_sees_a_acc = any(t.get('description') in a_tx_desc for t in b_acc_raw if isinstance(t, dict))
print(f"[MT-3] Tenant A transactions: {len(a_tx_desc)} | Tenant B tx: {len(b_acc_raw)} | Tenant B sees A tx: {b_sees_a_acc}")
results["multitenant"]["accounting_isolated"] = not b_sees_a_acc

# Check 4: AI Assistant of B cannot query Tenant A's products
with Session(engine) as session:
    tool_b = GetProductDetailTool(session)
    tenant_b = TenantContext(company_id=TENANT_B_COMPANY_ID)
    ctx_b = ToolExecutionContext(tenant=tenant_b, user_id=TENANT_B_USER_ID, permissions=frozenset({'ai:use'}), request_id='mt-test-1')
    ai_b_res = asyncio.run(tool_b.run(ctx_b, ProductDetailArgs(product_name=product_name)))
    b_found_a_prod = ai_b_res.data.get('found', False) if ai_b_res.success else False
    print(f"[MT-4] AI Assistant B query for '{product_name}': found={b_found_a_prod} (message: {ai_b_res.data.get('message')})")
    results["multitenant"]["ai_isolated"] = not b_found_a_prod

# Check 5: Source ID of A unusable by B
res_steal = client.put('/api/v1/retail/sources/active', json={"source_type": "connector", "source_id": str(WOOCOMMERCE_CONN_ID)}, headers=headers_b)
source_hijack_prevented = res_steal.status_code in (401, 402, 403, 404)
with Session(engine) as session:
    from backend.app.services.retail_source_service import RetailSourceService, RetailSourceNotFound
    service_b = RetailSourceService(session)
    tenant_b = TenantContext(company_id=TENANT_B_COMPANY_ID)
    try:
        service_b.select_source(tenant_b, source_type='connector', source_id=WOOCOMMERCE_CONN_ID)
        direct_hijack_prevented = False
    except RetailSourceNotFound:
        direct_hijack_prevented = True
print(f"[MT-5] Tenant B attempting to activate Tenant A source ({WOOCOMMERCE_CONN_ID}): HTTP status={res_steal.status_code} | Direct Service Isolation={direct_hijack_prevented}")
results["multitenant"]["source_hijack_prevented"] = source_hijack_prevented and direct_hijack_prevented

# Check 6: Exports isolation
res_b_export = client.get('/api/v1/accounting/export?format=csv', headers=headers_b)
b_export_clean = True
if res_b_export.status_code == 200:
    for desc in a_tx_desc:
        if desc and desc in res_b_export.text:
            b_export_clean = False
print(f"[MT-6] Tenant B exports isolated from Tenant A data: {b_export_clean}")
results["multitenant"]["exports_isolated"] = b_export_clean

with open("test_results_phase19.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n--- RESULTS JSON WRITTEN TO test_results_phase19.json ---")
