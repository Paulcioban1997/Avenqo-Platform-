"""Moteur vocal temps réel interchangeable et gestionnaire d'interruptions naturelles (Barge-In).

Fournit:
1. Contrat VoiceRealtimeProvider et adaptateurs temps réel complets pour Google Gemini Live,
   Telnyx Media Streaming et Retell.
2. GeminiLiveRealtimeAudioAdapter (conforme au protocole RealtimeAudioAdapter de TelnyxMediaBridge)
   connecté à l'API Google Gemini Live (`client.aio.live.connect`) avec conversion audio PCM 16kHz/24kHz
   et G.711 mu-law 8kHz via TelnyxAudioCodec.
3. FallbackRealtimeAudioAdapter garantissant le repli transparent vers le pipeline Telnyx/OpenAI
   en cas d'erreur de connexion ou de quota Gemini Live.
4. NaturalInterruptionManager gérant la coupure immédiate de lecture (barge-in), l'annulation des
   tours obsolètes, la déduplication stricte des appels d'outils et la suspension du barge-in
   pendant la saisie DTMF du NIP.
"""

from __future__ import annotations

import asyncio
import audioop
import base64
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import logging
from types import SimpleNamespace
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol
from uuid import UUID, uuid4

from backend.app.config.settings import Settings
from backend.app.core.locale_catalog import locale_info
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.voice.adapters import ExternalVoiceConfigurationRequired, OpenAIAudioConfig, RealtimeAudioAdapter
from backend.app.voice.audio_codec import TelnyxAudioCodec

logger = logging.getLogger("avenqo.voice.realtime")

_QUEUE_EOF = object()

# Modèles Gemini Live officiellement pris en charge (recommandé en tête).
SUPPORTED_GEMINI_LIVE_MODELS: tuple[str, ...] = (
    "gemini-3.8-live",
    "gemini-3.8-live-extended-thinking",
)

# Anciens identifiants retirés — ne jamais les substituer silencieusement.
RETIRED_GEMINI_LIVE_MODELS: frozenset[str] = frozenset(
    {
        "gemini-2.0-flash-live-001",
        "gemini-2.5-flash-native-audio-preview-12-2025",
        "gemini-2.0-flash-exp",
        "gemini-live-2.5-flash-preview",
        "gemini-2.5-flash-native-audio-preview-09-2025",
    }
)

DEFAULT_GEMINI_LIVE_MODEL = "gemini-3.8-live"


def _gemini_realtime_input_config(types: Any) -> Any:
    """Ask Gemini not to treat line echo as a barge-in.

    Telnyx still delivers caller audio. Authorized speech is requested only
    through speak(), so a model-side interruption must not cancel it.
    """
    handling = getattr(types, "ActivityHandling", None)
    config_type = getattr(types, "RealtimeInputConfig", None)
    if handling is None or config_type is None:
        return {"activity_handling": "NO_INTERRUPTION"}
    no_interruption = getattr(handling, "NO_INTERRUPTION", None)
    if no_interruption is None:
        return {"activity_handling": "NO_INTERRUPTION"}
    return config_type(activity_handling=no_interruption)


class UnsupportedGeminiLiveModelError(ValueError):
    """Raised when a configured/requested Gemini Live model is unknown or retired."""


def resolve_gemini_live_model(requested: str | None) -> str:
    """Return a supported Gemini Live model or raise — never silently remap."""
    model = (requested or DEFAULT_GEMINI_LIVE_MODEL).strip()
    if model in SUPPORTED_GEMINI_LIVE_MODELS:
        return model
    if model in RETIRED_GEMINI_LIVE_MODELS:
        logger.error(
            "gemini_live_model_retired requested=%s supported=%s",
            model,
            ",".join(SUPPORTED_GEMINI_LIVE_MODELS),
        )
        raise UnsupportedGeminiLiveModelError(
            f"Gemini Live model '{model}' is retired. "
            f"Use one of: {', '.join(SUPPORTED_GEMINI_LIVE_MODELS)}"
        )
    logger.error(
        "gemini_live_model_unsupported requested=%s supported=%s",
        model,
        ",".join(SUPPORTED_GEMINI_LIVE_MODELS),
    )
    raise UnsupportedGeminiLiveModelError(
        f"Gemini Live model '{model}' is not supported. "
        f"Use one of: {', '.join(SUPPORTED_GEMINI_LIVE_MODELS)}"
    )


@dataclass(frozen=True)
class VoiceRealtimeSessionDiagnostics:
    """Safe per-call diagnostics — never includes PIN, secrets, or spoken content."""

    provider: str
    model: str
    voice: str | None = None
    locale: str | None = None
    company_id: str | None = None
    fallback_reason: str | None = None
    error_code: str | None = None
    session_id: str | None = None

    def to_log_dict(self) -> dict[str, str | None]:
        return {
            "provider": self.provider,
            "model": self.model,
            "voice": self.voice,
            "locale": self.locale,
            "company_id": self.company_id,
            "fallback_reason": self.fallback_reason,
            "error_code": self.error_code,
            "session_id": self.session_id,
        }

# Correspondance entre les identifiants de voix Avenqo/OpenAI et les voix natives Gemini Live
GEMINI_VOICE_MAP: dict[str, str] = {
    "alloy": "Aoede",
    "shimmer": "Aoede",
    "coral": "Kore",
    "marin": "Aoede",
    "nova": "Kore",
    "echo": "Puck",
    "onyx": "Charon",
    "fable": "Fenrir",
    "ash": "Puck",
    "ballad": "Aoede",
    "sage": "Kore",
    "verse": "Puck",
    "aoede": "Aoede",
    "kore": "Kore",
    "puck": "Puck",
    "charon": "Charon",
    "fenrir": "Fenrir",
}


def resolve_gemini_voice(voice_id: str | None, default_voice: str = "Aoede") -> str:
    if not voice_id:
        return default_voice
    cleaned = voice_id.strip()
    if cleaned in {"Aoede", "Kore", "Puck", "Charon", "Fenrir"}:
        return cleaned
    return GEMINI_VOICE_MAP.get(cleaned.lower(), default_voice)


def build_personality_system_prompt(
    *,
    company_name: str,
    locale: str,
    personality_preset: str = "professional_premium_warm",
    professionalism_level: int = 100,
    warmth_level: int = 85,
    humor_level: int = 40,
    formality_level: int = 65,
    allow_natural_interruptions: bool = True,
    extra_instructions: str = "",
) -> str:
    lang_name = locale_info(locale).english_name
    preset_descriptions = {
        "professional_premium_warm": (
            "You are a high-end, warm, natural, and attentive human-like receptionist. "
            "You combine executive professionalism with genuine warmth and conversational fluidity."
        ),
        "formal": (
            "You are a formal, courteous, and institutional receptionist. "
            "Maintain a composed, respectful, and structured tone at all times."
        ),
        "casual_friendly": (
            "You are a friendly, upbeat, and approachable receptionist. "
            "Speak with dynamic energy while remaining helpful and accurate."
        ),
    }
    persona_desc = preset_descriptions.get(
        personality_preset,
        preset_descriptions["professional_premium_warm"],
    )
    barge_in_desc = (
        "Natural interruptions (barge-in) are enabled: keep sentences concise (1 to 2 short spoken sentences) "
        "so the caller can interject naturally at any moment."
        if allow_natural_interruptions
        else "Complete your concise spoken response clearly before waiting for the caller."
    )
    prompt = (
        f"You represent the company '{company_name}'. "
        f"Always pronounce and refer to the company strictly as '{company_name}'. "
        "Treat that spelling as a proper name in the caller's language. "
        "Do not read it as a number and do not replace it with an English common noun. "
        f"{persona_desc} "
        f"Start in {lang_name} and follow the caller's language if they switch languages. "
        f"Personality profile: preset={personality_preset}, professionalism={professionalism_level}%, "
        f"warmth={warmth_level}%, humor_and_spontaneity={humor_level}%, formality={formality_level}%. "
        "Never use humor during complaints, security/PIN checks, billing disputes, or urgent issues. "
        f"{barge_in_desc} "
        "STRICT RULE: Product reservations ('reserve_product') and phone checkouts are strictly prohibited over the phone; "
        "politely invite the caller to visit the physical store or official online website for product holds or purchases, "
        "while happily answering catalog, price, and stock questions or booking CRM service appointments ('create_appointment')."
    )
    if extra_instructions:
        prompt = f"{prompt}\n{extra_instructions.strip()}"
    return prompt


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
    event_type: str  # "turn_started", "audio_chunk", "transcript_partial", "transcript_final", "interruption", "tool_call", "turn_completed"
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
    formality_level: int = 65
    is_dtmf_pin_entry: bool = False
    system_instruction: str = ""
    allowed_tools: frozenset[str] = field(default_factory=frozenset)


