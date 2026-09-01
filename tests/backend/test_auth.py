from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.security import decode_access_token, verify_password
from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models import Base, Company, CompanyModule, CompanyOnboarding, Module, User
from backend.main import create_application
from scripts.seed_demo import DEMO_EMAIL, seed_demo
from tests.subscription_helpers import activate_subscription_by_id


class RecordingNotifier:
    """Capture les jetons sans envoyer de vrai courriel pendant les tests."""

    def __init__(self) -> None:
        self.verification_tokens: dict[str, str] = {}
        self.reset_tokens: dict[str, str] = {}

    def send_email_verification(self, email: str, token: str) -> None:
        self.verification_tokens[email] = token

    def send_password_reset(self, email: str, token: str) -> None:
        self.reset_tokens[email] = token


@pytest.fixture
def auth_environment(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session], RecordingNotifier], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
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
        yield client, testing_session, notifier


def registration_payload(
    email: str = "owner@acme.ca",
    company_name: str = "Acme Retail",
) -> dict[str, str]:
    return {
        "company_name": company_name,
        "company_email": f"billing+{email}",
        "first_name": "Alex",
        "last_name": "Martin",
        "email": email,
        "password": "Avenqo2026!",
        "country": "Canada",
        "timezone": "America/Toronto",
        "industry": "E-commerce",
    }


def verify_and_login(
    client: TestClient,
    notifier: RecordingNotifier,
    email: str,
    password: str = "Avenqo2026!",
) -> dict[str, object]:
    verification = client.post(
        "/api/v1/auth/email/verify",
        json={"token": notifier.verification_tokens[email]},
    )
    assert verification.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    return login.json()


def test_inscription_cree_tenant_owner_et_session_revoquable(auth_environment) -> None:
    client, session_factory, notifier = auth_environment
    payload = registration_payload()

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    assert payload["email"] in notifier.verification_tokens
    with session_factory() as session:
        companies = session.scalars(select(Company)).all()
        users = session.scalars(select(User)).all()
        assert len(companies) == len(users) == 1
        assert users[0].company_id == companies[0].id
        assert users[0].role.value == "owner"
        assert users[0].password_hash != payload["password"]
        assert verify_password(payload["password"], users[0].password_hash)

    immediate_login = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert immediate_login.status_code == 200

    login = verify_and_login(client, notifier, payload["email"])
    token = login["access_token"]
    claims = decode_access_token(token)
    assert claims["tenant_id"] == login["company"]["id"]
    assert login["refresh_token"] != token
    headers = {"Authorization": f"Bearer {token}"}
    identity = client.get("/api/v1/auth/me", headers=headers)
    assert identity.status_code == 200
    assert identity.json()["user"]["company_id"] == login["company"]["id"]
    assert "company:manage" in identity.json()["user"]["permissions"]

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    ).status_code == 401


def test_inscription_signale_une_erreur_smtp_sans_effacer_le_compte(auth_environment) -> None:
    client, _, notifier = auth_environment
    app = client.app

    class FailingNotifier:
        def send_email_verification(self, email: str, token: str) -> None:
            raise RuntimeError("smtp unavailable")

        def send_password_reset(self, email: str, token: str) -> None:
            return None

        def send_new_company(self, company: object, user: object, request: object) -> None:
            return None

    app.dependency_overrides[get_account_notifier] = lambda: FailingNotifier()
    payload = registration_payload("smtpfail@acme.ca", "SMTP Company")

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json()["email_delivery_configured"] is False
    assert "n'a pas pu être envoyé" in response.json()["message"].lower()

    token = notifier.verification_tokens.get(payload["email"])
    assert token is None
    verify = client.post("/api/v1/auth/verify-email", json={"token": "deadbeef" * 4})
    assert verify.status_code == 400


