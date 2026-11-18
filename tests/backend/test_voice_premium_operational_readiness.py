"""Tests de validation P1 : Préparation opérationnelle des 10 améliorations Voice AI.

Vérifie :
1. Préservation des statuts plateforme (6 Disponible, 3 En test, 1 À venir).
2. Calcul dynamique du statut opérationnel par entreprise (`operational_status`) :
   - `ready` : fonctionnalité disponible et configurée pour l'entreprise
   - `configuration_required` : fonctionnalité disponible mais nécessitant une configuration/activation
   - `not_entitled` : entreprise absente ou droits insuffisants
   - `in_testing` : fonctionnalité en test plateforme
   - `planned` : fonctionnalité planifiée
3. Présence des libellés bilingues et détails explicatifs pour chaque statut.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Base, Company, User
from backend.app.models.base import CompanyStatus
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.routers.voice import list_voice_premium_features


@pytest.fixture
def voice_db(tmp_path):
    db_path = tmp_path / "test_voice_readiness.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def test_voice_premium_operational_readiness_with_active_config(voice_db: Session):
    cid = uuid4()
    company = Company(
        id=cid,
        name="Produits Ero Test",
        slug="produits-ero-test",
        email="contact@produitsero.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        status=CompanyStatus.ACTIVE,
        subscription_plan="professional",
    )
    voice_db.add(company)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="founder@ero.com",
        password_hash="hashed_pw_test",
        first_name="Paul",
        last_name="M",
        is_active=True,
    )
    voice_db.add(user)

    config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company.id,
        business_name="Produits Éro",
        timezone_name="America/Toronto",
        opening_hours={"monday": "9h-17h"},
        services=["vente", "livraison"],
        transfer_phone="+15145551234",
        telnyx_phone_number="+14389536811",
        preferred_language="fr",
        greeting_message="Bonjour, bienvenue chez Produits Éro.",
        voice_api_key_hash="hash_abc123",
        voice_api_key_last4="1234",
        enabled=True,
    )
    voice_db.add(config)
    voice_db.commit()

    identity = MagicMock()
    identity.user = user

    result = list_voice_premium_features(identity=identity, db=voice_db)
    assert result["available_count"] == 6
    assert result["testing_count"] == 3
    assert result["coming_soon_count"] == 1

    features_by_key = {f["key"]: f for f in result["features"]}

    # Core available features should be 'ready' when enabled
    assert features_by_key["ultra_low_latency_voice"]["operational_status"] == "ready"
    assert features_by_key["adaptive_ai_router"]["operational_status"] == "ready"
    assert features_by_key["self_healing_voice"]["operational_status"] == "ready"
    assert features_by_key["live_multilingual_assistant"]["operational_status"] == "ready"
    assert features_by_key["smart_human_handoff"]["operational_status"] == "ready"
    assert features_by_key["company_knowledge_brain"]["operational_status"] == "ready"

    # Testing features stay 'in_testing'
    assert features_by_key["revenue_growth_copilot"]["operational_status"] == "in_testing"
    assert features_by_key["omnichannel_memory"]["operational_status"] == "in_testing"
    assert features_by_key["voice_roi_analytics"]["operational_status"] == "in_testing"

    # Coming soon stays 'planned'
    assert features_by_key["employee_performance_coach"]["operational_status"] == "planned"

    assert result["operational_ready_count"] == 6
    assert result["operational_configuration_required_count"] == 0


def test_voice_premium_operational_readiness_with_disabled_config(voice_db: Session):
    cid = uuid4()
    company = Company(
        id=cid,
        name="Inactive Company",
        slug="inactive-company",
        email="contact@inactivecompany.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        status=CompanyStatus.ACTIVE,
        subscription_plan="base",
    )
    voice_db.add(company)

    user = User(
        id=uuid4(),
        company_id=company.id,
        email="inactive@example.com",
        password_hash="hashed_pw_test",
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    voice_db.add(user)

    config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company.id,
        business_name="Inactive Business",
        timezone_name="America/Toronto",
        opening_hours={},
        services=[],
        voice_api_key_hash="hash_xyz789",
        voice_api_key_last4="7890",
        greeting_message="Hello",
        enabled=False,  # NOT active yet!
    )
    voice_db.add(config)
    voice_db.commit()

    identity = MagicMock()
    identity.user = user

    result = list_voice_premium_features(identity=identity, db=voice_db)
    # Available features should require configuration/activation
    features_by_key = {f["key"]: f for f in result["features"]}
    assert features_by_key["ultra_low_latency_voice"]["operational_status"] == "configuration_required"
    assert features_by_key["adaptive_ai_router"]["operational_status"] == "configuration_required"
    assert result["operational_configuration_required_count"] > 0


def test_voice_premium_operational_readiness_no_company(voice_db: Session):
    user = MagicMock()
    user.company_id = None
    identity = MagicMock()
    identity.user = user

    result = list_voice_premium_features(identity=identity, db=voice_db)
    for feature in result["features"]:
        assert feature["operational_status"] == "not_entitled"
        assert feature["operational_status_label_fr"] == "Non inclus"
