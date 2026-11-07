"""No provider calls: authoritative tenant aggregates and fail-closed credits."""
from types import SimpleNamespace
from uuid import UUID
from backend.app.ai.llm.schemas import LLMGeneration
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from tests.backend.test_auth import auth_environment
from tests.backend.test_workspace_os import _ready
from tests.backend.test_security_center import headers


def test_marketing_context_uses_server_tenant_and_selected_dates(auth_environment, monkeypatch):
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "marketing-fixture@example.ca", "Marketing fixture", modules=("marketing",))
    expected = UUID(owner["company"]["id"])
    observed = {}
    class Analytics:
        def build(self, tenant, **kwargs):
            assert tenant.company_id == expected
            observed["dates"] = (str(kwargs["date_from"]), str(kwargs["date_to"]))
            return {"available": True, "summary": {"total_customers": 17}, "segments": [], "currency": "CAD",
                    "source_context": {"name": "Isolated fixture"}, "items": [{"email": "never-send@example.test"}]}
    class LLM:
        async def generate(self, **kwargs):
            observed["context"] = kwargs["system_instruction"]
            return LLMGeneration(content="Réponse de test", provider="fixture", model="fixture")
    monkeypatch.setattr("backend.app.services.media_generation_service.resolve_media_analytics", lambda db: Analytics())
    monkeypatch.setattr("backend.app.services.media_generation_service.resolve_media_llm", lambda: LLM())
    response = client.post("/api/v1/media/generations", headers=headers(owner), json={
        "prompt": "Analyse les clients de notre entreprise", "period": "custom", "date_from": "2017-01-01", "date_to": "2017-12-31",
        "company_id": "foreign-tenant-ignored", "summary": {"total_customers": 999999}})
    assert response.status_code == 201, response.json()
    assert observed["dates"] == ("2017-01-01", "2017-12-31")
    assert '"total_customers": 17' in observed["context"]
    assert "999999" not in observed["context"] and "never-send" not in observed["context"]


def test_marketing_quota_failure_never_calls_provider(auth_environment, monkeypatch):
    client, factory, notifier = auth_environment
    owner = _ready(client, factory, notifier, "marketing-quota@example.ca", "Quota fixture", modules=("marketing",))
    calls = []
    class LLM:
        async def generate(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("Provider must not be called")
    monkeypatch.setattr("backend.app.services.media_generation_service.resolve_media_llm", lambda: LLM())
    def refuse(*args, **kwargs):
        raise AIQuotaExceededError("INSUFFICIENT_AI_CREDITS")
    monkeypatch.setattr("backend.app.ai.usage.service.AIUsageService.reserve_credits", refuse)
    response = client.post("/api/v1/media/generations", headers=headers(owner), json={"prompt": "Analyse nos données disponibles"})
    assert response.status_code == 402, response.json()
    assert calls == []