def test_inscription_persiste_le_profil_entreprise_et_les_besoins(auth_environment) -> None:
    client, session_factory, _ = auth_environment
    payload = registration_payload("profile@acme.ca", "Profile Company") | {
        "website": "https://profile.example",
        "region": "Europe",
        "company_size": "11-50",
        "preferred_language": "fr",
        "billing_email": "billing@profile.example",
        "job_title": "General Manager",
        "phone": "+33123456789",
        "plan_code": "professional",
        "business_goals": ["increase_sales", "reduce_churn"],
        "current_tools": ["csv", "crm"],
        "selected_modules": [
            "retail",
            "marketing",
            "crm",
            "hr",
            "accounting",
            "ocr",
            "voice",
            "media",
        ],
    }

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.name == "Profile Company"))
        assert company is not None
        assert company.website == "https://profile.example/"
        assert company.region == "Europe"
        assert company.company_size == "11-50"
        assert company.billing_email == "billing@profile.example"
        assert company.subscription_plan == "professional"
        user = session.scalar(select(User).where(User.email == "profile@acme.ca"))
        assert user is not None
        assert user.job_title == "General Manager"
        assert user.phone == "+33123456789"
        onboarding = session.get(CompanyOnboarding, company.id)
        assert onboarding is not None
        assert onboarding.business_goals == ["increase_sales", "reduce_churn"]
        assert onboarding.current_tools == ["csv", "crm"]
        selected_modules = session.execute(
            select(Module.code)
            .join(CompanyModule, CompanyModule.module_id == Module.id)
            .where(CompanyModule.company_id == company.id)
        ).scalars().all()
        assert set(selected_modules) == set(payload["selected_modules"])


def test_inscription_sans_site_web_est_valide(auth_environment) -> None:
    client, session_factory, _ = auth_environment
    payload = registration_payload("no-site@acme.ca", "No Site Company")
    payload["website"] = ""

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.name == "No Site Company"))
        assert company is not None
        assert company.website is None


def test_inscription_refuse_un_depassement_de_modules_sans_creer_de_compte(
    auth_environment,
) -> None:
    client, session_factory, _ = auth_environment
    payload = registration_payload("over-limit@acme.ca", "Over Limit Company") | {
        "plan_code": "demo",
        "selected_modules": ["retail", "crm", "accounting"],
    }

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 400
    with session_factory() as session:
        assert session.scalar(
            select(Company).where(Company.name == "Over Limit Company")
        ) is None
        assert session.scalar(
            select(User).where(User.email == "over-limit@acme.ca")
        ) is None


def test_refresh_token_est_rotatif_et_jwt_altere_est_refuse(auth_environment) -> None:
    client, _, notifier = auth_environment
    payload = registration_payload()
    client.post("/api/v1/auth/register", json=payload)
    login = verify_and_login(client, notifier, payload["email"])

    access_token = login["access_token"]
    # On altÃ¨re un caractÃ¨re au milieu de la signature (jamais le dernier
    # caractÃ¨re base64url) : le dernier caractÃ¨re d'un token peut encoder des
    # bits de bourrage inutilisÃ©s selon la longueur du segment, ce qui rendait
    # ce test intermittent (l'altÃ©ration pouvait parfois dÃ©coder aux mÃªmes
    # octets de signature et donc rester valide).
    middle_index = len(access_token) // 2
    replacement = "a" if access_token[middle_index] != "a" else "b"
    altered_token = f"{access_token[:middle_index]}{replacement}{access_token[middle_index + 1:]}"
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {altered_token}"},
    ).status_code == 401

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != login["refresh_token"]
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    ).status_code == 401
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    ).status_code == 200


def test_deux_compagnies_restent_isolees(auth_environment) -> None:
    client, _, notifier = auth_environment
    first = registration_payload("owner@acme.ca", "Acme Retail")
    second = registration_payload("owner@nova.ca", "Nova Commerce")
    assert client.post("/api/v1/auth/register", json=first).status_code == 201
    assert client.post("/api/v1/auth/register", json=second).status_code == 201

    first_login = verify_and_login(client, notifier, first["email"])
    second_login = verify_and_login(client, notifier, second["email"])

    assert first_login["company"]["id"] != second_login["company"]["id"]
    for login in (first_login, second_login):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.json()["company"]["id"] == login["company"]["id"]


