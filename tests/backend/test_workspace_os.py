"""Workspace OS, documents, automations, MFA and tenant isolation."""

from __future__ import annotations

import secrets
import pytest
from uuid import UUID

from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.totp import totp_code, verify_totp
from modules.registry import BUSINESS_MODULES_BY_KEY, ModuleAvailability
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_auth import auth_environment, registration_payload, verify_and_login
from tests.backend.test_security_center import account, headers
from tests.subscription_helpers import activate_subscription_by_id


@pytest.fixture
def non_sensitive_test_password() -> str:
    """Ephemeral credential for this test's isolated TestClient database only.

    Never read from environment variables or used against hosted services.
    """
    return secrets.token_urlsafe(24) + "Aa1!"


def _ready(client, factory, notifier, email, name, modules=(), plan=None):
    login = account(client, notifier, email, name)
    with factory() as db:
        from backend.app.models import Company

        company = db.get(Company, UUID(str(login["company"]["id"])))
        if plan and company is not None:
            company.subscription_plan = plan
        activate_subscription_by_id(db, login["company"]["id"])
        service = ModuleEntitlementService(db)
        tenant = TenantContext(UUID(str(login["company"]["id"])))
        for key in modules:
            service.activate_module(tenant, key)
        db.commit()
    return login


def test_registry_does_not_advertise_unbuilt_modules():
    assert BUSINESS_MODULES_BY_KEY["appointments"].availability == ModuleAvailability.COMING_SOON
    assert BUSINESS_MODULES_BY_KEY["hr"].availability == ModuleAvailability.COMING_SOON
    assert BUSINESS_MODULES_BY_KEY["ocr"].is_available
    assert BUSINESS_MODULES_BY_KEY["workflow"].is_available


def test_totp_round_trip():
    from backend.app.services.totp import generate_totp_secret

    secret = generate_totp_secret()
    assert verify_totp(secret, totp_code(secret))
    assert not verify_totp(secret, "000000")


def test_tasks_and_guidance_are_tenant_scoped(auth_environment):
    client, factory, notifier = auth_environment
    first = _ready(client, factory, notifier, "owner-a@example.ca", "Alpha")
    other = _ready(client, factory, notifier, "owner-b@example.ca", "Beta")
    created = client.post(
        "/api/v1/workspace/tasks",
        headers=headers(first),
        json={"assignee_user_id": first["user"]["id"], "title": "Relancer les factures", "priority": "high"},
    )
    assert created.status_code == 201
    other_tasks = client.get("/api/v1/workspace/tasks", headers=headers(other))
    assert other_tasks.status_code == 200
    assert other_tasks.json() == []
    briefing = client.get("/api/v1/workspace/guidance", headers=headers(first)).json()
    assert briefing["user_id"] == first["user"]["id"]
    assert any(task["title"] == "Relancer les factures" for task in briefing["open_tasks"])
    asked = client.post(
        "/api/v1/workspace/guidance/ask",
        headers=headers(first),
        json={"question": "Quelles tâches sont prioritaires ?"},
    )
    assert asked.status_code == 200
    assert asked.json()["invented"] is False
    assert asked.json()["intent"] == "priority_tasks"
    assert client.post(
        f"/api/v1/workspace/tasks/{created.json()['id']}/complete",
        headers=headers(other),
    ).status_code == 404


def test_invitation_respects_user_quota(auth_environment, non_sensitive_test_password):
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "seats@example.ca", "Seats Co")
    first = client.post(
        "/api/v1/workspace/invitations",
        headers=headers(owner),
        json={"email": "one@example.ca", "job_title": "Reception"},
    )
    assert first.status_code == 201 and first.json()["token"]
    accepted = client.post(
        "/api/v1/workspace/invitations/accept",
        json={
            "token": first.json()["token"],
            "first_name": "Sam",
            "last_name": "Lee",
            "password": non_sensitive_test_password,
        },
    )
    assert accepted.status_code == 201
    second = client.post(
        "/api/v1/workspace/invitations",
        headers=headers(owner),
        json={"email": "two@example.ca"},
    )
    assert second.status_code == 201
    third = client.post(
        "/api/v1/workspace/invitations",
        headers=headers(owner),
        json={"email": "three@example.ca"},
    )
    # Base plan: owner + 2 accepted/pending seats; the third invite is refused.
    assert third.status_code == 409
    assert third.json()["error"]["code"] == "plan_limit_reached"


