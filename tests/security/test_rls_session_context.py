from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from starlette.requests import Request

from backend.app.database.session import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.services.tenant_rls import apply_tenant_rls, set_rls_bypass
from shared.ai_engine.contracts import TenantContext


class _FakeSession:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def execute(self, statement, params=None):
        self.statements.append((str(statement), dict(params or {})))


def test_apply_tenant_rls_binds_company_and_disables_bypass() -> None:
    session = _FakeSession()
    company_id = uuid4()
    apply_tenant_rls(session, company_id)
    assert session.statements
    _sql, params = session.statements[-1]
    assert params["flag"] == "off"
    assert params["cid"] == str(company_id)


def test_set_rls_bypass_is_transaction_local() -> None:
    session = _FakeSession()
    set_rls_bypass(session, enabled=True)
    assert session.statements[-1][1]["flag"] == "on"
    set_rls_bypass(session, enabled=False)
    assert session.statements[-1][1]["flag"] == "off"


def test_get_db_does_not_enable_rls_bypass_by_default(monkeypatch) -> None:
    observed: list[bool] = []
    monkeypatch.setattr(
        "backend.app.services.tenant_rls.set_rls_bypass",
        lambda session, *, enabled: observed.append(enabled),
    )
    generator = get_db()
    next(generator)
    try:
        assert observed == []
    finally:
        generator.close()


def test_get_current_identity_applies_tenant_rls(monkeypatch) -> None:
    company_id = uuid4()
    user = SimpleNamespace(id=uuid4(), company_id=company_id, is_platform_admin=False)
    auth_session = SimpleNamespace()
    db = object()
    observed: list[tuple[object, object, bool]] = []

    def authenticate(_token: str):
        return auth_session, user

    monkeypatch.setattr(
        "backend.app.dependencies.auth.apply_tenant_rls",
        lambda session, cid, *, bypass=False: observed.append((session, cid, bypass)),
    )
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/crm/clients", "headers": []})
    identity = get_current_identity(
        request,
        credentials=SimpleNamespace(scheme="Bearer", credentials="access-token"),
        service=SimpleNamespace(authenticate=authenticate),
        db=db,
    )
    assert identity.user is user
    assert observed == [(db, company_id, False)]


def test_get_tenant_context_applies_tenant_rls_on_auth_path() -> None:
    company_id = uuid4()
    user_id = uuid4()
    identity = CurrentIdentity(
        auth_session=SimpleNamespace(),
        user=SimpleNamespace(company_id=company_id, id=user_id, is_platform_admin=False),
        raw_token="access-token",
    )
    db = _FakeSession()
    observed: list[tuple[object, object, bool]] = []

    from backend.app.dependencies import auth as auth_dep

    original = auth_dep.apply_tenant_rls

    def _capture(session, cid, *, bypass=False):
        observed.append((session, cid, bypass))
        return original(session, cid, bypass=bypass)

    auth_dep.apply_tenant_rls = _capture  # type: ignore[method-assign]
    try:
        tenant = get_tenant_context(identity, db)
    finally:
        auth_dep.apply_tenant_rls = original  # type: ignore[method-assign]

    assert tenant == TenantContext(company_id=company_id, user_id=user_id)
    assert observed == [(db, company_id, False)]
    assert db.statements[-1][1] == {"flag": "off", "cid": str(company_id)}


def test_retell_webhook_binds_tenant_after_company_id(monkeypatch) -> None:
    from backend.app.routers import voice as voice_router

    company_id = uuid4()
    observed: list[tuple[object, object]] = []
    monkeypatch.setattr(
        voice_router,
        "apply_tenant_rls",
        lambda session, cid, *, bypass=False: observed.append((session, cid)),
    )
    monkeypatch.setattr(voice_router, "_ensure_voice_access", lambda db, cid: None)
    db = SimpleNamespace()
    config = SimpleNamespace(company_id=company_id)
    service = SimpleNamespace(config_from_api_key=lambda _key: config)
    monkeypatch.setattr(voice_router, "_orchestrator", lambda _db, _settings: service)

    resolved, returned_service = voice_router._authenticated_voice_config(db, SimpleNamespace(), "avqv_key")
    assert resolved is config
    assert returned_service is service
    assert observed == [(db, company_id)]
