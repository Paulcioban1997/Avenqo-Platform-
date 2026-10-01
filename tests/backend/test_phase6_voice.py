from backend.app.core.locale_catalog import LOCALES
from backend.app.voice.central import default_voice_registry
from backend.app.voice.adapters import (
    ExternalVoiceConfigurationRequired,
    OpenAIAudioConfig,
    OpenAISpeechToTextAdapter,
    OpenAITextToSpeechAdapter,
)
import pytest


def test_voice_provider_capabilities_use_the_canonical_44_locales() -> None:
    codes = {locale.locale for locale in LOCALES}
    registry = default_voice_registry(codes)
    assert len(codes) == 44
    assert registry.compatible("fr", "speech_to_text")
    assert registry.compatible("ar", "text_to_speech") == ()
    assert registry.compatible("fr", "realtime_audio") == ()


def test_unconfigured_realtime_provider_is_not_claimed_as_available() -> None:
    registry = default_voice_registry({locale.locale for locale in LOCALES})
    assert all(provider.configured is False for provider in registry.list() if provider.provider_id == "retell")
    assert registry.compatible("fr", "realtime_audio") == ()


@pytest.mark.asyncio
async def test_configured_adapter_contract_fails_closed_without_provider_credentials() -> None:
    config = OpenAIAudioConfig(None, None, None, None)
    with pytest.raises(ExternalVoiceConfigurationRequired):
        await OpenAISpeechToTextAdapter(config).transcribe(b"audio", locale="fr", content_type="audio/webm")
    with pytest.raises(ExternalVoiceConfigurationRequired):
        await OpenAITextToSpeechAdapter(config).synthesize("hello", locale="fr")
