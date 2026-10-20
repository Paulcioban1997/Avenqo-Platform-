"""Sandbox integration boundary; never promote a lab benchmark into a live call.

The workers only receive audio or Central-approved text, never tenant IDs,
business tools or credentials. Callers cannot select workers or models.
PSTN selection remains blocked until inference hosting, cancellation-aware cost
settlement and telephone quality have been validated. No zero-cost assumption.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit
from uuid import uuid4

from backend.app.voice.open_speech import (
    OpenSpeechClient, OpenSpeechConfig, OpenSpeechRealtimeAdapter, SpeechUnavailable,
)
from backend.app.voice.open_speech_catalog import CHATTERBOX, KOKORO
from backend.app.voice.speech_jobs import PilotUsageLedger

logger = logging.getLogger("avenqo.voice.speech")


def build_lab_adapter(settings, *, company_id):
    """Server-only factory. company_id must come from authenticated tenant context.

    This is not an authorization substitute: the existing Central/Voice tool
    gates still apply. No HTTP route exposes this factory to a public caller.
    """
    if settings.environment != "sandbox" or not settings.voice_open_speech_lab_enabled:
        raise SpeechUnavailable("Speech lab disabled outside explicitly enabled Sandbox")
    if company_id not in settings.voice_open_speech_company_ids:
        raise SpeechUnavailable("Company not authorized for speech lab")
    if not all((settings.voice_open_speech_asr_url, settings.voice_open_speech_tts_url,
                settings.voice_open_speech_api_key)):
        raise SpeechUnavailable("Independent speech worker configuration incomplete")
    # Phase 8.7 budget override: no remote/paid inference has been authorized.
    # No public tunnel to the developer machine. Only local processes are allowed.
    if any(urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}
           for url in (settings.voice_open_speech_asr_url, settings.voice_open_speech_tts_url)):
        raise SpeechUnavailable("Zero-budget lab permits loopback inference only")
    artifacts = {"kokoro": KOKORO, "chatterbox": CHATTERBOX}
    artifact = artifacts.get(settings.voice_open_speech_tts_backend)
    if artifact is None:
        raise SpeechUnavailable("Unreviewed speech backend")
    ledger = PilotUsageLedger(company_id=company_id, call_id=uuid4(),
                              rate_usd_per_compute_second=0, source="existing-local-unpaid-lab")
    return OpenSpeechRealtimeAdapter(OpenSpeechClient(OpenSpeechConfig(
        asr_url=settings.voice_open_speech_asr_url,
        tts_url=settings.voice_open_speech_tts_url,
        api_key=settings.voice_open_speech_api_key, tts_artifact=artifact,
    ), usage_ledger=ledger))


def phone_readiness(settings):
    """Safe diagnostics, no keys, URLs, tenant data or provider requests."""
    return {
        "lab_enabled": settings.voice_open_speech_lab_enabled,
        "sandbox": settings.environment == "sandbox",
        "worker_configuration_present": bool(settings.voice_open_speech_asr_url
                                             and settings.voice_open_speech_tts_url
                                             and settings.voice_open_speech_api_key),
        "telephone_ready": False,
        "blockers": ["inference_hosting_not_validated", "cancelled_inference_cost_settlement_pending",
                     "zero_budget_remote_inference_not_authorized",
                     "telephone_latency_and_french_canadian_quality_not_certified"],
        "phone_provider": "existing_configured_provider",
    }


def build_phone_adapter(settings, fallback_factory):
    """Keep existing phone behavior; never replay a tool or switch mid-answer.

    Enabling the lab flag alone deliberately cannot incur hosted inference costs
    or bypass the existing usage ledger (which currently prices OpenAI events).
    """
    if settings.voice_open_speech_lab_enabled:
        logger.warning("speech_provider_selection status=blocked reason=lab_not_telephone_certified fallback=existing")
    return fallback_factory()
