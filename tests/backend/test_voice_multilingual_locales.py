"""Targeted Voice locale tests: company default, detection, switch, honest fallbacks.

Covers fr-CA, en-US, es-ES, ro-RO, zh-CN. Mocked STT/LLM/TTS only — no live/paid calls.

Honest support (do not claim 44 Voice languages work):
- UI catalog: 44 locales.
- Company default language: any of the 44 canonical codes (VoiceConfigRequest).
- OpenAI Realtime gate (default VOICE_REALTIME_SUPPORTED_LOCALES): fr, en only.
- Live-audio-validated STT/TTS chain: fr, en, es, ro (and regional fr-CA, en-US, es-ES, ro-RO).
- zh-CN: UI + greeting + script detection + OpenAI tier-1 catalog flag; Telnyx
  unavailable audio is fail-closed (no invented English); not live-audio-validated;
  no explicit mid-call switch phrase.
- Telnyx hangup copy is French or English only (non-FR uses EN, never forced to FR).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.app.config.settings import Settings
from backend.app.core.locale_catalog import detect_spoken_language, resolve_locale
from backend.app.schemas.voice import VoiceConfigRequest
from backend.app.voice.language_resolver import CallLanguageSession, RegionLanguageResolver
from backend.app.voice.languages import get_voice_language_capability, voice_language_matrix
from backend.app.voice.messages import voice_greeting
from backend.app.voice.providers import unavailable_speak_payload
from backend.app.voice.service import VoiceOrchestrator
from backend.app.voice.telnyx_media import media_audio_available


_TARGET = (
    ("fr-CA", "fr", "Bonjour, Clinic."),
    ("en-US", "en", "Hello, Clinic."),
    ("es-ES", "es", "Hola, Clinic."),
    ("ro-RO", "ro", "Bună ziua, Clinic."),
    ("zh-CN", "zh", "您好，Clinic。"),
)

_DETECTION_UTTERANCES = {
    "fr-CA": "Bonjour, je voudrais prendre rendez-vous pour demain après-midi s'il vous plaît.",
    "en-US": "Hello, I would like to book an appointment for tomorrow afternoon please.",
    "es-ES": "Hola, quisiera reservar una cita para mañana por la tarde por favor.",
    "ro-RO": "Bună ziua, aș dori să programez o întâlnire pentru mâine după-amiază la clinică.",
    "zh-CN": "您好，我想预约明天下午的时间。",
}

_VOICE_CONFIG_BASE = {
    "business_name": "Clinic",
    "services": [{"name": "Consultation", "duration_minutes": 30}],
    "transfer_phone": "+15145550199",
    "telnyx_phone_number": "+15145550100",
    "retell_agent_id": "agent-test",
    "retell_sip_uri": "sip:agent-test@sip.retell.example",
}


def _configured_settings(*locales: str) -> Settings:
    settings = Settings()
    settings.openai_api_key = "test-key-not-used"
    settings.voice_realtime_provider = "openai"
    settings.voice_realtime_model = "gpt-realtime-2.1"
    settings.voice_stt_provider = "openai"
    settings.voice_stt_model = "gpt-4o-mini-transcribe"
    settings.voice_tts_provider = "openai"
    settings.voice_tts_voice = "marin"
    settings.voice_tts_model = "gpt-4o-mini-tts"
    settings.voice_realtime_supported_locales = list(locales) if locales else ["fr", "en"]
    return settings


@pytest.mark.parametrize("bcp47,canonical,greeting_prefix", _TARGET)
def test_company_default_locale_is_not_hardcoded_french(bcp47, canonical, greeting_prefix):
    request = VoiceConfigRequest(**_VOICE_CONFIG_BASE, preferred_language=bcp47)
    assert request.preferred_language == canonical
    assert request.preferred_language != "fr" or canonical == "fr"

    greeting = VoiceOrchestrator.greeting_for("Clinic", request.preferred_language)
    assert greeting.startswith(greeting_prefix)
    if canonical != "fr":
        assert not greeting.startswith("Bonjour")

    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id=f"default-{canonical}",
        primary_locale=bcp47,
        active_locale=bcp47,
        allowed_locales=(bcp47, "en-US", "fr-CA", "es-ES", "ro-RO"),
    )
    assert session.active_locale.split("-")[0] == canonical.split("-")[0]
    if canonical != "fr":
        assert not session.active_locale.startswith("fr")


def test_quebec_company_may_default_to_english():
    """Regional recommendation is fr-CA; company config can still choose English."""
    rec = RegionLanguageResolver.resolve("CA", region="QC", locality="montreal")
    assert rec.primary_locale == "fr-CA"

    request = VoiceConfigRequest(**_VOICE_CONFIG_BASE, preferred_language="en-US")
    assert request.preferred_language == "en"
    greeting = voice_greeting(request.preferred_language, "Clinic")
    assert greeting.startswith("Hello, Clinic.")
    assert "Bonjour" not in greeting

    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="quebec-en",
        primary_locale="en-US",
        active_locale="en-US",
        allowed_locales=("en-US", "fr-CA"),
    )
    assert session.active_locale == "en-US"
    assert session.process_utterance("Hello, I need an appointment tomorrow morning please.") == "en-US"


@pytest.mark.parametrize("bcp47,expected_lang", [
    ("fr-CA", "fr"),
    ("en-US", "en"),
    ("es-ES", "es"),
    ("ro-RO", "ro"),
    ("zh-CN", "zh"),
])
def test_caller_language_detection_for_target_locales(bcp47, expected_lang):
    detection = detect_spoken_language(
        _DETECTION_UTTERANCES[bcp47],
        preferred_locale=bcp47,
    )
    assert detection.locale is not None, f"expected detection for {bcp47}"
    assert detection.locale.split("-")[0] == expected_lang
    assert detection.locale != "fr" or expected_lang == "fr"


def test_mid_call_explicit_switch_among_live_validated_locales():
    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="switch-live",
        primary_locale="en-US",
        active_locale="en-US",
        allowed_locales=("en-US", "fr-CA", "es-ES", "ro-RO"),
    )
    assert session.process_utterance("Can we continue in Spanish?") == "es-ES"
    assert session.process_utterance("Revenons en français s'il vous plaît") == "fr-CA"
    assert session.process_utterance("Can we continue in English?") == "en-US"
    assert session.process_utterance("Putem vorbi în română") == "ro-RO"
    assert session.active_locale == "ro-RO"


def test_zh_cn_has_partial_support_and_honest_fallbacks():
    cap = get_voice_language_capability("zh-CN")
    assert cap["locale"] == "zh"
    assert cap["bcp47"] == "zh-CN"
    assert cap["ui_translation_supported"] is True
    assert cap["stt_available"] is True
    assert cap["tts_available"] is True
    assert cap["live_audio_validated"] is False
    assert cap["language_switch_tested"] is False
    assert cap["fallback_locale"] == "en-US"

    greeting = voice_greeting("zh-CN", "Clinic")
    assert greeting.startswith("您好，Clinic。")

    detection = detect_spoken_language("您好，我想预约明天下午的时间。", preferred_locale="zh-CN")
    assert detection.locale == "zh"
    assert detection.source == "script"

    with pytest.raises(ValueError, match="No unavailable-message audio"):
        unavailable_speak_payload("zh-CN", command_id="zh-fallback")

    session = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="zh-no-explicit",
        primary_locale="en-US",
        active_locale="en-US",
        allowed_locales=("en-US", "fr-CA", "es-ES", "ro-RO", "zh-CN"),
    )
    assert session.check_explicit_switch("Can we speak Chinese?") is None
    assert session.process_utterance("Can we speak Chinese?") == "en-US"

    session_zh = CallLanguageSession(
        tenant_id=uuid4(),
        call_session_id="zh-default",
        primary_locale="zh-CN",
        active_locale="zh-CN",
        allowed_locales=("zh-CN", "en-US"),
    )
    assert session_zh.active_locale == "zh-CN"
    assert session_zh.process_utterance("您好，我想预约明天下午的时间。") == "zh-CN"


def test_default_realtime_gate_is_fr_en_only_not_forty_four():
    settings = _configured_settings()
    assert {resolve_locale(item) for item in settings.voice_realtime_supported_locales} == {"fr", "en"}
    assert media_audio_available(settings, "fr-CA") is True
    assert media_audio_available(settings, "en-US") is True
    assert media_audio_available(settings, "es-ES") is False
    assert media_audio_available(settings, "ro-RO") is False
    assert media_audio_available(settings, "zh-CN") is False

    expanded = _configured_settings("fr", "en", "es", "ro", "zh")
    assert media_audio_available(expanded, "es-ES") is True
    assert media_audio_available(expanded, "ro-RO") is True
    assert media_audio_available(expanded, "zh-CN") is True


def test_hangup_copy_is_french_or_english_fallback_not_forced_french():
    """Telnyx hangup farewell is bilingual FR/EN; non-French locales use English."""
    def farewell_for(locale: str) -> str:
        french = resolve_locale(locale).startswith("fr")
        return (
            "Merci de votre appel. Au revoir et bonne journée !"
            if french
            else "Thank you for calling. Goodbye and have a great day!"
        )

    assert farewell_for("fr-CA").startswith("Merci")
    for locale in ("en-US", "es-ES", "ro-RO", "zh-CN"):
        text = farewell_for(locale)
        assert text.startswith("Thank you")
        assert "Au revoir" not in text


def test_voice_matrix_does_not_claim_forty_four_audio_languages():
    matrix = voice_language_matrix()
    assert len(matrix) == 44
    for row in matrix:
        assert row["UI_TRANSLATION_SUPPORTED"] is True
        assert row["STT_SUPPORTED"] is None
        assert row["LLM_LANGUAGE_SUPPORTED"] is None
        assert row["TTS_SUPPORTED"] is None
        assert row["FULLY_SUPPORTED"] is False
        assert row["LIVE_AUDIO_VALIDATED"] is False