def test_ocr_and_legal_extract_real_text_and_stay_isolated(auth_environment, tmp_path, monkeypatch):
    from backend.app.config.settings import get_settings

    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    get_settings.cache_clear()
    client, factory, notifier = auth_environment
    first = _ready(
        client, factory, notifier, "docs-a@example.ca", "Docs A",
        modules=("ocr", "legal", "accounting"), plan="professional",
    )
    other = _ready(
        client, factory, notifier, "docs-b@example.ca", "Docs B",
        modules=("ocr", "legal", "accounting"), plan="professional",
    )
    upload = client.post(
        "/api/v1/ocr/documents",
        headers=headers(first),
        files={"file": ("invoice.txt", b"Invoice #INV-42\nTotal: 120.00 CAD\n", "text/plain")},
    )
    assert upload.status_code == 201
    assert "INV-42" in upload.json()["extracted_text"]
    assert upload.json()["classification"] == "invoice"
    assert client.get("/api/v1/ocr/documents", headers=headers(other)).json() == []
    legal = client.post(
        "/api/v1/legal/documents",
        headers=headers(first),
        files={"file": ("contract.txt", b"Clause 1: confidentiality.\nArticle 2: termination of the agreement.\n", "text/plain")},
    )
    assert legal.status_code == 201
    assert "avis juridique" in (legal.json()["disclaimer"] or "").lower()
    proposal = client.post(
        f"/api/v1/ocr/documents/{upload.json()['id']}/accounting-proposal",
        headers=headers(first),
    )
    assert proposal.status_code == 201
    assert proposal.json()["is_confirmed"] is False
    assert proposal.json()["total_amount"] == 120.0
    assert client.post(
        f"/api/v1/ocr/documents/{upload.json()['id']}/accounting-proposal",
        headers=headers(other),
    ).status_code == 404
    scanned = client.post(
        "/api/v1/ocr/documents",
        headers=headers(first),
        files={"file": ("scan.png", b"\x89PNG\r\n\x1a\nnot-a-real-image", "image/png")},
    )
    assert scanned.status_code == 422


def test_media_generation_does_not_invent_kpis(auth_environment, monkeypatch):
    from backend.app.ai.llm.schemas import LLMGeneration

    class FakeLLM:
        name = "test-llm"

        async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
            return LLMGeneration(content=f"Campagne:\n{prompt}", provider="test-llm", model="fake")

    monkeypatch.setattr(
        "backend.app.services.media_generation_service.resolve_media_llm",
        lambda: FakeLLM(),
    )
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "media@example.ca", "Media Co", modules=("media",))
    generated = client.post(
        "/api/v1/media/generations",
        headers=headers(owner),
        json={"prompt": "Relancer les clients inactifs de la boutique"},
    )
    assert generated.status_code == 201
    body = generated.json()["output_text"]
    assert "Relancer les clients inactifs" in body
    assert generated.json()["provider"] == "test-llm"
    assert "3.8" not in body and "ROI" not in body


def test_media_refuses_without_provider(auth_environment, monkeypatch):
    monkeypatch.setattr("backend.app.services.media_generation_service.resolve_media_llm", lambda: None)
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "media-empty@example.ca", "Media Empty", modules=("media",))
    generated = client.post(
        "/api/v1/media/generations",
        headers=headers(owner),
        json={"prompt": "Relancer les clients inactifs de la boutique"},
    )
    assert generated.status_code == 503


def test_automation_idempotency_and_module_gate(auth_environment):
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "auto@example.ca", "Auto Co", modules=("workflow",))
    created = client.post(
        "/api/v1/automations",
        headers=headers(owner),
        json={
            "name": "Tâche de suivi",
            "trigger_type": "manual",
            "action_type": "create_task",
            "action": {"title": "Appeler le client", "assignee_user_id": owner["user"]["id"]},
        },
    )
    assert created.status_code == 201
    first = client.post(
        f"/api/v1/automations/{created.json()['id']}/run",
        headers=headers(owner),
        json={"idempotency_key": "run-1"},
    )
    second = client.post(
        f"/api/v1/automations/{created.json()['id']}/run",
        headers=headers(owner),
        json={"idempotency_key": "run-1"},
    )
    assert first.status_code == 200 and first.json()["status"] == "completed"
    assert second.json()["id"] == first.json()["id"]
    tasks = client.get("/api/v1/workspace/tasks", headers=headers(owner)).json()
    assert any(task["title"] == "Appeler le client" for task in tasks)
    shopify = client.post(
        "/api/v1/automations",
        headers=headers(owner),
        json={
            "name": "Nouvelle commande",
            "trigger_type": "shopify_order",
            "action_type": "create_task",
            "action": {"title": "Analyser la commande", "assignee_user_id": owner["user"]["id"]},
        },
    )
    assert shopify.status_code == 201
    from backend.app.models import User
    from backend.app.services.automation_service import AutomationService

    with factory() as db:
        actor = db.get(User, UUID(owner["user"]["id"]))
        runs = AutomationService(db).dispatch(
            actor.company_id,
            "shopify_order",
            {"receipt_id": "wh-1", "topic": "orders/create"},
            actor=actor,
            idempotency_key="wh-1",
        )
        assert runs and runs[0].status == "completed"
    follow = client.get("/api/v1/workspace/tasks", headers=headers(owner)).json()
    assert any(task["title"] == "Analyser la commande" for task in follow)


