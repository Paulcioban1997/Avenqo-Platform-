"""Exercise the actual HTTP route rather than the former duplicate helper."""
from sqlalchemy import select
from backend.app.models import User, VoiceCallerCredential, BillingAccount
from tests.backend.test_auth import auth_environment, registration_payload, verify_and_login

def test_central_http_endpoint_runs_included_when_subscription_inactive(auth_environment, monkeypatch):
    from backend.app.dependencies.central_ai import get_central_ai_service
    from tests.backend.test_central_ai import make_service, MeteredStubProvider
    client, factory, notifier = auth_environment
    payload = registration_payload("central-owner@example.ca", "CentralOwner")
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = verify_and_login(client, notifier, payload["email"])
    headers = {"Authorization": "Bearer " + login["access_token"]}
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload["email"]))
        account = db.scalar(select(BillingAccount).where(BillingAccount.company_id == user.company_id))
        account.status = "inactive"
        db.commit()
    conversation = client.post("/api/v1/ai/chat/conversations", headers=headers, json={"title": "Central included"})
    assert conversation.status_code == 201
    assert client.post(f"/api/v1/ai/chat/conversations/{conversation.json()['id']}/messages", headers=headers, json={"content": "Bonjour"}).status_code == 402
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload["email"]))
        provider = MeteredStubProvider(classification="general")
        central, _, usage, _ = make_service(db, user.company, provider, limit=1, retail_entitled=False)
        balance = usage._get_or_create_credits(user.company_id)
        balance.monthly_used = 100000
        db.commit()
        client.app.dependency_overrides[get_central_ai_service] = lambda: central
        from types import SimpleNamespace
        from uuid import uuid4
        from backend.app.services.retail_source_service import RetailSourceService
        source_id = uuid4()
        monkeypatch.setattr(RetailSourceService, "context", lambda self, tenant: {
            "state": "READY", "source_type": "all", "source_id": source_id,
            "sources": [SimpleNamespace(enabled=True, source_type="shopify", source_id=source_id, display_name="QA source")],
        })
        try:
            response = client.post(f"/api/v1/ai/central/conversations/{conversation.json()['id']}/messages",
                headers={**headers, "Idempotency-Key": "central-included-http"},
                json={"content": "Bonjour, aide-moi à utiliser Avenqo", "locale": "fr"})
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "success"
            assert response.json()["answer"]
            assert response.json()["grounded_source"] is None
            assert usage.get_credit_balance(user.company_id, "base")["monthly_used"] == 100000
        finally:
            client.app.dependency_overrides.pop(get_central_ai_service, None)

def test_pin_setup_is_available_without_subscription_normalizes_phone_and_reauthenticates(auth_environment):
    client, factory, notifier = auth_environment
    payload = registration_payload("pin-owner@example.ca", "PinOwner")
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = verify_and_login(client, notifier, payload["email"])
    headers = {"Authorization": "Bearer " + login["access_token"]}
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload["email"]))
        account = db.scalar(select(BillingAccount).where(BillingAccount.company_id == user.company_id))
        account.status = "inactive"
        db.commit()
    assert client.get("/api/v1/voice/auth/pin/status", headers=headers).status_code == 200
    body = {"pin": "907182", "confirm_pin": "907182", "phone_number": "514-555-0198"}
    assert client.put("/api/v1/voice/auth/pin", headers=headers, json=body).status_code == 400
    body["current_password"] = payload["password"]
    response = client.put("/api/v1/voice/auth/pin", headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/voice/auth/pin/status", headers=headers).json()["has_pin"]
    assert client.put("/api/v1/voice/auth/phone-access", headers=headers, json={"enabled": False}).status_code == 200
    assert not client.get("/api/v1/voice/auth/pin/status", headers=headers).json()["phone_access_enabled"]
    assert client.post("/api/v1/voice/auth/sessions/revoke", headers=headers).status_code == 200
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload["email"]))
        credential = db.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.principal_id == user.id))
        assert user.phone == credential.phone_number == "+15145550198"
        assert credential.pin_hash != body["pin"]
    body["current_password"] = "IncorrectPassword123!"
    assert client.put("/api/v1/voice/auth/pin", headers=headers, json=body).status_code == 403