class NaturalInterruptionManager:
    """Gère la détection et le traitement des interruptions de parole (barge-in) et la sécurité d'outils.

    Règles de sécurité:
    1. Si le client entre son NIP au clavier (DTMF), le barge-in audio est désactivé
       pour ne pas annuler ou corrompre la saisie.
    2. Une interruption coupe immédiatement la sortie audio et marque le tour comme annulé.
    3. Aucun outil ne peut être exécuté sur un tour annulé/interrompu, et aucun outil ne peut
       être exécuté deux fois avec les mêmes arguments dans le même tour (idempotence).
    4. `reserve_product` est toujours bloqué sur les parcours vocaux.
    """

    def __init__(self) -> None:
        self._active_playbacks: dict[str, str] = {}  # session_id -> active_turn_id
        self._interrupted_turns: set[str] = set()
        self._executed_tools: dict[str, set[str]] = {}  # turn_id -> set of tool execution fingerprints
        self._cancel_callbacks: dict[str, list[Callable[[], Awaitable[None] | None]]] = {}

    def register_playback(
        self,
        session_id: str,
        turn_id: str,
        on_cancel: Callable[[], Awaitable[None] | None] | None = None,
    ) -> None:
        self._active_playbacks[session_id] = turn_id
        if on_cancel is not None:
            self._cancel_callbacks.setdefault(turn_id, []).append(on_cancel)

    def active_turn_for(self, session_id: str) -> str | None:
        return self._active_playbacks.get(session_id)

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
            self._active_playbacks.pop(session_id, None)
            logger.info("natural_interruption_triggered session=%s turn=%s", session_id, active_turn)
            return True

        return False

    def cancel_turn(self, session_id: str, turn_id: str) -> None:
        self._interrupted_turns.add(turn_id)
        if self._active_playbacks.get(session_id) == turn_id:
            self._active_playbacks.pop(session_id, None)

    def is_turn_cancelled(self, turn_id: str) -> bool:
        return turn_id in self._interrupted_turns

    @staticmethod
    def _tool_fingerprint(tool_name: str, tool_args: dict[str, Any] | None = None) -> str:
        serialized = json.dumps(tool_args or {}, sort_keys=True, default=str)
        digest = hashlib.sha256(f"{tool_name}:{serialized}".encode("utf-8")).hexdigest()[:24]
        return f"{tool_name}:{digest}"

    def can_execute_tool(
        self,
        turn_id: str,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> bool:
        """Vérifie qu'un outil est autorisé, que le tour n'est pas interrompu et qu'il n'a pas déjà été exécuté."""
        if tool_name == "reserve_product":
            logger.warning("voice_tool_blocked_reserve_product turn=%s", turn_id)
            return False
        if self.is_turn_cancelled(turn_id):
            logger.info("voice_tool_skipped_cancelled_turn turn=%s tool=%s", turn_id, tool_name)
            return False
        fp = self._tool_fingerprint(tool_name, tool_args)
        executed = self._executed_tools.get(turn_id, set())
        if fp in executed:
            logger.info("voice_tool_deduplicated turn=%s tool=%s", turn_id, tool_name)
            return False
        return True

    def record_tool_execution(
        self,
        turn_id: str,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> None:
        fp = self._tool_fingerprint(tool_name, tool_args)
        self._executed_tools.setdefault(turn_id, set()).add(fp)

    def complete_turn(self, session_id: str, turn_id: str) -> None:
        if self._active_playbacks.get(session_id) == turn_id:
            self._active_playbacks.pop(session_id, None)
        self._interrupted_turns.discard(turn_id)
        self._cancel_callbacks.pop(turn_id, None)


class GeminiLiveRealtimeAudioAdapter:
    """Adaptateur audio temps réel bidirectionnel connecté à Google Gemini Live API.

    Implémente le protocole `RealtimeAudioAdapter` utilisé par `TelnyxMediaBridge`:
    - `open(locale)` : ouvre une session WebSocket bidirectionnelle `client.aio.live.connect`
    - `send_audio(audio)` : convertit le flux PCM16 24kHz en PCM16 16kHz et l'envoie en temps réel,
      avec détection d'activité vocale (VAD) et barge-in naturel
    - `speak(text)` : demande à Gemini Live de vocaliser la réponse autorisée d'Avenqo Central AI
      et émet les deltas audio PCM16 24kHz vers TelnyxMediaBridge
    - `interrupt()` : coupe immédiatement la génération/lecture en cours
    - `clear_input()` : réinitialise l'état d'entrée audio (notamment lors de la saisie DTMF du NIP)
    - `events()` : génère les événements normalisés attendus par `TelnyxMediaBridge`
    """

    provider_id = "gemini_live"

    def __init__(
        self,
        settings: Settings | OpenAIAudioConfig,
        config: VoiceBusinessConfig | None = None,
        *,
        audio_config: OpenAIAudioConfig | None = None,
        api_key: str | None = None,
        model: str | None = None,
        voice_name: str | None = None,
        company_name: str | None = None,
        client_factory: Callable[[str], Any] | None = None,
        vad_rms_threshold: int = 450,
        silence_frames_threshold: int = 12,
    ) -> None:
        if isinstance(settings, OpenAIAudioConfig):
            audio_config = settings
            settings = Settings()
        self._settings = settings
        self._config = config
        self._audio_config = audio_config
        self._api_key = (
            api_key
            or getattr(settings, "google_ai_api_key", None)
            or getattr(settings, "google_ai_studio_api_key", None)
            or getattr(settings, "gemini_api_key", None)
        )
        configured_model = model or getattr(settings, "gemini_live_model", None) or DEFAULT_GEMINI_LIVE_MODEL
        self._model = resolve_gemini_live_model(configured_model)
        raw_voice = (
            voice_name
            or (getattr(config, "voice_id", None) if config is not None else None)
            or (audio_config.tts_voice if audio_config is not None else None)
            or getattr(settings, "gemini_live_voice", "Aoede")
        )
        self._voice_name = resolve_gemini_voice(raw_voice)
        self._client_factory = client_factory
        self._vad_rms_threshold = vad_rms_threshold
        self._silence_frames_threshold = max(2, silence_frames_threshold)
        self._diagnostics: VoiceRealtimeSessionDiagnostics | None = None

        from backend.app.voice.messages import voice_speech_name
        resolved_company = voice_speech_name(config) if config is not None else None
        resolved_company = resolved_company or (
            company_name
            or (getattr(config, "effective_voice_name", None) if config is not None else None)
            or (getattr(config, "voice_display_name", None) if config is not None else None)
            or (getattr(config, "business_name", None) if config is not None else None)
        )
        if not resolved_company or not str(resolved_company).strip():
            raise ExternalVoiceConfigurationRequired(
                "Gemini Live requires an authorized company voice name; no tenant brand fallback is allowed"
            )
        self._company_name = str(resolved_company).strip().replace("_", " ")
        self._personality_preset = getattr(config, "personality_preset", "professional_premium_warm") if config is not None else "professional_premium_warm"
        self._professionalism_level = int(getattr(config, "professionalism_level", 100) if config is not None else 100)
        self._warmth_level = int(getattr(config, "warmth_level", 85) if config is not None else 85)
        self._humor_level = int(getattr(config, "humor_level", 40) if config is not None else 40)
        self._formality_level = int(getattr(config, "formality_level", 65) if config is not None else 65)
        self._allow_natural_interruptions = bool(getattr(config, "allow_natural_interruptions", True) if config is not None else True)
        self._delivery_style = (
            audio_config.delivery_style
            if audio_config is not None
            else "warm, welcoming, and highly professional"
        )

        self._ctx_manager: Any = None
        self._session: Any = None
        self._receive_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._in_rate_state: Any = None
        self._out_rate_state: Any = None
        self._speech_active: bool = False
        self._silence_frames: int = 0
        self._current_item_id: str | None = None
        self._current_response_id: str | None = None
        self._interrupted_responses: set[str] = set()
        self._transcript_parts: list[str] = []
        self._emitted_items: set[str] = set()
        self._closed: bool = False
        self._tts_active = False
        self._tts_response_id: str | None = None
        self._tts_audio_chunks = 0

    def _build_genai_client(self) -> Any:
        if not self._api_key:
            raise ExternalVoiceConfigurationRequired("GOOGLE_AI_API_KEY is required for Google Gemini Live")
        if self._client_factory is not None:
            return self._client_factory(self._api_key)
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ExternalVoiceConfigurationRequired("google-genai package is required for Gemini Live") from exc
        return genai.Client(
            vertexai=False,
            api_key=self._api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )

    def _build_live_config(self, locale: str) -> Any:
        system_prompt = build_personality_system_prompt(
            company_name=self._company_name,
            locale=locale,
            personality_preset=self._personality_preset,
            professionalism_level=self._professionalism_level,
            warmth_level=self._warmth_level,
            humor_level=self._humor_level,
            formality_level=self._formality_level,
            allow_natural_interruptions=self._allow_natural_interruptions,
        )
        try:
            from google.genai import types
            config = types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                system_instruction=types.Content(
                    parts=[types.Part.from_text(text=system_prompt)]
                ),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self._voice_name,
                        )
                    )
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
            )
            try:
                return types.LiveConnectConfig(
                    response_modalities=[types.Modality.AUDIO],
                    system_instruction=types.Content(
                        parts=[types.Part.from_text(text=system_prompt)]
                    ),
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self._voice_name,
                            )
                        )
                    ),
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                    realtime_input_config=_gemini_realtime_input_config(types),
                )
            except TypeError:
                return config
        except Exception:
            return {
                "response_modalities": ["AUDIO"],
                "system_instruction": system_prompt,
                "voice_name": self._voice_name,
            }

    async def open(self, *, locale: str) -> None:
        client = self._build_genai_client()
        live_config = self._build_live_config(locale)
        self._closed = False
        self._ctx_manager = client.aio.live.connect(model=self._model, config=live_config)
        self._session = await self._ctx_manager.__aenter__()
        self._receive_task = asyncio.create_task(self._receive_loop())
        await self._event_queue.put(SimpleNamespace(type="session.updated"))
        logger.info(
            "gemini_live_adapter_opened model=%s voice=%s locale=%s company=%s",
            self._model,
            self._voice_name,
            locale,
            self._company_name,
        )

    async def send_audio(self, audio: bytes) -> None:
        if self._session is None or self._closed:
            raise ExternalVoiceConfigurationRequired("Gemini Live session is not open")
        if not audio:
            return
        if len(audio) % 2 != 0:
            audio = audio[:-1]
        if not audio:
            return

        # Détection d'activité vocale (VAD) locale réactive + gestion du barge-in
        rms = audioop.rms(audio, 2)
        if rms >= self._vad_rms_threshold:
            self._silence_frames = 0
            if not self._speech_active:
                self._speech_active = True
                self._current_item_id = f"gemini-item-{uuid4().hex[:12]}"
                await self._event_queue.put(
                    SimpleNamespace(
                        type="input_audio_buffer.speech_started",
                        item_id=self._current_item_id,
                    )
                )
        elif self._speech_active:
            self._silence_frames += 1
            if self._silence_frames >= self._silence_frames_threshold:
                self._speech_active = False
                self._silence_frames = 0
                stopped_item = self._current_item_id or f"gemini-item-{uuid4().hex[:12]}"
                await self._event_queue.put(
                    SimpleNamespace(
                        type="input_audio_buffer.speech_stopped",
                        item_id=stopped_item,
                    )
                )
                with suppress(Exception):
                    await self._session.send_realtime_input(audio_stream_end=True)

        # Conversion PCM16 24kHz (sortie TelnyxAudioCodec.inbound_pcm) -> PCM16 16kHz (entrée native Gemini Live)
        pcm_16k, self._in_rate_state = audioop.ratecv(audio, 2, 1, 24000, 16000, self._in_rate_state)
        try:
            from google.genai import types
            blob: Any = types.Blob(data=pcm_16k, mime_type="audio/pcm;rate=16000")
        except Exception:
            blob = {"data": pcm_16k, "mime_type": "audio/pcm;rate=16000"}
        await self._session.send_realtime_input(audio=blob)

    async def speak(self, text: str) -> None:
        if self._session is None or self._closed:
            raise ExternalVoiceConfigurationRequired("Gemini Live session is not open")
        cleaned = (text or "").strip()
        if not cleaned:
            return
        if self._config is not None:
            from backend.app.voice.messages import apply_spoken_pronunciation
            cleaned = apply_spoken_pronunciation(cleaned, self._config)
        resp_id = f"gemini-resp-{uuid4().hex[:12]}"
        self._tts_response_id = resp_id
        self._tts_active = True
        self._tts_audio_chunks = 0
        self._current_response_id = resp_id
        await self._event_queue.put(
            SimpleNamespace(
                type="response.created",
                response=SimpleNamespace(id=resp_id),
            )
        )
        instruction = (
            "Speak the following authorized response verbatim in its original language "
            f"with a {self._delivery_style} delivery and natural human intonation. "
            f"Do not translate, summarize, or add extra claims:\n{cleaned}"
        )
        try:
            from google.genai import types
            turns: Any = types.Content(
                role="user",
                parts=[types.Part.from_text(text=instruction)],
            )
        except Exception:
            turns = [{"role": "user", "parts": [{"text": instruction}]}]
        await self._session.send_client_content(turns=turns, turn_complete=True)

    async def interrupt(self) -> None:
        if self._tts_response_id is not None:
            self._interrupted_responses.add(self._tts_response_id)
        self._tts_active = False
        self._tts_response_id = None
        self._tts_audio_chunks = 0
        if self._current_response_id is not None:
            interrupted_id = self._current_response_id
            self._interrupted_responses.add(interrupted_id)
            self._current_response_id = None
            await self._event_queue.put(
                SimpleNamespace(
                    type="response.done",
                    response=SimpleNamespace(
                        id=interrupted_id,
                        status="cancelled",
                        usage=None,
                    ),
                )
            )

    async def clear_input(self) -> None:
        self._speech_active = False
        self._silence_frames = 0
        self._transcript_parts.clear()
        self._in_rate_state = None
        self._current_item_id = None

    async def _flush_transcript(self) -> None:
        if not self._transcript_parts:
            return
        full_text = " ".join(part.strip() for part in self._transcript_parts if part and part.strip()).strip()
        self._transcript_parts.clear()
        if not full_text:
            return
        item_id = self._current_item_id or f"gemini-item-{uuid4().hex[:12]}"
        if item_id in self._emitted_items:
            item_id = f"gemini-item-{uuid4().hex[:12]}"
        self._emitted_items.add(item_id)
        self._current_item_id = None
        est_tokens = max(1, len(full_text) // 4)
        await self._event_queue.put(
            SimpleNamespace(
                type="conversation.item.input_audio_transcription.completed",
                item_id=item_id,
                transcript=full_text,
                event_id=f"evt-{item_id}",
                usage={
                    "type": "tokens",
                    "input_tokens": est_tokens,
                    "output_tokens": 1,
                    "input_token_details": {
                        "audio_tokens": est_tokens,
                        "text_tokens": 0,
                    },
                },
            )
        )

    async def _receive_loop(self) -> None:
        try:
            # google-genai AsyncSession.receive() yields ONE model turn and
            # returns after turn_complete. Re-enter it for the next turn or
            # Telnyx goes silent immediately after the initial greeting.
            while not self._closed:
                received_any = False
                async for message in self._session.receive():
                    received_any = True
                    if self._closed:
                        break
                    server_content = getattr(message, "server_content", None)
                    if server_content is None and isinstance(message, dict):
                        server_content = message.get("server_content")

                    if server_content is not None:
                        interrupted = getattr(server_content, "interrupted", False) or (
                            server_content.get("interrupted", False) if isinstance(server_content, dict) else False
                        )
                        if interrupted:
                            logger.info(
                                "gemini_live_interrupted_ignored tts_active=%s chunks=%s",
                                self._tts_active,
                                self._tts_audio_chunks,
                            )

                        # Transcription entrante de l'appelant
                        in_trans = getattr(server_content, "input_transcription", None) or (
                            server_content.get("input_transcription") if isinstance(server_content, dict) else None
                        )
                        if in_trans is not None:
                            text_val = getattr(in_trans, "text", None) or (
                                in_trans.get("text") if isinstance(in_trans, dict) else None
                            )
                            finished = getattr(in_trans, "finished", None)
                            if finished is None and isinstance(in_trans, dict):
                                finished = in_trans.get("finished")
                            if isinstance(text_val, str) and text_val.strip():
                                self._transcript_parts.append(text_val.strip())
                                if finished is not False or not self._speech_active:
                                    if self._speech_active:
                                        self._speech_active = False
                                        await self._event_queue.put(
                                            SimpleNamespace(
                                                type="input_audio_buffer.speech_stopped",
                                                item_id=self._current_item_id or f"gemini-item-{uuid4().hex[:12]}",
                                            )
                                        )
                                    await self._flush_transcript()

                        # Audio sortant du modèle Gemini Live
                        model_turn = getattr(server_content, "model_turn", None) or (
                            server_content.get("model_turn") if isinstance(server_content, dict) else None
                        )
                        if model_turn is not None:
                            parts = getattr(model_turn, "parts", None) or (
                                model_turn.get("parts") if isinstance(model_turn, dict) else ()
                            ) or ()
                            for part in parts:
                                inline = getattr(part, "inline_data", None) or (
                                    part.get("inline_data") if isinstance(part, dict) else None
                                )
                                if inline is None:
                                    continue
                                raw_audio = getattr(inline, "data", None) or (
                                    inline.get("data") if isinstance(inline, dict) else None
                                )
                                mime_type = str(
                                    getattr(inline, "mime_type", None)
                                    or (inline.get("mime_type") if isinstance(inline, dict) else "audio/pcm;rate=24000")
                                    or "audio/pcm;rate=24000"
                                )
                                if isinstance(raw_audio, str):
                                    raw_audio = base64.b64decode(raw_audio)
                                if not isinstance(raw_audio, (bytes, bytearray)) or not raw_audio:
                                    continue
                                raw_bytes = bytes(raw_audio)
                                if len(raw_bytes) % 2 != 0:
                                    raw_bytes = raw_bytes[:-1]
                                if not raw_bytes:
                                    continue

                                # Spontaneous model audio is not an authorized Central AI answer.
                                # Forward PCM only for the speak() response that is still open.
                                if not self._tts_active or self._tts_response_id is None:
                                    continue
                                if self._tts_response_id in self._interrupted_responses:
                                    continue
                                self._tts_audio_chunks += 1

                                # Normalisation en 24kHz PCM16 pour TelnyxAudioCodec.outbound_pcm
                                if "16000" in mime_type:
                                    pcm_24k, self._out_rate_state = audioop.ratecv(
                                        raw_bytes, 2, 1, 16000, 24000, self._out_rate_state
                                    )
                                elif "8000" in mime_type:
                                    pcm_24k, self._out_rate_state = audioop.ratecv(
                                        raw_bytes, 2, 1, 8000, 24000, self._out_rate_state
                                    )
                                else:
                                    pcm_24k = raw_bytes

                                b64_delta = base64.b64encode(pcm_24k).decode("ascii")
                                await self._event_queue.put(
                                    SimpleNamespace(
                                        type="response.output_audio.delta",
                                        response_id=self._tts_response_id,
                                        delta=b64_delta,
                                    )
                                )

                        turn_complete = getattr(server_content, "turn_complete", False) or (
                            server_content.get("turn_complete", False) if isinstance(server_content, dict) else False
                        )
                        waiting_for_input = getattr(server_content, "waiting_for_input", False) or (
                            server_content.get("waiting_for_input", False) if isinstance(server_content, dict) else False
                        )
                        if (turn_complete or waiting_for_input) and self._transcript_parts:
                            await self._flush_transcript()

                        if turn_complete and self._tts_active and self._tts_audio_chunks <= 0:
                            # This completion belongs to a model turn that started
                            # before speak(). Closing it would drop the answer.
                            continue
                        if turn_complete and self._tts_active and self._tts_response_id is not None:
                            done_id = self._tts_response_id
                            self._current_response_id = None
                            self._tts_active = False
                            self._tts_response_id = None
                            self._tts_audio_chunks = 0
                            usage_meta = getattr(message, "usage_metadata", None) or (
                                message.get("usage_metadata") if isinstance(message, dict) else None
                            )
                            in_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 10) if usage_meta else 10
                            out_tok = int(getattr(usage_meta, "response_token_count", 0) or 20) if usage_meta else 20
                            await self._event_queue.put(
                                SimpleNamespace(
                                    type="response.done",
                                    response=SimpleNamespace(
                                        id=done_id,
                                        status="completed",
                                        usage={
                                            "input_tokens": in_tok,
                                            "output_tokens": out_tok,
                                            "input_token_details": {
                                                "audio_tokens": in_tok,
                                                "text_tokens": 0,
                                                "cached_tokens": 0,
                                                "cached_tokens_details": {"audio_tokens": 0, "text_tokens": 0},
                                            },
                                            "output_token_details": {
                                                "audio_tokens": out_tok,
                                                "text_tokens": 0,
                                            },
                                        },
                                    ),
                                )
                            )

                if not received_any:
                    # EOF without a turn is not a normal pause. Fail closed
                    # rather than spin a CPU-burning empty receive loop.
                    raise ExternalVoiceConfigurationRequired(
                        "Gemini Live receive iterator ended without a turn"
                    )
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("gemini_live_receive_error: %s", exc, exc_info=True)
            await self._event_queue.put(
                SimpleNamespace(
                    type="error",
                    error=SimpleNamespace(code="gemini_live_stream_error", message=str(exc)),
                )
            )
        finally:
            await self._event_queue.put(_QUEUE_EOF)

    async def close(self) -> None:
        self._closed = True
        if self._receive_task is not None:
            self._receive_task.cancel()
            with suppress(Exception, asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None
        if self._ctx_manager is not None:
            with suppress(Exception):
                await self._ctx_manager.__aexit__(None, None, None)
            self._ctx_manager = None
        self._session = None
        await self._event_queue.put(_QUEUE_EOF)

    async def events(self):
        if self._session is None and self._event_queue.empty():
            raise ExternalVoiceConfigurationRequired("Gemini Live session is not open")
        while True:
            item = await self._event_queue.get()
            if item is _QUEUE_EOF:
                break
            yield item


class FallbackRealtimeAudioAdapter:
    """Adaptateur résilient tentant le fournisseur primaire (ex: Gemini Live) et basculant
    automatiquement vers l'adaptateur de secours (OpenAI Realtime / Telnyx) en cas d'échec.
    """

    def __init__(
        self,
        primary_factory: Callable[[], RealtimeAudioAdapter],
        fallback_factory: Callable[[], RealtimeAudioAdapter],
    ) -> None:
        self._primary_factory = primary_factory
        self._fallback_factory = fallback_factory
        self._active: RealtimeAudioAdapter | None = None
        self.used_fallback: bool = False
        self.last_diagnostics: VoiceRealtimeSessionDiagnostics | None = None

    @property
    def provider_id(self) -> str:
        if self._active is not None:
            return getattr(self._active, "provider_id", "openai")
        return "gemini_live"

    @property
    def using_fallback(self) -> bool:
        return self.used_fallback

    async def open(self, *, locale: str = "fr-CA") -> None:
        primary = self._primary_factory()
        primary_model = str(getattr(primary, "_model", "") or getattr(primary, "model_name", "") or "unknown")
        primary_voice = str(getattr(primary, "_voice_name", "") or "") or None
        company_id = None
        config = getattr(primary, "_config", None)
        if config is not None and getattr(config, "company_id", None) is not None:
            company_id = str(config.company_id)
        try:
            try:
                await primary.open(locale=locale)
            except TypeError:
                await primary.open()  # type: ignore[call-arg]
            self._active = primary
            self.used_fallback = False
            self.last_diagnostics = VoiceRealtimeSessionDiagnostics(
                provider=str(getattr(primary, "provider_id", "gemini_live")),
                model=primary_model,
                voice=primary_voice,
                locale=locale,
                company_id=company_id,
            )
            logger.info("voice_realtime_session %s", self.last_diagnostics.to_log_dict())
        except Exception as exc:
            error_code = type(exc).__name__
            logger.warning(
                "realtime_adapter_primary_failed provider=%s model=%s error_code=%s falling_back=True",
                getattr(primary, "provider_id", "primary"),
                primary_model,
                error_code,
            )
            with suppress(Exception):
                await primary.close()
            fallback = self._fallback_factory()
            try:
                await fallback.open(locale=locale)
            except TypeError:
                await fallback.open()  # type: ignore[call-arg]
            self._active = fallback
            self.used_fallback = True
            self.last_diagnostics = VoiceRealtimeSessionDiagnostics(
                provider=str(getattr(fallback, "provider_id", "fallback")),
                model=str(getattr(fallback, "_model", "") or "fallback"),
                voice=primary_voice,
                locale=locale,
                company_id=company_id,
                fallback_reason="primary_open_failed",
                error_code=error_code,
            )
            logger.info("voice_realtime_session %s", self.last_diagnostics.to_log_dict())

    async def send_audio(self, audio: bytes) -> None:
        if self._active is None:
            raise ExternalVoiceConfigurationRequired("Realtime session is not open")
        await self._active.send_audio(audio)

    async def speak(self, text: str) -> None:
        if self._active is None:
            raise ExternalVoiceConfigurationRequired("Realtime session is not open")
        await self._active.speak(text)

    async def interrupt(self) -> None:
        if self._active is not None:
            await self._active.interrupt()

    async def clear_input(self) -> None:
        if self._active is not None:
            await self._active.clear_input()

    async def close(self) -> None:
        if self._active is not None:
            await self._active.close()
            self._active = None

    async def events(self):
        if self._active is None:
            raise ExternalVoiceConfigurationRequired("Realtime session is not open")
        async for event in self._active.events():
            yield event


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
        *,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        authorized_tools: list[dict[str, Any]] | None = None,
        interruption_manager: NaturalInterruptionManager | None = None,
        input_codec: str = "pcm_16k",
        output_codec: str = "pcm_24k",
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        """Diffuse les échanges audio bidirectionnels et les appels d'outils en temps réel."""
        ...

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        """Interrompt immédiatement la synthèse audio en cours pour ce tour."""
        ...


class RetellVoiceRealtimeProvider:
    """Adaptateur temps réel s'appuyant sur l'infrastructure Retell existante."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cancelled_turns: set[tuple[str, str]] = set()

    @property
    def provider_type(self) -> RealtimeProviderType:
        return RealtimeProviderType.RETELL

    def is_available(self) -> bool:
        return bool(self._settings.retell_api_key)

    async def stream_conversation(
        self,
        context: VoiceTurnContext,
        input_audio_stream: AsyncIterator[bytes],
        *,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        authorized_tools: list[dict[str, Any]] | None = None,
        interruption_manager: NaturalInterruptionManager | None = None,
        input_codec: str = "pcm_16k",
        output_codec: str = "pcm_24k",
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        mgr = interruption_manager or NaturalInterruptionManager()
        mgr.register_playback(context.session_id, context.turn_id)
        yield VoiceRealtimeEvent(
            event_type="turn_started",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={"provider": "retell", "personality": context.personality_preset},
        )
        seq = 0
        async for chunk in input_audio_stream:
            if not chunk:
                continue
            seq += 1
            if (context.session_id, context.turn_id) in self._cancelled_turns or mgr.is_turn_cancelled(context.turn_id):
                yield VoiceRealtimeEvent(
                    event_type="interruption",
                    session_id=context.session_id,
                    turn_id=context.turn_id,
                    payload={"provider": "retell", "sequence_id": seq},
                )
                break
            yield VoiceRealtimeEvent(
                event_type="audio_chunk",
                session_id=context.session_id,
                turn_id=context.turn_id,
                audio=chunk,
                payload={"provider": "retell", "sequence_id": seq},
            )
        mgr.complete_turn(context.session_id, context.turn_id)
        yield VoiceRealtimeEvent(
            event_type="turn_completed",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={"provider": "retell", "frames_processed": seq},
        )

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        self._cancelled_turns.add((session_id, turn_id))
        logger.info("retell_cancel_playback session=%s turn=%s", session_id, turn_id)


class TelnyxNativeRealtimeProvider:
    """Adaptateur temps réel s'appuyant sur Telnyx Media Streaming et TelnyxAudioCodec."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cancelled_turns: set[tuple[str, str]] = set()

    @property
    def provider_type(self) -> RealtimeProviderType:
        return RealtimeProviderType.TELNYX

    def is_available(self) -> bool:
        return bool(self._settings.telnyx_api_key or self._settings.openai_api_key)

    async def stream_conversation(
        self,
        context: VoiceTurnContext,
        input_audio_stream: AsyncIterator[bytes],
        *,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        authorized_tools: list[dict[str, Any]] | None = None,
        interruption_manager: NaturalInterruptionManager | None = None,
        input_codec: str = "pcmu_8k",
        output_codec: str = "pcmu_8k",
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        codec = TelnyxAudioCodec()
        mgr = interruption_manager or NaturalInterruptionManager()
        mgr.register_playback(context.session_id, context.turn_id)
        yield VoiceRealtimeEvent(
            event_type="turn_started",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={
                "provider": "telnyx",
                "barge_in": context.allow_natural_interruptions,
                "input_codec": input_codec,
                "output_codec": output_codec,
            },
        )
        seq = 0
        async for raw_frame in input_audio_stream:
            if not raw_frame:
                continue
            seq += 1
            if (context.session_id, context.turn_id) in self._cancelled_turns or mgr.is_turn_cancelled(context.turn_id):
                yield VoiceRealtimeEvent(
                    event_type="interruption",
                    session_id=context.session_id,
                    turn_id=context.turn_id,
                    payload={"provider": "telnyx", "sequence_id": seq},
                )
                break
            if input_codec == "pcmu_8k":
                b64_in = base64.b64encode(raw_frame[:160]).decode("ascii")
                pcm_24k = codec.inbound_pcm(b64_in)
            else:
                pcm_24k = raw_frame
            out_bytes = (
                codec.outbound_pcm(base64.b64encode(pcm_24k).decode("ascii"))
                if output_codec == "pcmu_8k"
                else pcm_24k
            )
            yield VoiceRealtimeEvent(
                event_type="audio_chunk",
                session_id=context.session_id,
                turn_id=context.turn_id,
                audio=out_bytes,
                payload={"provider": "telnyx", "sequence_id": seq},
            )
        mgr.complete_turn(context.session_id, context.turn_id)
        yield VoiceRealtimeEvent(
            event_type="turn_completed",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={"provider": "telnyx", "frames_processed": seq},
        )

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        self._cancelled_turns.add((session_id, turn_id))
        logger.info("telnyx_cancel_playback session=%s turn=%s", session_id, turn_id)


class GoogleGeminiLiveRealtimeProvider:
    """Fournisseur Google Gemini Live API (streaming audio bidirectionnel natif et appels d'outils Central AI).

    Connecté via `google.genai.Client.aio.live.connect`:
    - Authentification sécurisée par clé API (`GOOGLE_AI_API_KEY`)
    - Conversion audio transparente entre Telnyx G.711 mu-law 8kHz, PCM 16kHz (entrée Gemini) et PCM 24kHz (sortie Gemini)
    - Exécution des outils Avenqo Central autorisés avec blocage strict de `reserve_product` et déduplication par tour
    - Interruptions naturelles (barge-in) temps réel avec suppression pendant la saisie DTMF du NIP
    """

    def __init__(
        self,
        settings: Settings,
        api_key: str | None = None,
        *,
        model: str | None = None,
        voice_name: str | None = None,
        client_factory: Callable[[str], Any] | None = None,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        vad_rms_threshold: int = 450,
    ) -> None:
        self._settings = settings
        self._api_key = (
            api_key
            or getattr(settings, "google_ai_api_key", None)
            or getattr(settings, "google_ai_studio_api_key", None)
            or getattr(settings, "gemini_api_key", None)
        )
        configured_model = model or getattr(settings, "gemini_live_model", None) or DEFAULT_GEMINI_LIVE_MODEL
        self._model = resolve_gemini_live_model(configured_model)
        self._voice_name = resolve_gemini_voice(voice_name or getattr(settings, "gemini_live_voice", "Aoede"))
        self._client_factory = client_factory
        self._default_tool_executor = tool_executor
        self._vad_rms_threshold = vad_rms_threshold
        self._cancelled_turns: set[tuple[str, str]] = set()
        self._active_sessions: dict[str, Any] = {}
        self._last_diagnostics: VoiceRealtimeSessionDiagnostics | None = None

    @property
    def provider_type(self) -> RealtimeProviderType:
        return RealtimeProviderType.GEMINI_LIVE

    @property
    def model_name(self) -> str:
        return self._model

    def is_available(self) -> bool:
        return bool(self._api_key)

    def create_audio_adapter(
        self,
        config: VoiceBusinessConfig | None = None,
        audio_config: OpenAIAudioConfig | None = None,
    ) -> GeminiLiveRealtimeAudioAdapter:
        return GeminiLiveRealtimeAudioAdapter(
            self._settings,
            config,
            audio_config=audio_config,
            api_key=self._api_key,
            model=self._model,
            voice_name=self._voice_name,
            client_factory=self._client_factory,
            vad_rms_threshold=self._vad_rms_threshold,
        )

    def _build_client(self) -> Any:
        if not self.is_available():
            raise RuntimeError("Google Gemini Live API key is not configured")
        if self._client_factory is not None:
            return self._client_factory(str(self._api_key))
        from google import genai
        from google.genai import types
        return genai.Client(
            vertexai=False,
            api_key=self._api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )

    @staticmethod
    def sanitize_authorized_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Filtre les déclarations d'outils pour exclure strictement `reserve_product` sur les appels vocaux."""
        if not tools:
            return []
        sanitized: list[dict[str, Any]] = []
        for tool in tools:
            name = str(tool.get("name") or "")
            if not name or name == "reserve_product":
                continue
            sanitized.append(tool)
        return sanitized

    def _build_live_connect_config(
        self,
        context: VoiceTurnContext,
        authorized_tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        company_name = (context.company_name or "").strip()
        if not company_name:
            raise ExternalVoiceConfigurationRequired(
                "Gemini Live session requires context.company_name from the authorized tenant"
            )
        system_prompt = build_personality_system_prompt(
            company_name=company_name,
            locale=context.language or "fr-CA",
            personality_preset=context.personality_preset,
            professionalism_level=context.professionalism_level,
            warmth_level=context.warmth_level,
            humor_level=context.humor_level,
            formality_level=context.formality_level,
            allow_natural_interruptions=context.allow_natural_interruptions,
            extra_instructions=context.system_instruction,
        )
        safe_tools = self.sanitize_authorized_tools(authorized_tools)
        try:
            from google.genai import types
            tool_objs = None
            if safe_tools:
                func_decls = [
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("parameters"),
                    )
                    for t in safe_tools
                ]
                tool_objs = [types.Tool(function_declarations=func_decls)]
            return types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                system_instruction=types.Content(
                    parts=[types.Part.from_text(text=system_prompt)]
                ),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self._voice_name,
                        )
                    )
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
                tools=tool_objs,
            )
        except Exception:
            return {
                "response_modalities": ["AUDIO"],
                "system_instruction": system_prompt,
                "voice_name": self._voice_name,
                "tools": safe_tools,
            }

    async def stream_conversation(
        self,
        context: VoiceTurnContext,
        input_audio_stream: AsyncIterator[bytes],
        *,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        authorized_tools: list[dict[str, Any]] | None = None,
        interruption_manager: NaturalInterruptionManager | None = None,
        input_codec: str = "pcm_16k",
        output_codec: str = "pcm_24k",
    ) -> AsyncIterator[VoiceRealtimeEvent]:
        if not self.is_available():
            raise RuntimeError("Google Gemini Live API key is not configured")

        active_tool_executor = tool_executor or self._default_tool_executor
        mgr = interruption_manager or NaturalInterruptionManager()
        codec = TelnyxAudioCodec()
        in_rate_state: Any = None
        out_rate_state: Any = None
        safe_tools = self.sanitize_authorized_tools(authorized_tools)

        logger.info(
            "gemini_live_session_started tenant=%s session=%s model=%s warmth=%d humor=%d",
            context.tenant_id,
            context.session_id,
            self._model,
            context.warmth_level,
            context.humor_level,
        )

        yield VoiceRealtimeEvent(
            event_type="turn_started",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={
                "provider": "gemini_live",
                "model": self._model,
                "voice": self._voice_name,
                "personality": context.personality_preset,
                "natural_interruptions": context.allow_natural_interruptions,
                "authorized_tools": [t["name"] for t in safe_tools],
            },
        )

        client = self._build_client()
        live_config = self._build_live_connect_config(context, safe_tools)

        async with client.aio.live.connect(model=self._model, config=live_config) as session:
            self._active_sessions[context.session_id] = session
            mgr.register_playback(context.session_id, context.turn_id)

            event_queue: asyncio.Queue[VoiceRealtimeEvent | object] = asyncio.Queue()
            done_sentinel = object()
            assistant_speaking = False

            async def _pump_inbound_audio() -> None:
                nonlocal in_rate_state, assistant_speaking
                seq = 0
                try:
                    async for raw_item in input_audio_stream:
                        if isinstance(raw_item, VoiceAudioChunk):
                            chunk = raw_item.data
                            eff_codec = raw_item.format if raw_item.format != "pcm_16bit" else input_codec
                        else:
                            chunk = raw_item
                            eff_codec = input_codec
                        if not chunk:
                            continue
                        seq += 1
                        if eff_codec == "pcmu_8k":
                            b64_payload = base64.b64encode(chunk[:160]).decode("ascii")
                            pcm_24k = codec.inbound_pcm(b64_payload)
                            pcm_16k, in_rate_state = audioop.ratecv(pcm_24k, 2, 1, 24000, 16000, in_rate_state)
                        elif eff_codec == "pcm_24k":
                            pcm_16k, in_rate_state = audioop.ratecv(chunk, 2, 1, 24000, 16000, in_rate_state)
                        else:
                            pcm_16k = chunk if len(chunk) % 2 == 0 else chunk[:-1]

                        # Si l'appelant parle pendant que l'assistant joue de l'audio (et hors saisie DTMF NIP)
                        if pcm_16k and len(pcm_16k) >= 2:
                            rms = audioop.rms(pcm_16k, 2)
                            if rms >= self._vad_rms_threshold and assistant_speaking:
                                should_interrupt = mgr.on_caller_speech_detected(
                                    context.session_id,
                                    is_dtmf_pin_entry=context.is_dtmf_pin_entry,
                                    allow_interruptions=context.allow_natural_interruptions,
                                )
                                if should_interrupt:
                                    assistant_speaking = False
                                    await event_queue.put(
                                        VoiceRealtimeEvent(
                                            event_type="interruption",
                                            session_id=context.session_id,
                                            turn_id=context.turn_id,
                                            payload={
                                                "reason": "caller_barge_in",
                                                "sequence_id": seq,
                                                "cancelled_turn_id": context.turn_id,
                                            },
                                        )
                                    )

                        if not context.is_dtmf_pin_entry:
                            try:
                                from google.genai import types
                                blob: Any = types.Blob(data=pcm_16k, mime_type="audio/pcm;rate=16000")
                            except Exception:
                                blob = {"data": pcm_16k, "mime_type": "audio/pcm;rate=16000"}
                            await session.send_realtime_input(audio=blob)
                    with suppress(Exception):
                        await session.send_realtime_input(audio_stream_end=True)
                except Exception as exc:
                    logger.warning("gemini_live_inbound_stream_error session=%s: %s", context.session_id, exc)

            async def _pump_server_events() -> None:
                nonlocal out_rate_state, assistant_speaking
                try:
                    async for message in session.receive():
                        if (context.session_id, context.turn_id) in self._cancelled_turns:
                            mgr.cancel_turn(context.session_id, context.turn_id)

                        # 1. Traitement des appels d'outils Gemini Live vers Avenqo Central
                        tool_call = getattr(message, "tool_call", None) or (
                            message.get("tool_call") if isinstance(message, dict) else None
                        )
                        if tool_call is not None:
                            function_calls = getattr(tool_call, "function_calls", None) or (
                                tool_call.get("function_calls") if isinstance(tool_call, dict) else ()
                            ) or ()
                            responses_to_send = []
                            for fc in function_calls:
                                fc_id = getattr(fc, "id", None) or (fc.get("id") if isinstance(fc, dict) else str(uuid4()))
                                fc_name = str(getattr(fc, "name", None) or (fc.get("name") if isinstance(fc, dict) else ""))
                                fc_args = getattr(fc, "args", None) or (fc.get("args") if isinstance(fc, dict) else {}) or {}
                                if not isinstance(fc_args, dict):
                                    fc_args = dict(fc_args)

                                if not mgr.can_execute_tool(context.turn_id, fc_name, fc_args):
                                    reason = (
                                        "reserve_product is prohibited on voice calls"
                                        if fc_name == "reserve_product"
                                        else "turn_cancelled_or_duplicate"
                                    )
                                    tool_output = {"status": "blocked", "blocked": True, "error": reason}
                                    await event_queue.put(
                                        VoiceRealtimeEvent(
                                            event_type="tool_call",
                                            session_id=context.session_id,
                                            turn_id=context.turn_id,
                                            payload={
                                                "tool_name": fc_name,
                                                "tool_args": fc_args,
                                                "status": "blocked",
                                                "blocked": True,
                                                "reason": reason,
                                            },
                                        )
                                    )
                                elif active_tool_executor is not None:
                                    mgr.record_tool_execution(context.turn_id, fc_name, fc_args)
                                    tool_output = await active_tool_executor(fc_name, fc_args)
                                    await event_queue.put(
                                        VoiceRealtimeEvent(
                                            event_type="tool_call",
                                            session_id=context.session_id,
                                            turn_id=context.turn_id,
                                            payload={
                                                "tool_name": fc_name,
                                                "tool_args": fc_args,
                                                "status": "executed",
                                                "blocked": False,
                                                "result": tool_output,
                                            },
                                        )
                                    )
                                else:
                                    tool_output = {"status": "unavailable", "error": "no_tool_executor"}

                                try:
                                    from google.genai import types
                                    responses_to_send.append(
                                        types.FunctionResponse(
                                            id=str(fc_id),
                                            name=fc_name,
                                            response=tool_output,
                                        )
                                    )
                                except Exception:
                                    responses_to_send.append(
                                        {"id": str(fc_id), "name": fc_name, "response": tool_output}
                                    )

                            if responses_to_send and not mgr.is_turn_cancelled(context.turn_id):
                                await session.send_tool_response(function_responses=responses_to_send)

                        # 2. Traitement du contenu serveur (transcriptions, interruptions, audio sortant)
                        server_content = getattr(message, "server_content", None) or (
                            message.get("server_content") if isinstance(message, dict) else None
                        )
                        if server_content is None:
                            continue

                        srv_interrupted = getattr(server_content, "interrupted", False) or (
                            server_content.get("interrupted", False) if isinstance(server_content, dict) else False
                        )
                        if srv_interrupted:
                            triggered = mgr.on_caller_speech_detected(
                                context.session_id,
                                is_dtmf_pin_entry=context.is_dtmf_pin_entry,
                                allow_interruptions=context.allow_natural_interruptions,
                            )
                            if triggered:
                                assistant_speaking = False
                                await event_queue.put(
                                    VoiceRealtimeEvent(
                                        event_type="interruption",
                                        session_id=context.session_id,
                                        turn_id=context.turn_id,
                                        payload={"reason": "gemini_server_vad_interruption"},
                                    )
                                )

                        in_trans = getattr(server_content, "input_transcription", None) or (
                            server_content.get("input_transcription") if isinstance(server_content, dict) else None
                        )
                        if in_trans is not None:
                            t_text = getattr(in_trans, "text", None) or (
                                in_trans.get("text") if isinstance(in_trans, dict) else None
                            )
                            if isinstance(t_text, str) and t_text.strip():
                                await event_queue.put(
                                    VoiceRealtimeEvent(
                                        event_type="transcript_final",
                                        session_id=context.session_id,
                                        turn_id=context.turn_id,
                                        payload={"transcript": t_text.strip(), "direction": "inbound"},
                                    )
                                )

                        out_trans = getattr(server_content, "output_transcription", None) or (
                            server_content.get("output_transcription") if isinstance(server_content, dict) else None
                        )
                        if out_trans is not None and not mgr.is_turn_cancelled(context.turn_id):
                            ot_text = getattr(out_trans, "text", None) or (
                                out_trans.get("text") if isinstance(out_trans, dict) else None
                            )
                            if isinstance(ot_text, str) and ot_text.strip():
                                await event_queue.put(
                                    VoiceRealtimeEvent(
                                        event_type="transcript_partial",
                                        session_id=context.session_id,
                                        turn_id=context.turn_id,
                                        payload={"transcript": ot_text.strip(), "direction": "outbound"},
                                    )
                                )

                        model_turn = getattr(server_content, "model_turn", None) or (
                            server_content.get("model_turn") if isinstance(server_content, dict) else None
                        )
                        if model_turn is not None and not mgr.is_turn_cancelled(context.turn_id):
                            parts = getattr(model_turn, "parts", None) or (
                                model_turn.get("parts") if isinstance(model_turn, dict) else ()
                            ) or ()
                            for part in parts:
                                if mgr.is_turn_cancelled(context.turn_id):
                                    break
                                inline = getattr(part, "inline_data", None) or (
                                    part.get("inline_data") if isinstance(part, dict) else None
                                )
                                if inline is None:
                                    continue
                                raw_audio = getattr(inline, "data", None) or (
                                    inline.get("data") if isinstance(inline, dict) else None
                                )
                                if isinstance(raw_audio, str):
                                    raw_audio = base64.b64decode(raw_audio)
                                if not isinstance(raw_audio, (bytes, bytearray)) or not raw_audio:
                                    continue
                                pcm_bytes = bytes(raw_audio)
                                if len(pcm_bytes) % 2 != 0:
                                    pcm_bytes = pcm_bytes[:-1]
                                if not pcm_bytes:
                                    continue
                                assistant_speaking = True
                                if output_codec == "pcmu_8k":
                                    b64_pcm = base64.b64encode(pcm_bytes).decode("ascii")
                                    out_audio = codec.outbound_pcm(b64_pcm)
                                else:
                                    out_audio = pcm_bytes
                                await event_queue.put(
                                    VoiceRealtimeEvent(
                                        event_type="audio_chunk",
                                        session_id=context.session_id,
                                        turn_id=context.turn_id,
                                        audio=out_audio,
                                        payload={"codec": output_codec},
                                    )
                                )

                        turn_complete = getattr(server_content, "turn_complete", False) or (
                            server_content.get("turn_complete", False) if isinstance(server_content, dict) else False
                        )
                        if turn_complete:
                            assistant_speaking = False
                            break
                finally:
                    await event_queue.put(done_sentinel)

            inbound_task = asyncio.create_task(_pump_inbound_audio())
            server_task = asyncio.create_task(_pump_server_events())
            try:
                while True:
                    ev = await event_queue.get()
                    if ev is done_sentinel:
                        break
                    if isinstance(ev, VoiceRealtimeEvent):
                        yield ev
                await asyncio.gather(inbound_task, server_task, return_exceptions=True)
            finally:
                for t in (inbound_task, server_task):
                    if not t.done():
                        t.cancel()
                await asyncio.gather(inbound_task, server_task, return_exceptions=True)
                self._active_sessions.pop(context.session_id, None)
                mgr.complete_turn(context.session_id, context.turn_id)

        yield VoiceRealtimeEvent(
            event_type="turn_completed",
            session_id=context.session_id,
            turn_id=context.turn_id,
            payload={"provider": "gemini_live", "model": self._model},
        )

    async def cancel_playback(self, session_id: str, turn_id: str) -> None:
        self._cancelled_turns.add((session_id, turn_id))
        logger.info("gemini_live_cancel_playback session=%s turn=%s", session_id, turn_id)