def test_marketplace_marks_etsy_and_outlook_as_future(auth_environment):
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "market@example.ca", "Market Co")
    catalog = client.get("/api/v1/marketplace", headers=headers(owner)).json()
    etsy = next(item for item in catalog["connectors"] if item["key"] == "etsy")
    outlook = next(item for item in catalog["connectors"] if item["key"] == "outlook_calendar")
    assert etsy["availability"] == "coming_soon"
    assert outlook["availability"] == "available"
    assert next(item for item in catalog["connectors"] if item["key"] == "shopify")["availability"] == "available"


def test_mfa_enroll_confirm_and_login(auth_environment, non_sensitive_test_password):
    client, factory, notifier = auth_environment
    payload = registration_payload("mfa@example.ca", "MFA Co")
    payload["password"] = non_sensitive_test_password
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    owner = verify_and_login(client, notifier, payload["email"], non_sensitive_test_password)
    enroll = client.post("/api/v1/security/mfa/enroll", headers=headers(owner))
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    confirm = client.post(
        "/api/v1/security/mfa/confirm",
        headers=headers(owner),
        json={"code": totp_code(secret)},
    )
    assert confirm.status_code == 200
    recovery_codes = confirm.json()["recovery_codes"]
    assert len(recovery_codes) == 8
    overview = client.get("/api/v1/security/overview", headers=headers(owner))
    assert overview.status_code == 200
    assert overview.json()["mfa_enabled"] is True
    blocked = client.post("/api/v1/auth/login", json={"email": "mfa@example.ca", "password": non_sensitive_test_password})
    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "mfa_required"
    allowed = client.post(
        "/api/v1/auth/login",
        json={"email": "mfa@example.ca", "password": non_sensitive_test_password, "otp": totp_code(secret)},
    )
    assert allowed.status_code == 200
    recovered = client.post(
        "/api/v1/auth/login",
        json={"email": "mfa@example.ca", "password": non_sensitive_test_password, "otp": recovery_codes[0]},
    )
    assert recovered.status_code == 200
    reused = client.post(
        "/api/v1/auth/login",
        json={"email": "mfa@example.ca", "password": non_sensitive_test_password, "otp": recovery_codes[0]},
    )
    assert reused.status_code == 401
    history = client.get("/api/v1/security/login-history", headers={"Authorization": f"Bearer {allowed.json()['access_token']}"})
    assert history.status_code == 200
    assert history.json()


def test_login_lockout_after_repeated_failures(auth_environment):
    from backend.app.services.auth_service import AuthenticationError, AuthService

    client, factory, notifier = auth_environment
    account(client, notifier, "lock@example.ca", "Lock Co")
    with factory() as db:
        service = AuthService(db, notifier)
        for _ in range(8):
            try:
                service.login("lock@example.ca", "WrongPass1!")
            except AuthenticationError:
                pass
            else:
                raise AssertionError("wrong password should fail")
        try:
            service.login("lock@example.ca", "Avenqo2026!")
        except AuthenticationError as exc:
            assert "verrouillé" in str(exc)
        else:
            raise AssertionError("locked account should not authenticate")


def test_onboarding_draft_and_progress(auth_environment):
    client, factory, notifier = auth_environment
    owner = account(client, notifier, "onboard@example.ca", "Onboard Co")
    draft = client.post(
        "/api/v1/onboarding/draft",
        headers=headers(owner),
        json={"current_step": "modules", "business_goals": ["sell"], "refined_industry": "retail"},
    )
    assert draft.status_code == 200
    assert draft.json()["current_step"] == "modules"
    assert draft.json()["progress_percent"] >= 20
    assert any(item["key"] == "sector" and item["done"] for item in draft.json()["checklist"])
