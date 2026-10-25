"""Tests de sécurité et de conformité pour la sélection multi-sources par entreprise."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.core.security import create_access_token
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.main import create_application
from backend.app.models import (
    AuthSession,
    Base,
    BillingAccount,
    Company,
    CompanyMembership,
    User,
    UserRole,
    CommerceConnection,
    CommerceConnectionStatus,
    Dataset,
    DatasetStatus,
    NormalizedCommerceRecord,
    RetailActiveSource,
)
from backend.app.services.account_notifications import AccountNotifier


class _NullNotifier(AccountNotifier):
    def notify_user_status_changed(self, user: User, is_active: bool) -> None:
        pass


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'multi-source.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def client(db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "a" * 32)
    get_settings.cache_clear()
    app = create_application()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: _NullNotifier()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _company(session: Session, *, slug: str) -> Company:
    company = Company(
        name=f"Company {slug}",
        slug=slug,
        email=f"{slug}@example.test",
        country="CA",
        timezone="America/Montreal",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    session.add(
        BillingAccount(
            company_id=company.id,
            plan_code="professional",
            status="active",
        )
    )
    session.flush()
    return company


def _user(session: Session, company: Company, *, role: UserRole = UserRole.OWNER) -> User:
    user = User(
        company_id=company.id,
        first_name="Admin",
        last_name="User",
        email=f"{role.value}-{uuid4().hex[:6]}@example.test",
        password_hash="fakehash",
        role=role,
    )
    session.add(user)
    session.flush()
    session.add(CompanyMembership(user_id=user.id, company_id=company.id, role=role, is_active=True))
    session.flush()
    return user


def _token(session: Session, user: User) -> str:
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    session.add(
        AuthSession(
            id=session_id,
            user_id=user.id,
            token_hash=f"hash-{session_id}",
            created_at=now,
            expires_at=now + timedelta(days=1),
        )
    )
    session.commit()
    token, _ = create_access_token(user.id, user.company_id, session_id)
    return token


def _connection(session: Session, company: Company, provider: str, name: str, status: str = "READY") -> CommerceConnection:
    conn = CommerceConnection(
        company_id=company.id,
        provider=provider,
        external_account_id=f"{provider}-{uuid4().hex[:8]}",
        display_name=name,
        status=status,
    )
    session.add(conn)
    session.flush()
    if status == "READY":
        rec = NormalizedCommerceRecord(
            company_id=company.id,
            connection_id=conn.id,
            provider=provider,
            entity_type="orders",
            source_record_id=f"rec-{uuid4().hex[:8]}",
            normalized_data={"order_id": "test"},
            deleted=False,
        )
        session.add(rec)
        session.flush()
    return conn


def _dataset(session: Session, company: Company, name: str) -> Dataset:
    dataset = Dataset(
        company_id=company.id,
        name=name,
        type="csv",
        source="manual_upload",
        rows_count=100,
        columns_count=5,
        status=DatasetStatus.READY,
    )
    session.add(dataset)
    session.flush()
    return dataset


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_sources_selection_default_all(db_session, client: TestClient):
    """Par défaut, le mode de sélection est ALL et toutes les sources actives sont incluses."""
    company = _company(db_session, slug="sel-default")
    user = _user(db_session, company, role=UserRole.OWNER)
    c1 = _connection(db_session, company, "shopify", "Shopify Store A")
    c2 = _connection(db_session, company, "shopify", "Shopify Store B")
    d1 = _dataset(db_session, company, "Ventes Magasin CSV")
    db_session.commit()

    token = _token(db_session, user)
    response = client.get(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["mode"] == "ALL"
    assert data["effective_count"] == 3
    source_ids = {s["id"] for s in data["available_sources"]}
    assert str(c1.id) in source_ids
    assert str(c2.id) in source_ids
    assert str(d1.id) in source_ids
    assert all(s["is_selected"] for s in data["available_sources"])


def test_set_sources_selection_custom_set(db_session, client: TestClient):
    """Permet de sélectionner un sous-ensemble personnalisé de boutiques."""
    company = _company(db_session, slug="sel-custom")
    user = _user(db_session, company, role=UserRole.ADMIN)
    c1 = _connection(db_session, company, "shopify", "Shopify Montréal")
    c2 = _connection(db_session, company, "shopify", "Shopify Québec")
    c3 = _connection(db_session, company, "woocommerce", "WooCommerce France")
    db_session.commit()

    token = _token(db_session, user)

    # Sélectionner uniquement Montréal et France
    payload = {
        "mode": "CUSTOM_SET",
        "selected_source_ids": [str(c1.id), str(c3.id)],
    }
    post_res = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert post_res.status_code == 200, post_res.text
    data = post_res.json()

    assert data["mode"] == "CUSTOM_SET"
    assert data["effective_count"] == 2
    assert set(data["selected_source_ids"]) == {str(c1.id), str(c3.id)}

    # Vérifier que le GET ultérieur reflète exactement ce choix
    get_res = client.get(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["mode"] == "CUSTOM_SET"
    selected_in_available = [s["id"] for s in get_data["available_sources"] if s["is_selected"]]
    assert set(selected_in_available) == {str(c1.id), str(c3.id)}


def test_set_sources_selection_single(db_session, client: TestClient):
    """Permet d'isoler une source unique et préserve la rétrocompatibilité active_selection."""
    company = _company(db_session, slug="sel-single")
    user = _user(db_session, company, role=UserRole.OWNER)
    c1 = _connection(db_session, company, "shopify", "Boutique 1")
    c2 = _connection(db_session, company, "shopify", "Boutique 2")
    db_session.commit()

    token = _token(db_session, user)

    payload = {
        "mode": "SINGLE",
        "selected_source_ids": [str(c2.id)],
    }
    response = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "SINGLE"
    assert data["effective_count"] == 1
    assert data["selected_source_ids"] == [str(c2.id)]

    # Vérifier que RetailActiveSource en base pointe bien vers c2
    active = db_session.query(RetailActiveSource).filter_by(company_id=company.id).first()
    assert active is not None
    assert active.selection_mode == "SINGLE"
    assert active.connection_id == c2.id


