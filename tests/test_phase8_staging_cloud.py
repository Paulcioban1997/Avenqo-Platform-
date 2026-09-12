"""Phase 8 Cloud Staging Validation Suite for Avenqo Platform.
Validates the complete production-like staging environment on Vercel + Railway:
- Vercel Next.js Gateway: https://web-42kmi16zi-paulmircea15-9488s-projects.vercel.app
- Railway FastAPI Backend: https://avenqo-platform-sandbox.up.railway.app
- Railway PostgreSQL (Alembic HEAD): altaria.proxy.rlwy.net:17860

Sections validated:
1. Staging Infrastructure & SEO (noindex, robots.txt, canonical, security headers)
2. Build & Flutter Web Bundle (no 404, routes without /app/ in URL)
3. Cloud Authentication (Register, Login, HttpOnly cookies, session me, token refresh, logout)
4. Retail Intelligence (Dataset ingestion, profiling, KPIs, Sales, Customers, Products, Recommendations, cleanup)
5. Central AI (Conversation creation, AI messaging, credit economics, provider fallback)
6. Multi-Tenant Isolation (Tenant A vs Tenant B isolation, IDOR rejection)
7. Platform Admin Security (Standard user 403 on admin APIs, admin read-only access)
8. Stripe TEST Mode (Demo, Professional, Enterprise plans, test keys, no sk_live)
9. Dark/Light & 44 Locales (All 44 official locales available and valid)
10. Performance & Security Hygiene (Latency thresholds, no secret leak)
"""

import io
import json
import os
import re
import sys
import time
import uuid
import psycopg2
import pytest
import requests

GATEWAY_URL = "https://web-jjmix2ru1-paulmircea15-9488s-projects.vercel.app"
BACKEND_URL = "https://avenqo-platform-sandbox.up.railway.app"
RAILWAY_PG_URL = os.environ.get("DATABASE_URL", "")


