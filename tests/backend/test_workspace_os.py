"""Workspace OS, documents, automations, MFA and tenant isolation."""

from __future__ import annotations

from uuid import UUID

from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.totp import totp_code, verify_totp
from modules.registry import BUSINESS_MODULES_BY_KEY, ModuleAvailability
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_auth import auth_environment, registration_payload, verify_and_login
from tests.backend.test_security_center import account, headers
from tests.subscription_helpers import activate_subscription_by_id


def _ready(client, factory, notifier, email, name, modules=()):
    login = account(client, notifier, email, name)
    with factory() as db:
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
    assert client.post(
        f"/api/v1/workspace/tasks/{created.json()['id']}/complete",
        headers=headers(other),
    ).status_code == 404


def test_invitation_respects_user_quota(auth_environment):
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
            "password": "Avenqo2026!",
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
    first = _ready(client, factory, notifier, "docs-a@example.ca", "Docs A", modules=("ocr", "legal"))
    other = _ready(client, factory, notifier, "docs-b@example.ca", "Docs B", modules=("ocr", "legal"))
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


def test_media_generation_does_not_invent_kpis(auth_environment):
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
    assert "3.8" not in body and "ROI" not in body


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


def test_marketplace_marks_etsy_and_outlook_as_future(auth_environment):
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "market@example.ca", "Market Co")
    catalog = client.get("/api/v1/marketplace", headers=headers(owner)).json()
    etsy = next(item for item in catalog["connectors"] if item["key"] == "etsy")
    outlook = next(item for item in catalog["connectors"] if item["key"] == "outlook_calendar")
    assert etsy["availability"] == "coming_soon"
    assert outlook["availability"] == "coming_soon"
    assert next(item for item in catalog["connectors"] if item["key"] == "shopify")["availability"] == "available"


def test_mfa_enroll_confirm_and_login(auth_environment):
    client, factory, notifier = auth_environment
    owner = account(client, notifier, "mfa@example.ca", "MFA Co")
    enroll = client.post("/api/v1/security/mfa/enroll", headers=headers(owner))
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    confirm = client.post(
        "/api/v1/security/mfa/confirm",
        headers=headers(owner),
        json={"code": totp_code(secret)},
    )
    assert confirm.status_code == 200
    overview = client.get("/api/v1/security/overview", headers=headers(owner))
    assert overview.status_code == 200
    assert overview.json()["mfa_enabled"] is True
    blocked = client.post("/api/v1/auth/login", json={"email": "mfa@example.ca", "password": "Avenqo2026!"})
    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "mfa_required"
    allowed = client.post(
        "/api/v1/auth/login",
        json={"email": "mfa@example.ca", "password": "Avenqo2026!", "otp": totp_code(secret)},
    )
    assert allowed.status_code == 200
    history = client.get("/api/v1/security/login-history", headers={"Authorization": f"Bearer {allowed.json()['access_token']}"})
    assert history.status_code == 200
    assert history.json()


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
