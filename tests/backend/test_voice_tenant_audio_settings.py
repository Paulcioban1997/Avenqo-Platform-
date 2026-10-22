"""Tenant settings reach provider requests; no real inference or telephone calls."""
from types import SimpleNamespace
import secrets
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models import VoiceBusinessConfig
from backend.app.schemas.voice import VoiceCustomizationUpdateRequest
from backend.app.schemas.voice_onboarding import VoiceBusinessProfileRequest
from backend.app.services.voice_onboarding_service import VoiceOnboardingService
from backend.app.voice.adapters import OpenAIRealtimeAudioAdapter
from backend.app.voice.audio_preferences import phone_audio_config
from backend.app.voice.module_actions import company_call_language_session
from backend.app.voice.service import VoiceOrchestrator
from tests.backend.test_voice_module_permissions import _activate, _company, _engine


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-realtime", "gpt-4o-realtime-preview"])
@pytest.mark.parametrize("language,voice,speed,noise", [
    ("fr", "shimmer", 0.85, "near_field"),
    ("en", "echo", 1.15, "far_field"),
    ("ro", "alloy", 1.0, "off"),
])
async def test_saved_company_settings_reach_realtime_and_survive_reload(
    tmp_path, monkeypatch, model, language, voice, speed, noise
):
    sent = []

    async def send(event):
        sent.append(event)

    class Connection:
        async def __aenter__(self):
            return SimpleNamespace(send=send)

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr("backend.app.voice.adapters.AsyncOpenAI", lambda **_: SimpleNamespace(
        realtime=SimpleNamespace(connect=lambda **_: Connection())))
    with Session(_engine(tmp_path, "audio.db")) as db:
        company, owner = _company(db, "audio-fixture")
        tenant = _activate(db, company, "voice", "crm")
        other, other_owner = _company(db, "other-audio-fixture")
        other_tenant = _activate(db, other, "voice", "crm")
        onboarding = VoiceOnboardingService(db)
        onboarding.save(other_tenant, other_owner.id, VoiceBusinessProfileRequest(
            business_name=other.name, industry="Fixture", primary_locale="en"))
        config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company.id))
        config.greeting_message = VoiceOrchestrator.greeting_for(company.name, config.preferred_language)
        config.voice_id, config.speech_speed = voice, speed
        config.personality_tone = "chaleureux"
        onboarding.save(tenant, owner.id, VoiceBusinessProfileRequest(
            business_name=company.name, industry="Fixture", primary_locale=language,
            secondary_locales=[], input_noise_reduction=noise))
        db.expire_all()
        config = db.get(VoiceBusinessConfig, config.id)
        assert onboarding.view(tenant)["profile"]["input_noise_reduction"] == noise
        assert onboarding.view(other_tenant)["profile"]["input_noise_reduction"] == "off"
        assert config.greeting_message == VoiceOrchestrator.greeting_for(company.name, language)
        call = SimpleNamespace(company_id=company.id, id=uuid4(), source_context={})
        session = company_call_language_session(db, config, call)
        assert session.primary_locale.split("-")[0] == language
        assert len(session.allowed_locales) == 1
        # Even an explicit request cannot enable an unconfigured language.
        blocked = "Can we speak Spanish please?"
        assert session.process_utterance(blocked).split("-")[0] == language
        adapter = OpenAIRealtimeAudioAdapter(phone_audio_config(db, Settings(
            _env_file=None, OPENAI_API_KEY=secrets.token_urlsafe(32)), config), model)
        await adapter.open(locale=language)
        payload = sent[0]["session"]
        assert "warm and welcoming" in payload["instructions"]
        assert "Start in " in payload["instructions"]
        expected_noise = None if noise == "off" else {"type": noise}
        if "preview" in model:
            assert payload["voice"] == voice
            assert payload["speed"] == speed
            assert payload["input_audio_noise_reduction"] == expected_noise
        else:
            assert payload["audio"]["output"]["voice"] == voice
            assert payload["audio"]["output"]["speed"] == speed
            assert payload["audio"]["input"]["noise_reduction"] == expected_noise
        await adapter.close()


def test_noise_mode_and_realtime_speed_are_validated():
    with pytest.raises(ValidationError):
        VoiceBusinessProfileRequest(business_name="Fixture", industry="Fixture", input_noise_reduction="invented")
    with pytest.raises(ValidationError):
        VoiceCustomizationUpdateRequest(speech_speed=1.6)


def test_language_save_preserves_a_custom_greeting(tmp_path):
    with Session(_engine(tmp_path, "greeting.db")) as db:
        company, owner = _company(db, "greeting-fixture")
        tenant = _activate(db, company, "voice", "crm")
        config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company.id))
        config.greeting_message = "Custom message chosen by the company"
        VoiceOnboardingService(db).save(tenant, owner.id, VoiceBusinessProfileRequest(
            business_name=company.name, industry="Fixture", primary_locale="en"))
        assert config.greeting_message == "Custom message chosen by the company"
