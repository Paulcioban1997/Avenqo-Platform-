"""Demandes de devis Enterprise : landing, dashboard, destinataires, échecs et doublons."""

from __future__ import annotations

pytest_plugins = ["tests.backend.test_billing"]

from sqlalchemy import select

from backend.app.core.rate_limit import reset_rate_limiter
from backend.app.database import get_db
from backend.app.models.billing import EnterpriseQuote, EnterpriseQuoteDelivery
from backend.app.models.user import User
from backend.app.services.resend_client import PermanentEmailDeliveryError, TemporaryEmailDeliveryError
from tests.backend.test_billing import auth_headers, create_owner

LANDING_PAYLOAD = {
    "name": "Camille Roy",
    "email": "camille@nordicgarage.ca",
    "company": "Nordic Garage",
    "phone": "+1 514 555 0101",
    "need": "Devis Entreprise sur mesure",
    "message": "Nous voulons Voice, CRM et OCR pour trois ateliers.",
}

OWNERS = {"info@avenqo.ca", "paulmircea15@gmail.com"}


def _promote_admin(client, email: str) -> None:
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.is_platform_admin = True
        db.commit()
    finally:
        db_gen.close()


def _quotes(client) -> list[EnterpriseQuote]:
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        return list(db.scalars(select(EnterpriseQuote).order_by(EnterpriseQuote.created_at.desc())).all())
    finally:
        db_gen.close()


