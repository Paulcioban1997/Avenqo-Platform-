"""Display conversion keeps original amounts and each company's own currency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.security import create_access_token, hash_password
from backend.app.database import get_db
from backend.app.models import AuthSession, Base, Company, CompanyMembership, CompanyStatus, User, UserRole
from backend.app.services.fx_rates import convert_amount, quote_items
from backend.main import create_application
from tests.subscription_helpers import add_active_subscription


def test_transaction_date_uses_the_supplied_rate_and_a_failure_stays_original():
    shown = convert_amount(50, "CAD", "EUR", rate=0.67, rate_date="2026-01-15", on_date="2026-01-15")
    assert shown["valuation"] == "transaction_date"
    assert shown["converted"] is True
    assert shown["amount"] == 33.5
    assert shown["original_amount"] == 50
    assert shown["original_currency"] == "CAD"
    assert shown["currency"] == "EUR"
    assert shown["source"] == "ecb-frankfurter"

    failed = convert_amount(
        50,
        "CAD",
        "EUR",
        on_date="2026-01-15",
        fetch=lambda *_args: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert failed["converted"] is False
    assert failed["unavailable"] is True
    assert failed["amount"] == 50
    assert failed["currency"] == "CAD"
    assert failed["rate"] is None

    same = convert_amount(29.99, "CAD", "CAD", fetch=lambda *_args: (_ for _ in ()).throw(AssertionError("network")))
    assert same["converted"] is False
    assert same["unavailable"] is False
    assert same["currency"] == "CAD"
    assert same["amount"] == 29.99


def test_quote_items_ignore_a_client_company_and_do_not_invent_a_rate():
    def rates(source: str, target: str, on_date: str | None = None) -> tuple[float, str]:
        assert source == "USD"
        assert target == "CAD"
        assert on_date == "2026-03-01"
        return 1.25, "2026-03-01"

    quoted = quote_items("CAD", [{
        "id": "row-1",
        "amount": 80,
        "currency": "USD",
        "on_date": "2026-03-01",
        "company_id": "someone-else",
    }], fetch=rates)
    assert quoted[0]["amount"] == 100
    assert quoted[0]["original_currency"] == "USD"
    assert quoted[0]["valuation"] == "transaction_date"
    assert "company_id" not in quoted[0]

    missing = quote_items("EUR", [{"id": "row-2", "amount": 10, "currency": "CAD"}], fetch=lambda *_args: (_ for _ in ()).throw(RuntimeError("down")))
    assert missing[0]["converted"] is False
    assert missing[0]["unavailable"] is True
    assert missing[0]["amount"] == 10
    assert missing[0]["currency"] == "CAD"
    assert missing[0]["valuation"] == "current"


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fx.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def client(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "c" * 32)
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _tenant(session, slug: str, display: str | None, subscribed: bool) -> User:
    company = Company(
        name=f"Clinique {slug}",
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Health",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
        display_currency=display,
        currency_code="CAD",
    )
    session.add(company)
    session.flush()
    if subscribed:
        add_active_subscription(session, company)
    user = User(
        company_id=company.id,
        first_name="Owner",
        last_name=slug,
        email=f"{slug}-{uuid4()}@example.com",
        password_hash=hash_password("Ownerpass1!"),
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(CompanyMembership(user_id=user.id, company_id=company.id, role=UserRole.OWNER, is_active=True))
    session.commit()
    return user


def _headers(session, user: User) -> dict[str, str]:
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session.add(AuthSession(
        id=session_id,
        user_id=user.id,
        token_hash=f"hash-{session_id}",
        created_at=now,
        expires_at=now + timedelta(days=1),
    ))
    session.commit()
    token, _ = create_access_token(user.id, user.company_id, session_id)
    return {"Authorization": f"Bearer {token}", "X-Requested-With": "avenqo-web"}


def test_each_company_sees_only_its_display_currency(db_session, client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def rates(source: str, target: str, on_date: str | None = None) -> tuple[float, str]:
        assert source == "CAD"
        if target == "EUR":
            return (0.7, on_date or "2026-11-14")
        if target == "GBP":
            return (0.55, on_date or "2026-11-14")
        raise AssertionError(target)

    monkeypatch.setattr("backend.app.services.fx_rates.frankfurter_rate", rates)
    euro = _tenant(db_session, f"euro-{uuid4().hex[:8]}", "EUR", True)
    pound = _tenant(db_session, f"pound-{uuid4().hex[:8]}", "GBP", True)
    body = {"company_id": str(pound.company_id), "display_currency": "USD", "items": [{"id": "sale", "amount": 100, "currency": "CAD"}]}
    client.cookies.clear()
    euro_response = client.post("/api/v1/fx/display", json=body, headers=_headers(db_session, euro))
    client.cookies.clear()
    pound_response = client.post("/api/v1/fx/display", json=body, headers=_headers(db_session, pound))
    assert euro_response.status_code == 200
    assert pound_response.status_code == 200
    euro_row = euro_response.json()["items"][0]
    pound_row = pound_response.json()["items"][0]
    assert euro_response.json()["display_currency"] == "EUR"
    assert euro_row["amount"] == 70
    assert euro_row["currency"] == "EUR"
    assert euro_row["original_amount"] == 100
    assert euro_row["original_currency"] == "CAD"
    assert euro_row["valuation"] == "current"
    assert pound_response.json()["display_currency"] == "GBP"
    assert pound_row["currency"] == "GBP"
    assert pound_row["amount"] == 55

    client.cookies.clear()
    dated = client.post("/api/v1/fx/display", json={"items": [{"id": "journal", "amount": 100, "currency": "CAD", "on_date": "2026-02-02"}]}, headers=_headers(db_session, euro))
    assert dated.json()["items"][0]["valuation"] == "transaction_date"
    assert dated.json()["items"][0]["rate_date"] == "2026-02-02"

    monkeypatch.setattr("backend.app.services.fx_rates.frankfurter_rate", lambda *_args: (_ for _ in ()).throw(RuntimeError("down")))
    client.cookies.clear()
    missing = client.post("/api/v1/fx/display", json=body, headers=_headers(db_session, euro))
    missed = missing.json()["items"][0]
    assert missed["converted"] is False
    assert missed["unavailable"] is True
    assert missed["amount"] == 100
    assert missed["currency"] == "CAD"

    client.cookies.clear()
    assert client.post("/api/v1/fx/display", json=body).status_code == 401
    unpaid = _tenant(db_session, f"unpaid-{uuid4().hex[:8]}", "EUR", False)
    client.cookies.clear()
    assert client.post("/api/v1/fx/display", json=body, headers=_headers(db_session, unpaid)).status_code == 402