class VoiceRealtimeRouter:
    """Sélectionne le moteur vocal selon la configuration du tenant avec fallback automatique."""

    def __init__(
        self,
        settings: Settings,
        *,
        gemini_client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._retell = RetellVoiceRealtimeProvider(settings)
        self._telnyx = TelnyxNativeRealtimeProvider(settings)
        self._gemini = GoogleGeminiLiveRealtimeProvider(
            settings,
            client_factory=gemini_client_factory,
        )
        self._interruptions = NaturalInterruptionManager()

    def resolve_provider(self, config: VoiceBusinessConfig | None) -> VoiceRealtimeProvider:
        """Résout le fournisseur à utiliser avec bascule transparente en cas d'indisponibilité."""
        requested = getattr(config, "realtime_provider", "retell") if config is not None else "retell"
        gemini_enabled = bool(getattr(config, "gemini_live_enabled", False)) if config is not None else False

        # 1. Si Gemini Live est explicitement activé pour ce tenant et disponible
        if (requested == RealtimeProviderType.GEMINI_LIVE or gemini_enabled) and self._gemini.is_available():
            return self._gemini

        # 2. Si Retell est configuré et demandé
        if requested == RealtimeProviderType.RETELL and self._retell.is_available():
            return self._retell

        # 3. Si Telnyx est configuré et demandé
        if requested == RealtimeProviderType.TELNYX and self._telnyx.is_available():
            return self._telnyx

        # 4. Fallback vers le fournisseur disponible
        if self._retell.is_available():
            return self._retell
        if self._telnyx.is_available():
            return self._telnyx
        if self._gemini.is_available():
            return self._gemini

        # Défaut : Retell
        return self._retell

    def build_realtime_adapter(
        self,
        config: VoiceBusinessConfig | None,
        audio_config: OpenAIAudioConfig,
        *,
        fallback_factory: Callable[[], RealtimeAudioAdapter],
    ) -> RealtimeAudioAdapter:
        """Construit l'adaptateur audio temps réel pour `TelnyxMediaBridge`.

        - Si `gemini_live_enabled` (ou `realtime_provider == 'gemini_live'`) est actif pour
          l'entreprise et que la clé Gemini est configurée, utilise `GeminiLiveRealtimeAudioAdapter`
          encapsulé dans `FallbackRealtimeAudioAdapter` (repli automatique vers `fallback_factory`).
        - Sinon, utilise directement `fallback_factory()` (pipeline Telnyx/OpenAI existant).
        """
        requested = getattr(config, "realtime_provider", "retell") if config is not None else "retell"
        gemini_enabled = bool(getattr(config, "gemini_live_enabled", False)) if config is not None else False

        if (gemini_enabled or requested == RealtimeProviderType.GEMINI_LIVE) and self._gemini.is_available():
            logger.info(
                "voice_realtime_route provider=gemini_live model=%s company_id=%s",
                self._gemini.model_name,
                getattr(config, "company_id", None),
            )
            return FallbackRealtimeAudioAdapter(
                primary_factory=lambda: self._gemini.create_audio_adapter(config, audio_config),
                fallback_factory=fallback_factory,
            )
        logger.info(
            "voice_realtime_route provider=fallback_pipeline requested=%s gemini_enabled=%s company_id=%s",
            requested,
            gemini_enabled,
            getattr(config, "company_id", None),
        )
        return fallback_factory()

    @property
    def interruptions(self) -> NaturalInterruptionManager:
        return self._interruptions

    @property
    def gemini_model_name(self) -> str:
        return self._gemini.model_name
