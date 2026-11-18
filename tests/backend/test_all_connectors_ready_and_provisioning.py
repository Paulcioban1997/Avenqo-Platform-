import os
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.models.commerce_connection import CommerceConnection, NormalizedCommerceRecord
from backend.app.services.commerce_connection_service import CommerceConnectionService
from backend.app.services.company_intelligence_service import classify_product_freshness
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from shared.ai_engine.contracts import TenantContext


def _test_db(tmp_path):
    db_path = tmp_path / "connectors_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    company = Company(
        id=uuid4(),
        name="Produits Ero Test",
        slug="produits-ero-test",
        email="test@produits-ero.test",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        preferred_language="fr",
    )
    session.add(company)
    session.commit()
    return engine, session, company


def test_all_connectors_can_be_connected_and_provisioned(tmp_path):
    """Vérifie que n'importe quel connecteur (BigCommerce, Magento, Wix, Amazon, etc.)

    peut être connecté et provisionné avec son catalogue d'articles en direct.
    """
    engine, session, company = _test_db(tmp_path)
    cipher = ConnectorSecretCipher([Fernet.generate_key().decode()])
    service = CommerceConnectionService(session, object(), cipher)
    tenant = TenantContext(company_id=company.id)

    providers_to_test = [
        "bigcommerce",
        "adobe_commerce",
        "wix_ecommerce",
        "squarespace_commerce",
        "prestashop",
        "amazon_sp_api",
        "ebay",
        "etsy",
        "walmart_marketplace",
        "tiktok_shop",
        "square_pos",
        "clover_pos",
        "lightspeed_retail",
        "shipstation",
    ]

    conns_by_id = {}
    for prov in providers_to_test:
        conn = service.store_unverified_api_credentials(
            tenant,
            provider=prov,
            account_id=f"boutique-{prov}.example.com",
            api_key=f"api-key-{prov}-123456",
            api_secret=f"api-sec-{prov}-999999",
            activate=True,
            load_sample_catalog=True,
        )
        assert conn.status == "CONNECTED"
        assert conn.records_created == 4
        assert conn.last_successful_sync is not None
        conns_by_id[conn.id] = conn

        # Vérifier que les articles du catalogue sont créés et valides
        records = session.scalars(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.company_id == company.id,
                NormalizedCommerceRecord.connection_id == conn.id,
            )
        ).all()
        assert len(records) == 4

        # Vérifier la classification de fraîcheur du catalogue
        for rec in records:
            freshness, is_live = classify_product_freshness(rec, conns_by_id, now=datetime.now(timezone.utc))
            assert freshness == "FRESH"
            assert is_live is True

    session.close()
