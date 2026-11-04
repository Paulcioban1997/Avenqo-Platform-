"""Tests de non-régression multi-compte Stripe et multi-tenant pour la gestion des erreurs de compte."""

from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import stripe

from backend.app.database import get_db
from backend.app.models.base import Base, UserRole, CompanyStatus
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.user import User
from backend.app.services.billing_service import BillingService
from backend.app.services.stripe_gateway import (
    StripeGateway,
    StripeCustomerNotFoundError,
    StripePriceNotFoundError,
)
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.dependencies.billing import get_billing_service
from backend.main import create_application


@pytest.fixture
def db_session_and_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test_mismatch.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session, TestingSession
    finally:
        session.close()


def test_stripe_gateway_create_portal_customer_not_found():
    """Vérifie que 'No such customer' lève StripeCustomerNotFoundError au lieu d'une exception non gérée."""
    gateway = StripeGateway("sk_test_mock_key")
    with patch("stripe.billing_portal.Session.create") as mock_portal:
        mock_portal.side_effect = stripe.error.InvalidRequestError(
            message="No such customer: 'cus_VBhfUdTZqnatYg'",
            param="customer",
            code="resource_missing",
        )
        with pytest.raises(StripeCustomerNotFoundError) as exc_info:
            gateway.create_portal("cus_VBhfUdTZqnatYg", "https://example.com/billing")
        assert "cus_VBhfUdTZqnatYg" in str(exc_info.value)
        assert "contexte multi-compte" in str(exc_info.value)


def test_stripe_gateway_create_checkout_price_not_found():
    """Vérifie que 'No such price' lève StripePriceNotFoundError."""
    gateway = StripeGateway("sk_test_mock_key")
    with patch("stripe.Price.retrieve") as mock_price:
        mock_price.side_effect = stripe.error.InvalidRequestError(
            message="No such price: 'price_missing_123'",
            param="id",
            code="resource_missing",
        )
        with pytest.raises(StripePriceNotFoundError) as exc_info:
            gateway.create_checkout(
                customer_id="cus_123",
                price_id="price_missing_123",
                company_id=str(uuid4()),
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )
        assert "price_missing_123" in str(exc_info.value)


def test_billing_service_create_portal_preserves_customer_id_on_mismatch(db_session_and_factory):
    """Vérifie que create_portal ne supprime ni n'écrase le customer_id existant si le compte Stripe est en conflit."""
    session, _ = db_session_and_factory
    company_id = uuid4()
    company = Company(
        id=company_id,
        name="Produits_Ero",
        slug=f"produits-ero-{uuid4().hex[:6]}",
        email="gauffy95@gmail.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)
    session.flush()

    initial_customer_id = "cus_VBhfUdTZqnatYg"
    account = BillingAccount(
        company_id=company_id,
        plan_code="professional",
        status="active",
        stripe_customer_id=initial_customer_id,
        stripe_subscription_id="sub_1UP3OUK4vojCzpX2Q6ETWK9y",
    )
    session.add(account)
    session.commit()

    mock_provider = MagicMock()
    mock_provider.create_portal.side_effect = StripeCustomerNotFoundError(
        f"Le client '{initial_customer_id}' n'a pas été trouvé dans ce compte."
    )

    settings = MagicMock()
    settings.frontend_url = "https://avenqo.ca"

    service = BillingService(session, mock_provider, settings, MagicMock(), MagicMock())

    with pytest.raises(StripeCustomerNotFoundError):
        service.create_portal(company)

    # Vérification primordiale : le customer_id n'a PAS été écrasé ou supprimé !
    reloaded_account = session.scalar(
        select(BillingAccount).where(BillingAccount.company_id == company_id)
    )
    assert reloaded_account is not None
    assert reloaded_account.stripe_customer_id == initial_customer_id
    assert reloaded_account.stripe_subscription_id == "sub_1UP3OUK4vojCzpX2Q6ETWK9y"


def test_portal_endpoint_returns_404_not_500_on_customer_not_found(db_session_and_factory):
    """Vérifie que l'endpoint POST /api/v1/billing/portal retourne HTTP 404 explicite au lieu de HTTP 500."""
    session, SessionFactory = db_session_and_factory
    company_id = uuid4()
    company = Company(
        id=company_id,
        name="Produits_Ero",
        slug=f"produits-ero-{uuid4().hex[:6]}",
        email="gauffy95@gmail.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)
    user = User(
        id=uuid4(),
        company_id=company_id,
        first_name="Gauffy",
        last_name="Owner",
        email="gauffy95@gmail.com",
        password_hash="fakehash",
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(user)
    session.commit()

    mock_service = MagicMock()
    mock_service.create_portal.side_effect = StripeCustomerNotFoundError(
        "Le client Stripe 'cus_VBhfUdTZqnatYg' n'a pas été trouvé dans le compte Stripe configuré."
    )

    app = create_application()

    def override_db():
        with SessionFactory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_identity] = lambda: CurrentIdentity(
        auth_session=MagicMock(),
        user=user,
        raw_token="mock_token",
    )
    app.dependency_overrides[get_billing_service] = lambda: mock_service

    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/billing/portal")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        err_msg = data.get("error", {}).get("message", "") or data.get("detail", "")
        assert "cus_VBhfUdTZqnatYg" in err_msg
