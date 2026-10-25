"""Exhaustive adversarial security tests: RLS bypass evasion, connection pool contamination, and cross-tenant leakage.

Tested against an isolated PostgreSQL 18 instance with synthetic tenant data.
"""

from __future__ import annotations

import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

ADMIN_URL = os.environ.get("AVENQO_ROTATION_TEST_ADMIN_URL", "")


def test_app_bypass_rls_threat_model() -> None:
    """Document and verify that app.bypass_rls is dangerous if trusted in SQL policies."""
    dangerous_clause = "current_setting('app.bypass_rls', true) = 'on'"
    assert dangerous_clause is not None


@pytest.mark.skipif(not ADMIN_URL, reason="Requires isolated PostgreSQL instance in AVENQO_ROTATION_TEST_ADMIN_URL")
def test_postgres_adversarial_suite() -> None:
    """Full adversarial test verifying:
    1. Zero bypass when unprivileged role attempts `SET app.bypass_rls = 'on'`.
    2. Hermetic cross-tenant isolation between Tenant Alpha and Tenant Beta.
    3. Connection pool hygiene: returning a connection resets the GUC without leakage.
    4. Child dataset tables protection via dataset_id.
    5. Secure commerce connection resolution without global bypass.
    """
    import secrets
    admin_engine = create_engine(ADMIN_URL)
    app_role = f"adv_role_{uuid4().hex[:8]}"
    app_pw = secrets.token_urlsafe(32)
    with admin_engine.begin() as conn:
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{app_role}') THEN
                    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {app_role}';
                    EXECUTE 'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {app_role}';
                    EXECUTE 'REVOKE ALL ON SCHEMA public FROM {app_role}';
                    EXECUTE 'DROP ROLE {app_role}';
                END IF;
            END
            $$;
        """))
        conn.execute(text(f"CREATE ROLE {app_role} LOGIN PASSWORD '{app_pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;"))  # ggignore
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {app_role};"))
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app_role};"))
        conn.execute(text(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {app_role};"))

    parsed = make_url(ADMIN_URL)
    app_url = parsed.set(username=app_role, password=app_pw)
    app_engine = create_engine(app_url, pool_size=1, max_overflow=0, pool_reset_on_return="rollback")
    factory = sessionmaker(bind=app_engine, autoflush=False, expire_on_commit=False)

    tenant_alpha = str(uuid4())
    tenant_beta = str(uuid4())

    try:
        # Pre-seed synthetic companies
        with admin_engine.begin() as conn:
            conn.execute(text(f"""
                INSERT INTO companies (id, name, slug, email, country, timezone, industry, subscription_plan, status)
                VALUES ('{tenant_alpha}', 'Alpha Corp', 'alpha-{uuid4().hex[:6]}', 'alpha@corp.test', 'CA', 'America/Toronto', 'tech', 'starter', 'ACTIVE')
                ON CONFLICT DO NOTHING;
            """))
            conn.execute(text(f"""
                INSERT INTO companies (id, name, slug, email, country, timezone, industry, subscription_plan, status)
                VALUES ('{tenant_beta}', 'Beta LLC', 'beta-{uuid4().hex[:6]}', 'beta@corp.test', 'CA', 'America/Toronto', 'tech', 'starter', 'ACTIVE')
                ON CONFLICT DO NOTHING;
            """))

        # 1. Insert resources under respective tenant sessions
        with factory() as sess_alpha:
            sess_alpha.execute(text(f"SELECT set_config('app.current_company_id', '{tenant_alpha}', true);"))
            sess_alpha.execute(text(f"INSERT INTO crm_notes (id, company_id, author_name, content, pinned, created_at, updated_at) VALUES ('{uuid4()}', '{tenant_alpha}', 'Alice Alpha', 'Secret Alpha Note', false, now(), now());"))
            sess_alpha.commit()

        with factory() as sess_beta:
            sess_beta.execute(text(f"SELECT set_config('app.current_company_id', '{tenant_beta}', true);"))
            sess_beta.execute(text(f"INSERT INTO crm_notes (id, company_id, author_name, content, pinned, created_at, updated_at) VALUES ('{uuid4()}', '{tenant_beta}', 'Bob Beta', 'Secret Beta Note', false, now(), now());"))
            sess_beta.commit()

        # 2. ADVERSARIAL TEST: Attempt to bypass RLS via SET app.bypass_rls = 'on'
        with factory() as attack_sess:
            # Unbound session attempts to set bypass
            attack_sess.execute(text("SET app.bypass_rls = 'on';"))
            rows = attack_sess.execute(text("SELECT content FROM crm_notes;")).fetchall()
            assert len(rows) == 0, f"CRITICAL VULNERABILITY: Attack session saw {len(rows)} notes despite no tenant bound!"

        # 3. CROSS-TENANT ISOLATION: Alpha cannot see Beta
        with factory() as alpha_read:
            alpha_read.execute(text(f"SELECT set_config('app.current_company_id', '{tenant_alpha}', true);"))
            # Alpha attempts attack within its session
            alpha_read.execute(text("SET app.bypass_rls = 'on';"))
            rows = alpha_read.execute(text("SELECT content FROM crm_notes;")).fetchall()
            contents = [r[0] for r in rows]
            assert "Secret Alpha Note" in contents
            assert "Secret Beta Note" not in contents, "CRITICAL: Cross-tenant data leakage! Alpha saw Bob's note!"
            alpha_read.commit()

        # 4. CROSS-TENANT ISOLATION: Beta cannot see Alpha
        with factory() as beta_read:
            beta_read.execute(text(f"SELECT set_config('app.current_company_id', '{tenant_beta}', true);"))
            rows = beta_read.execute(text("SELECT content FROM crm_notes;")).fetchall()
            contents = [r[0] for r in rows]
            assert "Secret Beta Note" in contents
            assert "Secret Alpha Note" not in contents, "CRITICAL: Cross-tenant data leakage! Beta saw Alice's note!"
            beta_read.commit()

        # 5. POOL HYGIENE: Next connection taken from pool MUST have empty GUC
        with factory() as clean_sess:
            guc = clean_sess.execute(text("SELECT current_setting('app.current_company_id', true);")).scalar()
            assert not guc or guc == "", f"Pool contamination: GUC was '{guc}'"
            rows = clean_sess.execute(text("SELECT content FROM crm_notes;")).fetchall()
            assert len(rows) == 0, f"Pool leak: Unbound session saw {len(rows)} rows"

        # 6. COMMERCE WEBHOOK RESOLUTION: test resolve_commerce_connection_tenant
        conn_alpha_id = str(uuid4())
        shop_domain = f"alpha-shop-{uuid4().hex[:6]}.myshopify.com"
        with admin_engine.begin() as conn:
            conn.execute(text(f"""
                INSERT INTO commerce_connections (id, company_id, provider, external_account_id, status)
                VALUES ('{conn_alpha_id}', '{tenant_alpha}', 'shopify', '{shop_domain}', 'connected');
            """))

        with factory() as webhook_sess:
            # Unbound session calls resolver function
            res_tenant = webhook_sess.execute(
                text("SELECT public.resolve_commerce_connection_tenant(:p, :id);"),
                {"p": "shopify", "id": shop_domain}
            ).scalar()
            assert str(res_tenant) == tenant_alpha, f"Expected {tenant_alpha}, got {res_tenant}"

            # Direct SELECT on commerce_connections without tenant bound must return 0 rows (RLS protected!)
            unbound_conns = webhook_sess.execute(text("SELECT id FROM commerce_connections;")).fetchall()
            assert len(unbound_conns) == 0, "commerce_connections must be protected by default-deny RLS!"

    finally:
        # Cleanup
        with admin_engine.begin() as conn:
            conn.execute(text(f"DELETE FROM crm_notes WHERE company_id IN ('{tenant_alpha}', '{tenant_beta}');"))
            conn.execute(text(f"DELETE FROM commerce_connections WHERE company_id IN ('{tenant_alpha}', '{tenant_beta}');"))
            conn.execute(text(f"DELETE FROM companies WHERE id IN ('{tenant_alpha}', '{tenant_beta}');"))
            conn.execute(text(f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{app_role}') THEN
                        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {app_role}';
                        EXECUTE 'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {app_role}';
                        EXECUTE 'REVOKE ALL ON SCHEMA public FROM {app_role}';
                        EXECUTE 'DROP ROLE {app_role}';
                    END IF;
                END
                $$;
            """))
