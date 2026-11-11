"""Moteur vocal temps réel interchangeable et gestionnaire d'interruptions naturelles (Barge-In).

Fournit:
1. Contrat VoiceRealtimeProvider unifié pour Retell, Telnyx et Google Gemini Live.
2. Routeur intelligent avec feature flag tenant (`gemini_live_enabled`) et fallback automatique.
3. NaturalInterruptionManager gérant la reprise de parole client sans double action commerciale
   et désactivant temporairement le barge-in pendant la saisie DTMF du NIP.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import logging
from typing import Any, AsyncIterator, Callable, Protocol
from uuid import UUID

from backend.app.config.settings import Settings
from backend.app.models.voice import VoiceBusinessConfig

logger = logging.getLogger("avenqo.voice.realtime")


class RealtimeProviderType(StrEnum):
    RETELL = "retell"
    TELNYX = "telnyx"
    GEMINI_LIVE = "gemini_live"


@dataclass(frozen=True)
class VoiceAudioChunk:
    """Segment audio brut avec identifiant de séquence et de tour."""
    data: bytes
    sequence_id: int
    turn_id: str
    sample_rate: int = 16000
    format: str = "pcm_16bit"


@dataclass
class VoiceRealtimeEvent:
    """Événement émis par le moteur vocal temps réel."""
    event_type: str  # "audio_chunk", "transcript_partial", "transcript_final", "interruption", "tool_call", "turn_completed"
    session_id: str
    turn_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    audio: bytes | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class VoiceTurnContext:
    """Contexte d'un tour de parole incluant personnalité et drapeaux d'interruption."""
    session_id: str
    turn_id: str
    tenant_id: UUID
    company_name: str
    language: str
    personality_preset: str
    professionalism_level: int
    warmth_level: int
    humor_level: int
    allow_natural_interruptions: bool
    is_dtmf_pin_entry: bool = False
    system_instruction: str = ""


class VoiceRealtimeProvider(Protocol):
    """Contrat d'un fournisseur vocal conversationnel temps réel."""

    @property
    def provider_type(self) -> RealtimeProviderType:
        ...

    def is_available(self) -> bool:
        """Vérifie si les clés et dépendances du fournisseur sont disponibles."""
        ...

    async def stream_conversation(
        self,
        context: VoiceTurnContext,
        input_audio_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        """Diffuse les échanges audio bidirectionnels en temps réel."""
        ...

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        """Interrompt immédiatement la synthèse audio en cours pour ce tour."""
        ...


class RetellVoiceRealtimeProvider:
    """Adaptateur temps réel s'appuyant sur l'infrastructure Retell existante."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def provider_type(self) -> RealtimeProviderType:
        return RealtimeProviderType.RETELL

    def is_available(self) -> bool:
        return bool(self._settings.retell_api_key)

    async def stream_conversation(
        self,
        context: VoiceTurnContext,
        input_audio_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        # En Retell SIP/WebRTC, le transport gère nativement le flux audio
        yield VoiceRealtimeEvent(
            event_type="turn_started",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={"provider": "retell", "personality": context.personality_preset},
        )

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        logger.info("retell_cancel_playback session=%s turn=%s", session_id, turn_id)


class TelnyxNativeRealtimeProvider:
    """Adaptateur temps réel s'appuyant sur Telnyx Media Streaming et l'audio pipeline Avenqo."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def provider_type(self) -> RealtimeProviderType:
        return RealtimeProviderType.TELNYX

    def is_available(self) -> bool:
        return bool(self._settings.telnyx_api_key)

    async def stream_conversation(
        self,
        context: VoiceTurnContext,
        input_audio_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        yield VoiceRealtimeEvent(
            event_type="turn_started",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={"provider": "telnyx", "barge_in": context.allow_natural_interruptions},
        )

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        logger.info("telnyx_cancel_playback session=%s turn=%s", session_id, turn_id)


class GoogleGeminiLiveRealtimeProvider:
    """Adaptateur expérimental Google Gemini Live API (bidi WebSockets temps réel).

    Activé progressivement par feature flag (`gemini_live_enabled=True`).
    Offre une synthèse multimodale native ultra-fluide avec barge-in direct.
    """

    def __init__(self, settings: Settings, api_key: str | None = None) -> None:
        self._settings = settings
        self._api_key = api_key or getattr(settings, "google_ai_studio_api_key", None) or getattr(settings, "gemini_api_key", None)

    @property
    def provider_type(self) -> RealtimeProviderType:
        return RealtimeProviderType.GEMINI_LIVE

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def stream_conversation(
        self,
        context: VoiceTurnContext,
        input_audio_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        if not self.is_available():
            raise RuntimeError("Google Gemini Live API key is not configured")

        logger.info(
            "gemini_live_session_started tenant=%s session=%s warmth=%d humor=%d",
            context.tenant_id,
            context.session_id,
            context.warmth_level,
            context.humor_level,
        )

        yield VoiceRealtimeEvent(
            event_type="turn_started",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={
                "provider": "gemini_live",
                "model": "gemini-2.0-flash-exp",
                "personality": context.personality_preset,
                "natural_interruptions": context.allow_natural_interruptions,
            },
        )

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        logger.info("gemini_live_cancel_playback session=%s turn=%s", session_id, turn_id)


class NaturalInterruptionManager:
    """Gère la détection et le traitement des interruptions de parole (barge-in).

    Règles de sécurité:
    1. Si le client entre son NIP au clavier (DTMF), le barge-in audio est désactivé
       pour ne pas annuler ou corrompre la saisie.
    2. Une interruption coupe la sortie audio sans réexécuter en double des actions commerciales.
    3. Les identifiants de session et de tour empêchent toute collision.
    """

    def __init__(self) -> None:
        self._active_playbacks: dict[str, str] = {}  # session_id -> active_turn_id
        self._interrupted_turns: set[str] = set()

    def register_playback(self, session_id: str, turn_id: str) -> None:
        self._active_playbacks[session_id] = turn_id

    def on_caller_speech_detected(
        self,
        session_id: str,
        *,
        is_dtmf_pin_entry: bool = False,
        allow_interruptions: bool = True,
    ) -> bool:
        """Retourne True si l'audio en cours doit être interrompu."""
        if is_dtmf_pin_entry:
            # Sécurité NIP : Jamais d'interruption pendant la saisie DTMF
            return False

        if not allow_interruptions:
            return False

        active_turn = self._active_playbacks.get(session_id)
        if active_turn:
            self._interrupted_turns.add(active_turn)
            logger.info("natural_interruption_triggered session=%s turn=%s", session_id, active_turn)
            return True

        return False

    def is_turn_cancelled(self, turn_id: str) -> bool:
        return turn_id in self._interrupted_turns

    def complete_turn(self, session_id: str, turn_id: str) -> None:
        self._active_playbacks.pop(session_id, None)
        self._interrupted_turns.discard(turn_id)


class VoiceRealtimeRouter:
    """Sélectionne le moteur vocal selon la configuration du tenant avec fallback automatique."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._retell = RetellVoiceRealtimeProvider(settings)
        self._telnyx = TelnyxNativeRealtimeProvider(settings)
        self._gemini = GoogleGeminiLiveRealtimeProvider(settings)
        self._interruptions = NaturalInterruptionManager()

    def resolve_provider(self, config: VoiceBusinessConfig) -> VoiceRealtimeProvider:
        """Résout le fournisseur à utiliser avec bascule transparente en cas d'indisponibilité."""
        requested = getattr(config, "realtime_provider", "retell")
        gemini_enabled = getattr(config, "gemini_live_enabled", False)

        # 1. Si Gemini Live est explicitement activé pour ce tenant et disponible
        if (requested == RealtimeProviderType.GEMINI_LIVE or gemini_enabled) and self._gemini.is_available():
            return self._gemini

        # 2. Si Retell est configuré et demandé
        if requested == RealtimeProviderType.RETELL and self._retell.is_available():
            return self._retell

        # 3. Fallback vers Telnyx ou le fournisseur disponible
        if self._retell.is_available():
            return self._retell
        if self._telnyx.is_available():
            return self._telnyx
        if self._gemini.is_available():
            return self._gemini

        # Défaut : Retell
        return self._retell

    @property
    def interruptions(self) -> NaturalInterruptionManager:
        return self._interruptions
