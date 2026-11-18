"""Comprehensive verification tests for Commerce Connectors, Demo Stores, and Storage Quotas."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.app.config.settings import Settings, get_settings
from backend.app.models import (
    BillingAccount,
    CommerceConnection,
    CommerceConnectionStatus,
    Company,
    CompanyMembership,
    NormalizedCommerceRecord,
    User,
)
from backend.app.routers.commerce import (
    ProvisionStoreRequest,
    delete_demo_stores,
    provision_store,
)
from backend.app.routers.voice import list_voice_premium_features
from backend.app.services.commerce_connection_service import (
    CommerceAuthorizationError,
    CommerceConnectionService,
)
from backend.app.services.company_intelligence_service import (
    CompanyIntelligenceService,
    classify_connector_freshness,
    classify_product_freshness,
)
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.voice.direct_answers import spoken_catalog_answer
from payments.plans import DATA_IMPORT_LIMITS_BY_PLAN, PlanCode
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_agent import _voice_database


def _make_service(session):
    cipher = MagicMock()
    cipher.encrypt = MagicMock(return_value="encrypted_fake_key")
    registry = MagicMock()
    return CommerceConnectionService(db=session, registry=registry, cipher=cipher)


def test_storage_quotas_by_plan():
    """Verify official platform quotas: Base=500GB, Pro=2TB, Enterprise=100TB."""
    base_limits = DATA_IMPORT_LIMITS_BY_PLAN[PlanCode.BASE]
    assert base_limits.max_storage_gb == 500
    assert base_limits.max_storage_label == "500 GB"

    pro_limits = DATA_IMPORT_LIMITS_BY_PLAN[PlanCode.PROFESSIONAL]
    assert pro_limits.max_storage_gb == 2048
    assert pro_limits.max_storage_label == "2 TB"

    ent_limits = DATA_IMPORT_LIMITS_BY_PLAN[PlanCode.ENTERPRISE]
    assert ent_limits.max_storage_gb == 102400
    assert ent_limits.max_storage_label == "100 TB"

    # Test storage quota policy helper
    policy = DataImportPolicy(MagicMock())
    policy._plan_code = MagicMock(return_value="base")
    policy._session.scalar.return_value = 0
    quota = policy.storage_quota_for_tenant(MagicMock())
    assert quota["max_storage_gb"] == 500
    assert quota["max_storage_label"] == "500 GB"

    policy._plan_code = MagicMock(return_value="enterprise")
    ent_quota = policy.storage_quota_for_tenant(MagicMock())
    assert ent_quota["max_storage_gb"] == 102400
    assert ent_quota["max_storage_label"] == "100 TB"


def test_unverified_api_credentials_rejects_oauth_providers(tmp_path):
    """Submitting raw API keys for OAuth-only providers like Shopify or BigCommerce is strictly rejected."""
    _engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    service = _make_service(session)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="test@ero.com",
        password_hash="hashed_pw_test",
        first_name="Test",
        last_name="Ero",
        is_active=True,
    )
    session.add(user)
    session.commit()

    tenant_ctx = TenantContext(
        company_id=company.id,
        user_id=user.id,
    )

    # Shopify requires OAuth
    with pytest.raises(CommerceAuthorizationError) as exc_info:
        service.store_unverified_api_credentials(
            tenant_ctx,
            provider="shopify",
            account_id="my-shopify-shop.myshopify.com",
            api_key="sample_auth_token_for_oauth_test",
        )
    assert "OAuth" in str(exc_info.value)

    # BigCommerce requires OAuth
    with pytest.raises(CommerceAuthorizationError) as exc_info2:
        service.store_unverified_api_credentials(
            tenant_ctx,
            provider="bigcommerce",
            account_id="stores/abc12345",
            api_key="sample_auth_token_for_oauth_test",
        )
    assert "OAuth" in str(exc_info2.value)


def test_unverified_api_credentials_rejects_fake_and_short_keys(tmp_path):
    """Submitting dummy or short mock keys is rejected."""
    _engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    service = _make_service(session)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="test2@ero.com",
        password_hash="hashed_pw_test",
        first_name="Test",
        last_name="Ero",
        is_active=True,
    )
    session.add(user)
    session.commit()

    tenant_ctx = TenantContext(
        company_id=company.id,
        user_id=user.id,
    )

    # Too short (< 8 chars)
    with pytest.raises(CommerceAuthorizationError) as exc_short:
        service.store_unverified_api_credentials(
            tenant_ctx,
            provider="adobe-commerce",
            account_id="https://magento.store.test",
            api_key="short",
        )
    assert "minimum 8 caractères" in str(exc_short.value)

    # Dummy key "sandbox-key"
    with pytest.raises(CommerceAuthorizationError) as exc_dummy:
        service.store_unverified_api_credentials(
            tenant_ctx,
            provider="adobe-commerce",
            account_id="https://magento.store.test",
            api_key="sandbox-key",
        )
    assert "valeur de test fictive" in str(exc_dummy.value) or "rejetée" in str(exc_dummy.value)


def test_unverified_api_credentials_sets_connecting_and_no_fake_sync(tmp_path):
    """Legitimate API credentials start in CONNECTING status with NO fake last_successful_sync."""
    _engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    service = _make_service(session)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="test3@ero.com",
        password_hash="hashed_pw_test",
        first_name="Test",
        last_name="Ero",
        is_active=True,
    )
    session.add(user)
    session.commit()

    tenant_ctx = TenantContext(
        company_id=company.id,
        user_id=user.id,
    )

    conn = service.store_unverified_api_credentials(
        tenant_ctx,
        provider="adobe_commerce",
        account_id="https://my-magento-production.com",
        api_key="token_valid_for_adobe_commerce",
    )

    assert conn.status == CommerceConnectionStatus.CONNECTING.value
    assert conn.last_successful_sync is None
    assert conn.sync_completed_at is None
    assert conn.is_demo is False
    assert conn.records_created == 0


def test_provision_demo_store_and_separation(tmp_path):
    """Demo stores have is_demo=True, isolated synthetic items, and no fake last_successful_sync."""
    _engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    service = _make_service(session)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="test4@ero.com",
        password_hash="hashed_pw_test",
        first_name="Test",
        last_name="Ero",
        is_active=True,
    )
    session.add(user)
    session.commit()

    tenant_ctx = TenantContext(
        company_id=company.id,
        user_id=user.id,
    )

    demo_conn = service.provision_demo_store(
        tenant_ctx,
        provider="woocommerce",
        store_name="Planches & Fixations Démo",
    )

    assert demo_conn.is_demo is True
    assert demo_conn.last_successful_sync is None  # NEVER invent last_successful_sync!
    assert "Boutique de démonstration — données fictives" in demo_conn.display_name

    # Check the 4 demo items
    records = session.query(NormalizedCommerceRecord).filter_by(connection_id=demo_conn.id).all()
    assert len(records) == 4
    for r in records:
        assert r.is_demo is True
        assert r.normalized_data.get("is_demo") is True
        assert r.normalized_data.get("is_live_stock") is False
        assert r.normalized_data.get("stock_status") == "demo_synthetic"

    # Intelligence & Freshness Evaluation
    conn_freshness = classify_connector_freshness(demo_conn)
    assert conn_freshness == "DEMO_SIMULATION"

    prod_freshness, is_live = classify_product_freshness(records[0], {demo_conn.id: demo_conn})
    assert prod_freshness == "DEMO_SIMULATION"
    assert is_live is False

    # Voice answer behavior: demo products must carry explicit demo tag and cannot be stated as live in stock
    sample_prod = records[0].normalized_data
    voice_resp = spoken_catalog_answer([sample_prod], locale="fr", retail_enabled=True)
    assert "démonstration" in voice_resp.lower()
    assert "(prix démonstration)" in voice_resp.lower()

    # Clean Purge
    deleted_count = service.delete_demo_stores(tenant_ctx)
    assert deleted_count >= 1

    remaining_demo_conn = session.query(CommerceConnection).filter_by(
        company_id=tenant_ctx.company_id, is_demo=True
    ).count()
    assert remaining_demo_conn == 0

    remaining_demo_records = session.query(NormalizedCommerceRecord).filter_by(
        company_id=tenant_ctx.company_id, is_demo=True
    ).count()
    assert remaining_demo_records == 0


def test_provision_store_endpoint_forbidden_in_production(tmp_path):
    """POST /api/v1/connectors/provision-store must be rejected with 403 in production."""
    _engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    service = _make_service(session)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="test5@ero.com",
        password_hash="hashed_pw_test",
        first_name="Test",
        last_name="Ero",
        is_active=True,
    )
    session.add(user)
    session.commit()

    tenant_ctx = TenantContext(
        company_id=company.id,
        user_id=user.id,
    )

    mock_identity = MagicMock()
    mock_identity.user = user
    mock_identity.company = company

    with patch("backend.app.routers.commerce.get_settings") as mock_settings:
        mock_s = MagicMock()
        mock_s.is_production = True
        mock_s.environment = "production"
        mock_settings.return_value = mock_s

        req = ProvisionStoreRequest(provider="woocommerce", store_name="Prod Store")
        with pytest.raises(HTTPException) as exc_info:
            provision_store(
                request=req,
                identity=mock_identity,
                _=tenant_ctx,
                service=service,
            )
        assert exc_info.value.status_code == 403
        assert "strictement interdit en environnement de production" in exc_info.value.detail


def test_voice_premium_features_certified_status(tmp_path):
    """GET /api/v1/voice/premium-features returns the verified status of the 10 features."""
    _engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="test6@ero.com",
        password_hash="hashed_pw_test",
        first_name="Test",
        last_name="Ero",
        is_active=True,
    )
    session.add(user)
    session.commit()

    mock_identity = MagicMock()
    mock_identity.user = user

    result = list_voice_premium_features(identity=mock_identity, db=session)
    assert "features" in result
    features = result["features"]
    assert len(features) == 10

    # 6 available
    available = [f for f in features if f["status"] == "available"]
    assert len(available) == 6
    assert result["available_count"] == 6

    # 3 testing
    testing = [f for f in features if f["status"] == "testing"]
    assert len(testing) == 3
    assert result["testing_count"] == 3

    # 1 coming soon
    coming_soon = [f for f in features if f["status"] == "coming_soon"]
    assert len(coming_soon) == 1
    assert result["coming_soon_count"] == 1
    assert coming_soon[0]["key"] == "employee_performance_coach"
