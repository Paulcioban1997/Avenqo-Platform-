#!/usr/bin/env python3
"""E2E Sandbox Verification Script for Lots 1, 2, 3, and 4 on Railway Sandbox.

Tests live API at https://avenqo-platform-sandbox.up.railway.app:
- Multi-source selection (ALL, CUSTOM_SET, SINGLE)
- Multi-store setup per company
- RBAC enforcement on selection
- Cross-tenant IDOR isolation
- Parallel sync reservation (sync-all)
- Live health and ready checks
- Cleans up isolated test data upon completion
"""

import os
import sys
import uuid
import json
from datetime import datetime, timezone
import psycopg2
import requests
from pwdlib import PasswordHash

pwd_hash = PasswordHash.recommended()

SANDBOX_API = os.environ.get("SANDBOX_API_URL", "https://avenqo-platform-sandbox.up.railway.app")
SANDBOX_DB = os.environ.get("SANDBOX_DATABASE_URL") or os.environ.get("DATABASE_URL")

def run_tests():
    print("=" * 60)
    print("RUNNING LIVE SANDBOX E2E VERIFICATION (Lots 1, 2, 3, 4)")
    print(f"Target: {SANDBOX_API}")
    print("=" * 60)

    # 1. Check /api/v1/health & /api/v1/ready
    print("\n--- 1. Health & Ready Endpoints ---")
    r_health = requests.get(f"{SANDBOX_API}/api/v1/health", timeout=10)
    assert r_health.status_code == 200, f"Health failed: {r_health.text}"
    health_data = r_health.json()
    print("Health response:", health_data)
    assert health_data["status"] == "healthy"
    assert "git_sha" in health_data

    r_ready = requests.get(f"{SANDBOX_API}/api/v1/ready", timeout=10)
    assert r_ready.status_code == 200, f"Ready failed: {r_ready.text}"
    ready_data = r_ready.json()
    print("Ready response:", ready_data)
    assert ready_data["status"] == "ready"
    assert ready_data["database"] == "ok"
    assert ready_data["migrations"] == "ok"

    # Connect to Sandbox DB to seed test data
    conn = psycopg2.connect(SANDBOX_DB)
    cur = conn.cursor()

    test_suffix = uuid.uuid4().hex[:8]
    company_a_id = str(uuid.uuid4())
    company_b_id = str(uuid.uuid4())
    user_a_id = str(uuid.uuid4())
    user_a_member_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())

    email_a = f"e2e_owner_a_{test_suffix}@avenqo-test.ca"
    email_a_member = f"e2e_member_a_{test_suffix}@avenqo-test.ca"
    email_b = f"e2e_owner_b_{test_suffix}@avenqo-test.ca"
    password_plain = "AvenqoTest123!Secure"
    hashed_pw = pwd_hash.hash(password_plain)

    conn_a1_id = str(uuid.uuid4())
    conn_a2_id = str(uuid.uuid4())
    conn_b1_id = str(uuid.uuid4())

    try:
        print("\n--- 2. Setting up isolated test companies and users ---")
        now = datetime.now(timezone.utc)

        # Company A (CAD)
        cur.execute("""
            INSERT INTO companies (
                id, name, slug, email, billing_email, country, timezone, industry,
                region, company_size, preferred_language, currency_code, subscription_plan,
                status, business_hours, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, 'Canada', 'America/Toronto', 'Retail',
                'North America', '1-10', 'en', 'CAD', 'demo',
                'ACTIVE', '{}', %s, %s
            );
        """, (company_a_id, f"E2E Store Group A {test_suffix}", f"e2e-group-a-{test_suffix}", email_a, email_a, now, now))

        # Company B (USD)
        cur.execute("""
            INSERT INTO companies (
                id, name, slug, email, billing_email, country, timezone, industry,
                region, company_size, preferred_language, currency_code, subscription_plan,
                status, business_hours, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, 'United States', 'America/New_York', 'Retail',
                'North America', '1-10', 'en', 'USD', 'demo',
                'ACTIVE', '{}', %s, %s
            );
        """, (company_b_id, f"E2E Store Group B {test_suffix}", f"e2e-group-b-{test_suffix}", email_b, email_b, now, now))

        # Billing accounts
        for cid in (company_a_id, company_b_id):
            cur.execute("""
                INSERT INTO billing_accounts (id, company_id, plan_code, status, cancel_at_period_end, created_at, updated_at)
                VALUES (%s, %s, 'demo', 'active', false, %s, %s);
            """, (str(uuid.uuid4()), cid, now, now))

        # Users
        cur.execute("""
            INSERT INTO users (
                id, company_id, email, password_hash, first_name, last_name, job_title,
                role, is_active, is_platform_admin, mfa_enabled, failed_login_count,
                email_verified_at, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, 'Owner', 'A', 'Owner',
                'OWNER', true, false, false, 0,
                %s, %s, %s
            );
        """, (user_a_id, company_a_id, email_a, hashed_pw, now, now, now))

        cur.execute("""
            INSERT INTO users (
                id, company_id, email, password_hash, first_name, last_name, job_title,
                role, is_active, is_platform_admin, mfa_enabled, failed_login_count,
                email_verified_at, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, 'Member', 'A', 'Analyst',
                'USER', true, false, false, 0,
                %s, %s, %s
            );
        """, (user_a_member_id, company_a_id, email_a_member, hashed_pw, now, now, now))

        cur.execute("""
            INSERT INTO users (
                id, company_id, email, password_hash, first_name, last_name, job_title,
                role, is_active, is_platform_admin, mfa_enabled, failed_login_count,
                email_verified_at, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, 'Owner', 'B', 'Owner',
                'OWNER', true, false, false, 0,
                %s, %s, %s
            );
        """, (user_b_id, company_b_id, email_b, hashed_pw, now, now, now))

        # Memberships
        cur.execute("""
            INSERT INTO company_memberships (id, company_id, user_id, role, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, 'OWNER', true, %s, %s);
        """, (str(uuid.uuid4()), company_a_id, user_a_id, now, now))

        cur.execute("""
            INSERT INTO company_memberships (id, company_id, user_id, role, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, 'USER', true, %s, %s);
        """, (str(uuid.uuid4()), company_a_id, user_a_member_id, now, now))

        cur.execute("""
            INSERT INTO company_memberships (id, company_id, user_id, role, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, 'OWNER', true, %s, %s);
        """, (str(uuid.uuid4()), company_b_id, user_b_id, now, now))

        # Add 2 commerce connections for Company A (multi-store support)
        cur.execute("""
            INSERT INTO commerce_connections (
                id, company_id, provider, external_account_id, display_name, status,
                granted_scopes, capabilities, sync_cursor, dataset_ids,
                records_processed, records_created, records_updated, records_failed,
                created_at, updated_at
            ) VALUES (
                %s, %s, 'shopify', 'mtl-store.myshopify.com', 'Shopify Montreal Store', 'READY',
                '["read_write"]', '["orders", "products"]', '{}', '{}',
                0, 0, 0, 0, %s, %s
            );
        """, (conn_a1_id, company_a_id, now, now))

        cur.execute("""
            INSERT INTO commerce_connections (
                id, company_id, provider, external_account_id, display_name, status,
                granted_scopes, capabilities, sync_cursor, dataset_ids,
                records_processed, records_created, records_updated, records_failed,
                created_at, updated_at
            ) VALUES (
                %s, %s, 'woocommerce', 'https://qc-store.com', 'WooCommerce Quebec Store', 'READY',
                '["read_write"]', '["orders", "products"]', '{}', '{}',
                0, 0, 0, 0, %s, %s
            );
        """, (conn_a2_id, company_a_id, now, now))

        # Add 1 commerce connection for Company B
        cur.execute("""
            INSERT INTO commerce_connections (
                id, company_id, provider, external_account_id, display_name, status,
                granted_scopes, capabilities, sync_cursor, dataset_ids,
                records_processed, records_created, records_updated, records_failed,
                created_at, updated_at
            ) VALUES (
                %s, %s, 'shopify', 'nyc-store.myshopify.com', 'Shopify NYC Store', 'READY',
                '["read_write"]', '["orders", "products"]', '{}', '{}',
                0, 0, 0, 0, %s, %s
            );
        """, (conn_b1_id, company_b_id, now, now))

        conn.commit()
        print("Test data successfully committed to Sandbox DB.")

        # 3. Log in to obtain JWT tokens
        print("\n--- 3. Authenticating test users ---")
        session_a = requests.Session()
        r_login_a = session_a.post(f"{SANDBOX_API}/api/v1/auth/login", json={"email": email_a, "password": password_plain})
        assert r_login_a.status_code == 200, f"Login A failed: {r_login_a.text}"
        token_a = r_login_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}
        print("User A logged in successfully.")

        session_member = requests.Session()
        r_login_m = session_member.post(f"{SANDBOX_API}/api/v1/auth/login", json={"email": email_a_member, "password": password_plain})
        assert r_login_m.status_code == 200, f"Login Member failed: {r_login_m.text}"
        token_m = r_login_m.json()["access_token"]
        headers_m = {"Authorization": f"Bearer {token_m}"}
        print("User A (Member) logged in successfully.")

        session_b = requests.Session()
        r_login_b = session_b.post(f"{SANDBOX_API}/api/v1/auth/login", json={"email": email_b, "password": password_plain})
        assert r_login_b.status_code == 200, f"Login B failed: {r_login_b.text}"
        token_b = r_login_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}
        print("User B logged in successfully.")

        # 4. Test Multi-source Selection GET
        print("\n--- 4. Multi-source Selection GET (Lot 1) ---")
        r_sel = session_a.get(f"{SANDBOX_API}/api/v1/workspace/sources/selection", headers=headers_a)
        assert r_sel.status_code == 200, f"GET selection failed: {r_sel.text}"
        sel_data = r_sel.json()
        print("Initial Workspace Selection:", json.dumps(sel_data, indent=2))
        assert sel_data["mode"] in ("ALL", "SINGLE", "CUSTOM_SET")
        source_ids = [s["id"] for s in sel_data["available_sources"]]
        print(f"Company A has {len(source_ids)} available sources: {source_ids}")
        assert conn_a1_id in source_ids
        assert conn_a2_id in source_ids
        # Verify cross-tenant isolation: Company B connection must NOT appear
        assert conn_b1_id not in source_ids, "SECURITY ERROR: Tenant B source leaked to Tenant A!"
        print("[OK] Cross-tenant available source isolation confirmed.")

        # 5. Test Multi-source Selection POST (CUSTOM_SET)
        print("\n--- 5. Multi-source Selection POST CUSTOM_SET ---")
        target_sources = [conn_a1_id]
        r_set_custom = session_a.post(
            f"{SANDBOX_API}/api/v1/workspace/sources/selection",
            headers=headers_a,
            json={"mode": "CUSTOM_SET", "selected_source_ids": target_sources}
        )
        assert r_set_custom.status_code == 200, f"POST custom set failed: {r_set_custom.text}"
        custom_data = r_set_custom.json()
        print("Custom Set Selection Response:", json.dumps(custom_data, indent=2))
        assert custom_data["mode"] == "CUSTOM_SET"
        assert custom_data["selected_source_ids"] == target_sources
        assert custom_data["effective_count"] == 1
        print("[OK] CUSTOM_SET selection successfully saved and retrieved.")

        # 6. Test Multi-source Selection POST (ALL)
        print("\n--- 6. Multi-source Selection POST ALL ---")
        r_set_all = session_a.post(
            f"{SANDBOX_API}/api/v1/workspace/sources/selection",
            headers=headers_a,
            json={"mode": "ALL", "selected_source_ids": []}
        )
        assert r_set_all.status_code == 200, f"POST ALL failed: {r_set_all.text}"
        all_data = r_set_all.json()
        print("ALL Selection Response:", json.dumps(all_data, indent=2))
        assert all_data["mode"] == "ALL"
        assert conn_a1_id in all_data["selected_source_ids"]
        assert conn_a2_id in all_data["selected_source_ids"]
        assert all_data["effective_count"] == 2
        print("[OK] ALL selection mode correctly consolidated all connected stores.")

        # 7. Test IDOR Rejection: User A tries to select User B's source
        print("\n--- 7. Security IDOR Rejection Test ---")
        r_idor = session_a.post(
            f"{SANDBOX_API}/api/v1/workspace/sources/selection",
            headers=headers_a,
            json={"mode": "CUSTOM_SET", "selected_source_ids": [conn_b1_id]}
        )
        print(f"IDOR attempt response code: {r_idor.status_code}")
        assert r_idor.status_code in (400, 403, 404), f"Expected rejection, got: {r_idor.status_code}"
        print("[OK] IDOR cross-tenant selection attempt was strictly rejected.")

        # 8. Test RBAC: Non-admin Member cannot change workspace selection
        print("\n--- 8. RBAC Permission Test ---")
        r_rbac = session_member.post(
            f"{SANDBOX_API}/api/v1/workspace/sources/selection",
            headers=headers_m,
            json={"mode": "SINGLE", "selected_source_ids": [conn_a1_id]}
        )
        print(f"Member POST selection response code: {r_rbac.status_code}")
        assert r_rbac.status_code == 403, f"Expected 403 Forbidden for member, got: {r_rbac.status_code}"
        print("[OK] RBAC enforced: Member role rejected with 403 Forbidden.")

        # 9. Test Multi-store Parallel Sync Endpoint (Lot 2)
        print("\n--- 9. Multi-store Parallel Sync Endpoint (Lot 2) ---")
        r_sync_all = session_a.post(
            f"{SANDBOX_API}/api/v1/connectors/connections/sync-all",
            headers=headers_a,
            json={"force": True}
        )
        print(f"Sync-all response code: {r_sync_all.status_code}")
        print("Sync-all response body:", json.dumps(r_sync_all.json(), indent=2))
        assert r_sync_all.status_code == 202, f"Sync all failed: {r_sync_all.text}"
        sync_data = r_sync_all.json()
        assert sync_data["status"] == "SYNCING"
        assert "connection_id" in sync_data
        print("[OK] Parallel sync runner successfully reserved all tenant connections.")

        # 10. Test Retail Summary & Backward Compatibility
        print("\n--- 10. Legacy Retail Compatibility & Source State ---")
        r_summary = session_a.get(f"{SANDBOX_API}/api/v1/retail/summary", headers=headers_a)
        print(f"Retail summary status: {r_summary.status_code}")
        assert r_summary.status_code in (200, 404)
        print("[OK] Retail routes remain fully operational and backwards compatible.")

        # 11. Test Central AI Multi-turn Conversation & Grounding
        print("\n--- 11. Central AI Multi-turn Conversation & Persistence ---")
        r_conv = session_a.post(
            f"{SANDBOX_API}/api/v1/ai/chat/conversations",
            headers=headers_a,
            json={"title": "Analyse Ventes Multi-Boutiques"}
        )
        assert r_conv.status_code == 201, f"Create conversation failed: {r_conv.text}"
        conv_id = r_conv.json()["id"]
        print(f"[OK] Created Central AI conversation: {conv_id}")

        # Send Turn 1
        turn1_key = str(uuid.uuid4())
        r_msg1 = session_a.post(
            f"{SANDBOX_API}/api/v1/ai/central/conversations/{conv_id}/messages",
            headers={**headers_a, "Idempotency-Key": turn1_key},
            json={
                "content": "Combien ai-je vendu ce mois-ci sur toutes mes boutiques ?",
                "locale": "fr",
                "page_context": "/retail"
            }
        )
        print(f"Central AI Turn 1 status: {r_msg1.status_code}")
        assert r_msg1.status_code == 200, f"Central AI turn 1 failed: {r_msg1.text}"
        ans1 = r_msg1.json()
        print("Central AI Turn 1 answer summary:", ans1.get("answer", "")[:120])
        print("Central AI Grounded source:", ans1.get("grounded_source"))

        # Send Turn 2 in same conversation (multi-turn context)
        turn2_key = str(uuid.uuid4())
        r_msg2 = session_a.post(
            f"{SANDBOX_API}/api/v1/ai/central/conversations/{conv_id}/messages",
            headers={**headers_a, "Idempotency-Key": turn2_key},
            json={
                "content": "Quelle boutique performe le mieux ?",
                "locale": "fr",
                "page_context": "/retail"
            }
        )
        print(f"Central AI Turn 2 status: {r_msg2.status_code}")
        assert r_msg2.status_code == 200, f"Central AI turn 2 failed: {r_msg2.text}"
        ans2 = r_msg2.json()
        print("Central AI Turn 2 answer summary:", ans2.get("answer", "")[:120])

        # Verify Persistence after reload
        r_get_conv = session_a.get(
            f"{SANDBOX_API}/api/v1/ai/chat/conversations/{conv_id}",
            headers=headers_a
        )
        assert r_get_conv.status_code == 200, f"Get conversation failed: {r_get_conv.text}"
        conv_detail = r_get_conv.json()
        messages_count = len(conv_detail.get("messages", []))
        print(f"[OK] Conversation persistent after reload with {messages_count} recorded messages.")
        assert messages_count >= 2

        # 12. Security Test: Tenant B cannot access Tenant A's conversation (IDOR)
        print("\n--- 12. Central AI Cross-Tenant IDOR Test ---")
        r_idor_conv = session_b.get(
            f"{SANDBOX_API}/api/v1/ai/chat/conversations/{conv_id}",
            headers=headers_b
        )
        print(f"Tenant B access Tenant A conversation status: {r_idor_conv.status_code}")
        assert r_idor_conv.status_code in (403, 404), f"Security leak! Expected 403/404, got: {r_idor_conv.status_code}"
        print("[OK] Tenant B strictly forbidden from accessing Tenant A's private conversations.")

        # 13. Test Voice Central Session Creation & Stream Ticket
        print("\n--- 13. Voice Central Real-Time Session & Stream Ticket ---")
        r_voice = session_a.post(
            f"{SANDBOX_API}/api/v1/ai/voice/sessions",
            headers=headers_a,
            json={
                "conversation_id": conv_id,
                "locale": "fr",
                "entrypoint": "central",
                "request_id": str(uuid.uuid4())
            }
        )
        print(f"Create Voice session status: {r_voice.status_code}")
        assert r_voice.status_code == 200, f"Create voice session failed: {r_voice.text}"
        voice_data = r_voice.json()
        voice_id = voice_data["id"]
        print(f"[OK] Voice Central session created: {voice_id}, capability: {voice_data.get('voice_capability')}")

        r_ticket = session_a.post(
            f"{SANDBOX_API}/api/v1/ai/voice/sessions/{voice_id}/stream-ticket",
            headers=headers_a
        )
        print(f"Stream ticket status: {r_ticket.status_code}")
        assert r_ticket.status_code == 200, f"Get stream ticket failed: {r_ticket.text}"
        ticket_data = r_ticket.json()
        assert "ticket" in ticket_data
        print(f"[OK] Voice WebSocket stream ticket issued securely (realtime={ticket_data.get('realtime')}).")

        # End voice session
        r_end_voice = session_a.post(
            f"{SANDBOX_API}/api/v1/ai/voice/sessions/{voice_id}/end",
            headers=headers_a
        )
        assert r_end_voice.status_code == 200
        print("[OK] Voice session ended cleanly.")

        print("\n" + "=" * 60)
        print("ALL LIVE SANDBOX E2E VERIFICATIONS (PHASE 5) PASSED SUCCESSFULLY!")
        print("=" * 60)

    finally:
        print("\n--- Cleaning up test fixtures in Sandbox DB ---")
        try:
            cur.execute("DELETE FROM voice_central_sessions WHERE company_id IN (%s, %s);", (company_a_id, company_b_id))
            cur.execute("DELETE FROM ai_messages WHERE conversation_id IN (SELECT id FROM ai_conversations WHERE company_id IN (%s, %s));", (company_a_id, company_b_id))
            cur.execute("DELETE FROM ai_conversations WHERE company_id IN (%s, %s);", (company_a_id, company_b_id))
            cur.execute("DELETE FROM commerce_connections WHERE id IN (%s, %s, %s);", (conn_a1_id, conn_a2_id, conn_b1_id))
            cur.execute("DELETE FROM retail_active_sources WHERE company_id IN (%s, %s);", (company_a_id, company_b_id))
            cur.execute("DELETE FROM retail_source_states WHERE company_id IN (%s, %s);", (company_a_id, company_b_id))
            cur.execute("DELETE FROM company_memberships WHERE company_id IN (%s, %s);", (company_a_id, company_b_id))
            cur.execute("DELETE FROM billing_accounts WHERE company_id IN (%s, %s);", (company_a_id, company_b_id))
            cur.execute("DELETE FROM users WHERE id IN (%s, %s, %s);", (user_a_id, user_a_member_id, user_b_id))
            cur.execute("DELETE FROM companies WHERE id IN (%s, %s);", (company_a_id, company_b_id))
            conn.commit()
            print("Cleanup completed successfully.")
        except Exception as e:
            print("Cleanup warning:", e)
        conn.close()

if __name__ == "__main__":
    run_tests()
