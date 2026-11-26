from uuid import uuid4
from shared.ai_engine.contracts import TenantContext
from backend.app.voice import service

def test_source_refresh_replaces_old_snapshot_and_preserves_call_identity(monkeypatch):
    tenant = TenantContext(company_id=uuid4(), user_id=uuid4())
    old = {"state": "READY", "sources": [{"source_id": "old"}], "business_profile": {"business_name": "Old"}, "resolved_at": "before", "routing_nip": "retained", "ivr_stage": "staff_authenticated"}
    fresh = {"state": "READY", "sources": [{"source_id": "new"}], "business_profile": {"business_name": "Current"}, "resolved_at": "now"}
    monkeypatch.setattr(service, "resolve_voice_source_context", lambda db, identity: fresh if identity == tenant else {})
    result = service.refresh_voice_source_context(object(), tenant, old)
    assert result["sources"] == fresh["sources"]
    assert result["business_profile"] == fresh["business_profile"]
    assert result["resolved_at"] == "now"
    assert result["routing_nip"] == "retained"
    assert result["ivr_stage"] == "staff_authenticated"
    assert old["sources"] == [{"source_id": "old"}]

def test_unavailable_source_clears_previous_call_data(monkeypatch):
    tenant = TenantContext(company_id=uuid4())
    monkeypatch.setattr(service, "resolve_voice_source_context", lambda *_: {"state": "SOURCE_UNAVAILABLE", "sources": [], "business_profile": None})
    result = service.refresh_voice_source_context(object(), tenant, {"sources": [{"source_id": "removed"}], "business_profile": {"business_name": "Old"}})
    assert result["sources"] == []
    assert result["business_profile"] is None
