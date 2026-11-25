"""Comprehensive verification suite for PR 5 — Security Hardening & Optional CrowdStrike FCS / NG-SIEM (Phase B & I5).

Covers:
1. `.github/workflows/crowdstrike-fcs-scan.yml` YAML validity, native CycloneDX SBOM job,
   `CrowdStrike/fcs-action` step, no kernel sensor assumption, and license-free graceful skip.
2. Optional activation: disabled by default -> zero network calls, zero business impact, honest
   `"disabled"` status (never `"protected"` / `"Protégé par CrowdStrike"`).
3. Missing credentials vs invalid credentials (HTTP 401/403) vs unreachable vs verified (HTTP 200) ->
   controlled technical status, circuit-breaker resilience, and zero secret leaked in responses/repr/logs.
4. All 10 normalized security event categories validated end-to-end.
5. Strict recursive scrubbing of PINs (`123456`), NIPs, JWTs, Bearer tokens, API keys (`sk-...`),
   passwords, private document bodies, and confidential voice transcripts from emitted HEC payloads.
6. Strict RBAC (`401`/`403`) on `/api/v1/admin/security/*` against unauthenticated, non-admin,
   cross-tenant, and non-security platform roles, plus RFC 6749 `Cache-Control: no-store` token hardening.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import secrets
from typing import Any

import httpx
import pytest
from sqlalchemy import select
import yaml

from backend.app.models import User, UserRole
from backend.app.security.crowdstrike_siem import (
    ALL_SECURITY_EVENT_TYPES,
    CrowdStrikeConfig,
    CrowdStrikeConnectionStatus,
    CrowdStrikeSIEMConnector,
    SecurityEventType,
    build_normalized_event,
    reset_crowdstrike_connector,
)
from backend.app.services.security_posture_service import SecurityPostureService
from tests.backend.test_auth import (
    NON_SENSITIVE_TEST_PASSWORD,
    auth_environment,
    registration_payload,
    verify_and_login,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FCS_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "crowdstrike-fcs-scan.yml"


@pytest.fixture(autouse=True)
def _isolate_crowdstrike_singleton():
    reset_crowdstrike_connector(None)
    yield
    reset_crowdstrike_connector(None)


def _register_and_login(client, notifier, email: str, company_name: str) -> dict[str, Any]:
    res = client.post("/api/v1/auth/register", json=registration_payload(email, company_name))
    assert res.status_code == 201
    return verify_and_login(client, notifier, email)


def _bearer_headers(login_payload: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {login_payload['access_token']}"}


# ---------------------------------------------------------------------------
# 1. CI/CD CrowdStrike Falcon Cloud Security & Native SBOM Workflow Validation
# ---------------------------------------------------------------------------


def test_crowdstrike_fcs_workflow_yaml_sbom_and_license_free_gating() -> None:
    assert FCS_WORKFLOW_PATH.is_file(), "Missing .github/workflows/crowdstrike-fcs-scan.yml"
    raw_text = FCS_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw_text)

    assert isinstance(workflow, dict)
    assert "on" in workflow
    assert workflow.get("permissions", {}).get("contents") == "read"

    jobs = workflow.get("jobs", {})
    assert "native-sbom" in jobs
    assert "crowdstrike-fcs-scan" in jobs

    # Native SBOM job runs unconditionally without CrowdStrike license secrets
    sbom_job = jobs["native-sbom"]
    assert "if" not in sbom_job
    sbom_steps = sbom_job.get("steps", [])
    assert any("cyclonedx" in str(step.get("run", "")).lower() for step in sbom_steps)
    assert any(str(step.get("uses", "")).startswith("actions/upload-artifact@") for step in sbom_steps)

    # Falcon Cloud Security job uses official CrowdStrike/fcs-action and gates cleanly on secret presence
    fcs_job = jobs["crowdstrike-fcs-scan"]
    fcs_steps = fcs_job.get("steps", [])
    fcs_action_steps = [
        step for step in fcs_steps if str(step.get("uses", "")).startswith("CrowdStrike/fcs-action@")
    ]
    assert len(fcs_action_steps) >= 1
    for step in fcs_action_steps:
        assert step.get("if") == "steps.fcs_gate.outputs.configured == 'true'"
        with_cfg = step.get("with", {})
        assert "FCS_FAIL_ON_SEVERITY" in str(with_cfg.get("fail-on", ""))

    # Severity gate policy is CRITICAL,HIGH + approved exceptions file documented
    env_cfg = workflow.get("env", {})
    assert env_cfg.get("FCS_FAIL_ON_SEVERITY") == "CRITICAL,HIGH"
    assert env_cfg.get("FCS_EXCEPTIONS_FILE") == ".crowdstrike-fcs-exceptions.yaml"

    # Honest step summary when unconfigured
    fallback_steps = [
        step for step in fcs_steps if step.get("if") == "steps.fcs_gate.outputs.configured != 'true'"
    ]
    assert len(fallback_steps) == 1
    assert "CrowdStrike FCS non configuré" in str(fallback_steps[0].get("run", ""))

    # Never install or assume kernel-level Falcon sensor on managed PaaS
    forbidden_kernel_commands = (
        "apt-get install -y falcon-sensor",
        "yum install falcon-sensor",
        "dpkg -i falcon-sensor",
        "systemctl start falcon-sensor",
        "/opt/CrowdStrike/falconctl",
    )
    for forbidden in forbidden_kernel_commands:
        assert forbidden not in raw_text


# ---------------------------------------------------------------------------
# 2. Optional Activation: Disabled by Default -> Zero Network Calls & Honest Status
# ---------------------------------------------------------------------------


def test_crowdstrike_disabled_by_default_makes_zero_network_calls() -> None:
    network_calls: list[httpx.Request] = []

    def _forbidden_handler(request: httpx.Request) -> httpx.Response:
        network_calls.append(request)
        return httpx.Response(200, json={"text": "Success"})

    cfg = CrowdStrikeConfig.from_env({})
    assert cfg.siem_enabled is False
    connector = CrowdStrikeSIEMConnector(cfg, transport=httpx.MockTransport(_forbidden_handler))

    summary = connector.current_status_summary()
    assert summary["siem_enabled"] is False
    assert summary["status"] == CrowdStrikeConnectionStatus.DISABLED.value
    assert summary["verified"] is False
    assert summary["protected_by_crowdstrike"] is False
    assert "Protégé par CrowdStrike" not in summary["display_badge_fr"]
    assert "Protected by CrowdStrike" not in summary["display_badge_en"]
    assert summary["display_badge_fr"] == "Non configuré — mode natif actif"

    receipt = connector.emit_event(
        SecurityEventType.SUSPICIOUS_LOGIN_ATTEMPT,
        summary="Failed login while SIEM disabled",
        outcome="denied",
    )
    assert receipt.buffered_locally is True
    assert receipt.delivered_to_siem is False
    assert receipt.status == CrowdStrikeConnectionStatus.DISABLED.value

    conn_check = connector.test_connection()
    assert conn_check.status == CrowdStrikeConnectionStatus.DISABLED.value
    assert conn_check.verified is False
    assert conn_check.protected_by_crowdstrike is False
    assert len(network_calls) == 0


# ---------------------------------------------------------------------------
# 3. Missing Secret vs Invalid Secret (401/403) vs Unreachable vs Verified
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 403])
def test_missing_and_invalid_credentials_never_leak_secrets(
    status_code: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    synthetic_hec_secret = "hec-secret-" + secrets.token_urlsafe(24)
    hec_url = "https://ingest.us-2.crowdstrike.example/services/collector/event"

    # 3a. Enabled but missing token -> missing_credentials, zero HTTP calls
    missing_calls = 0

    def _count_handler(_req: httpx.Request) -> httpx.Response:
        nonlocal missing_calls
        missing_calls += 1
        return httpx.Response(200)

    missing_cfg = CrowdStrikeConfig.from_env({
        "CROWDSTRIKE_SIEM_ENABLED": "true",
        "CROWDSTRIKE_HEC_URL": hec_url,
    })
    missing_connector = CrowdStrikeSIEMConnector(
        missing_cfg, transport=httpx.MockTransport(_count_handler)
    )
    missing_res = missing_connector.test_connection()
    assert missing_res.status == CrowdStrikeConnectionStatus.MISSING_CREDENTIALS.value
    assert missing_res.verified is False
    assert missing_res.protected_by_crowdstrike is False
    assert missing_calls == 0

    # 3b. Enabled with invalid token -> HTTP 401/403 -> invalid_credentials, zero secret leak
    def _unauthorized_handler(req: httpx.Request) -> httpx.Response:
        assert req.headers.get("Authorization") == f"Bearer {synthetic_hec_secret}"
        return httpx.Response(status_code, json={"text": "Invalid token", "code": 4})

    invalid_cfg = CrowdStrikeConfig.from_env({
        "CROWDSTRIKE_SIEM_ENABLED": "true",
        "CROWDSTRIKE_HEC_URL": hec_url,
        "CROWDSTRIKE_HEC_TOKEN": synthetic_hec_secret,
    })
    assert synthetic_hec_secret not in repr(invalid_cfg)

    caplog.set_level(logging.DEBUG)
    invalid_connector = CrowdStrikeSIEMConnector(
        invalid_cfg, transport=httpx.MockTransport(_unauthorized_handler)
    )
    invalid_res = invalid_connector.test_connection()
    assert invalid_res.status == CrowdStrikeConnectionStatus.INVALID_CREDENTIALS.value
    assert invalid_res.http_status == status_code
    assert invalid_res.verified is False
    assert invalid_res.protected_by_crowdstrike is False

    serialized_res = json.dumps(invalid_res.to_dict())
    assert synthetic_hec_secret not in serialized_res
    assert synthetic_hec_secret not in caplog.text


def test_unreachable_siem_opens_circuit_breaker_and_never_breaks_caller() -> None:
    attempts = 0

    def _failing_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectTimeout("HEC collector timed out", request=request)

    cfg = CrowdStrikeConfig.from_env({
        "CROWDSTRIKE_SIEM_ENABLED": "true",
        "CROWDSTRIKE_HEC_URL": "https://ingest.crowdstrike.example/services/collector",
        "CROWDSTRIKE_HEC_TOKEN": "hec-" + secrets.token_urlsafe(18),
        "CROWDSTRIKE_HEC_CIRCUIT_FAILURE_THRESHOLD": "2",
        "CROWDSTRIKE_HEC_CIRCUIT_COOLDOWN_SECONDS": "60",
    })
    connector = CrowdStrikeSIEMConnector(cfg, transport=httpx.MockTransport(_failing_handler))

    r1 = connector.emit_event(SecurityEventType.REPEATED_API_ERROR_SPIKE, summary="Spike 1")
    r2 = connector.emit_event(SecurityEventType.REPEATED_API_ERROR_SPIKE, summary="Spike 2")
    # 3rd call hits open circuit breaker immediately without hanging on network timeout
    r3 = connector.emit_event(SecurityEventType.REPEATED_API_ERROR_SPIKE, summary="Spike 3")

    assert r1.status == CrowdStrikeConnectionStatus.UNREACHABLE.value
    assert r2.status == CrowdStrikeConnectionStatus.UNREACHABLE.value
    assert r3.status == "circuit_open"
    assert attempts == 2


# ---------------------------------------------------------------------------
# 4. All 10 Normalized Security Event Categories Validated
# ---------------------------------------------------------------------------


def test_all_10_normalized_security_event_categories_and_schema() -> None:
    expected_10 = {
        "suspicious_login_attempt",
        "repeated_mfa_failure",
        "cross_tenant_access_attempt",
        "rbac_permission_denied",
        "forbidden_tool_invocation",
        "suspicious_role_modification",
        "abnormal_token_or_credit_activity",
        "repeated_api_error_spike",
        "secret_or_config_modification",
        "file_upload_security_event",
    }
    assert set(ALL_SECURITY_EVENT_TYPES) == expected_10
    assert len(ALL_SECURITY_EVENT_TYPES) == 10

    emitted_payloads: list[dict[str, Any]] = []

    def _capture_hec(request: httpx.Request) -> httpx.Response:
        emitted_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"text": "Success", "code": 0})

    cfg = CrowdStrikeConfig.from_env({
        "CROWDSTRIKE_SIEM_ENABLED": "true",
        "CROWDSTRIKE_HEC_URL": "https://ingest.crowdstrike.example/services/collector",
        "CROWDSTRIKE_HEC_TOKEN": "hec-" + secrets.token_urlsafe(18),
        "ENVIRONMENT": "sandbox",
    })
    connector = CrowdStrikeSIEMConnector(cfg, transport=httpx.MockTransport(_capture_hec))

    conn_res = connector.test_connection()
    assert conn_res.status == CrowdStrikeConnectionStatus.CONNECTED_VERIFIED.value
    assert conn_res.verified is True
    assert conn_res.protected_by_crowdstrike is True

    emitted_payloads.clear()
    for category in ALL_SECURITY_EVENT_TYPES:
        receipt = connector.emit_event(
            category,
            summary=f"Validation test for {category}",
            outcome="detected",
            details={"status_code": 403, "category_checked": category},
        )
        assert receipt.delivered_to_siem is True
        assert receipt.status == "delivered"

    assert len(emitted_payloads) == 10
    observed_types = set()
    for envelope in emitted_payloads:
        assert envelope["sourcetype"] == "avenqo:security:event"
        assert isinstance(envelope["time"], float)
        ev = envelope["event"]
        assert ev["vendor"] == "avenqo"
        assert ev["product"] == "avenqo-platform"
        assert ev["environment"] == "sandbox"
        assert ev["severity"] in {"low", "medium", "high", "critical"}
        observed_types.add(ev["event_type"])

    assert observed_types == expected_10

    with pytest.raises(ValueError, match="Unsupported security event type"):
        build_normalized_event("unknown_custom_category", summary="Must fail")


# ---------------------------------------------------------------------------
# 5. Strict Secret, PIN, JWT, API Key, Document & Voice Transcript Scrubbing
# ---------------------------------------------------------------------------


def test_strict_scrubbing_strips_pins_jwts_api_keys_documents_and_transcripts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured_raw_bodies: list[str] = []

    def _capture_raw(request: httpx.Request) -> httpx.Response:
        captured_raw_bodies.append(request.content.decode("utf-8"))
        return httpx.Response(200, json={"text": "Success"})

    cfg = CrowdStrikeConfig.from_env({
        "CROWDSTRIKE_SIEM_ENABLED": "true",
        "CROWDSTRIKE_HEC_URL": "https://ingest.crowdstrike.example/services/collector",
        "CROWDSTRIKE_HEC_TOKEN": "hec-" + secrets.token_urlsafe(18),
    })
    connector = CrowdStrikeSIEMConnector(cfg, transport=httpx.MockTransport(_capture_raw))

    # Build synthetic sensitive markers at runtime so static secret scanners stay clean
    sensitive_pin = "123456"
    sensitive_nip = "847291"
    inline_pin = "4928"
    synthetic_jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwidGVuYW50IjoiYXZlbnFvIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    synthetic_sk = "sk-" + "liveSecretKeyMaterial998877"
    synthetic_bearer = "Bearer " + "topSecretSessionBearerTokenXYZ987"
    private_doc_body = "CONFIDENTIAL ACQUISITION AGREEMENT — PRICE CAD 4,200,000 CLAUSE 14"
    private_voice_transcript = "Bonjour, voici ma transcription vocale confidentielle avec le client Tremblay."
    user_password = "MyUltraSecretPassword!2026"
    synthetic_db_secret = "SyntheticDbSecret" + secrets.token_hex(4)
    synthetic_dsn = "postgresql" + "://avenqo_app:" + synthetic_db_secret + "@db.internal:5432/avenqo"

    caplog.set_level(logging.DEBUG)
    receipt = connector.emit_event(
        SecurityEventType.FORBIDDEN_TOOL_INVOCATION,
        summary=f"Caller entered PIN: {inline_pin} with {synthetic_bearer} and key {synthetic_sk}",
        outcome="blocked",
        company_id="550e8400-e29b-41d4-a716-446655440000",
        details={
            "pin": sensitive_pin,
            "callerNip": sensitive_nip,
            "password": user_password,
            "jwt": synthetic_jwt,
            "authorization": synthetic_bearer,
            "openai_api_key": synthetic_sk,
            "cookie": "avenqo_access_token=" + synthetic_jwt,
            "document_body": private_doc_body,
            "raw_content": private_doc_body,
            "transcript": private_voice_transcript,
            "nested": {
                "voice_transcript": private_voice_transcript,
                "note": f"Attempted keypad {sensitive_pin} and token {synthetic_jwt}",
                "dsn": synthetic_dsn,
            },
            "tool_name": "export_accounting_ledger",
            "status_code": 403,
        },
    )
    assert receipt.delivered_to_siem is True
    assert len(captured_raw_bodies) == 1

    emitted_body = captured_raw_bodies[0]
    recent_json = json.dumps(connector.recent_events(limit=5))

    forbidden_leaks = [
        sensitive_pin,
        sensitive_nip,
        inline_pin,
        synthetic_jwt,
        synthetic_sk,
        "topSecretSessionBearerTokenXYZ987",
        private_doc_body,
        private_voice_transcript,
        user_password,
        synthetic_db_secret,
    ]
    for secret_fragment in forbidden_leaks:
        assert secret_fragment not in emitted_body, f"Leaked {secret_fragment!r} into HEC payload!"
        assert secret_fragment not in recent_json, f"Leaked {secret_fragment!r} into recent_events!"
        assert secret_fragment not in caplog.text, f"Leaked {secret_fragment!r} into logs!"

    # Safe operational fields and tenant UUID remain intact
    parsed = json.loads(emitted_body)["event"]
    assert parsed["company_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert parsed["details"]["tool_name"] == "export_accounting_ledger"
    assert parsed["details"]["status_code"] == 403
    assert parsed["details"]["pin"] == "[REDACTED]"
    assert parsed["details"]["document_body"] == "[REDACTED]"
    assert parsed["details"]["transcript"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# 6. Admin Security RBAC (`401`/`403`), Cross-Tenant Isolation & Auth Hardening
# ---------------------------------------------------------------------------


def test_admin_security_endpoints_enforce_strict_rbac_and_honest_posture(auth_environment) -> None:
    client, session_factory, notifier = auth_environment

    tenant_a_owner = _register_and_login(client, notifier, "owner-a@acme.ca", "Acme Alpha")
    tenant_b_owner = _register_and_login(client, notifier, "owner-b@beta.ca", "Beta Corp")
    platform_finance = _register_and_login(client, notifier, "finance@avenqo.ca", "Avenqo Finance")
    platform_sec_admin = _register_and_login(client, notifier, "secadmin@avenqo.ca", "Avenqo SecOps")

    # Verify B1 auth hardening: login response carries Cache-Control: no-store
    fresh_login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner-a@acme.ca", "password": NON_SENSITIVE_TEST_PASSWORD},
    )
    assert fresh_login_res.status_code == 200
    assert fresh_login_res.headers.get("cache-control") == "no-store"
    assert fresh_login_res.headers.get("pragma") == "no-cache"
    client.cookies.clear()

    with session_factory() as db:
        fin_user = db.scalar(select(User).where(User.email == "finance@avenqo.ca"))
        assert fin_user is not None
        fin_user.is_platform_admin = True
        fin_user.platform_role = "PLATFORM_FINANCE"

        sec_user = db.scalar(select(User).where(User.email == "secadmin@avenqo.ca"))
        assert sec_user is not None
        sec_user.is_platform_admin = True
        sec_user.platform_role = "PLATFORM_SECURITY_AUDITOR"

        b_user = db.scalar(select(User).where(User.email == "owner-b@beta.ca"))
        assert b_user is not None
        b_user.role = UserRole.ADMIN
        db.commit()

    # 1) Unauthenticated -> 401
    assert client.get("/api/v1/admin/security/posture").status_code == 401
    assert client.get("/api/v1/admin/security/events").status_code == 401
    assert client.post("/api/v1/admin/security/crowdstrike/test-connection").status_code == 401

    # 2) Non-admin Tenant A OWNER & Tenant B ADMIN -> 403 on every route
    for non_admin_login in (tenant_a_owner, tenant_b_owner):
        hdrs = _bearer_headers(non_admin_login)
        assert client.get("/api/v1/admin/security/posture", headers=hdrs).status_code == 403
        assert client.get("/api/v1/admin/security/events", headers=hdrs).status_code == 403
        assert client.post("/api/v1/admin/security/crowdstrike/test-connection", headers=hdrs).status_code == 403

    # 3) Platform admin with non-security role (PLATFORM_FINANCE) -> 403
    fin_hdrs = _bearer_headers(platform_finance)
    assert client.get("/api/v1/admin/security/posture", headers=fin_hdrs).status_code == 403
    assert client.post("/api/v1/admin/security/crowdstrike/test-connection", headers=fin_hdrs).status_code == 403

    # 4) Trigger a cross-tenant switch attempt from Tenant A -> Tenant B -> 403 + normalized alert
    cross_switch = client.post(
        "/api/v1/auth/switch-tenant",
        headers=_bearer_headers(tenant_a_owner),
        json={"company_id": tenant_b_owner["company"]["id"]},
    )
    assert cross_switch.status_code == 403

    # 5) Authorized PLATFORM_SECURITY_AUDITOR -> 200 with honest native posture & normalized events
    sec_hdrs = _bearer_headers(platform_sec_admin)
    posture_res = client.get("/api/v1/admin/security/posture", headers=sec_hdrs)
    assert posture_res.status_code == 200
    posture = posture_res.json()
    assert posture["crowdstrike"]["siem_enabled"] is False
    assert posture["crowdstrike"]["status"] == "disabled"
    assert posture["crowdstrike"]["protected_by_crowdstrike"] is False
    assert posture["crowdstrike"]["fcs_ci_workflow_present"] is True
    assert len(posture["controls"]) == 10

    # SQLite test DB must honestly report non-PostgreSQL RLS session
    rls_ctrl = next(c for c in posture["controls"] if c["id"] == "postgres_tenant_rls")
    assert rls_ctrl["evidence"]["postgresql_rls_active"] is False

    test_conn_res = client.post("/api/v1/admin/security/crowdstrike/test-connection", headers=sec_hdrs)
    assert test_conn_res.status_code == 200
    assert test_conn_res.json()["status"] == "disabled"
    assert test_conn_res.json()["protected_by_crowdstrike"] is False

    events_res = client.get("/api/v1/admin/security/events?limit=20", headers=sec_hdrs)
    assert events_res.status_code == 200
    events_payload = events_res.json()
    event_types = {ev["event_type"] for ev in events_payload["events"]}
    assert "rbac_permission_denied" in event_types
    assert "cross_tenant_access_attempt" in event_types


def test_security_posture_service_direct_evaluation() -> None:
    svc = SecurityPostureService()
    posture = svc.evaluate_posture()
    assert posture["summary_counts"]["total_controls"] == 10
    assert posture["crowdstrike"]["kernel_sensor_assumed"] is False
    assert posture["crowdstrike"]["deployment_mode"] == "managed_paas_agentless"
