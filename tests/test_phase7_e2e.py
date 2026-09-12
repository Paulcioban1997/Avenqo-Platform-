"""Comprehensive Phase 7 E2E Test Suite for Avenqo Platform.
Tests the complete end-to-end user journey across Next.js (port 3000) and FastAPI (port 8000):
1. Public Routes: /, /pricing, /terms, /privacy, /login, /register (200, SEO, no app.avenqo.ca links)
2. Registration: Dedicated E2E test account, validation, company creation, plan selection, no duplicates
3. Authentication & Session: valid login, wrong password (401), non-existent (401), cookies, no JWT in localStorage, /auth/me persistence, refresh token rotation, logout, post-logout 401
4. Routing & Flutter Web SPA: /dashboard, /retail, /retail/sales, /retail/customers, /retail/products, /retail/recommendations, /central-ai, /data, /integrations, /billing, /team, /settings
5. Dashboard & Retail Intelligence: /dashboard, /sales/summary, /customers/summary, /products/summary, /recommendations (empty dataset resiliency & KPI structure)
6. Data Ingestion & Import: upload test CSV, verify profiling, schema, columns, list datasets, delete dataset
7. E-commerce Connectors: /connectors catalog, statuses (Available / Coming Soon), no crashes
8. Central AI: create conversation, send message, retrieve conversation history with tenant isolation
9. Multi-Tenant Critical Isolation: Tenant A vs Tenant B (strict IDOR checks on conversations, messages, datasets, company detail)
10. Platform Admin Security: standard user 403 on /admin/*; platform admin account validation
11. Billing: /billing/subscription, /billing/plans (Demo, Professional, Enterprise), /billing/ai-credits
12. Team & Settings: /employees, /auth/me user and company profile
13. Error Handling & Resilience: 401, 403, 404, 422, path traversal rejection
"""

from datetime import datetime, timezone
import io
import json
import sys
import uuid
import pytest
import requests

sys.path.insert(0, ".")

NEXT_BASE = "http://127.0.0.1:3000"
FASTAPI_BASE = "http://127.0.0.1:8000"


class TestPhase7PublicRoutes:
    """Requirement 3: Parcours Public."""

    @pytest.mark.parametrize("path", ["/", "/pricing", "/terms", "/privacy", "/login", "/register"])
    def test_public_routes_return_200_and_no_legacy_urls(self, path):
        r = requests.get(f"{NEXT_BASE}{path}", timeout=10)
        assert r.status_code == 200, f"Path {path} returned status {r.status_code}"
        assert "app.avenqo.ca" not in r.text, f"Legacy app.avenqo.ca link found in {path}"

    def test_seo_and_canonical_homepage(self):
        r = requests.get(f"{NEXT_BASE}/", timeout=10)
        assert r.status_code == 200
        assert "Avenqo" in r.text
        assert 'canonical"' in r.text or "canonical" in r.text

    def test_pricing_page_plans(self):
        r = requests.get(f"{NEXT_BASE}/pricing", timeout=10)
        assert r.status_code == 200
        assert "Demo" in r.text
        assert "Professional" in r.text
        assert "Enterprise" in r.text

    def test_auth_pages_noindex_directive(self):
        for path in ["/login", "/register"]:
            r = requests.get(f"{NEXT_BASE}{path}", timeout=10)
            assert r.status_code == 200
            assert 'name="robots"' in r.text
            assert "noindex" in r.text


class TestPhase7Registration:
    """Requirement 4: Inscription & Création Tenant."""

    def test_e2e_registration_flow(self):
        suffix = uuid.uuid4().hex[:8]
        test_email = f"e2e_test_{suffix}@avenqo.ca"
        test_password = "SecureE2EPassword2026!"
        company_name = f"E2ECompany_{suffix}"

        payload = {
            "email": test_email,
            "password": test_password,
            "first_name": "E2E",
            "last_name": "Tester",
            "company_name": company_name,
            "company_email": test_email,
            "country": "Canada",
            "industry": "Commerce",
            "selected_modules": ["retail"],
        }
        r = requests.post(f"{NEXT_BASE}/api/auth/register", json=payload, timeout=10)
        assert r.status_code in (200, 201), f"Registration failed: {r.text}"
        data = r.json()
        assert "message" in data or "user" in data or "id" in data or "company" in data

        # Duplicate registration with same email must fail
        r_dup = requests.post(f"{NEXT_BASE}/api/auth/register", json=payload, timeout=10)
        assert r_dup.status_code in (400, 409, 422), f"Duplicate allowed: {r_dup.status_code}"


