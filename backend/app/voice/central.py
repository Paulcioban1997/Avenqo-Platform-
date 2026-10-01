"""Provider-neutral Voice Central contracts and configured capability registry."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class VoiceProviderCapabilities:
    provider_id: str
    realtime_audio: bool
    speech_to_text: bool
    text_to_speech: bool
    streaming_stt: bool
    streaming_tts: bool
    interruption: bool
    supported_locales: frozenset[str]
    configured: bool = False


class VoiceProviderRegistry:
    def __init__(self, providers: Iterable[VoiceProviderCapabilities] = ()) -> None:
        self._providers = {provider.provider_id: provider for provider in providers}

    def register(self, provider: VoiceProviderCapabilities) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"Voice provider '{provider.provider_id}' already registered")
        self._providers[provider.provider_id] = provider

    def list(self) -> tuple[VoiceProviderCapabilities, ...]:
        return tuple(self._providers.values())

    def compatible(self, locale: str, capability: str) -> tuple[VoiceProviderCapabilities, ...]:
        return tuple(
            provider for provider in self._providers.values()
            if provider.configured
            and locale in provider.supported_locales
            and bool(getattr(provider, capability, False))
        )


class ExternalVoiceConfiguration:
    """Explicit fallback state when no STT/TTS credentials are configured."""

    reason = "external_configuration_required"

    def stt(self, *_args, **_kwargs):
        raise RuntimeError(self.reason)

    def tts(self, *_args, **_kwargs):
        raise RuntimeError(self.reason)


def default_voice_registry(locales: Iterable[str]) -> VoiceProviderRegistry:
    supported = frozenset(locales)
    return VoiceProviderRegistry((
        VoiceProviderCapabilities(
            provider_id="retell",
            realtime_audio=True,
            speech_to_text=True,
            text_to_speech=True,
            streaming_stt=True,
            streaming_tts=True,
            interruption=True,
            supported_locales=supported,
            configured=False,
        ),
        VoiceProviderCapabilities(
            provider_id="browser_speech",
            realtime_audio=False,
            speech_to_text=True,
            text_to_speech=False,
            streaming_stt=True,
            streaming_tts=False,
            interruption=True,
            supported_locales=supported,
            configured=True,
        ),
    ))
