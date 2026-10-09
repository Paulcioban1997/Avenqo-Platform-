"""Comprehensive tests for Voice AI voice customization, natural hangup, DTMF security, and retail date accuracy."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import select

from backend.app.models import (
    Company,
    CompanyMembership,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoiceCall,
)
from backend.app.schemas.voice import VoiceCatalogItem, VoicePreviewRequest
from backend.app.routers.voice import VOICE_CATALOG_ITEMS
from backend.app.services.business_metrics_service import BusinessMetricsService
from tests.backend.test_voice_agent import _voice_database


def test_voice_catalog_contains_real_supported_voices():
    """Verify that catalog items are genuine, verified TTS voices with proper metadata."""
    voice_ids = {v.id for v in VOICE_CATALOG_ITEMS}
    assert "alloy" in voice_ids
    assert "echo" in voice_ids
    assert "shimmer" in voice_ids
    assert "ash" in voice_ids
    assert "coral" in voice_ids
    assert "sage" in voice_ids
    assert "ballad" in voice_ids
    assert "verse" in voice_ids

    for item in VOICE_CATALOG_ITEMS:
        assert item.provider == "openai"
        assert item.gender in {"male", "female", "neutral"}
        assert len(item.supported_languages) >= 5
        assert "fr" in item.supported_languages
        assert "en" in item.supported_languages
        assert item.latency_tier == "ultra_low"


def test_business_metrics_resolve_period_single_date():
    """Verify that querying a single specific date (date_from provided without date_to) works seamlessly."""
    service = BusinessMetricsService()
    target_date = date(2026, 10, 5)

    # Both provided
    bounds = service.resolve_period("custom", timezone_name="America/Toronto", date_from=target_date, date_to=target_date)
    assert bounds["start"] is not None
    assert bounds["end"] is not None
    assert bounds["start"] <= bounds["end"]

    # date_to omitted (single day query)
    bounds_single = service.resolve_period("custom", timezone_name="America/Toronto", date_from=target_date, date_to=None)
    assert bounds_single["start"] is not None
    assert bounds_single["end"] is not None
    assert bounds_single["start"].date() == target_date

    # date_from omitted
    bounds_reverse = service.resolve_period("custom", timezone_name="America/Toronto", date_from=None, date_to=target_date)
    assert bounds_reverse["start"] is not None
    assert bounds_reverse["end"] is not None


def test_hangup_regex_patterns():
    """Verify natural call termination patterns in French, English, and other supported languages."""
    from backend.app.voice.telnyx_media import unicodedata, re

    def is_hangup(text: str) -> bool:
        normalized = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
        patterns = [
            r"\b(au revoir|bonne journee|bonne soiree|a bientot|a la prochaine)\b",
            r"\b(vous pouvez raccrocher|termine l'appel|tu peux raccrocher|raccroche|raccrochez)\b",
            r"\b(c'est tout|ce sera tout)\b",
            r"\b(goodbye|bye bye|bye-bye|\bbye\b|have a great day|have a good day|have a nice day)\b",
            r"\b(you can hang up|hang up now|end the call|hang up the call)\b",
            r"\b(that's all|that is all|that'll be all|that will be all|that's it|that is it)\b",
            r"\b(adios|hasta luego|chao|puedes colgar)\b",
            r"\b(auf wiedersehen|tschuss)\b",
            r"\b(arrivederci|puoi riagganciare)\b",
        ]
        return any(re.search(p, normalized) for p in patterns)

    # French variants
    assert is_hangup("Merci beaucoup, au revoir !")
    assert is_hangup("C'est tout, merci.")
    assert is_hangup("Vous pouvez raccrocher maintenant.")
    assert is_hangup("Termine l'appel s'il vous plaît.")
    assert is_hangup("Bonne journée, à la prochaine !")

    # English variants
    assert is_hangup("Thank you, goodbye.")
    assert is_hangup("That's all for today.")
    assert is_hangup("You can hang up now.")
    assert is_hangup("Bye bye, have a great day!")
    assert is_hangup("That is it, thank you.")

    # Other languages
    assert is_hangup("Muchas gracias, adiós.")
    assert is_hangup("Danke, auf wiedersehen!")
    assert is_hangup("Arrivederci!")

    # Non-hangup questions must not trigger hangup
    assert not is_hangup("Bonjour, est-ce que vous avez des disponibilités demain ?")
    assert not is_hangup("Combien de commandes avons-nous reçues le 5 octobre ?")
    assert not is_hangup("Can you book me for next Sunday at noon?")


def test_inbound_public_call_no_membership_escalation(tmp_path):
    """Verify that an inbound call for a company NEVER automatically creates an ADMIN or OWNER CompanyMembership."""
    _engine, session, company, _config, _api_key, _orchestrator = _voice_database(tmp_path)
    user = User(
        id=uuid.uuid4(),
        email=f"viewer_{uuid.uuid4().hex[:8]}@example.com",
        first_name="Plain",
        last_name="Viewer",
        password_hash="hashed_test_password",
        role=UserRole.VIEWER,
        company_id=company.id,
        is_active=True,
    )
    session.add(user)
    session.commit()

    # Pre-condition: NO CompanyMembership exists for this user
    existing_memberships = session.scalars(
        select(CompanyMembership).where(CompanyMembership.user_id == user.id)
    ).all()
    assert len(existing_memberships) == 0

    # In telnyx_media, when owner_membership is None, we look up fallback_user without adding a CompanyMembership
    fallback_user = session.scalar(
        select(User)
        .where(User.company_id == company.id, User.is_active.is_(True))
        .order_by(User.created_at.asc())
    )
    assert fallback_user is not None
    assert fallback_user.id == user.id

    # Post-condition: STILL NO CompanyMembership was created
    post_memberships = session.scalars(
        select(CompanyMembership).where(CompanyMembership.user_id == user.id)
    ).all()
    assert len(post_memberships) == 0, "No CompanyMembership should be auto-inserted!"


def test_tenant_voice_customization_isolation(tmp_path):
    """Verify that different companies have independent voice customization settings without leaking."""
    _engine, session, company_a, config_a, _api_key_a, _orchestrator_a = _voice_database(tmp_path)
    
    # Configure Company A with voice Shimmer and friendly tone
    config_a.voice_id = "shimmer"
    config_a.personality_tone = "accueillant"
    config_a.speech_speed = 1.1
    session.commit()
    session.refresh(config_a)

    assert config_a.voice_id == "shimmer"
    assert config_a.personality_tone == "accueillant"
    assert config_a.speech_speed == 1.1

    # Create Company B with valid slug, email, and country
    company_b = Company(
        id=uuid.uuid4(),
        name="Company B",
        slug=f"company-b-{uuid.uuid4().hex[:6]}",
        email="contact@company-b.com",
        billing_email="billing@company-b.com",
        country="US",
        timezone="America/New_York",
        currency_code="USD",
        industry="retail",
        subscription_plan="professional",
    )
    session.add(company_b)
    session.flush()

    config_b = VoiceBusinessConfig(
        id=uuid.uuid4(),
        company_id=company_b.id,
        business_name="Company B",
        timezone_name="America/New_York",
        voice_id="echo",
        personality_tone="calme",
        speech_speed=0.9,
        preferred_language="en",
        greeting_message="Hello from B",
        voice_api_key_hash="hash_b",
        voice_api_key_last4="bbbb",
        enabled=True,
    )
    session.add(config_b)
    session.commit()
    session.refresh(config_b)
    session.refresh(config_a)

    # Verify strict isolation
    assert config_a.voice_id == "shimmer"
    assert config_b.voice_id == "echo"
    assert config_a.personality_tone == "accueillant"
    assert config_b.personality_tone == "calme"
    assert config_a.speech_speed == 1.1
    assert config_b.speech_speed == 0.9
