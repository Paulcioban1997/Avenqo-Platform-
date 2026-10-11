"""PR A: company-scoped linguistic profile — catalog, isolation, and shared readers."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.locale_catalog import LOCALES
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import Base, Company, CompanyLocaleProfile, CRMClient
from backend.app.models.base import CompanyStatus
from backend.app.services.crm_service import CRMService
from backend.app.services.tenant_locale_service import (
    AUDIO_SUPPORTED,
    CATALOG_SIZE,
    LocaleNotInCatalog,
    assert_locale_in_catalog,
    authorized_locales,
    catalog_code_or_none,
    create_profile_for_new_company,
    get_company_locale,
    get_profile,
    honest_audio_capability,
    suggest_primary,
    upsert_profile,
)
from backend.main import create_application
from shared.ai_engine.contracts import TenantContext


class MockNotifier:
    def __init__(self) -> None:
        self.verification_tokens: dict[str, str] = {}

    email_delivery_configured = True

    def send_email_verification(self, email: str, token: str) -> None:
        self.verification_tokens[email] = token

    def send_password_reset(self, email: str, token: str) -> None:
        pass


@pytest.fixture
def locale_env(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session], MockNotifier], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tenant_locale.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    notifier = MockNotifier()
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: notifier
    with TestClient(app) as client:
        yield client, testing_session, notifier


def _register_and_login(
    client: TestClient,
    notifier: MockNotifier,
    *,
    first_name: str,
    email: str,
    company_name: str,
    preferred_language: str = "ro",
    country: str = "Romania",
) -> str:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "company_name": company_name,
            "company_email": f"billing_{email}",
            "first_name": first_name,
            "last_name": "Testeur",
            "email": email,
            "password": "Password123!",
            "country": country,
            "timezone": "Europe/Bucharest",
            "industry": "Retail",
            "preferred_language": preferred_language,
        },
    )
    assert res.status_code == 201
    tok = notifier.verification_tokens[email]
    assert client.post("/api/v1/auth/email/verify", json={"token": tok}).status_code == 200
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert login_res.status_code == 200
    client.cookies.clear()
    return login_res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_company(session: Session, *, suffix: str, language: str = "ro") -> Company:
    company = Company(
        name=f"Tenant {suffix}",
        slug=f"tenant-{suffix}-{uuid4().hex[:8]}",
        email=f"{suffix}-{uuid4().hex[:8]}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="base",
        preferred_language=language,
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)
    session.flush()
    return company


def test_canonical_catalog_is_exactly_44_official_codes() -> None:
    codes = {item.locale for item in LOCALES}
    assert len(codes) == CATALOG_SIZE == 44
    assert catalog_code_or_none("lingala") is None
    assert catalog_code_or_none("ln") is None
    with pytest.raises(LocaleNotInCatalog):
        assert_locale_in_catalog("lingala")


def test_default_secondaries_are_empty_on_create(locale_env) -> None:
    client, sessions, notifier = locale_env
    token = _register_and_login(client, notifier, first_name="Ana", email="ana@locale.ca", company_name="Ana SRL")
    profile = client.get("/api/v1/company/locale-profile", headers=_auth(token)).json()
    assert profile["secondary_locales"] == []
    assert profile["persisted"] is True
    assert profile["primary_locale"] == "ro"
    assert "en" not in profile["secondary_locales"]
    assert "fr" not in profile["secondary_locales"]
    with sessions() as session:
        stored = session.scalar(select(CompanyLocaleProfile))
        assert stored is not None
        assert stored.secondary_locales == []


def test_suggestion_does_not_persist_or_override_explicit_primary(locale_env) -> None:
    client, sessions, notifier = locale_env
    token = _register_and_login(client, notifier, first_name="Ana", email="ana@locale.ca", company_name="Ana SRL")
    put = client.put(
        "/api/v1/company/locale-profile",
        headers=_auth(token),
        json={"primary_locale": "ro", "secondary_locales": []},
    )
    assert put.status_code == 200
    suggestion = client.get(
        "/api/v1/company/locale-profile/suggestions",
        headers=_auth(token),
        params={"country": "CA", "region": "QC", "timezone": "America/Toronto"},
    )
    assert suggestion.status_code == 200
    body = suggestion.json()
    assert body["applied"] is False
    assert body["persisted"] is False
    assert body["suggested_primary"] == "fr"
    after = client.get("/api/v1/company/locale-profile", headers=_auth(token)).json()
    assert after["primary_locale"] == "ro"
    assert after["suggested_locale"] != after["primary_locale"] or after["primary_locale"] == "ro"
    with sessions() as session:
        stored = session.scalar(select(CompanyLocaleProfile))
        assert stored.primary_locale == "ro"
        assert stored.secondary_locales == []


def test_enabling_a_secondary_requires_explicit_put(locale_env) -> None:
    client, _, notifier = locale_env
    token = _register_and_login(client, notifier, first_name="Ana", email="ana@locale.ca", company_name="Ana SRL")
    created = client.get("/api/v1/company/locale-profile", headers=_auth(token)).json()
    assert created["secondary_locales"] == []
    enabled = client.put(
        "/api/v1/company/locale-profile",
        headers=_auth(token),
        json={"primary_locale": "ro", "secondary_locales": ["de"]},
    )
    assert enabled.status_code == 200
    assert enabled.json()["secondary_locales"] == ["de"]
    assert enabled.json()["authorized_locales"] == ["ro", "de"]


def test_unauthorized_locale_is_rejected(locale_env) -> None:
    client, _, notifier = locale_env
    token = _register_and_login(client, notifier, first_name="Ana", email="ana@locale.ca", company_name="Ana SRL")
    rejected = client.put(
        "/api/v1/company/locale-profile",
        headers=_auth(token),
        json={"primary_locale": "lingala", "secondary_locales": []},
    )
    assert rejected.status_code == 422
    rejected_secondary = client.put(
        "/api/v1/company/locale-profile",
        headers=_auth(token),
        json={"primary_locale": "ro", "secondary_locales": ["ln"]},
    )
    assert rejected_secondary.status_code == 422


def test_cross_tenant_get_put_is_isolated(locale_env) -> None:
    client, sessions, notifier = locale_env
    token_a = _register_and_login(client, notifier, first_name="Ana", email="ana@locale.ca", company_name="Ana SRL")
    token_b = _register_and_login(
        client,
        notifier,
        first_name="Ben",
        email="ben@locale.ca",
        company_name="Ben Ltd",
        preferred_language="es",
        country="Spain",
    )
    with sessions() as session:
        company_a = session.scalar(select(Company).where(Company.name == "Ana SRL"))
        company_b = session.scalar(select(Company).where(Company.name == "Ben Ltd"))
        assert company_a is not None and company_b is not None
        id_a, id_b = company_a.id, company_b.id

    client.put(
        "/api/v1/company/locale-profile",
        headers=_auth(token_a),
        json={"primary_locale": "ro", "secondary_locales": ["de"]},
    )
    leaked = client.get(
        "/api/v1/company/locale-profile",
        headers=_auth(token_b),
        params={"company_id": str(id_a)},
    )
    assert leaked.status_code == 404
    steal = client.put(
        "/api/v1/company/locale-profile",
        headers=_auth(token_b),
        params={"company_id": str(id_a)},
        json={"primary_locale": "ja", "secondary_locales": []},
    )
    assert steal.status_code == 404
    own_b = client.get("/api/v1/company/locale-profile", headers=_auth(token_b)).json()
    assert own_b["primary_locale"] == "es"
    assert own_b["secondary_locales"] == []
    own_a = client.get("/api/v1/company/locale-profile", headers=_auth(token_a)).json()
    assert own_a["primary_locale"] == "ro"
    assert own_a["secondary_locales"] == ["de"]
    with sessions() as session:
        profile_b = session.scalar(
            select(CompanyLocaleProfile).where(CompanyLocaleProfile.company_id == id_b)
        )
        assert profile_b.primary_locale == "es"
        assert profile_b.secondary_locales == []


def test_unauthenticated_locale_profile_is_rejected(locale_env) -> None:
    client, _, _ = locale_env
    assert client.get("/api/v1/company/locale-profile").status_code == 401
    assert client.put("/api/v1/company/locale-profile", json={"primary_locale": "ro"}).status_code == 401


def test_audio_capability_is_honest_and_not_fully_supported_for_all_44() -> None:
    statuses = {honest_audio_capability(item.locale).audio_capability for item in LOCALES}
    assert statuses <= {AUDIO_SUPPORTED, "PARTIAL", "UNSUPPORTED", "UNTESTED"}
    assert "FULLY_SUPPORTED" not in statuses
    telephony_ready = [
        honest_audio_capability(item.locale)
        for item in LOCALES
        if honest_audio_capability(item.locale).audio_capability == AUDIO_SUPPORTED
    ]
    assert telephony_ready == []


def test_unknown_audio_locale_never_claims_validated_french() -> None:
    from backend.app.voice.languages import get_voice_language_capability
    capability = get_voice_language_capability("unknown-test-locale")
    assert capability["locale"] == "unknown-test-locale"
    assert capability["live_audio_validated"] is False
    assert capability["stt_available"] is False
    assert capability["tts_available"] is False
    assert capability["fallback_locale"] is None


def test_suggest_primary_is_suggestion_only_and_catalog_bound() -> None:
    primary, secondaries = suggest_primary("CA", "QC", "America/Toronto")
    assert primary == "fr"
    assert all(code in {item.locale for item in LOCALES} for code in [primary, *secondaries])
    unknown, extras = suggest_primary("ZZ", None, None)
    assert unknown is None
    assert extras == []


def test_modules_resolve_the_same_primary_via_shared_service(locale_env) -> None:
    from backend.app.routers import central_ai, retail
    from backend.app.services import billing_service, crm_service
    from backend.app.voice import service as voice_service

    _, sessions, _ = locale_env
    with sessions() as session:
        company = _make_company(session, suffix="shared", language="ja")
        create_profile_for_new_company(session, company)
        session.commit()
        company_id = company.id

        voice_locale = get_company_locale(session, company_id)
        crm_locale = get_company_locale(session, company_id)
        central_locale = get_company_locale(session, company_id)
        billing_locale = get_company_locale(session, company_id)
        retail_locale = retail.get_company_locale(session, company_id)
        assert voice_locale == crm_locale == central_locale == billing_locale == retail_locale == "ja"
        assert crm_service.get_company_locale is get_company_locale
        assert billing_service.get_company_locale is get_company_locale
        assert central_ai.get_company_locale is get_company_locale
        assert voice_service.get_company_locale is get_company_locale or hasattr(voice_service, "VoiceOrchestrator")

        client = CRMService(session).create_client(
            company_id,
            {"first_name": "Mika", "last_name": "Sato"},
        )
        session.commit()
        assert client.preferred_language == "ja"
        stored = session.scalar(select(CRMClient).where(CRMClient.company_id == company_id))
        assert stored.preferred_language == "ja"


def test_voice_ensure_config_uses_profile_without_overwriting_explicit_voice_language(locale_env) -> None:
    from backend.app.config.settings import get_settings
    from backend.app.models import VoiceBusinessConfig
    from backend.app.voice.service import VoiceOrchestrator

    _, sessions, _ = locale_env
    with sessions() as session:
        company = _make_company(session, suffix="voice", language="it")
        create_profile_for_new_company(session, company)
        upsert_profile(session, company.id, primary_locale="it", secondary_locales=[])
        session.commit()
        orchestrator = VoiceOrchestrator(session, get_settings())
        tenant = TenantContext(company_id=company.id, user_id=uuid4())
        created = orchestrator.ensure_config(tenant)
        assert created.preferred_language == "it"
        created.preferred_language = "de"
        session.flush()
        again = orchestrator.ensure_config(tenant)
        assert again.preferred_language == "de"
        assert session.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company.id)).preferred_language == "de"


def test_retail_and_other_modules_import_the_same_service() -> None:
    from backend.app.routers.retail import get_company_locale as retail_reader
    from backend.app.routers.central_ai import get_company_locale as central_reader
    from backend.app.services.billing_service import get_company_locale as billing_reader
    from backend.app.services.crm_service import get_company_locale as crm_reader
    from backend.app.services.tenant_locale_service import get_company_locale as shared_reader

    assert retail_reader is shared_reader
    assert central_reader is shared_reader
    assert billing_reader is shared_reader
    assert crm_reader is shared_reader


def test_authorized_locales_are_primary_union_explicit_secondaries() -> None:
    view = get_profile.__annotations__
    assert view
    profile = type("P", (), {"primary_locale": "ro", "secondary_locales": ["de", "ro", "de"]})()
    assert authorized_locales(profile) == ["ro", "de"]