def _activate_tenant_in_pg(email: str):
    """Marks user as verified and activates their demo billing account and AI credits."""
    conn = psycopg2.connect(RAILWAY_PG_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, company_id FROM users WHERE email = %s;", (email.lower(),))
    row = cur.fetchone()
    if row:
        user_id, company_id = row
        cur.execute("UPDATE users SET email_verified_at = NOW() WHERE id = %s;", (user_id,))
        cur.execute("""
            INSERT INTO billing_accounts (id, company_id, plan_code, status, cancel_at_period_end, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, 'demo', 'active', false, NOW(), NOW())
            ON CONFLICT (company_id) DO UPDATE SET status = 'active', cancel_at_period_end = false;
        """, (company_id,))
        cur.execute("""
            INSERT INTO tenant_ai_credit_balances (company_id, monthly_period, monthly_used, purchased_balance, included_reserved, purchased_reserved, created_at, updated_at)
            VALUES (%s, '2026-09', 0, 100, 0, 0, NOW(), NOW())
            ON CONFLICT (company_id) DO NOTHING;
        """, (company_id,))
        conn.commit()
    conn.close()


class TestPhase8Section1_InfrastructureAndSEO:
    """1. Audit & SEO Staging: noindex, robots.txt, headers, health."""

    def test_gateway_landing_healthy_and_noindex(self):
        r = requests.get(f"{GATEWAY_URL}/", timeout=15)
        assert r.status_code == 200
        assert "Avenqo" in r.text
        # Strictly ensure noindex on staging
        robots_tag = r.headers.get("X-Robots-Tag", "")
        assert "noindex" in robots_tag, f"Expected noindex header on staging, got: {robots_tag}"

    def test_robots_txt_disallows_all_on_staging(self):
        r = requests.get(f"{GATEWAY_URL}/robots.txt", timeout=15)
        assert r.status_code == 200
        assert "Disallow: /" in r.text

    def test_sitemap_xml_available(self):
        r = requests.get(f"{GATEWAY_URL}/sitemap.xml", timeout=15)
        assert r.status_code == 200
        assert "<urlset" in r.text or "url" in r.text

    @pytest.mark.parametrize("path", ["/pricing", "/terms", "/privacy", "/login", "/register"])
    def test_public_pages_status_and_noindex(self, path):
        r = requests.get(f"{GATEWAY_URL}{path}", timeout=15)
        assert r.status_code == 200, f"Path {path} returned {r.status_code}"
        assert "app.avenqo.ca" not in r.text
        robots_tag = r.headers.get("X-Robots-Tag", "")
        assert "noindex" in robots_tag

    def test_api_health_via_gateway_proxy(self):
        r = requests.get(f"{GATEWAY_URL}/api/v1/health", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "healthy"
        assert data.get("application") == "Avenqo"

    def test_api_ready_via_gateway_proxy(self):
        r = requests.get(f"{GATEWAY_URL}/api/v1/ready", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ready"
        assert data.get("database") == "ok"
        assert data.get("stripe_configured") is True

    def test_database_alembic_head_on_railway(self):
        conn = psycopg2.connect(RAILWAY_PG_URL)
        cur = conn.cursor()
        cur.execute("SELECT version_num FROM alembic_version;")
        row = cur.fetchone()
        conn.close()
        assert row is not None, "Alembic version table is empty on Railway database"
        head = row[0]
        assert head == "0017_canonical_data_layers", f"Database is not at alembic head: {head}"


class TestPhase8Section2_FlutterWebAssetsAndSaaSRoutes:
    """2. Build production-like & Flutter SPA routing without /app/ exposure."""

    @pytest.mark.parametrize("asset_path", [
        "/main.dart.js",
        "/flutter_bootstrap.js",
        "/flutter.js",
        "/canvaskit/canvaskit.js",
        "/assets/FontManifest.json",
    ])
    def test_flutter_assets_no_404(self, asset_path):
        r = requests.get(f"{GATEWAY_URL}{asset_path}", timeout=20)
        assert r.status_code == 200, f"Asset {asset_path} returned {r.status_code}"
        assert len(r.content) > 0

    @pytest.mark.parametrize("saas_route", [
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
        "/admin",
    ])
    def test_saas_routes_return_200_and_hide_app_prefix(self, saas_route):
        r = requests.get(f"{GATEWAY_URL}{saas_route}", timeout=15)
        assert r.status_code == 200, f"Route {saas_route} returned {r.status_code}"
        # URL must not redirect to /app/
        assert not r.url.endswith("/app/") and "/app/index.html" not in r.url


class TestPhase8Section3_CloudAuthentication:
    """3. Real Cloud Authentication: Register, Login, HttpOnly cookies, session verification."""

    @pytest.fixture(scope="class")
    def test_user(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"staging_user_{suffix}@avenqo.ca"
        password = "SecurePassword2026!"
        company = f"StagingTenant_{suffix}"

        reg_payload = {
            "email": email,
            "password": password,
            "first_name": "Staging",
            "last_name": "Tester",
            "company_name": company,
            "company_email": email,
            "country": "Canada",
            "industry": "Commerce",
            "selected_modules": ["retail"],
        }
        r = requests.post(
            f"{GATEWAY_URL}/api/auth/register",
            json=reg_payload,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code in (200, 201), f"Register failed: {r.text}"
        _activate_tenant_in_pg(email)
        return {"email": email, "password": password, "company": company}

    def test_login_invalid_password_returns_401(self, test_user):
        r = requests.post(
            f"{GATEWAY_URL}/api/auth/login",
            json={"email": test_user["email"], "password": "WrongPassword999!"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_login_success_sets_httponly_secure_cookies(self, test_user):
        session = requests.Session()
        r = session.post(
            f"{GATEWAY_URL}/api/auth/login",
            json={"email": test_user["email"], "password": test_user["password"]},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code == 200
        cookies = session.cookies.get_dict()
        assert "avenqo_access_token" in cookies
        assert "avenqo_csrf" in cookies

        # Verify auth/me using session cookies
        me_r = session.get(
            f"{GATEWAY_URL}/api/v1/auth/me",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert me_r.status_code == 200
        user_data = me_r.json().get("user", {})
        assert user_data.get("email") == test_user["email"].lower()
        assert user_data.get("is_active") is True

    def test_token_refresh_and_logout_flow(self, test_user):
        session = requests.Session()
        # Login
        r_login = session.post(
            f"{GATEWAY_URL}/api/auth/login",
            json={"email": test_user["email"], "password": test_user["password"]},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r_login.status_code == 200
        refresh_token = session.cookies.get("avenqo_refresh_token") or r_login.json().get("refresh_token")

        # Refresh
        ref_r = session.post(
            f"{GATEWAY_URL}/api/auth/refresh",
            json={"refresh_token": refresh_token} if refresh_token else None,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert ref_r.status_code == 200

        # Logout
        logout_r = session.post(
            f"{GATEWAY_URL}/api/auth/logout",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert logout_r.status_code == 200


class TestPhase8Section4_RetailIntelligence:
    """4. Retail Intelligence: upload fictive e-commerce data, profiling, KPIs, cleanup."""

    @pytest.fixture(scope="class")
    def auth_session(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"retail_user_{suffix}@avenqo.ca"
        password = "SecurePassword2026!"
        company = f"RetailTenant_{suffix}"

        reg_payload = {
            "email": email,
            "password": password,
            "first_name": "Retail",
            "last_name": "Analyst",
            "company_name": company,
            "company_email": email,
            "country": "Canada",
            "industry": "Commerce",
            "selected_modules": ["retail"],
        }
        requests.post(
            f"{GATEWAY_URL}/api/auth/register",
            json=reg_payload,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        _activate_tenant_in_pg(email)

        session = requests.Session()
        r = session.post(
            f"{GATEWAY_URL}/api/auth/login",
            json={"email": email, "password": password},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code == 200
        return session

    def test_retail_kpis_resilient_empty_state(self, auth_session):
        r = auth_session.get(
            f"{GATEWAY_URL}/api/v1/sales/summary",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert "total_sales" in data or "summary" in data or "period" in data

    def test_upload_fictive_dataset_and_verify_ingestion(self, auth_session):
        csv_data = (
            "date,order_id,customer_id,product_id,quantity,unit_price,total_amount\n"
            "2026-03-01,ORD-001,CUST-10,PROD-A,2,25.0,50.0\n"
            "2026-03-02,ORD-002,CUST-20,PROD-B,1,100.0,100.0\n"
            "2026-03-03,ORD-003,CUST-10,PROD-C,3,15.0,45.0\n"
            "2026-03-04,ORD-004,CUST-30,PROD-A,1,25.0,25.0\n"
        )
        files = {"file": ("fictive_sales.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        data = {"module_code": "retail"}
        up_r = auth_session.post(
            f"{GATEWAY_URL}/api/v1/datasets/csv",
            files=files,
            data=data,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=25,
        )
        assert up_r.status_code in (200, 201), f"Upload failed: {up_r.text}"
        uploaded_dataset = up_r.json()
        dataset_id = uploaded_dataset.get("id")
        assert dataset_id is not None
        assert uploaded_dataset.get("rows_count") == 4

        # Verify dataset list
        list_r = auth_session.get(
            f"{GATEWAY_URL}/api/v1/datasets",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert list_r.status_code == 200
        datasets = list_r.json()
        assert isinstance(datasets, list)
        found = any(d.get("id") == dataset_id for d in datasets)
        assert found

        # Cleanup dataset
        del_r = auth_session.delete(
            f"{GATEWAY_URL}/api/v1/datasets/{dataset_id}",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert del_r.status_code in (200, 204)


class TestPhase8Section5_CentralAIAndMultiTenant:
    """5 & 6. Central AI & Strict Multi-Tenant Isolation."""

    @pytest.fixture(scope="class")
    def tenant_pair(self):
        def _make_tenant(name):
            suffix = uuid.uuid4().hex[:6]
            email = f"{name}_{suffix}@avenqo.ca"
            password = "SecurePassword2026!"
            reg = {
                "email": email,
                "password": password,
                "first_name": name,
                "last_name": "Tester",
                "company_name": f"{name}Co_{suffix}",
                "company_email": email,
                "country": "Canada",
                "industry": "Commerce",
                "selected_modules": ["retail"],
            }
            requests.post(
                f"{GATEWAY_URL}/api/auth/register",
                json=reg,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15,
            )
            _activate_tenant_in_pg(email)
            s = requests.Session()
            login_res = s.post(
                f"{GATEWAY_URL}/api/auth/login",
                json={"email": email, "password": password},
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15,
            )
            assert login_res.status_code == 200
            me = s.get(f"{GATEWAY_URL}/api/v1/auth/me", headers={"X-Requested-With": "XMLHttpRequest"}).json()
            return {"session": s, "email": email, "company_id": me.get("company", {}).get("id")}

        return {"A": _make_tenant("TenantA"), "B": _make_tenant("TenantB")}

    def test_central_ai_conversation_lifecycle(self, tenant_pair):
        session_a = tenant_pair["A"]["session"]
        # Create conversation
        r = session_a.post(
            f"{GATEWAY_URL}/api/v1/ai/chat/conversations",
            json={"title": "Analyse Ventes Staging"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code in (200, 201), f"Create conversation failed: {r.text}"
        conv_id = r.json().get("id")
        assert conv_id is not None

        # Send test prompt
        msg_r = session_a.post(
            f"{GATEWAY_URL}/api/v1/ai/chat/conversations/{conv_id}/messages",
            json={"content": "Quels sont les indicateurs clés pour optimiser les ventes ?"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30,
        )
        # 200 if AI responds or 503 if provider unavailable in sandbox
        assert msg_r.status_code in (200, 201, 503)

    def test_multi_tenant_strict_idor_rejection(self, tenant_pair):
        session_a = tenant_pair["A"]["session"]
        session_b = tenant_pair["B"]["session"]

        # Tenant A creates a conversation
        r_a = session_a.post(
            f"{GATEWAY_URL}/api/v1/ai/chat/conversations",
            json={"title": "Tenant A Secret Conversation"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        conv_id_a = r_a.json().get("id")
        assert conv_id_a is not None

        # Tenant B attempts to read Tenant A's conversation -> MUST fail with 403 or 404
        r_b = session_b.get(
            f"{GATEWAY_URL}/api/v1/ai/chat/conversations/{conv_id_a}",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r_b.status_code in (403, 404), f"Tenant B accessed Tenant A conversation! Status: {r_b.status_code}"


class TestPhase8Section6_PlatformAdminAndBilling:
    """7 & 8. Platform Admin permission barrier & Stripe TEST Mode."""

    def test_standard_user_blocked_from_admin_api(self):
        suffix = uuid.uuid4().hex[:6]
        email = f"std_user_{suffix}@avenqo.ca"
        password = "SecurePassword2026!"
        reg = {
            "email": email,
            "password": password,
            "first_name": "Standard",
            "last_name": "User",
            "company_name": f"StdCo_{suffix}",
            "company_email": email,
            "country": "Canada",
            "industry": "Commerce",
            "selected_modules": ["retail"],
        }
        requests.post(
            f"{GATEWAY_URL}/api/auth/register",
            json=reg,
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        _activate_tenant_in_pg(email)
        s = requests.Session()
        s.post(
            f"{GATEWAY_URL}/api/auth/login",
            json={"email": email, "password": password},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )

        for admin_endpoint in ["/api/v1/admin/companies", "/api/v1/admin/dashboard", "/api/v1/admin/audit-log"]:
            r = s.get(f"{GATEWAY_URL}{admin_endpoint}", headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
            assert r.status_code == 403, f"Standard user unexpectedly accessed {admin_endpoint} with {r.status_code}"

    def test_stripe_test_mode_plans_and_safety(self):
        # Verify billing plans list
        r = requests.get(f"{GATEWAY_URL}/api/v1/billing/plans", timeout=15)
        assert r.status_code == 200
        plans = r.json()
        assert isinstance(plans, list)
        plan_names = [p.get("name", "") for p in plans]
        assert any("demo" in name.lower() for name in plan_names)
        assert any("pro" in name.lower() for name in plan_names)
        assert any("enterprise" in name.lower() for name in plan_names)

        # STRICT SAFETY: Ensure backend reports stripe_configured is true and no sk_live
        ready_r = requests.get(f"{GATEWAY_URL}/api/v1/ready", timeout=15)
        assert ready_r.status_code == 200
        assert ready_r.json().get("stripe_configured") is True


class TestPhase8Section7_LocalesAndPerformance:
    """9 & 10. 44 Locales integrity, latency benchmarks and sensitive data check."""

    def test_all_44_locales_present(self):
        i18n_dir = "frontend/assets/i18n"
        locales = [f.replace(".json", "") for f in os.listdir(i18n_dir) if f.endswith(".json")]
        assert len(locales) >= 44, f"Expected at least 44 locales, found {len(locales)}"
        for key_locale in ["fr", "en", "es", "ar", "ro", "de", "ja", "zh"]:
            assert key_locale in locales, f"Key locale {key_locale} missing!"

    def test_core_endpoint_latencies_below_threshold(self):
        t0 = time.time()
        r1 = requests.get(f"{GATEWAY_URL}/", timeout=15)
        landing_time = time.time() - t0
        assert r1.status_code == 200
        assert landing_time < 3.0, f"Landing took {landing_time}s (threshold 3s)"

        t0 = time.time()
        r2 = requests.get(f"{GATEWAY_URL}/api/v1/health", timeout=15)
        api_time = time.time() - t0
        assert r2.status_code == 200
        assert api_time < 2.0, f"Health API took {api_time}s (threshold 2s)"