def test_set_sources_selection_cardinality_validation(db_session, client: TestClient):
    """Valide les règles de cardinalité : SINGLE exige 1 ID, CUSTOM_SET exige >= 1 ID."""
    company = _company(db_session, slug="sel-cardinality")
    user = _user(db_session, company, role=UserRole.OWNER)
    c1 = _connection(db_session, company, "shopify", "Store 1")
    c2 = _connection(db_session, company, "shopify", "Store 2")
    db_session.commit()

    token = _token(db_session, user)

    # SINGLE avec 0 ID -> 400
    res = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "SINGLE", "selected_source_ids": []},
    )
    assert res.status_code == 400

    # SINGLE avec 2 IDs -> 400
    res = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "SINGLE", "selected_source_ids": [str(c1.id), str(c2.id)]},
    )
    assert res.status_code == 400

    # CUSTOM_SET avec 0 ID -> 400
    res = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "CUSTOM_SET", "selected_source_ids": []},
    )
    assert res.status_code == 400


def test_set_sources_selection_disconnected_refused(db_session, client: TestClient):
    """Une boutique déconnectée ne peut pas être sélectionnée."""
    company = _company(db_session, slug="sel-disc")
    user = _user(db_session, company, role=UserRole.OWNER)
    conn_disc = _connection(db_session, company, "shopify", "Dead Store", status="DISCONNECTED")
    db_session.commit()

    token = _token(db_session, user)
    res = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token}"},
        json={"mode": "SINGLE", "selected_source_ids": [str(conn_disc.id)]},
    )
    assert res.status_code == 400


def test_set_sources_selection_cross_tenant_prohibited(db_session, client: TestClient):
    """Exigence 5 : Refus strict (403) si un tenant tente de sélectionner la source d'une autre entreprise."""
    company_alpha = _company(db_session, slug="alpha-tenant")
    company_beta = _company(db_session, slug="beta-tenant")

    user_alpha = _user(db_session, company_alpha, role=UserRole.OWNER)
    conn_beta = _connection(db_session, company_beta, "shopify", "Beta Private Shop")
    db_session.commit()

    token_alpha = _token(db_session, user_alpha)

    # Alpha tente d'inclure la boutique de Beta
    res = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token_alpha}"},
        json={"mode": "SINGLE", "selected_source_ids": [str(conn_beta.id)]},
    )
    assert res.status_code == 403


def test_set_sources_selection_rbac_permissions(db_session, client: TestClient):
    """Exigence 4 : Vérification des permissions rôle. VIEWER peut lire mais pas modifier."""
    company = _company(db_session, slug="sel-rbac")
    viewer = _user(db_session, company, role=UserRole.VIEWER)
    c1 = _connection(db_session, company, "shopify", "Boutique RBAC")
    db_session.commit()

    token_viewer = _token(db_session, viewer)

    # Lecture autorisée (data:read)
    get_res = client.get(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token_viewer}"},
    )
    assert get_res.status_code == 200

    # Écriture refusée (manque data:manage)
    post_res = client.post(
        "/api/v1/workspace/sources/selection",
        headers={"Authorization": f"Bearer {token_viewer}"},
        json={"mode": "SINGLE", "selected_source_ids": [str(c1.id)]},
    )
    assert post_res.status_code == 403


def test_legacy_retail_sources_active_backward_compatibility(db_session, client: TestClient):
    """Exigence 10 : Préserver les contrats existants (/api/v1/retail/sources/active)."""
    company = _company(db_session, slug="sel-legacy")
    user = _user(db_session, company, role=UserRole.OWNER)
    c1 = _connection(db_session, company, "shopify", "Legacy Shop")
    db_session.commit()

    token = _token(db_session, user)

    # Appel au point d'entrée historique retail
    res = client.put(
        "/api/v1/retail/sources/active",
        headers={"Authorization": f"Bearer {token}"},
        json={"source_type": "connector", "source_id": str(c1.id)},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["source_id"] == str(c1.id)
    assert data["active"] is True
