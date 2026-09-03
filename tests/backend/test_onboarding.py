"""Tests du questionnaire d'onboarding post-inscription (scopé au tenant)."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import Base, Company, User, UserRole
from backend.main import create_application

from tests.backend.test_auth import RecordingNotifier, registration_payload, verify_and_login
from tests.subscription_helpers import activate_subscription


@pytest.fixture
def onboarding_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, RecordingNotifier, sessionmaker[Session]], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'onboarding.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    notifier = RecordingNotifier()
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
        yield client, notifier, testing_session


def _register_and_login(client: TestClient, notifier: RecordingNotifier) -> str:
    email = "owner@onboarding-test.ca"
    response = client.post(
        "/api/v1/auth/register",
        json=registration_payload(email=email, company_name="Onboarding Test Co"),
    )
    assert response.status_code == 201
    session = verify_and_login(client, notifier, email)
    assert session["company"]["onboarding_status"] == "pending"
    return session["access_token"]


def test_new_company_defaults_to_pending(onboarding_environment) -> None:
    client, notifier, _ = onboarding_environment
    token = _register_and_login(client, notifier)

    response = client.get(
        "/api/v1/onboarding", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["business_goals"] == []
    assert body["current_tools"] == []
    assert body["team_size"] is None


def test_complete_onboarding_persists_answers(onboarding_environment) -> None:
    client, notifier, _ = onboarding_environment
    token = _register_and_login(client, notifier)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/onboarding/complete",
        headers=headers,
        json={
            "business_goals": ["increase_sales", "reduce_churn"],
            "current_tools": ["pos", "spreadsheets"],
            "team_size": "2_10",
            "refined_industry": "Specialty retail",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["business_goals"] == ["increase_sales", "reduce_churn"]
    assert body["team_size"] == "2_10"
    assert body["refined_industry"] == "Specialty retail"
    assert body["completed_at"] is not None

    # Le statut se propage à /auth/me, source de vérité pour le frontend.
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["company"]["onboarding_status"] == "completed"


def test_skip_onboarding_marks_status_skipped(onboarding_environment) -> None:
    client, notifier, _ = onboarding_environment
    token = _register_and_login(client, notifier)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/onboarding/skip", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["company"]["onboarding_status"] == "skipped"


def test_onboarding_requires_authentication(onboarding_environment) -> None:
    client, _notifier, _ = onboarding_environment
    response = client.get("/api/v1/onboarding")
    assert response.status_code == 401


def test_onboarding_is_tenant_isolated(onboarding_environment) -> None:
    client, notifier, _ = onboarding_environment
    token_a = _register_and_login(client, notifier)

    response_b = client.post(
        "/api/v1/auth/register",
        json=registration_payload(email="owner-b@onboarding-test.ca", company_name="Other Co"),
    )
    assert response_b.status_code == 201
    token_b = verify_and_login(client, notifier, "owner-b@onboarding-test.ca")["access_token"]

    client.post(
        "/api/v1/onboarding/complete",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"business_goals": ["increase_sales"], "team_size": "solo"},
    )

    status_b = client.get(
        "/api/v1/onboarding", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert status_b.json()["status"] == "pending"


def test_onboarding_activates_selected_module_allowed_by_plan(onboarding_environment) -> None:
    """L'offre Demo autorise le module "retail" (voir `payments/plans.py`) :
    le sélectionner à l'onboarding doit créer un `CompanyModule` actif."""
    client, notifier, session_factory = onboarding_environment
    token = _register_and_login(client, notifier)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/onboarding/complete",
        headers=headers,
        json={
            "business_goals": ["increase_sales"],
            "team_size": "solo",
            "selected_modules": ["retail"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["activated_modules"] == ["retail"]
    assert body["unavailable_modules"] == []

    with session_factory() as session:
        company = session.scalar(
            select(Company).where(Company.name == "Onboarding Test Co")
        )
        assert company is not None
        activate_subscription(session, company)

    upload = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        data={"module_code": "retail"},
        files={"file": ("data.csv", b"id,age\n1,20\n2,30\n", "text/csv")},
    )
    dataset_id = upload.json()["dataset_id"]
    prepare = client.post(
        f"/api/v1/datasets/{dataset_id}/capabilities/churn/prepare",
        headers=headers,
    )
    assert prepare.status_code != 403


def test_onboarding_never_activates_coming_soon_modules(onboarding_environment) -> None:
    client, notifier, _ = onboarding_environment
    token = _register_and_login(client, notifier)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/onboarding/complete",
        headers=headers,
        json={
            "business_goals": ["increase_sales"],
            "team_size": "solo",
            "selected_modules": ["retail", "crm", "accounting"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["activated_modules"] == ["retail"]
    assert body["unavailable_modules"] == ["crm", "accounting"]


def test_module_entitlement_api_is_tenant_scoped(onboarding_environment) -> None:
    client, notifier, session_factory = onboarding_environment
    token_a = _register_and_login(client, notifier)
    response_b = client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email="modules-b@onboarding-test.ca",
            company_name="Modules Tenant B",
        ),
    )
    assert response_b.status_code == 201
    token_b = verify_and_login(
        client, notifier, "modules-b@onboarding-test.ca"
    )["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    with session_factory() as session:
        companies = list(session.scalars(select(Company)))
        for company in companies:
            activate_subscription(session, company)
        tenant_b_admin = session.scalar(
            select(User).where(User.email == "modules-b@onboarding-test.ca")
        )
        assert tenant_b_admin is not None
        tenant_b_admin.role = UserRole.ADMIN
        session.commit()

    initial = client.get("/api/v1/modules/entitlements", headers=headers_a)
    assert initial.status_code == 200
    assert initial.json()["module_limit"] == 2
    assert initial.json()["active_modules"] == []

    activated = client.post("/api/v1/modules/retail/activate", headers=headers_a)
    assert activated.status_code == 200
    assert activated.json()["active_modules"] == ["retail"]
    assert activated.json()["remaining_module_slots"] == 1

    coming_soon = client.post("/api/v1/modules/crm/activate", headers=headers_a)
    assert coming_soon.status_code == 409
    assert "not available" in coming_soon.json()["error"]["message"]

    tenant_b = client.get("/api/v1/modules/entitlements", headers=headers_b)
    assert tenant_b.status_code == 200
    assert tenant_b.json()["active_modules"] == []
    deactivated_by_admin = client.post(
        "/api/v1/modules/retail/deactivate", headers=headers_b
    )
    assert deactivated_by_admin.status_code == 200
    tenant_a = client.get("/api/v1/modules/entitlements", headers=headers_a)
    assert tenant_a.json()["active_modules"] == ["retail"]

