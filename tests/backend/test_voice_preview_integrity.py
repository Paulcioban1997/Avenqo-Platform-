"""Preview failures must not masquerade as successful or substituted audio."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.app.config.settings import Settings
from backend.app.models import BillingAccount
from backend.app.routers.voice import preview_voice, update_voice_customization
from backend.app.schemas.voice import VoicePreviewRequest, VoiceCustomizationUpdateRequest
from tests.backend.test_voice_agent import _voice_database


def test_preview_preserves_voice_and_model_and_fails_explicitly(tmp_path, monkeypatch):
    engine, db, company, config, *_ = _voice_database(tmp_path)
    db.add(BillingAccount(company_id=company.id, plan_code="professional", status="active"))
    db.commit()
    identity = SimpleNamespace(user=SimpleNamespace(company_id=company.id, company=company))
    settings = Settings(OPENAI_API_KEY="test-provider-key", VOICE_TTS_MODEL="gpt-4o-mini-tts")
    speech = AsyncMock(return_value=SimpleNamespace(content=b"real-mocked-audio"))
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **kwargs: SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(create=speech))))
    try:
        response = asyncio.run(preview_voice(VoicePreviewRequest(voice_id="ballad"), identity, db, settings))
        assert response.body == b"real-mocked-audio"
        assert speech.call_args.kwargs["voice"] == "ballad"
        assert speech.call_args.kwargs["model"] == "gpt-4o-mini-tts"
        assert speech.call_args.kwargs["response_format"] == "mp3"
        speech.side_effect = RuntimeError("provider unavailable")
        with pytest.raises(HTTPException) as failure:
            asyncio.run(preview_voice(VoicePreviewRequest(), identity, db, settings))
        assert failure.value.status_code == 503
        with pytest.raises(HTTPException) as unavailable:
            asyncio.run(preview_voice(VoicePreviewRequest(voice_id="ballad"), identity, db, settings.model_copy(update={"voice_tts_model": "tts-1"})))
        assert unavailable.value.status_code == 422
        with pytest.raises(HTTPException) as unconfigured:
            asyncio.run(preview_voice(VoicePreviewRequest(), identity, db, settings.model_copy(update={"openai_api_key": None})))
        assert unconfigured.value.status_code == 503
    finally:
        db.close()
        engine.dispose()


def test_partial_customization_preserves_values_and_can_clear_greeting(tmp_path):
    engine, db, company, config, *_ = _voice_database(tmp_path)
    db.add(BillingAccount(company_id=company.id, plan_code="professional", status="active"))
    db.commit()
    identity = SimpleNamespace(user=SimpleNamespace(company_id=company.id))
    try:
        config.speech_speed = 1.15
        config.personality_tone = "chaleureux"
        db.commit()
        result = update_voice_customization(VoiceCustomizationUpdateRequest(greeting_message=""), identity, db, Settings())
        assert result.greeting_message == ""
        assert result.speech_speed == 1.15
        assert result.personality_tone == "chaleureux"
        with pytest.raises(HTTPException) as invalid:
            update_voice_customization(VoiceCustomizationUpdateRequest(voice_id="invented"), identity, db, Settings())
        assert invalid.value.status_code == 422
    finally:
        db.close()
        engine.dispose()