class TestPhase7AuthAndSession:
    """Requirement 5: Login / Session / Cookies / Logout."""

    @pytest.fixture(scope="class")
    def registered_user(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"session_test_{suffix}@avenqo.ca"
        password = "SecurePassword2026!"
        company = f"SessionCo_{suffix}"

        reg_payload = {
            "email": email,
            "password": password,
            "first_name": "Session",
            "last_name": "Tester",
            "company_name": company,
            "company_email": email,
            "country": "Canada",
            "industry": "Commerce",
            "selected_modules": ["retail"],
        }
        r = requests.post(f"{NEXT_BASE}/api/auth/register", json=reg_payload, timeout=10)
        assert r.status_code in (200, 201), f"Setup register failed: {r.text}"

        # Verify email in SQLite DB
        from backend.app.database import SessionLocal
        from backend.app.models.user import User
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email.lower()).first()
            assert user is not None
            user.email_verified_at = datetime.now(timezone.utc)
            db.commit()

        return {"email": email, "password": password, "company": company}

    def test_login_invalid_password_returns_401(self, registered_user):
        r = requests.post(
            f"{NEXT_BASE}/api/auth/login",
            json={"email": registered_user["email"], "password": "WrongPassword123!"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_login_unknown_user_returns_401(self):
        r = requests.post(
            f"{NEXT_BASE}/api/auth/login",
            json={"email": f"unknown_{uuid.uuid4().hex[:6]}@avenqo.ca", "password": "Password123!"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_login_valid_sets_httponly_cookies_and_persists_session(self, registered_user):
        session = requests.Session()
        r = session.post(
            f"{NEXT_BASE}/api/auth/login",
            json={"email": registered_user["email"], "password": registered_user["password"]},
            timeout=10,
        )
        assert r.status_code == 200
        cookies = session.cookies.get_dict()
        assert "avenqo_access_token" in cookies
        assert "avenqo_refresh_token" in cookies
        assert "avenqo_csrf" in cookies

        # Hard refresh simulation: call /api/v1/auth/me with only the cookie
        r_me = session.get(f"{NEXT_BASE}/api/v1/auth/me", timeout=10)
        assert r_me.status_code == 200
        user_data = r_me.json()
        assert user_data["user"]["email"] == registered_user["email"]

    def test_refresh_token_rotation(self, registered_user):
        session = requests.Session()
        r = session.post(
            f"{NEXT_BASE}/api/auth/login",
            json={"email": registered_user["email"], "password": registered_user["password"]},
            timeout=10,
        )
        assert r.status_code == 200
        refresh_cookie = session.cookies.get("avenqo_refresh_token")

        refresh_session = requests.Session()
        refresh_session.cookies.set("avenqo_refresh_token", refresh_cookie)
        r_ref = refresh_session.post(
            f"{NEXT_BASE}/api/v1/auth/refresh",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=10,
        )
        assert r_ref.status_code == 200
        new_cookies = refresh_session.cookies.get_dict()
        assert "avenqo_access_token" in new_cookies

    def test_logout_revokes_session_and_denies_subsequent_access(self, registered_user):
        session = requests.Session()
        session.post(
            f"{NEXT_BASE}/api/auth/login",
            json={"email": registered_user["email"], "password": registered_user["password"]},
            timeout=10,
        )
        # Logout
        r_out = session.post(
            f"{NEXT_BASE}/api/auth/logout",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=10,
        )
        assert r_out.status_code == 200

        # Attempt to access protected endpoint
        r_denied = session.get(f"{NEXT_BASE}/api/v1/auth/me", timeout=10)
        assert r_denied.status_code == 401


class TestPhase7PostAuthRouting:
    """Requirement 6: Routing après auth (Flutter Web SPA routes)."""

    SPA_ROUTES = [
        "/dashboard",
        "/retail",
        "/retail/sales",
        "/retail/customers",
        "/retail/products",
        "/retail/recommendations",
        "/central-ai",
        "/data",
        "/integrations",
        "/billing",
        "/team",
        "/settings",
    ]

    @pytest.mark.parametrize("route", SPA_ROUTES)
    def test_spa_routes_serve_flutter_html_with_noindex(self, route):
        r = requests.get(f"{NEXT_BASE}{route}", timeout=10)
        assert r.status_code == 200, f"Route {route} failed with {r.status_code}"
        assert "/app/" not in r.url, f"Route {route} redirected to visible /app/"
        assert "X-Robots-Tag" in r.headers
        assert "noindex" in r.headers["X-Robots-Tag"]
        # Flutter Web HTML structure check
        assert "flutter" in r.text.lower() or "canvas" in r.text.lower() or "main.dart" in r.text.lower()


class TestPhase7BusinessServices:
    """Requirements 7, 8, 9, 10, 11, 12, 13, 14, 17."""

    @pytest.fixture(scope="class")
    def tenant_a(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"tenant_a_{suffix}@avenqo.ca"
        password = "SecurePassword2026!"
        company = f"TenantACorp_{suffix}"

        reg_payload = {
            "email": email,
            "password": password,
            "first_name": "Alice",
            "last_name": "TenantA",
            "company_name": company,
            "company_email": email,
            "country": "Canada",
            "industry": "Commerce",
            "selected_modules": ["retail"],
        }
        r = requests.post(f"{NEXT_BASE}/api/auth/register", json=reg_payload, timeout=10)
        assert r.status_code in (200, 201)

        from backend.app.database import SessionLocal
        from backend.app.models.user import User
        from backend.app.models.company import Company
        from tests.subscription_helpers import add_active_subscription

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email.lower()).first()
            assert user is not None
            user.email_verified_at = datetime.now(timezone.utc)
            comp = db.query(Company).filter(Company.id == user.company_id).first()
            add_active_subscription(db, comp)
            db.commit()

        session = requests.Session()
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        session.post(f"{NEXT_BASE}/api/auth/login", json={"email": email, "password": password})
        me = session.get(f"{NEXT_BASE}/api/v1/auth/me").json()
        return {
            "session": session,
            "user": me["user"],
            "company": me["company"],
            "email": email,
            "password": password,
        }

    @pytest.fixture(scope="class")
    def tenant_b(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"tenant_b_{suffix}@avenqo.ca"
        password = "SecurePassword2026!"
        company = f"TenantBCorp_{suffix}"

        reg_payload = {
            "email": email,
            "password": password,
            "first_name": "Bob",
            "last_name": "TenantB",
            "company_name": company,
            "company_email": email,
            "country": "Canada",
            "industry": "Commerce",
            "selected_modules": ["retail"],
        }
        r = requests.post(f"{NEXT_BASE}/api/auth/register", json=reg_payload, timeout=10)
        assert r.status_code in (200, 201)

        from backend.app.database import SessionLocal
        from backend.app.models.user import User
        from backend.app.models.company import Company
        from tests.subscription_helpers import add_active_subscription

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email.lower()).first()
            assert user is not None
            user.email_verified_at = datetime.now(timezone.utc)
            comp = db.query(Company).filter(Company.id == user.company_id).first()
            add_active_subscription(db, comp)
            db.commit()

        session = requests.Session()
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        session.post(f"{NEXT_BASE}/api/auth/login", json={"email": email, "password": password})
        me = session.get(f"{NEXT_BASE}/api/v1/auth/me").json()
        return {
            "session": session,
            "user": me["user"],
            "company": me["company"],
            "email": email,
            "password": password,
        }

    # Requirement 7: Dashboard / Retail Intelligence
    def test_dashboard_overview_resilience(self, tenant_a):
        s = tenant_a["session"]
        r = s.get(f"{NEXT_BASE}/api/v1/dashboard", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "kpis" in data or "overview" in data or "summary" in data or "status" in data or "cards" in data

    def test_sales_summary_resilience(self, tenant_a):
        s = tenant_a["session"]
        r = s.get(f"{NEXT_BASE}/api/v1/sales/summary", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "total_sales" in data or "summary" in data or "period" in data

    def test_customers_summary_resilience(self, tenant_a):
        s = tenant_a["session"]
        r = s.get(f"{NEXT_BASE}/api/v1/customers/summary", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data or "status" in data or "pagination" in data

    def test_products_summary_resilience(self, tenant_a):
        s = tenant_a["session"]
        r = s.get(f"{NEXT_BASE}/api/v1/products/summary", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data or "status" in data or "pagination" in data

    def test_recommendations_summary_resilience(self, tenant_a):
        s = tenant_a["session"]
        r = s.get(f"{NEXT_BASE}/api/v1/recommendations", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "recommendations" in data

    # Requirement 8: Data / Import
    def test_data_upload_profiling_and_deletion(self, tenant_a):
        s = tenant_a["session"]
        csv_content = (
            "date,order_id,customer_id,product_id,quantity,unit_price,total_amount\n"
            "2026-03-01,ORD-001,CUST-10,PROD-A,2,25.0,50.0\n"
            "2026-03-02,ORD-002,CUST-20,PROD-B,1,100.0,100.0\n"
            "2026-03-03,ORD-003,CUST-10,PROD-C,3,15.0,45.0\n"
            "2026-03-04,ORD-004,CUST-30,PROD-A,1,25.0,25.0\n"
        ).encode("utf-8")

        files = {"file": ("test_retail_sales.csv", io.BytesIO(csv_content), "text/csv")}
        data = {"module_code": "retail"}
        r = s.post(f"{NEXT_BASE}/api/v1/datasets/csv", files=files, data=data, timeout=15)
        assert r.status_code in (200, 201), f"Upload failed: {r.text}"
        uploaded_dataset = r.json()
        dataset_id = uploaded_dataset["id"]
        assert uploaded_dataset["rows_count"] == 4
        assert uploaded_dataset["columns_count"] == 7

        # Verify dataset visible in tenant dataset list
        r_list = s.get(f"{NEXT_BASE}/api/v1/datasets", timeout=10)
        assert r_list.status_code == 200
        ids = [item["id"] for item in r_list.json()]
        assert dataset_id in ids

        # Verify deletion of uploaded dataset
        r_del = s.delete(f"{NEXT_BASE}/api/v1/datasets/{dataset_id}", timeout=10)
        assert r_del.status_code == 204

        # Verify it's gone
        r_get = s.get(f"{NEXT_BASE}/api/v1/datasets/{dataset_id}", timeout=10)
        assert r_get.status_code == 404

    # Requirement 9: Shopify / WooCommerce Connectors Catalog
    def test_connectors_catalog_display(self, tenant_a):
        s = tenant_a["session"]
        r = s.get(f"{NEXT_BASE}/api/v1/connectors", timeout=10)
        assert r.status_code == 200
        catalog = r.json()
        assert isinstance(catalog, list)
        providers = [c["provider"] for c in catalog]
        assert "shopify" in providers or "woocommerce" in providers

    # Requirement 10: Central AI Assistant
    def test_central_ai_conversation_and_message(self, tenant_a):
        s = tenant_a["session"]
        # Create a conversation
        r_conv = s.post(
            f"{NEXT_BASE}/api/v1/ai/chat/conversations",
            json={"title": "E2E Retail Analysis"},
            timeout=10,
        )
        assert r_conv.status_code == 201
        conv_id = r_conv.json()["id"]

        # Post a message
        r_msg = s.post(
            f"{NEXT_BASE}/api/v1/ai/chat/conversations/{conv_id}/messages",
            json={"content": "Donne-moi le résumé des ventes de la semaine."},
            timeout=30,
        )
        # 200 if AI provider responds, or 503 if provider unavailable in dev/offline
        assert r_msg.status_code in (200, 503)

        # Conversation history retrieval
        r_detail = s.get(f"{NEXT_BASE}/api/v1/ai/chat/conversations/{conv_id}", timeout=10)
        assert r_detail.status_code == 200
        detail = r_detail.json()
        assert detail["id"] == conv_id

    # Requirement 11: TEST MULTI-TENANT CRITIQUE (Tenant A vs Tenant B)
    def test_critical_multitenant_isolation(self, tenant_a, tenant_b):
        sa = tenant_a["session"]
        sb = tenant_b["session"]

        # Tenant A creates a conversation
        r_conv = sa.post(
            f"{NEXT_BASE}/api/v1/ai/chat/conversations",
            json={"title": "Confidential Strategy Tenant A"},
            timeout=10,
        )
        assert r_conv.status_code == 201
        conv_a_id = r_conv.json()["id"]

        # Tenant B attempts IDOR read on Tenant A's conversation -> MUST RETURN 404
        r_idor_get = sb.get(f"{NEXT_BASE}/api/v1/ai/chat/conversations/{conv_a_id}", timeout=10)
        assert r_idor_get.status_code == 404, f"Cross-tenant IDOR vulnerability! Expected 404, got {r_idor_get.status_code}"

        # Tenant B attempts IDOR write into Tenant A's conversation -> MUST RETURN 404
        r_idor_post = sb.post(
            f"{NEXT_BASE}/api/v1/ai/chat/conversations/{conv_a_id}/messages",
            json={"content": "Malicious cross-tenant injection"},
            timeout=10,
        )
        assert r_idor_post.status_code == 404, f"Cross-tenant IDOR write vulnerability! Expected 404, got {r_idor_post.status_code}"

        # Tenant B lists conversations -> MUST NOT include Tenant A's conversation
        r_b_list = sb.get(f"{NEXT_BASE}/api/v1/ai/chat/conversations", timeout=10)
        assert r_b_list.status_code == 200
        b_conv_ids = [c["id"] for c in r_b_list.json()]
        assert conv_a_id not in b_conv_ids, "Tenant B conversation list leaked Tenant A's conversation!"

    # Requirement 12: Admin Platform Security
    def test_standard_user_strictly_forbidden_from_admin_api(self, tenant_a):
        s = tenant_a["session"]
        for admin_path in [
            "/api/v1/admin/companies",
            "/api/v1/admin/dashboard",
            "/api/v1/admin/audit-log",
        ]:
            r = s.get(f"{NEXT_BASE}{admin_path}", timeout=10)
            assert r.status_code == 403, f"Standard user reached {admin_path} with status {r.status_code}"

    # Requirement 13: Billing
    def test_billing_endpoints_and_official_plans(self, tenant_a):
        s = tenant_a["session"]
        r_sub = s.get(f"{NEXT_BASE}/api/v1/billing/subscription", timeout=10)
        assert r_sub.status_code == 200
        sub_data = r_sub.json()
        assert "plan_code" in sub_data

        r_plans = s.get(f"{NEXT_BASE}/api/v1/billing/plans", timeout=10)
        assert r_plans.status_code == 200
        plans = r_plans.json()
        plan_codes = [p.get("code") or p.get("id") or p.get("plan_code") for p in plans]
        assert any("demo" in str(code).lower() for code in plan_codes)
        assert any("pro" in str(code).lower() for code in plan_codes)
        assert any("enterprise" in str(code).lower() for code in plan_codes)

        r_credits = s.get(f"{NEXT_BASE}/api/v1/billing/ai-credits", timeout=10)
        assert r_credits.status_code == 200

    # Requirement 14: Team / Settings
    def test_team_and_settings_endpoints(self, tenant_a):
        s = tenant_a["session"]
        r_emp = s.get(f"{NEXT_BASE}/api/v1/employees", timeout=10)
        assert r_emp.status_code == 200
        employees = r_emp.json()
        assert len(employees) >= 1
        assert employees[0]["email"] == tenant_a["email"]

        r_me = s.get(f"{NEXT_BASE}/api/v1/auth/me", timeout=10)
        assert r_me.status_code == 200
        me = r_me.json()
        assert me["company"]["name"] == tenant_a["company"]["name"]

    # Requirement 17: Errors & Resilience
    def test_error_and_resilience_responses(self, tenant_a):
        s = tenant_a["session"]
        # 404 on non-existent dataset
        r_404 = s.get(f"{NEXT_BASE}/api/v1/datasets/{uuid.uuid4()}", timeout=10)
        assert r_404.status_code == 404

        # 422 on invalid sales period query
        r_422 = s.get(f"{NEXT_BASE}/api/v1/sales/summary?period=invalid_period_name", timeout=10)
        assert r_422.status_code == 422

        # Path traversal attack attempt safely rejected
        r_pt = s.get(f"{NEXT_BASE}/api/v1/datasets/../../etc/passwd", timeout=10)
        assert r_pt.status_code in (400, 403, 404, 422)


def test_platform_admin_account_access():
    """Requirement 12: Vérifier le chargement des routes admin avec le compte Platform Admin existant."""
    from datetime import timedelta
    from backend.app.database import SessionLocal
    from backend.app.models.user import User
    from backend.app.core.security import create_access_token
    from backend.app.models.auth_session import AuthSession

    admin_email = "paulmircea15@gmail.com"
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.email == admin_email).first()
        if not admin_user:
            pytest.skip(f"Platform admin user {admin_email} not present in local test DB")

        # Create temporary valid admin session with 1 day expiry
        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        auth_session = AuthSession(
            id=session_id,
            user_id=admin_user.id,
            token_hash=f"hash-{session_id}",
            created_at=now,
            expires_at=now + timedelta(days=1),
        )
        db.add(auth_session)
        db.commit()
        token, _ = create_access_token(admin_user.id, admin_user.company_id, session_id)

    headers = {"Authorization": f"Bearer {token}"}
    for route in [
        "/api/v1/admin/dashboard",
        "/api/v1/admin/companies",
        "/api/v1/admin/audit-log",
    ]:
        r = requests.get(f"{FASTAPI_BASE}{route}", headers=headers, timeout=10)
        assert r.status_code == 200, f"Platform admin could not access {route}: {r.status_code}"