def test_reset_password_revoque_les_sessions_existantes(auth_environment) -> None:
    client, _, notifier = auth_environment
    payload = registration_payload()
    client.post("/api/v1/auth/register", json=payload)
    login = verify_and_login(client, notifier, payload["email"])
    old_headers = {"Authorization": f"Bearer {login['access_token']}"}

    forgot = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": payload["email"]},
    )
    assert forgot.status_code == 200
    reset = client.post(
        "/api/v1/auth/password/reset",
        json={
            "token": notifier.reset_tokens[payload["email"]],
            "new_password": "Avenqo2027!Secure",
        },
    )
    assert reset.status_code == 200
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
    assert client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login["refresh_token"]},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "Avenqo2027!Secure"},
    ).status_code == 200


def test_conflits_et_recuperation_ne_revelent_pas_les_comptes(auth_environment) -> None:
    client, _, _ = auth_environment
    payload = registration_payload()
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409

    known = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": payload["email"]},
    )
    unknown = client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "unknown@example.ca"},
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "Incorrect2026!"},
    ).status_code == 401


def test_gestion_employes_respecte_roles_et_tenants(auth_environment) -> None:
    client, session_factory, notifier = auth_environment
    acme = registration_payload("owner@acme.ca", "Acme Retail")
    nova = registration_payload("owner@nova.ca", "Nova Commerce")
    client.post("/api/v1/auth/register", json=acme)
    client.post("/api/v1/auth/register", json=nova)
    acme_login = verify_and_login(client, notifier, acme["email"])
    nova_login = verify_and_login(client, notifier, nova["email"])
    with session_factory() as session:
        activate_subscription_by_id(session, acme_login["company"]["id"])
        activate_subscription_by_id(session, nova_login["company"]["id"])
    acme_headers = {"Authorization": f"Bearer {acme_login['access_token']}"}
    nova_headers = {"Authorization": f"Bearer {nova_login['access_token']}"}

    employee_payload = {
        "first_name": "Marie",
        "last_name": "Tremblay",
        "email": "manager@acme.ca",
        "password": "Manager2026!",
        "role": "manager",
    }
    created = client.post("/api/v1/employees", json=employee_payload, headers=acme_headers)
    assert created.status_code == 201
    employee_id = created.json()["id"]
    assert created.json()["company_id"] == acme_login["company"]["id"]

    employee_login = verify_and_login(client, notifier, employee_payload["email"], employee_payload["password"])
    employee_headers = {"Authorization": f"Bearer {employee_login['access_token']}"}
    assert client.get("/api/v1/employees", headers=employee_headers).status_code == 403
    assert client.patch(
        f"/api/v1/employees/{employee_id}",
        json={"last_name": "Intrusion"},
        headers=nova_headers,
    ).status_code == 404

    admin_payload = {
        "first_name": "Sam",
        "last_name": "Admin",
        "email": "admin@acme.ca",
        "password": "AdminSecure2026!",
        "role": "admin",
    }
    admin = client.post("/api/v1/employees", json=admin_payload, headers=acme_headers)
    assert admin.status_code == 201
    admin_login = verify_and_login(client, notifier, admin_payload["email"], admin_payload["password"])
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
    assert client.post(
        "/api/v1/employees",
        json={**admin_payload, "email": "second-admin@acme.ca"},
        headers=admin_headers,
    ).status_code == 403
    assert client.patch(
        f"/api/v1/employees/{acme_login['user']['id']}",
        json={"first_name": "Changed"},
        headers=admin_headers,
    ).status_code == 403

    deactivated = client.patch(
        f"/api/v1/employees/{employee_id}",
        json={"is_active": False},
        headers=acme_headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=employee_headers).status_code == 401


def test_seed_demo_est_idempotent(auth_environment) -> None:
    client, session_factory, _ = auth_environment
    with session_factory() as session:
        first = seed_demo(session, "Avenqo2026!")
        first_id = first.id
    with session_factory() as session:
        second = seed_demo(session, "Avenqo2026!")
        assert second.id == first_id
        assert session.scalars(select(User).where(User.email == DEMO_EMAIL)).all() == [second]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": "Avenqo2026!"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "owner"