def test_landing_and_dashboard_quotes_notify_both_recipients(billing_environment) -> None:
    reset_rate_limiter()
    client, _, notifier = billing_environment
    landing = client.post("/api/v1/public/enterprise-quote", json=LANDING_PAYLOAD)
    assert landing.status_code == 200
    landing_body = landing.json()
    assert landing_body["notification_status"] == "sent"
    assert landing_body["acknowledgment_status"] == "sent"

    login = create_owner(client, notifier, email="owner@garage.ca", company_name="Dashboard Garage")
    dashboard = client.post(
        "/api/v1/billing/enterprise-quote",
        json={
            "requested_modules": ["voice", "crm"],
            "estimated_users": 12,
            "monthly_volume": "20k appels",
            "required_integrations": ["Telnyx"],
            "notes": "Nous avons besoin d'un devis Enterprise pour trois sites.",
        },
        headers=auth_headers(login),
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["notification_status"] == "sent"

    owner_messages = [
        item for item in notifier.quote_mailer.messages if set(item["to"]) == OWNERS
    ]
    assert len(owner_messages) == 2
    landing_mail, dashboard_mail = owner_messages
    assert landing_mail["text_body"]
    assert "Référence :" in landing_mail["text_body"]
    assert "Camille Roy" in landing_mail["text_body"]
    assert "Nordic Garage" in landing_mail["text_body"]
    assert "camille@nordicgarage.ca" in landing_mail["text_body"]
    assert "+1 514 555 0101" in landing_mail["text_body"]
    assert "Devis Entreprise sur mesure" in landing_mail["text_body"]
    assert landing_body["reference_id"] in landing_mail["subject"]
    assert landing_mail["to"] == dashboard_mail["to"] == ["info@avenqo.ca", "paulmircea15@gmail.com"]
    assert landing_mail["text_body"] != dashboard_mail["text_body"]
    assert any(item["to"] == ["camille@nordicgarage.ca"] for item in notifier.quote_mailer.messages)

    _promote_admin(client, "owner@garage.ca")
    admin = client.get("/api/v1/admin/enterprise-quotes", headers=auth_headers(login))
    assert admin.status_code == 200
    references = {item["reference_id"] for item in admin.json()}
    assert landing_body["reference_id"] in references
    assert dashboard.json()["reference_id"] in references
    landing_row = next(item for item in admin.json() if item["reference_id"] == landing_body["reference_id"])
    assert landing_row["company_name"] == "Nordic Garage"
    assert landing_row["status"] == "received"
    assert landing_row["notification_status"] == "sent"


def test_provider_failure_does_not_claim_success(billing_environment) -> None:
    reset_rate_limiter()
    client, _, notifier = billing_environment
    notifier.quote_mailer.error = PermanentEmailDeliveryError("Transactional email API rejected the request (401)")
    response = client.post("/api/v1/public/enterprise-quote", json=LANDING_PAYLOAD)
    assert response.status_code == 503
    body = response.json()
    assert body["reference_id"]
    assert "n'a pas été confirmé" in body["detail"]
    stored = _quotes(client)
    assert len(stored) == 1
    assert stored[0].notification_status != "sent"


def test_temporary_failure_retries_without_duplicate_emails(billing_environment) -> None:
    reset_rate_limiter()
    client, _, notifier = billing_environment
    attempts = {"count": 0}

    def flaky_send(**kwargs):
        attempts["count"] += 1
        if attempts["count"] <= 2:
            raise TemporaryEmailDeliveryError("Transactional email API returned 503")
        notifier.quote_mailer.messages.append(kwargs)
        return f"re_{attempts['count']}"

    notifier.quote_mailer.send = flaky_send  # type: ignore[method-assign]
    response = client.post("/api/v1/public/enterprise-quote", json=LANDING_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["notification_status"] == "sent"
    owner_sends = [item for item in notifier.quote_mailer.messages if set(item["to"]) == OWNERS]
    assert len(owner_sends) == 1
    assert owner_sends[0]["to"] == ["info@avenqo.ca", "paulmircea15@gmail.com"]


def test_identical_retry_does_not_create_duplicate_quote_or_emails(billing_environment) -> None:
    reset_rate_limiter()
    client, _, notifier = billing_environment
    first = client.post("/api/v1/public/enterprise-quote", json=LANDING_PAYLOAD)
    second = client.post("/api/v1/public/enterprise-quote", json=LANDING_PAYLOAD)
    assert first.status_code == second.status_code == 200
    assert first.json()["reference_id"] == second.json()["reference_id"]
    assert len(_quotes(client)) == 1
    owner_sends = [item for item in notifier.quote_mailer.messages if set(item["to"]) == OWNERS]
    assert len(owner_sends) == 1
    assert owner_sends[0]["idempotency_key"] == f"eq-{first.json()['reference_id']}-owner"


def test_spam_honeypot_and_rate_limit_are_rejected(billing_environment) -> None:
    reset_rate_limiter()
    client, _, notifier = billing_environment
    honeypot = client.post("/api/v1/public/enterprise-quote", json={**LANDING_PAYLOAD, "website": "http://spam.test"})
    assert honeypot.status_code == 400
    assert _quotes(client) == []

    invalid = client.post(
        "/api/v1/public/enterprise-quote",
        json={**LANDING_PAYLOAD, "email": "not-an-email", "message": "short"},
    )
    assert invalid.status_code == 422

    for index in range(3):
        payload = {**LANDING_PAYLOAD, "message": f"{LANDING_PAYLOAD['message']} variante {index}"}
        assert client.post("/api/v1/public/enterprise-quote", json=payload).status_code == 200
    limited = client.post(
        "/api/v1/public/enterprise-quote",
        json={**LANDING_PAYLOAD, "message": "Quatrième demande distincte pour le même courriel."},
    )
    assert limited.status_code == 429
    assert len(notifier.quote_mailer.messages) >= 6


def test_delivery_report_marks_owner_emails_sent_without_resending(billing_environment) -> None:
    reset_rate_limiter()
    client, _, notifier = billing_environment
    notifier.quote_mailer.error = PermanentEmailDeliveryError("missing key")
    created = client.post("/api/v1/public/enterprise-quote", json=LANDING_PAYLOAD)
    reference = created.json()["reference_id"]
    notifier.quote_mailer.error = None
    report = client.post(
        f"/api/v1/public/enterprise-quote/{reference}/deliveries",
        json={
            "deliveries": [
                {"kind": "owner", "recipient": "info@avenqo.ca", "provider_message_id": "re_info"},
                {"kind": "owner", "recipient": "paulmircea15@gmail.com", "provider_message_id": "re_paul"},
            ]
        },
    )
    assert report.status_code == 200
    assert report.json()["notification_status"] == "sent"
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        jobs = list(db.scalars(select(EnterpriseQuoteDelivery)).all())
        owner_ids = {job.provider_message_id for job in jobs if job.kind == "owner"}
        assert owner_ids == {"re_info", "re_paul"}
    finally:
        db_gen.close()


def test_migration_0051_on_isolated_sqlite(tmp_path) -> None:
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(f"sqlite:///{tmp_path / 'enterprise-quote-0051.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE enterprise_quotes (
                id VARCHAR(36) PRIMARY KEY,
                reference_id VARCHAR(64) NOT NULL,
                company_id VARCHAR(36) NOT NULL,
                user_id VARCHAR(36),
                contact_name VARCHAR(255),
                contact_email VARCHAR(255),
                contact_phone VARCHAR(64),
                requested_modules TEXT NOT NULL,
                estimated_users INTEGER,
                monthly_volume VARCHAR(255),
                required_integrations TEXT NOT NULL,
                notes TEXT,
                status VARCHAR(64) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        ))
        path = (
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "0051_enterprise_quote_deliveries.py"
        )
        spec = importlib.util.spec_from_file_location("enterprise_quote_0051", path)
        migration = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns("enterprise_quotes")}
    assert {
        "source",
        "company_name",
        "need",
        "notification_status",
        "acknowledgment_status",
        "idempotency_key",
        "submitted_at",
    }.issubset(columns)
    assert "enterprise_quote_deliveries" in inspector.get_table_names()
    delivery_columns = {item["name"] for item in inspector.get_columns("enterprise_quote_deliveries")}
    assert {"quote_id", "kind", "recipient", "idempotency_key", "status", "provider_message_id"}.issubset(delivery_columns)
    engine.dispose()
