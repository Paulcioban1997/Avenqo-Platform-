"""Disabled-by-default Telnyx media transport for the existing Voice audio engine."""

from __future__ import annotations

import asyncio
import time
import base64
import binascii
from collections import deque
from contextlib import suppress
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import unicodedata
import logging
from typing import Any, Awaitable, Callable, Optional, Tuple, cast
from uuid import UUID, uuid4

import jwt
from fastapi import Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import CursorResult, select, text, update
from sqlalchemy.orm import Session

logger = logging.getLogger("avenqo.voice.media")

from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.config.settings import Settings, get_settings
from backend.app.core.locale_catalog import detect_spoken_language, resolve_locale
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import allow_rate_limit
from backend.app.database import get_db
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities
from backend.app.models import (
    AIMessageRole,
    BillingAccount,
    Company,
    CompanyMembership,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCallerCredential,
    VoicePhoneNumber,
    VoiceToolAction,
)
from backend.app.services.company_intelligence_service import CompanyIntelligenceService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.adapters import OpenAIRealtimeAudioAdapter
from backend.app.voice.direct_answers import sanitize_retail_voice_text
from backend.app.voice.messages import apply_spoken_pronunciation
from backend.app.voice.turn_control import (
    ConversationState,
    VoiceTurnOrchestrator,
    adjudicate_transcript,
    build_correction_clarification,
    extract_reformulation_after_correction,
    is_attention_check,
    is_correction_or_objection,
    is_explicit_interruption,
    is_playback_echo,
)
from backend.app.voice.auth import VoiceCallerAuth, utc, normalized_phone
from backend.app.voice.usage import VoiceUsageLedger, voice_pricing_catalog
from backend.app.voice.service import resolve_voice_source_context
from backend.app.voice.messages import voice_auth_message, voice_greeting
from backend.app.voice.providers import TelnyxClient
from shared.ai_engine.contracts import TenantContext

from backend.app.voice.auth import redact_voice_secrets
from backend.app.voice.caller_scope import PUBLIC_VOICE_CALLER_PERMISSIONS
from backend.app.voice.language_resolver import CallLanguageSession
from backend.app.voice.module_actions import company_call_language_session, voice_agent_language


from backend.app.voice.audio_codec import InvalidMediaFrame, TelnyxAudioCodec
from backend.app.voice.open_speech_runtime import build_phone_adapter


_LIVE_MEDIA_STATUSES = frozenset({"answering", "routed", "in_progress", "appointment_booked"})
_SESSION_MEDIA_STATUSES = _LIVE_MEDIA_STATUSES
_HANGUP_MEDIA_STATUSES = _SESSION_MEDIA_STATUSES | frozenset({
    "appointment_cancelled", "transferred", "blocked_credits", "blocked_announcement", "completed",
})



def media_transport_context(
    db: Session,
    settings: Settings,
    call_id: UUID,
    *,
    allow_statuses: frozenset[str] | None = None,
    require_active: bool = True,
):
    if not settings.telnyx_media_enabled:
        raise PermissionError("Telnyx media transport disabled")
    db.expire_all()
    from backend.app.services.tenant_rls import apply_tenant_rls, supports_rls
    if supports_rls(db):
        try:
            resolved_cid = db.execute(
                text("SELECT public.resolve_voice_call_tenant(:call_id, NULL)"),
                {"call_id": call_id},
            ).scalar()
            if resolved_cid is not None:
                apply_tenant_rls(db, UUID(str(resolved_cid)), bypass=False)
            else:
                logger.warning("resolve_voice_call_tenant returned None for call_id %s", call_id)
        except Exception as exc:
            logger.warning("resolve_voice_call_tenant failed for call_id %s: %s", call_id, exc, exc_info=True)
    call = db.get(VoiceCall, call_id)
    allowed = allow_statuses if allow_statuses is not None else _SESSION_MEDIA_STATUSES
    if (
        call is None
        or not call.telnyx_call_control_id
        or call.status not in allowed
        or (require_active and call.ended_at is not None)
    ):
        raise PermissionError("Active tenant call required")
    apply_tenant_rls(db, call.company_id, bypass=False)
    is_dispatcher_call = bool(
        (call.source_context or {}).get("dispatcher_routing")
        or (call.source_context or {}).get("routing_nip")
    )
    from backend.app.services.voice_lifecycle_service import VoiceLifecycleService
    caller_phone = call.caller_phone or ""
    admitted, reason = VoiceLifecycleService(db).is_call_admissible(call.company_id, caller_phone)
    if not admitted and not is_dispatcher_call:
        raise PermissionError(f"Voice agent lifecycle not admitted: {reason}")
    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.id == call.config_id, VoiceBusinessConfig.company_id == call.company_id))
    number = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.company_id == call.company_id,
        VoicePhoneNumber.config_id == call.config_id, VoicePhoneNumber.status == "ACTIVE", VoicePhoneNumber.provider == "telnyx"))
    account = db.scalar(select(BillingAccount).where(BillingAccount.company_id == call.company_id))
    company = db.get(Company, call.company_id)
    if config is None or company is None:
        raise PermissionError("Tenant configuration unavailable")
    is_dispatcher_call = bool(
        (call.source_context or {}).get("dispatcher_routing")
        or (call.source_context or {}).get("routing_nip")
    )
    if not is_dispatcher_call:
        if number is None or number.phone_number != config.telnyx_phone_number or "voice" not in (number.capabilities or []):
            raise PermissionError("Tenant number binding unavailable")
        if not settings.telnyx_voice_connection_id or number.provider_connection_id != settings.telnyx_voice_connection_id:
            raise PermissionError("Verified Voice connection required")
    else:
        from backend.app.models.voice import CompanyRoutingNip
        active_nip = db.scalar(
            select(CompanyRoutingNip.id).where(
                CompanyRoutingNip.company_id == call.company_id,
                CompanyRoutingNip.status == "ACTIVE",
            )
        )
        if active_nip is None and (number is None or number.status != "ACTIVE"):
            raise PermissionError("Company routing NIP or dedicated number required")
    if account is None or account.status.strip().lower() not in {"active", "trialing"} or not ModuleEntitlementService(db).can_use_module(TenantContext(call.company_id), "voice"):
        raise PermissionError("Voice entitlement unavailable")
    return call, config, company


def media_call_context(db: Session, settings: Settings, call_id: UUID, **context_kwargs):
    call, config, company = media_transport_context(db, settings, call_id, **context_kwargs)
    auth = VoiceCallerAuth(db, settings).valid_session(call)
    if auth is None or auth.caller_type not in {"OWNER", "EMPLOYEE"} or call.caller_type not in {"OWNER", "EMPLOYEE"} or call.pin_challenge_hash:
        raise PermissionError("Verified staff call required")
    user = db.get(User, auth.principal_id)
    membership = db.scalar(select(CompanyMembership).where(CompanyMembership.company_id == call.company_id,
        CompanyMembership.user_id == auth.principal_id, CompanyMembership.is_active.is_(True)))
    if user is None or membership is None:
        raise PermissionError("Caller unavailable")
    permissions = frozenset(permissions_for(membership.role)).intersection(auth.permissions)
    if "ai:use" not in permissions:
        raise PermissionError("AI permission unavailable")
    return call, config, company, user, permissions, auth


def issue_media_client_state(db: Session, settings: Settings, call_id: UUID, *, public_mode: bool = False) -> str:
    if public_mode:
        if not settings.telnyx_media_inbound_enabled:
            raise PermissionError("Public inbound media disabled")
        call, config, _company = media_transport_context(db, settings, call_id)
        auth_epoch = "public"
    else:
        call, config, _company, _user, _permissions, auth = media_call_context(db, settings, call_id)
        auth_epoch = utc(auth.authenticated_at).isoformat()
    now = datetime.now(timezone.utc)
    nonce = str(uuid4())
    token = jwt.encode({"type": "telnyx_media", "call_id": str(call.id), "tenant_id": str(call.company_id),
        "config_id": str(config.id), "auth_epoch": auth_epoch, "jti": nonce,
        "iat": now, "exp": now + timedelta(seconds=60), "iss": settings.auth_jwt_issuer,
        "aud": "telnyx-media"}, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)
    lease_key = "media-active:" + str(call.id)
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": lease_key})
    lease = db.scalar(select(VoiceToolAction).where(VoiceToolAction.company_id == call.company_id,
        VoiceToolAction.config_id == config.id, VoiceToolAction.action_id == lease_key))
    if lease is None:
        db.add(VoiceToolAction(company_id=call.company_id, config_id=config.id, action_id=lease_key,
            tool_name="telnyx_media_session", result={"active": False}))
    db.add(VoiceToolAction(company_id=call.company_id, config_id=config.id,
        action_id="media-ticket:" + hashlib.sha256(nonce.encode()).hexdigest(), tool_name="telnyx_media_ticket", result={"claimed": False}))
    db.commit()
    return base64.b64encode(token.encode()).decode("ascii")


def claim_media_start(db: Session, settings: Settings, call_id: UUID, start: dict, *, public_mode: bool = False) -> tuple:
    if public_mode:
        if not settings.telnyx_media_inbound_enabled:
            raise PermissionError("Public inbound media disabled")
        call, config, _company = media_transport_context(db, settings, call_id)
        auth_epoch = "public"
    else:
        call, config, _company, _user, _permissions, auth = media_call_context(db, settings, call_id)
        auth_epoch = utc(auth.authenticated_at).isoformat()
    state = start.get("client_state")
    if not isinstance(state, str) or len(state) > 4096:
        raise PermissionError("Invalid media authorization")
    try:
        token = base64.b64decode(state, validate=True).decode("ascii")
        claims = jwt.decode(token, settings.auth_jwt_secret, algorithms=[settings.auth_jwt_algorithm],
            issuer=settings.auth_jwt_issuer, audience="telnyx-media",
            options={"require": ["type", "call_id", "tenant_id", "config_id", "auth_epoch", "jti", "iat", "exp"]})
    except (ValueError, binascii.Error, UnicodeDecodeError, jwt.InvalidTokenError):
        raise PermissionError("Invalid media authorization") from None
    expected_to = (
        (call.source_context or {}).get("destination_number")
        if (call.source_context or {}).get("dispatcher_routing")
        else config.telnyx_phone_number
    )
    start_to = start.get("to")
    start_call_control_id = start.get("call_control_id")
    if (
        claims["type"] != "telnyx_media"
        or claims["call_id"] != str(call.id)
        or claims["tenant_id"] != str(call.company_id)
        or claims["config_id"] != str(config.id)
        or claims["auth_epoch"] != auth_epoch
        or (start_call_control_id and call.telnyx_call_control_id and start_call_control_id != call.telnyx_call_control_id)
        or (start_to and expected_to and normalized_phone(start_to) != normalized_phone(expected_to) and start_to != expected_to)
    ):
        raise PermissionError("Media authorization scope mismatch")
    nonce = claims["jti"]
    if not isinstance(nonce, str) or len(nonce) > 128:
        raise PermissionError("Invalid media authorization")
    action_id = "media-ticket:" + hashlib.sha256(nonce.encode()).hexdigest()
    result = cast(CursorResult[Any], db.execute(update(VoiceToolAction).where(VoiceToolAction.company_id == call.company_id,
        VoiceToolAction.config_id == config.id, VoiceToolAction.action_id == action_id,
        VoiceToolAction.tool_name == "telnyx_media_ticket", VoiceToolAction.result["claimed"].as_boolean().is_(False))
        .values(result={"claimed": True}).execution_options(synchronize_session=False)))
    if result.rowcount != 1:
        db.rollback()
        raise PermissionError("Media authorization already consumed")
    lease = cast(CursorResult[Any], db.execute(update(VoiceToolAction).where(VoiceToolAction.company_id == call.company_id,
        VoiceToolAction.config_id == config.id, VoiceToolAction.action_id == "media-active:" + str(call.id),
        VoiceToolAction.tool_name == "telnyx_media_session", VoiceToolAction.result["active"].as_boolean().is_(False))
        .values(result={"active": True, "owner": action_id}).execution_options(synchronize_session=False)))
    if lease.rowcount != 1:
        db.rollback()
        raise PermissionError("Media session already active")
    db.commit()
    return call.company_id, config.id, action_id


def release_media_session(db: Session, call_id: UUID, claim: tuple) -> None:
    company_id, config_id, owner = claim
    db.execute(update(VoiceToolAction).where(VoiceToolAction.company_id == company_id,
        VoiceToolAction.config_id == config_id, VoiceToolAction.action_id == "media-active:" + str(call_id),
        VoiceToolAction.tool_name == "telnyx_media_session", VoiceToolAction.result["owner"].as_string() == owner)
        .values(result={"active": False}).execution_options(synchronize_session=False))
    db.commit()


def clean_voice_text(text: str, *, locale: str = "fr-CA") -> str:
    """Nettoie le texte destiné à la synthèse vocale téléphonique (TTS).
    Supprime la syntaxe markdown (listes à puces, numérotation, astérisques, dièses, crochets)
    ainsi que les noms de champs techniques bruts (ex: compare_at_price, inventory_quantity),
    pour garantir une lecture orale fluide et naturelle sans artefacts robotiques.
    """
    if not text:
        return ""
    cleaned = sanitize_retail_voice_text(text, locale=locale)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"^\s*\d+[\.\)]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[\-\*•]\s*", "", cleaned, flags=re.MULTILINE)
    # Do not hardcode any tenant brand here — spoken company names come from authorized config.
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    cleaned = " ".join(lines)
    return re.sub(r"\s+", " ", cleaned).strip()


_RE_PIN_MGMT = re.compile(
    r"(creer|configur|changer|modifier|reinitialis|oubli|create|change|set|reset).{0,30}\b(nip|pin)\b"
)
_RE_PIN_INQUIRY = re.compile(
    r"\b(authentifi|authentification|identifier|connexion|login)\b.{0,30}\b(nip|pin|securis)\b"
    r"|\b(nip|pin)\b.{0,30}\b(securis|authentifi)\b"
    r"|\b(entrer|composer|saisir|fournir|taper)\b.{0,20}\b(nip|pin)\b"
    r"|\b(code nip|code pin)\b"
)
_RE_PUBLIC_CUSTOMER_INTENT = re.compile(
    r"\b(rendez[- ]vous|rdv|appointment|booking|cita|reunion|programare|intalnire|intalnirea|rencontrer|rencontre|parler|parle|hablar|vorbi|speak|talk|contacter|contact|message|mensaje|mesaj|recrutement|recruitment|embauche|hiring|emploi|job|empleo|angajare|candidature|postuler|apply|entrevue|interview|entrevista|interviu|joindre|reach)\b"
)
_RE_PRIVATE_DATA = re.compile(
    r"\b(chiffre d'affaires|ventes du jour|ventes d'aujourd'hui|ventes aujourd'hui|produits vendus|commandes internes|mes clients|autres clients|internal|internes|metriques|metrics|revenus|revenue|credits|abonnement|subscription|retail|comptabilite|accounting|dashboard|factures|invoices)\b"
    r"|\b(commande|commandes|order|orders)\b.{0,25}\b(recu|recues|aujourd'hui|jour|du jour|recent|recentes|total|nombre|recents|derniere|dernieres|today)\b"
    r"|\b(combien de commandes|combien de ventes|combien de transactions|combien d'argent)\b"
    r"|\b(niveau de stock|etat des stocks|stock restant)\b"
    r"|\b(ingresos|ventas de hoy|pedidos internos|facturas|contabilidad|metricas|cuanto dinero|estado de los stocks|stock restante)\b"
    r"|\b(cifra de afaceri|venituri(le)?|vanzari(le)? de astazi|comenzi interne|facturi|contabilitate|cati bani|nivelul stocului|stoc ramas)\b"
    r"|\b(je suis|i am|yo soy|sunt)\b.{0,15}\b(proprietaire|owner|patron|boss|manager|employe|employee|due[nñ]o|gerente|sef|proprietar)\b"
    r"|\b(mode|espace|session|connexion|portail|acceso|spatiu)\b.{0,20}\b(proprietaire|owner|patron|boss|manager|employe|employee|gestion|direction|due[nñ]o|gerente|conducere)\b"
    r"|\b(mon shift|mes taches|mes priorites|briefing employe|coaching employe|my shift|my tasks|my priorities|employee briefing|mis tareas|mi turno|mi coaching|sarcinile mele|tura mea)\b"
    r"|\b(coaching|conseils?|astuces?)\b.{0,20}\b(marketing|vente|ventes|commercial|clients?|acquisition)\b"
    r"|\b(strategie marketing|acquisition client|acquisition de clients|marketing strategy|customer acquisition|captacion de clientes|atragerea clientilor)\b"
    r"|\b(attirer|trouver|avoir|gagner)\b.{0,20}\b(clients?|clientele|customers)\b"
)
_RE_MANAGEMENT_CONTACT = re.compile(
    r"\b(proprietaire|owner|patron|boss|manager|direction|due[nñ]o|jefe|gerente|encargado|proprietar|sef|conducere|conducerea|director|directorul)\b"
)
_RE_CUSTOMER_VERIFY = re.compile(
    r"mes rendez.vous|my appointments|mon dossier client|my record|mis citas"
)
_RE_BOOKING_MGMT = re.compile(
    r"mes rendez.vous|my appointments|mon dossier|my record|mis citas|annuler|cancel|deplacer|reschedule"
)
_RE_PICKUP = re.compile(
    r"reserver|reserve|reservation|cueillette|cueillir|ramassage|ramasser|venir chercher|passer prendre|recuperer|retrait|pick.?up|mettre de cote|bloquer"
)
_RE_BOOKING = re.compile(
    r"rendez[- .]vous|appointment|booking|disponibilit|disponible|availability|available"
)

_RE_SESSION_RETENTION = re.compile(
    r"\b(non\b.*(ne\s*passe\s*pas|pas\s*changer|pas\s*passer|garde|reste))"
    r"|\b(ne\s*passe\s*pas|ne\s*pas\s*changer|pas\s*changer\s*d\W*employe|pas\s*passer\s*le\s*telephone)\b"
    r"|\b(je\s*vais\s*rester|je\s*reste|rester\s*moi\W*meme|reviens\s*a|garde\s*ma\s*session|garde\s*la\s*session|garde\s*mon\s*compte|c'?est\s*toujours\s*moi|garder\s*la\s*session)\b"
    r"|\b(no\s*voy\s*a\s*pasar|no\s*cambiar|no\s*le\s*paso|me\s*quedo(\s*yo)?|sigo\s*siendo|mantener\s*sesion|conservar\s*sesion)\b"
    r"|\b(nu\s*schimb|nu\s*dau\s*telefonul|raman(\s*eu)?|pastreaza\s*sesiunea)\b"
    r"|\b(do\s*not\s*pass|don'?t\s*pass|keep\s*my\s*session|i\s*will\s*stay|i'?ll\s*stay|remain)\b"
)

_RE_PIN_CANCELLATION = re.compile(
    r"\b(annuler|annule|annulez|laisse\s*tomber|non\s*merci|arrete|arret|stop|quitter|abandonner|pas\s*de\s*nip|annule\s*le\s*code|annule\s*le\s*nip|cancel|abort|quit|never\s*mind|no\s*thanks|cancelar|dejarlo|anulare|anuleaza|renunta)\b"
    r"|\b(non\b.{0,20}\b(veux\s*pas|pas\s*de\s*code|pas\s*de\s*nip|reviens|reste))\b"
)

_RE_HANDOVER_POSITIVE = re.compile(
    r"\b(changer\s*d\W*employe|change\s*employe|autre\s*employe|nouvel\s*employe|passe\s*mon\s*collegue|passe\s*le\s*telephone|je\s*te\s*passe|switch\s*employee|change\s*employee|pass\s*the\s*phone|hand\s*over|schimba\s*angajatul|iti\s*dau\s*colegul|pasez\s*telefonul|cambiar\s*de\s*empleado|te\s*paso\s*a\s*mi\s*colega)\b"
)


def is_session_retention_intent(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    norm = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
    return bool(_RE_SESSION_RETENTION.search(norm))


def is_pin_challenge_cancellation(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    norm = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
    return bool(_RE_PIN_CANCELLATION.search(norm))


def is_handover_positive_intent(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    norm = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
    if is_session_retention_intent(norm):
        return False
    neg_prefix = r"\b(ne\s*pas|pas\s*de|ne\s*veux\s*pas|pas\s*question|jamais|don'?t|do\s*not|no\s*quiero|no\s*voy\s*a|nu\s*vreau)\s*"
    if re.search(neg_prefix + r".{0,15}" + _RE_HANDOVER_POSITIVE.pattern, norm):
        return False
    return bool(_RE_HANDOVER_POSITIVE.search(norm))


class PublicInboundConversation:
    def __init__(self, db: Session, settings: Settings, call_id: UUID, telnyx=None):
        self.db = db
        self.settings = settings
        self.call_id = call_id
        self.telnyx = telnyx or TelnyxClient(settings)

    def context(self):
        if not self.settings.telnyx_media_inbound_enabled and not self.settings.telnyx_media_enabled:
            raise PermissionError("Voice media transport disabled")
        return media_transport_context(self.db, self.settings, self.call_id, allow_statuses=_SESSION_MEDIA_STATUSES)

    def greeting(self) -> str:
        _call, config, _company = self.context()
        from backend.app.voice.messages import voice_natural_greeting
        from backend.app.voice.messages import voice_speech_name
        return voice_natural_greeting(voice_agent_language(self.db, config), voice_speech_name(config))

    def portal_message(self) -> str:
        call, config, _company = self.context()
        loc = resolve_locale(call.locale or config.preferred_language).casefold()
        if loc.startswith("fr"):
            return "Créez ou modifiez votre NIP Voice depuis votre espace Avenqo authentifié, dans Voice AI, Sécurité. Ne dites jamais votre NIP à voix haute."
        if loc.startswith("es"):
            return "Cree o modifique su PIN de Voice desde su espacio Avenqo autenticado, en Voice AI, Seguridad. Nunca diga su PIN en voz alta."
        if loc.startswith("ro"):
            return "Creați sau modificați codul PIN Voice din spațiul Avenqo autentificat, la Voice AI, Securitate. Nu rostiți niciodată PIN-ul cu voce tare."
        return "Create or change your Voice PIN in your authenticated Avenqo workspace, under Voice AI, Security. Never say your PIN aloud."

    def has_configured_pin(self, call: VoiceCall) -> bool:
        phone = normalized_phone(call.caller_phone)
        if phone:
            has_cred = self.db.scalar(
                select(VoiceCallerCredential.id).where(
                    VoiceCallerCredential.company_id == call.company_id,
                    VoiceCallerCredential.phone_number == phone,
                    VoiceCallerCredential.enabled.is_(True),
                )
            )
            if has_cred is not None:
                return True
        return VoiceCallerAuth(self.db, self.settings).has_owner_credential(call.company_id)

    def consume_pending_auth_query(self) -> str | None:
        call = self.db.get(VoiceCall, self.call_id)
        if call is None or not call.source_context:
            return None
        pending = call.source_context.get("pending_auth_query")
        if pending:
            ctx = dict(call.source_context)
            ctx.pop("pending_auth_query", None)
            call.source_context = ctx
            self.db.commit()
        return pending

    def security_gate(self, transcript: str) -> dict | None:
        """Inspects transcript for security restrictions (PIN modification, owner auth, private client data).

        Returns a dict action if a security gate applies, or None to allow natural conversational AI.
        """
        call, config, _company = self.context()
        safe = redact_voice_secrets(transcript)
        normalized = "".join(character for character in unicodedata.normalize("NFKD", safe.casefold()) if not unicodedata.combining(character))
        loc = resolve_locale(call.locale or config.preferred_language).casefold()
        french = loc.startswith("fr")
        spanish = loc.startswith("es")
        romanian = loc.startswith("ro")

        # 1. PIN creation/configuration/management instructions
        if _RE_PIN_MGMT.search(normalized):
            return {"status": "success", "answer": self.portal_message(), "public": True}

        # 2. Inquiries specifically about PIN authentication / secure authentication
        pin_inquiry = bool(_RE_PIN_INQUIRY.search(normalized))

        # Check if caller has a public customer intent (appointment, speaking/contacting, recruitment, job application)
        is_public_customer_intent = bool(_RE_PUBLIC_CUSTOMER_INTENT.search(normalized))

        # 3. Requests for confidential business, financial or inventory data
        # MUST BE ANALYZED UNCONDITIONALLY across all languages
        private_data = _RE_PRIVATE_DATA.search(normalized)

        # PRIORITY RULE: Private data or PIN inquiry ALWAYS takes precedence over public intent.
        # A mixed request containing both a public intent (e.g. contact/appointment) and private data
        # (e.g. today's revenue / sales) MUST require authentication or be refused.
        if pin_inquiry or private_data:
            has_pin = self.has_configured_pin(call)
            if has_pin:
                # Save the pending query for automatic execution post-authentication
                call.source_context = {**(call.source_context or {}), "pending_auth_query": safe}
                self.db.commit()

                if pin_inquiry:
                    if spanish:
                        prompt = (
                            "Sí, el acceso seguro se realiza mediante PIN con las teclas de su teléfono. "
                            "Por favor, introduzca su código PIN en el teclado de su teléfono seguido de almohadilla. "
                            "Nunca pronuncie su PIN en voz alta."
                        )
                    elif french:
                        prompt = (
                            "Oui, l'accès sécurisé s'effectue par NIP à l'aide des touches de votre téléphone. "
                            "Veuillez saisir votre code NIP sur le clavier de votre téléphone, suivi du carré. "
                            "Ne prononcez jamais votre NIP à voix haute."
                        )
                    elif romanian:
                        prompt = (
                            "Da, autentificarea securizată se realizează prin PIN folosind tastatura telefonului. "
                            "Vă rugăm să introduceți codul PIN pe tastatură urmat de diez. "
                            "Nu rostiți niciodată PIN-ul cu voce tare."
                        )
                    else:
                        prompt = (
                            "Yes, secure authentication is available using your phone keypad. "
                            "Please enter your PIN on your phone keypad, followed by pound. "
                            "Never say your PIN aloud."
                        )
                else:
                    if spanish:
                        prompt = (
                            "Para acceder a los datos de su empresa, por favor introduzca su PIN "
                            "con las teclas de su teléfono. Nunca pronuncie su PIN en voz alta."
                        )
                    elif french:
                        prompt = (
                            "Pour accéder aux données de votre entreprise, veuillez saisir votre NIP "
                            "à l'aide des touches de votre téléphone. Ne prononcez jamais votre NIP à voix haute."
                        )
                    elif romanian:
                        prompt = (
                            "Pentru a accesa datele companiei dumneavoastră, vă rugăm să introduceți PIN-ul "
                            "folosind tastele telefonului. Nu rostiți niciodată PIN-ul cu voce tare."
                        )
                    else:
                        prompt = (
                            "To access your business data, please enter your PIN using your phone keypad. "
                            "Never say your PIN aloud."
                        )
                return {"status": "success", "answer": prompt, "auth_required": True, "public": True}
            else:
                if pin_inquiry:
                    answer = (
                        ("L'authentification par NIP est disponible, mais aucun NIP n'est configuré pour ce numéro. " if french else ("La autenticación por PIN está disponible, pero no hay ningún PIN configurado para este número. " if spanish else ("Autentificarea prin PIN este disponibilă, dar nu este configurat niciun PIN pentru acest număr. " if romanian else "PIN authentication is available, but no PIN is configured for this number. ")))
                        + self.portal_message()
                    )
                else:
                    answer = (
                        ("L'accès aux données de votre entreprise nécessite la configuration d'un NIP. " if french else ("El acceso a los datos de su empresa requiere configurar un PIN. " if spanish else ("Accesul la datele companiei dumneavoastră necesită configurarea unui PIN. " if romanian else "Accessing company data requires configuring a PIN. ")))
                        + self.portal_message()
                    )
                return {"status": "success", "answer": answer, "public": True}

        if _RE_CUSTOMER_VERIFY.search(normalized):
            if spanish:
                answer = "Se requiere verificar su identidad de cliente para acceder a sus datos personales o modificar una cita."
            elif french:
                answer = "Une vérification de votre identité client est nécessaire pour accéder à vos données personnelles ou modifier un rendez-vous."
            elif romanian:
                answer = "Verificarea identității este necesară pentru a accesa datele personale sau a modifica o programare."
            else:
                answer = "Customer identity verification is required to access personal information or change an appointment."
            return {"status": "success", "answer": answer, "customer_verification_required": True, "public": True}
        return None

    def public_answer(self, transcript: str) -> dict:
        call, config, _company = self.context()
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService
        profile = CompanyIntelligenceService(self.db).get_profile(call.company_id)
        safe = redact_voice_secrets(transcript)
        normalized = "".join(character for character in unicodedata.normalize("NFKD", safe.casefold()) if not unicodedata.combining(character))
        loc = resolve_locale(call.locale or config.preferred_language).casefold()
        french = loc.startswith("fr")
        spanish = loc.startswith("es")
        romanian = loc.startswith("ro")
        if _RE_PIN_MGMT.search(normalized):
            return {"status": "success", "answer": self.portal_message(), "public": True}

        is_public_customer_intent = bool(_RE_PUBLIC_CUSTOMER_INTENT.search(normalized))
        is_management_contact = bool(_RE_MANAGEMENT_CONTACT.search(normalized))
        # Requests for confidential business, financial or inventory data
        # MUST BE ANALYZED UNCONDITIONALLY across all languages
        private = _RE_PRIVATE_DATA.search(normalized)
        if private:
            call.source_context = {**(call.source_context or {}), "pending_auth_query": safe}
            self.db.commit()
            prompt = voice_auth_message(call.locale or config.preferred_language, 0)
            return {"status": "success", "answer": prompt + " " + self.portal_message(), "auth_required": True, "public": True}

        if _RE_BOOKING_MGMT.search(normalized):
            if spanish:
                answer = "Se requiere verificar su identidad de cliente para acceder a sus datos personales o modificar una cita."
            elif french:
                answer = "Une vérification de votre identité client est nécessaire pour accéder à vos données personnelles ou modifier un rendez-vous."
            elif romanian:
                answer = "Verificarea identității este necesară pentru a accesa datele personale sau a modifica o programare."
            else:
                answer = "Customer identity verification is required to access personal information or change an appointment."
            return {"status": "success", "answer": answer, "customer_verification_required": True, "public": True}

        is_pickup_reservation = bool(_RE_PICKUP.search(normalized))
        is_booking_request = bool(_RE_BOOKING.search(normalized)) or is_pickup_reservation or (is_management_contact and is_public_customer_intent)

        if is_booking_request or (is_management_contact and not private):
            if not profile.has_crm_booking or is_management_contact:
                if is_management_contact:
                    if spanish:
                        answer = "La administración y la gerencia no están disponibles directamente por teléfono en este momento. Puede dejar un mensaje o escribir por correo electrónico para coordinar una cita o enviar su consulta."
                    elif french:
                        answer = "La direction et le propriétaire ne sont pas joignables directement par téléphone pour le moment. Vous pouvez laisser un message ou écrire par courriel pour convenir d'un rendez-vous ou transmettre votre demande."
                    elif romanian:
                        answer = "Conducerea și proprietarul nu pot fi contactați direct prin telefon în acest moment. Puteți lăsa un mesaj sau trimite un e-mail pentru a stabili o întâlnire."
                    else:
                        answer = "Management and the owner are not directly reachable by phone at the moment. You can leave a message or send an email to request an appointment or submit your inquiry."
                    return {"status": "success", "answer": answer, "public": True}
                else:
                    if spanish:
                        answer = "Actualmente no hay ningún servicio reservable ni recogida en tienda configurado para esta empresa."
                    elif french:
                        answer = "Aucune prestation réservable ou cueillette en magasin n’est actuellement configurée pour cette entreprise."
                    elif romanian:
                        answer = "Nu există servicii rezervabile sau ridicare din magazin configurate în prezent pentru această companie."
                    else:
                        answer = "No bookable service or store pickup is currently configured for this business."
                    return {"status": "success", "answer": answer, "public": True}

            if is_pickup_reservation:
                if spanish:
                    answer = "Las reservas de productos no se realizan por teléfono. Para recogida en tienda o una cita de servicio, indique el servicio y la fecha deseados."
                elif french:
                    answer = "Les réservations de produits ne sont pas effectuées par téléphone. Pour une cueillette ou un rendez-vous de service, veuillez indiquer la prestation et la date souhaitées."
                elif romanian:
                    answer = "Rezervările de produse nu se efectuează prin telefon. Pentru ridicare sau o programare, vă rugăm să indicați serviciul și data dorite."
                else:
                    answer = "Product reservations are not processed by phone. For store pickup or a service appointment, please provide the desired service and date."
            else:
                if spanish:
                    answer = "Para solicitar una cita, indique el servicio y la fecha deseados. Ninguna reserva está confirmada todavía."
                elif french:
                    answer = "Pour demander un rendez-vous, indiquez le service et la date souhaités. Aucun rendez-vous n'est encore confirmé."
                elif romanian:
                    answer = "Pentru a solicita o programare, indicați serviciul și data dorite. Nicio programare nu este confirmată încă."
                else:
                    answer = "For an appointment request, please provide the service and desired date. No booking is confirmed yet."
            call.source_context = {**(call.source_context or {}), "public_appointment_request": True}
            self.db.commit()
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"heures|horaires|hours|ouvert|opening|schedule", normalized):
            raw_hours = getattr(_company, "business_hours", None) or getattr(config, "opening_hours", None) or {}
            hours_dict = {}
            if isinstance(raw_hours, dict) and "weekly" in raw_hours and isinstance(raw_hours["weekly"], dict):
                for day, ranges in raw_hours["weekly"].items():
                    if isinstance(ranges, list) and ranges:
                        r_str = ", ".join(f"{r.get('open')} à {r.get('close')}" for r in ranges if isinstance(r, dict) and r.get("open") and r.get("close"))
                        if r_str:
                            hours_dict[day.lower()] = r_str
            elif isinstance(raw_hours, dict):
                for day, val in raw_hours.items():
                    if isinstance(val, dict) and val.get("open") and val.get("close"):
                        hours_dict[day.lower()] = f"{val.get('open')} à {val.get('close')}"
            day_map_fr = {
                "monday": "lundi", "tuesday": "mardi", "wednesday": "mercredi",
                "thursday": "jeudi", "friday": "vendredi", "saturday": "samedi", "sunday": "dimanche"
            }
            if hours_dict:
                if french:
                    summary = ", ".join(f"{day_map_fr.get(day, day)}: {h}" for day, h in hours_dict.items())
                    answer = f"Nos heures d'ouverture sont : {summary}."
                else:
                    summary = ", ".join(f"{day}: {h}" for day, h in hours_dict.items())
                    answer = f"Our opening hours are: {summary}."
            else:
                answer = "Les heures d'ouverture ne sont pas encore configurées." if french else "Opening hours have not been supplied yet."
            return {"status": "success", "answer": answer, "public": True}

        if re.search(r"shopify|site web|boutique en ligne|commander en ligne|achat en ligne|online store|website", normalized):
            if profile.has_online_store and profile.online_store_url:
                answer = (
                    f"Oui ! Vous pouvez passer commande directement sur notre boutique officielle : {profile.online_store_url}. "
                    "Pour des raisons de sécurité, nous ne prenons pas de carte bancaire par téléphone."
                    if french else
                    f"Yes! You can place orders on our official store: {profile.online_store_url}. "
                    "For your security, we do not accept credit card details over the phone."
                )
            else:
                answer = (
                    "Notre boutique en ligne est en cours de configuration. Pour commander, vous pouvez nous joindre en magasin ou par téléphone."
                    if french else
                    "Our online store is currently being configured. You can reach us directly to place an order."
                )
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"services|prix|price|tarif", normalized):
            services = [{key: value[key] for key in ("name", "duration_minutes", "price", "currency") if key in value} for value in profile.configured_crm_services if isinstance(value, dict)]
            if services:
                def _sym(curr: Any) -> str:
                    c = str(curr or "").strip().upper()
                    return "$" if c in ("CAD", "USD", "$") or not c else ("€" if c in ("EUR", "€") else ("£" if c in ("GBP", "£") else c))
                summary = ", ".join(f"{s.get('name', '')} ({s.get('price', '')} {_sym(s.get('currency'))})".strip() for s in services)
                answer = ("Nos services: " if french else "Our services: ") + summary
            else:
                answer = "Les services publics ne sont pas encore renseignés." if french else "Public services have not been supplied yet."
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"fournisseur\w*|fournir|vendre nos produits|devenir fournisseur|supplier\w*|vendor\w*|furnizor\w*|proveedor\w*", normalized):
            supp_pol = getattr(profile, "supplier_policy", None) or (profile.business_configuration.get("supplier_policy") if getattr(profile, "business_configuration", None) else None)
            acc_supp = getattr(profile, "accepts_suppliers", None)
            if acc_supp is None and getattr(profile, "business_configuration", None):
                acc_supp = profile.business_configuration.get("accepts_suppliers")
            comp_email = getattr(profile, "email", None) or getattr(_company, "email", None)
            comp_web = getattr(profile, "website", None) or getattr(_company, "website", None)

            if supp_pol:
                answer = str(supp_pol)
            elif acc_supp is False:
                answer = "Notre entreprise ne recherche pas de nouveaux fournisseurs pour le moment." if french else "Our company is not currently looking for new suppliers or vendors."
            elif acc_supp is True:
                if comp_email:
                    answer = f"Nous sommes à l'écoute de nouveaux partenaires et fournisseurs. Vous pouvez nous transmettre votre proposition par courriel à {comp_email}." if french else f"We are open to new partners and suppliers. You can send your proposal by email to {comp_email}."
                elif comp_web:
                    answer = f"Nous étudions les propositions de partenaires et fournisseurs via notre site officiel {comp_web}." if french else f"We review partner and vendor proposals through our official website at {comp_web}."
                else:
                    answer = "Nous étudions les propositions de partenaires et fournisseurs. Je peux prendre un message et vos coordonnées pour notre direction." if french else "We review partner and vendor proposals. I can take your contact details and message for management."
            else:
                if comp_web:
                    answer = f"La politique relative aux fournisseurs n'est pas spécifiée pour notre établissement. Pour toute proposition, vous pouvez consulter notre site {comp_web} ou laisser vos coordonnées." if french else f"Our supplier policy is not currently configured. For inquiries, please check our website {comp_web} or leave your contact details."
                elif comp_email:
                    answer = f"Les modalités concernant les fournisseurs ne sont pas confirmées. Vous pouvez nous écrire à {comp_email} ou laisser vos coordonnées." if french else f"Supplier policies are not confirmed. You can reach us at {comp_email} or leave your contact details."
                else:
                    answer = "Les modalités concernant les fournisseurs ne sont pas confirmées pour notre établissement. Je peux prendre votre message et vos coordonnées pour les transmettre à la direction." if french else "Supplier policies are not confirmed for our business. I can take your contact details and message for management."
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"recrut\w*|embauch\w*|postul\w*|candidat\w*|emploi\w*|job\w*|hiring|career\w*|angajar\w*|angajat\w*|empleo\w*|contrat\s*(?:de\s*travail|d['’]embauche|de\s*stage|professionnalisation)|work\s*contract|employment\s*contract", normalized):
            rec_pol = getattr(profile, "recruitment_policy", None) or (profile.business_configuration.get("recruitment_policy") if getattr(profile, "business_configuration", None) else None)
            is_hiring = getattr(profile, "is_hiring", None)
            if is_hiring is None and getattr(profile, "business_configuration", None):
                is_hiring = profile.business_configuration.get("is_hiring")
            comp_email = getattr(profile, "email", None) or getattr(_company, "email", None)
            comp_web = getattr(profile, "website", None) or getattr(_company, "website", None)

            if rec_pol:
                answer = str(rec_pol)
            elif is_hiring is False:
                answer = "Notre entreprise n'a aucun poste ouvert et ne recrute pas actuellement." if french else "Our company has no open positions and is not hiring at this time."
            elif is_hiring is True:
                if comp_web:
                    answer = f"Notre entreprise recrute actuellement. Vous pouvez consulter nos offres d'emploi sur notre site officiel {comp_web}." if french else f"Our company is currently hiring. You can view our job openings on our official website at {comp_web}."
                elif comp_email:
                    answer = f"Notre entreprise recrute actuellement. Vous pouvez faire parvenir votre curriculum vitae à notre adresse courriel {comp_email}." if french else f"Our company is currently hiring. You can submit your resume to our email at {comp_email}."
                else:
                    answer = "Notre entreprise a des opportunités d'emploi. Je peux noter vos coordonnées pour notre équipe des ressources humaines." if french else "Our company has job opportunities. I can take your contact details for our hiring team."
            else:
                if comp_web:
                    answer = f"Les opportunités d'embauche ne sont pas confirmées actuellement. Vous pouvez consulter notre site {comp_web} ou laisser un message avec vos coordonnées." if french else f"Hiring opportunities are not confirmed at this time. You can check our website {comp_web} or leave a message."
                elif comp_email:
                    answer = f"Les opportunités de recrutement ne sont pas confirmées. Vous pouvez nous faire parvenir vos coordonnées ou écrire à {comp_email}." if french else f"Recruitment opportunities are not confirmed. You can reach out to {comp_email} or leave your contact details."
                else:
                    answer = "Les opportunités de recrutement ne sont pas confirmées pour notre établissement. Je peux noter vos coordonnées pour transmettre votre intérêt à notre équipe." if french else "Recruitment opportunities are not confirmed for our business. I can take your contact details to express your interest."
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"commande|order|produit|product|stock|inventaire|inventory|magasin|boutique|retail|accessoire|accessoires|accessory|accessories|equipement|equipements|equipment|planche|planches|snowboard|snowboards", normalized):
            if not profile.has_retail_commerce and not profile.public_products:
                if profile.has_crm_booking:
                    answer = "Notre établissement propose principalement des services professionnels plutôt que des produits en vente directe. Je peux vous renseigner sur nos prestations ou planifier un rendez-vous. Que souhaitez-vous savoir ?" if french else "Our company primarily provides professional services rather than retail products. I can assist you with our services or booking. What would you like to know?"
                else:
                    answer = "Notre entreprise ne propose pas de vente directe de produits ou d'inventaire en ligne. Pour toute information générale, je reste à votre disposition." if french else "Our company does not offer retail product sales or online inventory. For general inquiries, I am here to help."
                return {"status": "success", "answer": answer, "public": True}
            from backend.app.voice.direct_answers import spoken_catalog_answer
            answer = spoken_catalog_answer(
                profile.public_products,
                retail_enabled=True,
                locale=call.locale or config.preferred_language,
                currency=getattr(profile, "currency_code", None),
                query=safe,
            )
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"parler|quelqu.un|agent|humain|reception|personne|speak|someone|representative|human", normalized):
            answer = "Je peux prendre votre message ou vous renseigner sur nos services, horaires et rendez-vous. Comment puis-je vous aider ?" if french else "I can take a message or assist with services, hours, and appointments. How can I help you?"
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"^\s*(bonjour|salut|allo|allô|bon matin|bonsoir|oui bonjour|hello|hi|hey)\s*[.!?]?\s*$", normalized):
            return {"status": "success", "answer": "Bonjour ! Comment puis-je vous aider aujourd'hui ?" if french else "Hello! How can I help you today?", "public": True}
        if not profile.has_crm_booking and not profile.has_retail_commerce:
            answer = "Je peux vous renseigner sur notre entreprise et nos coordonnées. Les opérations internes nécessitent une authentification personnelle." if french else "I can provide information about our business and contact details. Internal operations require personal authentication."
            return {"status": "success", "answer": answer, "public": True}
        if not profile.has_crm_booking:
            answer = "Je peux vous renseigner sur notre entreprise. Les données de ventes et de stock nécessitent une authentification personnelle." if french else "I can help with business information. Sales and internal stock require personal authentication."
            return {"status": "success", "answer": answer, "public": True}
        answer = "Je peux vous renseigner sur nos heures d'ouverture, nos produits, ou pour une réservation et cueillette en magasin. Comment puis-je vous aider ?" if french else "I can help with our opening hours, products, or a booking and store pickup. How can I help you?"
        return {"status": "success", "answer": answer, "public": True}

    async def begin_pin(self, item_id: str) -> dict:
        call, config, _company = self.context()
        maximum = self.settings.voice_pin_max_attempts
        action_id = "media-pin:" + hashlib.sha256(f"{call.id}:{item_id}".encode()).hexdigest()
        existing = self.db.scalar(select(VoiceToolAction).where(VoiceToolAction.company_id == call.company_id,
            VoiceToolAction.config_id == config.id, VoiceToolAction.action_id == action_id))
        if existing is not None:
            return existing.result
        if not call.telnyx_call_control_id:
            return {"success": False, "error": "caller_authentication_unavailable"}
        if call.verification_attempts >= maximum:
            return {"success": False, "error": "caller_authentication_failed"}
        call.pin_challenge_hash = None
        call.pin_challenge_expires_at = None
        if self.settings.rate_limit_enabled and not allow_rate_limit("voice_media_pin", str(call.company_id) + ":" + str(call.id), maximum):
            return {"success": False, "error": "caller_authentication_rate_limited"}
        client_state = VoiceCallerAuth(self.db, self.settings).challenge(call)
        call.source_context = {**(call.source_context or {}), "pin_gather_status": "pending"}
        receipt = VoiceToolAction(company_id=call.company_id, config_id=config.id, action_id=action_id,
            tool_name="voice_media_pin", result={"success": True, "authentication_pending": True})
        self.db.add(receipt)
        self.db.commit()
        try:
            await self.telnyx.gather_pin(call.telnyx_call_control_id,
                command_id=str(UUID(hashlib.sha256(action_id.encode()).hexdigest()[:32])), client_state=client_state)
        except Exception:
            call.pin_challenge_hash = None; call.pin_challenge_expires_at = None
            call.source_context = {**(call.source_context or {}), "pin_gather_status": "refused"}
            receipt.result = {"success": False, "error": "caller_authentication_unavailable"}
            self.db.commit()
        return receipt.result

    def pin_state(self) -> str:
        call, _config, _company = self.context()
        if call.pin_challenge_hash and call.pin_challenge_expires_at and utc(call.pin_challenge_expires_at) <= datetime.now(timezone.utc):
            call.pin_challenge_hash = None; call.pin_challenge_expires_at = None
            call.source_context = {**(call.source_context or {}), "pin_gather_status": "refused"}
            self.db.commit()
        if call.pin_challenge_hash:
            return "pending"
        gather_status = (call.source_context or {}).get("pin_gather_status")
        if gather_status == "authenticated":
            auth = VoiceCallerAuth(self.db, self.settings).valid_session(call)
            return "authenticated" if auth is not None and auth.caller_type in {"OWNER", "EMPLOYEE"} else "refused"
        if gather_status == "cancelled":
            return "cancelled"
        if gather_status == "retry_needed":
            return "retry_needed"
        return "refused"

    def cancel_pin(self) -> None:
        call, _config, _company = self.context()
        call.pin_challenge_hash = None
        call.pin_challenge_expires_at = None
        existing_ctx = dict(call.source_context or {})
        existing_ctx.pop("handover_revoked", None)
        existing_ctx["handover_cancelled"] = True
        existing_ctx["public_fallback"] = True
        existing_ctx["pin_gather_status"] = "cancelled"
        call.source_context = existing_ctx
        self.db.commit()

    def reset_pin_retry(self) -> None:
        call, _config, _company = self.context()
        call.source_context = {**(call.source_context or {}), "pin_gather_status": "pending_retry"}
        self.db.commit()


class TelnyxAudioReorderBuffer:
    """Bounded jitter and frame reordering buffer for Telnyx inbound media packets.

    Handles:
    - strict sequential ordering
    - out-of-order frame buffering
    - duplicate frame detection and drop
    - late frame drop
    - missing frame recovery (advancing expected sequence after gap/capacity reached)
    - bounded memory (never grows unbounded)
    - strict metric counters without sensitive audio bytes
    """

    def __init__(self, max_buffer_size: int = 10, max_gap_tolerance: int = 2) -> None:
        self.max_buffer_size = max(2, max_buffer_size)
        self.max_gap_tolerance = max(1, max_gap_tolerance)
        self._expected_chunk: int | None = None
        self._last_emitted_chunk: int = 0
        self._buffer: dict[int, bytes] = {}
        # Metrics without sensitive audio content
        self.duplicate_frames: int = 0
        self.late_frames: int = 0
        self.missing_frames: int = 0
        self.out_of_order_frames: int = 0
        self.reordered_frames: int = 0
        self.inbound_frames: int = 0

    def reset(self) -> None:
        self._expected_chunk = None
        self._last_emitted_chunk = 0
        self._buffer.clear()

    def push(self, chunk: int, payload: bytes) -> list[bytes]:
        """Pushes an incoming frame (chunk sequence number and decoded PCM payload).
        Returns a list of payloads ready to be emitted in strict sequential order.
        """
        self.inbound_frames += 1
        if self._expected_chunk is None:
            self._expected_chunk = chunk

        # Late frame detection (arrived after window has advanced past it)
        if chunk < self._expected_chunk:
            self.late_frames += 1
            return []

        # Duplicate frame detection (already in buffer)
        if chunk in self._buffer:
            self.duplicate_frames += 1
            return []

        to_emit: list[bytes] = []

        if chunk == self._expected_chunk:
            to_emit.append(payload)
            self._last_emitted_chunk = chunk
            self._expected_chunk += 1
            # Drain any consecutive buffered frames that were waiting for this chunk
            while self._expected_chunk in self._buffer:
                buffered = self._buffer.pop(self._expected_chunk)
                to_emit.append(buffered)
                self._last_emitted_chunk = self._expected_chunk
                self._expected_chunk += 1
                self.reordered_frames += 1
            return to_emit

        # Out-of-order frame (chunk > self._expected_chunk)
        self.out_of_order_frames += 1
        self._buffer[chunk] = payload

        # Check for gap tolerance or capacity limits
        # If newest chunk is too far ahead of expected chunk (>= max_gap_tolerance),
        # or if buffer capacity is reached, advance past missing frames.
        while self._buffer and (
            len(self._buffer) >= self.max_buffer_size
            or (chunk - self._expected_chunk >= self.max_gap_tolerance)
        ):
            oldest_chunk = min(self._buffer.keys())
            if oldest_chunk > self._expected_chunk:
                self.missing_frames += oldest_chunk - self._expected_chunk
                self._expected_chunk = oldest_chunk

            while self._expected_chunk in self._buffer:
                buffered = self._buffer.pop(self._expected_chunk)
                to_emit.append(buffered)
                self._last_emitted_chunk = self._expected_chunk
                self._expected_chunk += 1

        return to_emit

    def flush(self) -> list[bytes]:
        """Emits any remaining frames in ascending order, clearing the buffer and counting missing frames."""
        to_emit: list[bytes] = []
        if self._buffer:
            sorted_chunks = sorted(self._buffer.keys())
            if self._expected_chunk is not None and sorted_chunks[0] > self._expected_chunk:
                self.missing_frames += sorted_chunks[0] - self._expected_chunk
            for i, ch in enumerate(sorted_chunks):
                if i > 0 and ch > sorted_chunks[i - 1] + 1:
                    self.missing_frames += ch - sorted_chunks[i - 1] - 1
                to_emit.append(self._buffer[ch])
                self._last_emitted_chunk = ch
            self._buffer.clear()
            self._expected_chunk = self._last_emitted_chunk + 1
        return to_emit


class TelnyxMediaBridge:
    def __init__(
        self, socket, adapter, *, locale: str,
        validate_start: Callable[[dict], Awaitable[None]],
        authorize: Callable[[], Awaitable[None]],
        execute_turn: Callable[[str, str], Awaitable[dict]],
        usage_ledger=None, stt_model: str | None = None, realtime_model: str | None = None,
        initial_answer: str | None = None,
        begin_pin: Callable[[str], Awaitable[dict]] | None = None,
        poll_pin: Callable[[], Awaitable[str]] | None = None,
        reset_pin_retry: Callable[[], Awaitable[None]] | None = None,
        cancel_pin: Callable[[], Awaitable[None]] | None = None,
        consume_pending_query: Callable[[], Awaitable[str | None]] | None = None,
        hangup_call: Callable[[], Awaitable[None]] | None = None,
        max_output_queue: int = 64,
        max_session_seconds: float | None = None,
        idle_seconds: float | None = None,
        allow_natural_interruptions: bool = True,
        interruption_manager: Any | None = None,
        prepare_speech: Callable[[str], str] | None = None,
    ) -> None:
        self.socket = socket
        self.adapter = adapter
        self.locale = locale
        self.validate_start = validate_start
        self.authorize = authorize
        self.execute_turn = execute_turn
        self.usage = usage_ledger
        self._ledger_history = [usage_ledger] if usage_ledger is not None else []
        self.stt_model = stt_model
        self.realtime_model = realtime_model
        self.initial_answer = initial_answer
        self.begin_pin: Callable[[str], Awaitable[dict]] | None = begin_pin
        self.poll_pin: Callable[[], Awaitable[str]] | None = poll_pin
        self.reset_pin_retry: Callable[[], Awaitable[None]] | None = reset_pin_retry
        self.cancel_pin: Callable[[], Awaitable[None]] | None = cancel_pin
        self.consume_pending_query: Callable[[], Awaitable[str | None]] | None = consume_pending_query
        self.hangup_call: Callable[[], Awaitable[None]] | None = hangup_call
        self.allow_natural_interruptions = bool(allow_natural_interruptions)
        self.interruption_manager = interruption_manager
        self.prepare_speech = prepare_speech
        if max_session_seconds is not None and max_session_seconds <= 0:
            raise ValueError("Session duration must be positive")
        self.max_session_seconds = max_session_seconds
        self.idle_seconds = idle_seconds
        self._last_activity = time.monotonic()
        self._authorized_session = False
        self._termination_requested = False
        self._stop_event = asyncio.Event()
        self.codec = TelnyxAudioCodec()
        self.reorder_buffer = TelnyxAudioReorderBuffer(max_buffer_size=10, max_gap_tolerance=2)
        self.stream_id = None
        self.epoch = 0
        self.response_id = None
        self.pending_epoch = None
        self.response_epoch = None
        self.input_paused = False
        self._last_chunk = 0
        self._seen_items: set[str] = set()
        self._output = asyncio.Queue(maxsize=max_output_queue)
        self._remainder = b""
        self._send_lock = asyncio.Lock()
        self._background = []
        self._turns = asyncio.Queue(maxsize=2)
        self._pending_speech = deque()
        self._responses = {}
        self._cancelled_responses: set[str] = set()
        self._current_turn_task: asyncio.Task | None = None
        self._turn_metrics: dict[str, dict[str, Any]] = {}
        self._last_transcription_at: float | None = None
        self._last_speech_started_at: float | None = None
        self._last_interrupted_at: float | None = None
        self._interrupted_item_ids: set[str] = set()
        self._last_barge_in_item_id: str | None = None
        self._playback_active: bool = False
        self._active_play_mark: str | None = None
        self.orchestrator = VoiceTurnOrchestrator()
        self._pin_turn = None
        self._pin_mark = None
        self._pin_started = False
        self._pin_deadline = None
        self._pin_prompt_spoken = False
        self._pin_prompt_finish_time = None
        self._pin_retry_count = 0
        self.max_pin_retries = 3
        # Backpressure & health metrics (no raw audio)
        self.dropped_inbound_frames = 0
        self.dropped_outbound_frames = 0
        self.central_ai_timeouts = 0
        self.central_ai_missing_answers = 0
        self.central_ai_replies_queued = 0
        self.central_ai_discarded_epochs = 0
        self._executing_turn = False
        self._in_flight_transcript: str | None = None
        self._last_spoken: str | None = None
        self._last_filler_time: float = 0.0
        self.phase = "LISTENING"
        self.call_correlation: str | None = None
        self.turn_correlation: str | None = None
        self.tts_failures = 0
        self.tts_timeout = 10.0
        self.central_ai_timeout = 18.0
        self.inbound_audio_timeout = 5.0
        self._call_start_time: float = time.monotonic()
        self._last_speech_stopped_at: float | None = None
        # Safe call telemetry (no raw audio, no secrets)
        self.telemetry: dict[str, Any] = {
            "call_answered": True,
            "media_connected": False,
            "inbound_frames": 0,
            "inbound_audio_ms": 0,
            "speech_detected": False,
            "speech_started_count": 0,
            "speech_stopped_count": 0,
            "stt_partial_count": 0,
            "stt_final_count": 0,
            "speech_stopped_without_transcript": 0,
            "stt_rescue_succeeded": 0,
            "barge_in_triggered_count": 0,
            "telnyx_clear_sent_count": 0,
            "late_transcripts_discarded": 0,
            "stt_audio_sent": False,
            "transcription_received": False,
            "central_ai_called": False,
            "tts_generated": False,
            "outbound_frames": 0,
            "final_state": "CONNECTING",
            "provider_error": None,
            "conversation_phase": "LISTENING",
            "central_ai_response_ready": 0,
            "tts_request_started": 0,
            "tts_first_audio_chunk_received": 0,
            "tts_audio_bytes_generated": 0,
            "audio_encoding_completed": 0,
            "outbound_audio_frames_sent": 0,
            "outbound_audio_bytes_sent": 0,
            "outbound_playback_acknowledged": 0,
            "tts_provider_error": 0,
            "voice_response_cancelled": 0,
            "voice_response_completed": 0,
            "active_provider": getattr(adapter, "provider_id", "unknown"),
            "active_model": getattr(adapter, "model_name", realtime_model or "unknown"),
            "connection_establishment_duration_ms": 0,
            "first_audible_response_latency_ms": 0,
            "fallback_occurred": False,
            "fallback_reason": None,
            "fallback_duration_ms": None,
            "crm_function_failures": 0,
            "unexpected_silence_count": 0,
            "vad_interruptions_count": 0,
        }

    def _clear_all_buffers(self) -> None:
        self.reorder_buffer.reset()
        self._remainder = b""
        self.codec.reset()
        while not self._output.empty():
            with suppress(Exception):
                self._output.get_nowait()
        while not self._turns.empty():
            with suppress(Exception):
                item_id, _transcript, _epoch = self._turns.get_nowait()
                if self.usage is not None:
                    self.usage.settle(item_id)
        while self._pending_speech:
            item_id, _epoch, turn_ledger = self._pending_speech.popleft()
            if turn_ledger is not None:
                turn_ledger.settle(item_id)
        for _resp_id, (item_id, _resp_epoch, resp_ledger) in list(self._responses.items()):
            if resp_ledger is not None:
                resp_ledger.settle(item_id)
        self._responses.clear()

    def _set_phase(self, phase: str) -> None:
        self.phase = phase
        self.telemetry["conversation_phase"] = phase
        self.orchestrator.transition(phase)

    def _set_playback_active(self, active: bool) -> None:
        self._playback_active = bool(active)
        if hasattr(self.adapter, "set_playback_active"):
            fn: Any = getattr(self.adapter, "set_playback_active")
            with suppress(Exception):
                fn(self._playback_active)

    def _spoken(self, text: str) -> str:
        cleaned = clean_voice_text(redact_voice_secrets(text), locale=self.locale)
        if self.prepare_speech is not None:
            cleaned = self.prepare_speech(cleaned)
        self._last_spoken = cleaned
        return cleaned

    def get_turn_metrics(self, item_id: str) -> dict[str, Any]:
        """Return instrumentation latency metrics for a specific turn."""
        return dict(self._turn_metrics.get(str(item_id), {}))

    def get_latency_summary(self) -> dict[str, dict[str, float | int | None]]:
        """Return p50/p95 latency measurements across barge-in, first-audio, and Central AI stages."""
        return self.orchestrator.latency_summary()

    async def interrupt(
        self,
        *,
        pause_input: bool = False,
        originating_response_id: str | None = None,
        reason: str = "interruption",
    ) -> None:
        if originating_response_id:
            if not self.orchestrator.mark_response_cancelled(originating_response_id):
                return
            if originating_response_id in self._cancelled_responses:
                return
            self._cancelled_responses.add(originating_response_id)
            if len(self._cancelled_responses) > 500:
                self._cancelled_responses.clear()

        now_t = time.monotonic()
        self.telemetry["vad_interruptions_count"] += 1
        if reason in {
            "caller_speech_barge_in",
            "partial_transcript_barge_in",
            "untranscribed_speech_barge_in",
            "pin_challenge_verbal_cancellation",
        }:
            self.telemetry["barge_in_triggered_count"] += 1
            if self._last_speech_started_at is not None:
                reaction_ms = max(0.0, (now_t - self._last_speech_started_at) * 1000.0)
                self.orchestrator.record_barge_in_latency(reaction_ms)
        if self.response_id and str(self.response_id) in self._turn_metrics:
            self._turn_metrics[str(self.response_id)]["interruption_reason"] = reason
            self._turn_metrics[str(self.response_id)]["telnyx_clear_sent_at"] = now_t

        cancel_response = (
            self.response_id is not None
            or self.pending_epoch is not None
            or self.phase in {"PLAYING", "SYNTHESIZING", "SPEAKING"}
            or self._playback_active
            or not self._output.empty()
        )
        session_key = str(self.stream_id or "default")

        # Co-operatively abort any in-flight Central AI execution task (except current task)
        curr_task = asyncio.current_task()
        if (
            self._current_turn_task is not None
            and self._current_turn_task is not curr_task
            and not self._current_turn_task.done()
        ):
            self._current_turn_task.cancel()

        old_epoch = self.epoch
        self.epoch += 1
        self.orchestrator.epoch = self.epoch
        self.pending_epoch = None
        self.response_epoch = None
        if self.response_id:
            self.orchestrator.mark_response_cancelled(str(self.response_id))
        self.response_id = None
        self._active_play_mark = None
        self._set_playback_active(False)
        self._last_interrupted_at = now_t
        self._remainder = b""
        self.codec.reset()
        self.reorder_buffer.reset()

        # IMPORTANT: Preserve turns queued for the current or future epoch!
        # Only discard turns whose epoch is strictly older than old_epoch.
        preserved_turns = []
        while not self._turns.empty():
            t = self._turns.get_nowait()
            if t[2] >= old_epoch:
                preserved_turns.append((t[0], t[1], self.epoch))
            else:
                self._interrupted_item_ids.add(str(t[0]))
                if self.interruption_manager is not None:
                    self.interruption_manager.cancel_turn(session_key, str(t[0]))
                if self.usage is not None:
                    self.usage.settle(t[0])
        for t in preserved_turns:
            try:
                self._turns.put_nowait(t)
            except asyncio.QueueFull:
                break

        while not self._output.empty():
            self._output.get_nowait()
        while self._pending_speech:
            item_id, _epoch, turn_ledger = self._pending_speech.popleft()
            self._interrupted_item_ids.add(str(item_id))
            if self.interruption_manager is not None:
                self.interruption_manager.cancel_turn(session_key, str(item_id))
            if turn_ledger is not None:
                turn_ledger.settle(item_id)
        for _resp_id, (item_id, _resp_epoch, resp_ledger) in list(self._responses.items()):
            self._interrupted_item_ids.add(str(item_id))
            if self.interruption_manager is not None:
                self.interruption_manager.cancel_turn(session_key, str(item_id))
            if resp_ledger is not None:
                resp_ledger.settle(item_id)
        self._responses.clear()
        async with self._send_lock:
            await self.socket.send_json({"event": "clear"})
        self.telemetry["telnyx_clear_sent_count"] += 1
        self._set_phase("INTERRUPTED")
        self.telemetry["voice_response_cancelled"] += 1
        if cancel_response:
            await self.adapter.interrupt()
        if pause_input:
            self.input_paused = True
            await self.adapter.clear_input()

    async def _speak_system(self, item_id: str, answer: str) -> None:
        if self.usage is not None and not self.usage.reserve(item_id):
            raise PermissionError("Voice usage quota unavailable")
        self.pending_epoch = self.epoch
        self._pending_speech.append((item_id, self.epoch, self.usage))
        self.telemetry["tts_generated"] = True
        self.telemetry["tts_request_started"] += 1
        self._set_phase("SYNTHESIZING")
        await self.adapter.speak(self._spoken(answer))

    async def _execute(self, item_id: str, transcript: str, epoch: int) -> None:
        requested_audio = False
        turn_ledger = self.usage
        try:
            if epoch != self.epoch or self.input_paused:
                return
            if self.interruption_manager is not None and self.interruption_manager.is_turn_cancelled(str(item_id)):
                return
            if not transcript or not transcript.strip():
                return
            await self.authorize()
            self.turn_correlation = str(item_id)[:64]
            self._in_flight_transcript = transcript
            self.telemetry["central_ai_called"] = True
            self._executing_turn = True
            self._set_phase("THINKING")

            metric = self._turn_metrics.setdefault(str(item_id), {})
            metric["tool_start_at"] = time.monotonic()

            filler_task = None
            async def _play_thinking_filler() -> None:
                try:
                    await asyncio.sleep(2.8)
                    now_time = asyncio.get_event_loop().time()
                    if (
                        self._executing_turn
                        and epoch == self.epoch
                        and not self.input_paused
                        and (now_time - getattr(self, "_last_filler_time", 0.0)) >= 25.0
                    ):
                        self._last_filler_time = now_time
                        loc = resolve_locale(self.locale)
                        if loc.startswith("ro"):
                            filler_phrase = "Un moment, verific pentru dumneavoastră..."
                        elif loc.startswith("fr"):
                            filler_phrase = "Un instant, je vérifie..."
                        elif loc.startswith("es"):
                            filler_phrase = "Un momento, estoy verificando..."
                        else:
                            filler_phrase = "One moment, checking that for you..."
                        await self._speak_system(f"filler:{item_id}", filler_phrase)
                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.debug("Voice thinking filler prompt ignored: %s", ex)

            filler_task = asyncio.create_task(_play_thinking_filler())
            try:
                result = await asyncio.wait_for(
                    self.execute_turn(item_id, redact_voice_secrets(transcript)),
                    timeout=self.central_ai_timeout
                )
            except asyncio.TimeoutError:
                self.central_ai_timeouts += 1
                self.telemetry["crm_function_failures"] += 1
                logger.warning(
                    "Voice Central AI turn timed out; timeout_seconds=%s count=%s",
                    self.central_ai_timeout, self.central_ai_timeouts,
                )
                loc = resolve_locale(self.locale)
                if loc.startswith("ro"):
                    timeout_answer = (
                        "Ne cerem scuze pentru așteptare. Vă pot ajuta direct cu informații despre produsele noastre, "
                        "programul de lucru sau programări. Ce ați dori să știți?"
                    )
                elif loc.startswith("fr"):
                    timeout_answer = (
                        "Désolé pour cette attente. Je peux vous renseigner directement sur nos produits, "
                        "nos horaires ou la prise de rendez-vous. Que souhaitez-vous savoir ?"
                    )
                else:
                    timeout_answer = (
                        "Sorry for the delay. I can help you directly with our products, "
                        "opening hours, or booking an appointment. What would you like to know?"
                    )
                result = {"status": "success", "answer": timeout_answer}
            except Exception as exc:
                self.telemetry["crm_function_failures"] += 1
                logger.warning(
                    "Voice Central AI execution failed; error=%s",
                    type(exc).__name__,
                )
                loc = resolve_locale(self.locale)
                if loc.startswith("ro"):
                    error_answer = (
                        "Ne cerem scuze, a apărut o problemă tehnică la procesarea solicitării. "
                        "Ați putea reformula întrebarea?"
                    )
                elif loc.startswith("fr"):
                    error_answer = (
                        "Désolé, une erreur technique est survenue lors du traitement de votre demande. "
                        "Pouvez-vous reformuler votre question ?"
                    )
                else:
                    error_answer = (
                        "Sorry, a technical error occurred while processing your request. "
                        "Could you rephrase your question?"
                    )
                result = {"status": "success", "answer": error_answer}
            finally:
                if filler_task is not None and not filler_task.done():
                    filler_task.cancel()
                metric["tool_end_at"] = time.monotonic()
                if metric.get("tool_start_at") is not None:
                    self.orchestrator.record_central_ai_latency(
                        (metric["tool_end_at"] - metric["tool_start_at"]) * 1000.0
                    )
            if epoch != self.epoch:
                self.central_ai_discarded_epochs += 1
                metric["discard_reason"] = f"epoch_superseded_{epoch}_vs_{self.epoch}"
                logger.info(
                    "Voice AI result superseded by caller interruption; call=%s turn=%s count=%s",
                    self.call_correlation,
                    self.turn_correlation,
                    self.central_ai_discarded_epochs,
                )
                return
            if not result.get("auth_required") and not (
                result.get("status") == "success"
                and isinstance(result.get("answer"), str)
                and result["answer"].strip()
            ):
                self.central_ai_missing_answers += 1
                logger.warning(
                    "Voice Central AI returned no usable response; count=%s status=%s",
                    self.central_ai_missing_answers,
                    str(result.get("status") or "missing")[:40],
                )
                result = {"status": "success", "answer": (
                    "Je n'ai pas pu récupérer cette information pour le moment. "
                    "Puis-je vous aider avec une autre question ?"
                    if resolve_locale(self.locale).startswith("fr")
                    else "I couldn't retrieve that information right now. "
                         "Can I help with another question?"
                )}
            if result.get("auth_required"):
                if self.begin_pin is None or self.poll_pin is None:
                    raise PermissionError("Keypad authentication unavailable")
                await self.interrupt(pause_input=False)
                epoch = self.epoch
                self._pin_turn = item_id
                self._pin_started = False
                self._pin_deadline = asyncio.get_running_loop().time() + 120
                self._pin_prompt_spoken = False
                self._pin_prompt_finish_time = None
            elif self.interruption_manager is not None and self.interruption_manager.is_turn_cancelled(str(item_id)):
                return
            elif self.input_paused:
                return
            if result.get("status") == "success" and isinstance(result.get("answer"), str) and result["answer"].strip():
                self.telemetry["central_ai_response_ready"] += 1
                if len(self._pending_speech) >= 8:
                    oldest = self._pending_speech.popleft()
                    if oldest[2] is not None:
                        oldest[2].settle(oldest[0])
                    self.dropped_outbound_frames += 1
                speak_epoch = self.epoch
                self.pending_epoch = speak_epoch
                self._pending_speech.append((item_id, speak_epoch, turn_ledger))
                requested_audio = True
                self.telemetry["tts_generated"] = True
                self.telemetry["tts_request_started"] += 1
                self.telemetry["final_state"] = "RESPONDING"
                self._set_phase("SYNTHESIZING")
                metric["response_ready_at"] = time.monotonic()
                try:
                    await asyncio.wait_for(
                        self.adapter.speak(self._spoken(result["answer"])),
                        timeout=self.tts_timeout
                    )
                    self.central_ai_replies_queued += 1
                    logger.info("Voice conversation reply submitted to TTS; count=%s", self.central_ai_replies_queued)
                    if result.get("auth_required"):
                        self._last_spoken_prompt = self._spoken(result["answer"])
                        self._pin_mark = "pin-prompt:" + hashlib.sha256(item_id.encode()).hexdigest()[:24]
                        self._pin_prompt_safe_duration = max(len(str(result.get("answer") or "")) * 0.075, 4.0)
                        if not getattr(self, "_draining_events", False):
                            try:
                                self._output.put_nowait((self.epoch, {"event": "mark", "mark": {"name": self._pin_mark}}))
                            except asyncio.QueueFull:
                                self.dropped_outbound_frames += 1
                            self._pin_prompt_spoken = True
                            self._pin_prompt_finish_time = asyncio.get_running_loop().time()
                except Exception as exc:
                    self.tts_failures += 1
                    self.telemetry["tts_provider_error"] += 1
                    self._set_phase("RECOVERING")
                    logger.warning("Voice conversation TTS submission failed; error_type=%s", type(exc).__name__)
                    requested_audio = False
                    if self._pending_speech and self._pending_speech[-1][0] == item_id:
                        self._pending_speech.pop()
                    if result.get("auth_required") and not self._pin_started and self.begin_pin is not None:
                        result_pin = await self.begin_pin(item_id)
                        self._pin_started = True
                        if not result_pin.get("success"):
                            await self._finish_pin("refused")
                    else:
                        recovery = (
                            "Je n'arrive pas à lire la réponse pour le moment. Pouvez-vous répéter votre question ?"
                            if resolve_locale(self.locale).startswith("fr")
                            else "I can't play the answer right now. Could you repeat your question?"
                        )
                        try:
                            await asyncio.wait_for(self.adapter.speak(recovery), timeout=self.tts_timeout)
                            self.central_ai_replies_queued += 1
                            requested_audio = True
                        except Exception:
                            logger.warning("Voice recovery TTS also failed")
                            if turn_ledger is not None:
                                turn_ledger.settle(item_id)
                if result.get("hangup"):
                    drained = 0
                    while not self._output.empty() and drained < 40:
                        await asyncio.sleep(0.05)
                        drained += 1
                    await asyncio.sleep(0.15)
                    if self.hangup_call is not None:
                        with suppress(Exception):
                            await self.hangup_call()
                    self._stop_event.set()
        finally:
            self._executing_turn = False
            self._in_flight_transcript = None
            if self.phase == "THINKING":
                self._set_phase("LISTENING")
            if turn_ledger is not None and not requested_audio:
                turn_ledger.settle(item_id)

    async def _execute_turns(self) -> None:
        while True:
            item_id, transcript, epoch = await self._turns.get()
            if epoch != self.epoch:
                logger.info("Voice turn %s skipped (epoch %s != %s)", item_id, epoch, self.epoch)
                continue
            self._current_turn_task = asyncio.create_task(
                self._execute(item_id, transcript, epoch)
            )
            try:
                await self._current_turn_task
            except asyncio.CancelledError:
                logger.info("Voice turn %s task cancelled (stale calculation halted)", item_id)
            finally:
                self._current_turn_task = None
            # A completed wait_for child can race with cancellation during
            # shutdown. Do not re-enter the queue with a pending cancellation.
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise asyncio.CancelledError

    def _enqueue(self, raw: bytes, *, final: bool = False) -> None:
        self._remainder += raw
        while len(self._remainder) >= 160:
            frame = (self.epoch, self._remainder[:160])
            self._remainder = self._remainder[160:]
            try:
                self._output.put_nowait(frame)
            except asyncio.QueueFull:
                try:
                    self._output.get_nowait()
                    self.dropped_outbound_frames += 1
                    self._output.put_nowait(frame)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    self.dropped_outbound_frames += 1
        if final and self._remainder:
            frame = (self.epoch, self._remainder.ljust(160, b"\xff"))
            self._remainder = b""
            try:
                self._output.put_nowait(frame)
            except asyncio.QueueFull:
                try:
                    self._output.get_nowait()
                    self.dropped_outbound_frames += 1
                    self._output.put_nowait(frame)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    self.dropped_outbound_frames += 1

    async def _write_audio(self) -> None:
        loop = asyncio.get_running_loop()
        next_send_time = None
        current_epoch = self.epoch
        while True:
            epoch, raw = await self._output.get()
            if epoch != current_epoch:
                current_epoch = epoch
                next_send_time = None
            async with self._send_lock:
                if epoch == self.epoch:
                    if isinstance(raw, dict):
                        await self.socket.send_json(raw)
                    else:
                        self._set_playback_active(True)
                        await self.socket.send_json({"event": "media", "media": {"payload": base64.b64encode(raw).decode("ascii")}})
                        self.telemetry["outbound_frames"] += 1
                        self.telemetry["outbound_audio_frames_sent"] += 1
                        self.telemetry["outbound_audio_bytes_sent"] += len(raw)
            if isinstance(raw, bytes):
                now = loop.time()
                if next_send_time is None or next_send_time < now - 0.1:
                    # Pre-buffer: brief micro-pause if queue is low to prevent buffer underflows/crackles
                    if self._output.qsize() < 2:
                        await asyncio.sleep(0.04)
                    next_send_time = loop.time() + 0.02
                    await asyncio.sleep(0.02)
                else:
                    next_send_time += 0.02
                    delay = next_send_time - loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)

    async def _drain_provider_events(self) -> None:
        self._draining_events = True
        async for event in self.adapter.events():
            kind = getattr(event, "type", None) or getattr(event, "kind", "")
            if kind == "session.updated":
                logger.info("Realtime session configured successfully (model=%s, stt=%s)", self.realtime_model, self.stt_model)
                self.telemetry["final_state"] = "LISTENING"
            elif kind == "input_audio_buffer.speech_started" and not self.input_paused:
                now_t = time.monotonic()
                self._last_activity = now_t
                self._last_speech_started_at = now_t
                self.orchestrator.last_speech_started_at = now_t
                self.telemetry["speech_started_count"] += 1
                logger.info("Caller speech started (epoch=%s)", self.epoch)
                self.telemetry["speech_detected"] = True
                if self.phase == "LISTENING" and self._pin_turn is None:
                    self.orchestrator.transition(ConversationState.USER_SPEAKING)
                # Phone echo trips VAD as soon as playback starts. Do NOT send Telnyx clear
                # or interrupt audio on raw speech_started during PIN prompt, as acoustic echo
                # would cut off the prompt immediately. Instead, cancellation and verbal
                # barge-in are safely adjudicated on partial/final transcription or rescue.
            elif kind == "input_audio_buffer.speech_stopped" and not self.input_paused:
                self._last_speech_stopped_at = time.monotonic()
                self.telemetry["speech_stopped_count"] += 1
                logger.info("Caller speech stopped (epoch=%s)", self.epoch)
                self.telemetry["final_state"] = "PROCESSING"
            elif kind == "input_audio_buffer.transcription_missing" and not self.input_paused:
                # Explicitly track untranscribed speech segments separately from true silence
                self.telemetry["speech_stopped_without_transcript"] += 1
                item_id = str(getattr(event, "item_id", "") or "")
                duration_ms = int(getattr(event, "duration_ms", 0) or 0)
                logger.warning(
                    "Caller speech segment ended without transcript (item_id=%s, duration_ms=%d, phase=%s)",
                    item_id[:64],
                    duration_ms,
                    self.phase,
                )
                playing = (
                    self.response_id is not None
                    or self.pending_epoch is not None
                    or not self._output.empty()
                    or self.phase in {"PLAYING", "SPEAKING"}
                    or self._playback_active
                )
                if (
                    self._pin_turn is None
                    and playing
                    and self.allow_natural_interruptions
                    and duration_ms >= 450
                ):
                    await self.interrupt(reason="untranscribed_speech_barge_in")
                    self._set_phase("RECOVERING")
                    loc = resolve_locale(self.locale).casefold()
                    if loc.startswith("es"):
                        rec_prompt = "Perdón, le escucho."
                    elif loc.startswith("ro"):
                        rec_prompt = "Pardon, vă ascult."
                    elif loc.startswith("en"):
                        rec_prompt = "Sorry, I'm listening."
                    else:
                        rec_prompt = "Pardon, je vous écoute."
                    with suppress(Exception):
                        await self._speak_system(f"recover-{item_id or uuid4().hex[:8]}", rec_prompt)
            elif kind == "conversation.item.input_audio_transcription.delta" and not self.input_paused:
                self.telemetry["stt_partial_count"] += 1
                item_id = str(getattr(event, "item_id", "") or "")
                partial_text = str(getattr(event, "transcript", None) or getattr(event, "delta", "") or "").strip()
                if item_id and item_id not in self._turn_metrics:
                    self._turn_metrics[item_id] = {
                        "speech_started_at": self._last_speech_started_at,
                        "stt_partial_at": time.monotonic(),
                        "transcript_final_at": None,
                        "interruption_detected_at": None,
                        "telnyx_clear_sent_at": None,
                        "tool_start_at": None,
                        "tool_end_at": None,
                        "response_ready_at": None,
                        "first_pcm_sent_at": None,
                        "playback_acknowledged_at": None,
                        "playback_completed_at": None,
                        "interruption_reason": None,
                        "discard_reason": None,
                    }
                if (
                    self._pin_turn is None
                    and partial_text
                    and self.allow_natural_interruptions
                    and item_id != self._last_barge_in_item_id
                ):
                    playing = (
                        self.response_id is not None
                        or self.pending_epoch is not None
                        or not self._output.empty()
                        or self.phase in {"PLAYING", "SPEAKING"}
                        or self._playback_active
                    )
                    if (
                        playing
                        and not is_playback_echo(partial_text, self._last_spoken)
                        and (
                            is_explicit_interruption(partial_text)
                            or is_correction_or_objection(partial_text)
                            or is_attention_check(partial_text)
                        )
                    ):
                        self._last_barge_in_item_id = item_id
                        if item_id in self._turn_metrics:
                            self._turn_metrics[item_id]["interruption_detected_at"] = time.monotonic()
                        if self.interruption_manager is not None:
                            self.interruption_manager.on_caller_speech_detected(
                                str(self.stream_id or "default"),
                                is_dtmf_pin_entry=False,
                                allow_interruptions=True,
                            )
                        await self.interrupt(reason="partial_transcript_barge_in")
            elif kind == "conversation.item.input_audio_transcription.completed" and not self.input_paused:
                now_t = time.monotonic()
                self._last_activity = now_t
                self._last_transcription_at = now_t
                self.telemetry["stt_final_count"] += 1
                if getattr(event, "rescued", False):
                    self.telemetry["stt_rescue_succeeded"] += 1
                item_id = getattr(event, "item_id", "")
                transcript = getattr(event, "transcript", "")
                logger.info("Caller speech transcribed (item_id=%s, length=%d)", item_id, len(transcript) if isinstance(transcript, str) else 0)
                if not isinstance(item_id, str) or not item_id or len(item_id) > 255 or not isinstance(transcript, str) or len(transcript) > 12000:
                    raise InvalidMediaFrame("Invalid transcription event")
                if item_id in self._seen_items or not transcript.strip():
                    continue
                if len(self._seen_items) >= 1000:
                    raise InvalidMediaFrame("Call turn capacity exceeded")
                # Guard against stale/late transcription arriving for an already-cancelled older turn
                if (
                    item_id in self._interrupted_item_ids
                    and not is_correction_or_objection(transcript)
                    and not is_attention_check(transcript)
                ):
                    self.telemetry["late_transcripts_discarded"] += 1
                    logger.info("Late superseded transcript discarded (item_id=%s)", item_id)
                    continue
                self._seen_items.add(item_id)
                self.telemetry["transcription_received"] = True
                self.telemetry["final_state"] = "PROCESSING"

                if self._pin_turn is not None:
                    last_prompt = getattr(self, "_last_spoken_prompt", None)
                    if last_prompt and is_playback_echo(transcript, last_prompt):
                        logger.info("Acoustic echo detected during PIN challenge ignored (item_id=%s, length=%d)", item_id, len(transcript))
                        continue
                    if is_pin_challenge_cancellation(transcript) or is_session_retention_intent(transcript):
                        logger.info("Caller cancelled PIN challenge verbally (item_id=%s, length=%d)", item_id, len(transcript))
                        playing = (
                            self.response_id is not None
                            or self.pending_epoch is not None
                            or not self._output.empty()
                            or self.phase == "PLAYING"
                            or self._playback_active
                        )
                        if playing:
                            await self.interrupt(reason="pin_challenge_verbal_cancellation")
                        await self._finish_pin("cancelled")
                        continue
                    else:
                        logger.info("Non-cancellation speech during PIN challenge ignored (item_id=%s, length=%d)", item_id, len(transcript))
                        continue
                if str(item_id) not in self._turn_metrics:
                    self._turn_metrics[str(item_id)] = {
                        "speech_started_at": self._last_speech_started_at,
                        "speech_stopped_at": self._last_speech_stopped_at,
                        "stt_partial_at": None,
                        "transcript_final_at": now_t,
                        "interruption_detected_at": None,
                        "telnyx_clear_sent_at": None,
                        "tool_start_at": None,
                        "tool_end_at": None,
                        "response_ready_at": None,
                        "first_pcm_sent_at": None,
                        "playback_acknowledged_at": None,
                        "playback_completed_at": None,
                        "interruption_reason": None,
                        "discard_reason": None,
                    }
                else:
                    self._turn_metrics[str(item_id)]["transcript_final_at"] = now_t
                    self._turn_metrics[str(item_id)]["speech_stopped_at"] = self._last_speech_stopped_at
                if self.usage is not None:
                    if not self.usage.reserve(item_id):
                        raise PermissionError("Voice usage quota unavailable")
                    self.usage.record_transcription(item_id, event, model=self.stt_model)
                secs_since_last = max(0.0, now_t - self.orchestrator.last_user_turn_at)
                effective_phase = "PLAYING" if (self._playback_active or not self._output.empty()) and self.phase == "LISTENING" else self.phase
                decision = adjudicate_transcript(
                    transcript,
                    phase=effective_phase,
                    in_flight_transcript=self._in_flight_transcript,
                    last_spoken=self._last_spoken,
                    allow_barge_in=self.allow_natural_interruptions,
                    seconds_since_last_turn=secs_since_last,
                )
                if decision == "ignore":
                    logger.info(
                        "Voice transcript ignored; call=%s turn=%s phase=%s",
                        self.call_correlation, str(item_id)[:64], effective_phase,
                    )
                    continue
                if decision == "replace":
                    already_interrupted_on_partial = (item_id == self._last_barge_in_item_id)
                    playing = (
                        self.response_id is not None
                        or self.pending_epoch is not None
                        or not self._output.empty()
                        or effective_phase in {"PLAYING", "SPEAKING"}
                        or self._playback_active
                    )
                    if playing and self.allow_natural_interruptions and not already_interrupted_on_partial:
                        if str(item_id) in self._turn_metrics:
                            self._turn_metrics[str(item_id)]["interruption_detected_at"] = now_t
                        if self.interruption_manager is not None:
                            self.interruption_manager.on_caller_speech_detected(
                                str(self.stream_id or "default"),
                                is_dtmf_pin_entry=bool(self.input_paused or self._pin_turn is not None),
                                allow_interruptions=True,
                            )
                        if self._current_turn_task is not None and not self._current_turn_task.done():
                            self._current_turn_task.cancel()
                        await self.interrupt(reason="caller_speech_barge_in")
                    elif self._executing_turn and not already_interrupted_on_partial:
                        if self._current_turn_task is not None and not self._current_turn_task.done():
                            self._current_turn_task.cancel()
                        self.epoch += 1
                        self.orchestrator.epoch = self.epoch
                        logger.info(
                            "Voice in-flight answer superseded by a confirmed question; call=%s epoch=%s",
                            self.call_correlation,
                            self.epoch,
                        )
                self.orchestrator.begin_turn(str(item_id), self.epoch)
                try:
                    self._turns.put_nowait((item_id, transcript, self.epoch))
                except asyncio.QueueFull:
                    raise InvalidMediaFrame("Pending turn capacity exceeded") from None
            elif kind == "response.created":
                self.telemetry["final_state"] = "RESPONDING"
                self.response_id = getattr(getattr(event, "response", None), "id", None)
                if self._pending_speech:
                    item_id, response_epoch, response_ledger = self._pending_speech.popleft()
                    self._responses[self.response_id] = (item_id, response_epoch, response_ledger)
                    self.response_epoch = response_epoch
                    if self.interruption_manager is not None:
                        self.interruption_manager.register_playback(str(self.stream_id or "default"), str(item_id))
                else:
                    self.response_epoch = None
                self.pending_epoch = None
            elif kind == "response.output_audio.delta":
                if self.response_epoch == self.epoch and self.response_id == getattr(event, "response_id", None):
                    delta = getattr(event, "delta", None)
                    try:
                        pcm_length = len(delta) if isinstance(delta, (bytes, bytearray)) else 0
                        if isinstance(delta, str):
                            pcm_length = len(base64.b64decode(delta, validate=False))
                        self.telemetry["tts_audio_bytes_generated"] += pcm_length
                        if self.telemetry["tts_first_audio_chunk_received"] == 0:
                            self.telemetry["tts_first_audio_chunk_received"] = 1
                            baseline_time = (
                                self._last_speech_stopped_at
                                or getattr(self, "_last_transcription_at", None)
                                or self._last_activity
                            )
                            if baseline_time is not None:
                                latency_ms = max(1, int((time.monotonic() - baseline_time) * 1000))
                                self.telemetry["first_audible_response_latency_ms"] = latency_ms
                                self.orchestrator.record_first_audio_latency(float(latency_ms))
                            if self.response_id and self.response_id in self._responses:
                                r_item_id = str(self._responses[self.response_id][0])
                                if r_item_id in self._turn_metrics and self._turn_metrics[r_item_id]["first_pcm_sent_at"] is None:
                                    self._turn_metrics[r_item_id]["first_pcm_sent_at"] = time.monotonic()
                        encoded = self.codec.outbound_pcm(delta)
                        self.telemetry["audio_encoding_completed"] += 1
                        self._set_phase("PLAYING")
                        self._enqueue(encoded)
                    except InvalidMediaFrame:
                        self.telemetry["tts_provider_error"] += 1
                        logger.warning(
                            "Voice TTS chunk rejected; call=%s turn=%s",
                            self.call_correlation, self.turn_correlation,
                        )
            elif kind == "response.interrupted":
                resp_id = getattr(event, "response_id", None)
                logger.info(
                    "Voice provider response interrupted; call=%s resp_id=%s",
                    self.call_correlation,
                    resp_id,
                )
                if resp_id and str(resp_id) in self._cancelled_responses:
                    continue
                if resp_id and resp_id in self._responses:
                    r_item_id = str(self._responses[resp_id][0])
                    if r_item_id in self._turn_metrics:
                        self._turn_metrics[r_item_id]["interruption_reason"] = "provider_response_interrupted"
                is_active = (self.response_id == resp_id and self.response_epoch == self.epoch)
                if not (self.input_paused or self._pin_turn is not None) and is_active:
                    await self.interrupt(originating_response_id=str(resp_id) if resp_id else None, reason="provider_response_interrupted")
            elif kind == "response.done":
                self.telemetry["final_state"] = "LISTENING"
                resp_obj = getattr(event, "response", None)
                resp_status = getattr(resp_obj, "status", None)
                completed_id = getattr(resp_obj, "id", None)
                if completed_id and completed_id in self._responses:
                    r_item_id = str(self._responses[completed_id][0])
                    if r_item_id in self._turn_metrics:
                        self._turn_metrics[r_item_id]["playback_completed_at"] = time.monotonic()
                if resp_status == "cancelled":
                    logger.info("Voice provider response cancelled; call=%s id=%s", self.call_correlation, completed_id)
                    already_cancelled = completed_id and str(completed_id) in self._cancelled_responses
                    completed = self._responses.pop(completed_id, None)
                    if completed is not None and self.interruption_manager is not None:
                        self.interruption_manager.cancel_turn(str(self.stream_id or "default"), str(completed[0]))
                    if completed is not None and completed[2] is not None:
                        completed[2].settle(completed[0])
                    if not (self.input_paused or self._pin_turn is not None) and not already_cancelled:
                        if completed is not None and completed[1] == self.epoch:
                            await self.interrupt(originating_response_id=str(completed_id) if completed_id else None, reason="provider_response_cancelled")
                    if completed_id:
                        self._cancelled_responses.add(str(completed_id))
                    continue
                completed = self._responses.pop(completed_id, None)
                if completed is not None and self.interruption_manager is not None:
                    self.interruption_manager.complete_turn(str(self.stream_id or "default"), str(completed[0]))
                if completed is not None and completed[2] is not None:
                    completed[2].record_realtime_response(completed[0], event, model=self.realtime_model)
                    completed[2].settle(completed[0])
                if self.response_epoch == self.epoch and self.response_id == getattr(getattr(event, "response", None), "id", None):
                    self._enqueue(b"", final=True)
                    self.telemetry["voice_response_completed"] += 1
                    is_pin_turn = completed is not None and (
                        completed[0] == self._pin_turn
                        or str(completed[0]).startswith("pin-reprompt:")
                        or (self._pin_turn is not None and str(completed[0]).endswith(str(self._pin_turn)))
                    )
                    if is_pin_turn and self._pin_turn is not None:
                        mark_item = str(completed[0]) if completed is not None else self._pin_turn
                        self._pin_mark = "pin-prompt:" + hashlib.sha256(mark_item.encode()).hexdigest()[:24]
                        try:
                            self._output.put_nowait((self.epoch, {"event": "mark", "mark": {"name": self._pin_mark}}))
                        except asyncio.QueueFull:
                            self.dropped_outbound_frames += 1
                        self._pin_prompt_spoken = True
                        self._pin_prompt_finish_time = asyncio.get_running_loop().time()
                        self._pin_prompt_safe_duration = getattr(self, "_pin_prompt_safe_duration", 4.0)
                    elif completed_id:
                        play_mark = f"play-{completed_id}"
                        self._active_play_mark = play_mark
                        try:
                            self._output.put_nowait((self.epoch, {"event": "mark", "mark": {"name": play_mark}}))
                        except asyncio.QueueFull:
                            self.dropped_outbound_frames += 1
                    self.response_id = None
                    self.response_epoch = None
                    if self._output.empty():
                        self._set_playback_active(False)
                        self._set_phase("LISTENING")
            elif kind == "error":
                err = getattr(event, "error", None)
                code = getattr(err, "code", "") if err is not None else ""
                message = str(getattr(err, "message", "") or getattr(event, "message", "") or err or event)
                if (
                    code in ("response_cancel_not_active", "conversation_already_has_active_response")
                    or "no active response" in message.lower()
                    or "cancellation failed" in message.lower()
                ):
                    logger.info("Benign audio provider event (ignored): code=%s message=%s", code, message)
                    continue
                self.telemetry["provider_error"] = str(code or "unknown")
                logger.error("Audio provider error event: %s", getattr(event, "error", event))
                raise InvalidMediaFrame("Audio provider unavailable")

    async def _provider_events(self) -> None:
        reconnect_attempts = 0
        max_reconnects = 2
        while not self._stop_event.is_set():
            try:
                self._draining_events = True
                try:
                    await self._drain_provider_events()
                finally:
                    self._draining_events = False
                if not self._stop_event.is_set() and hasattr(self.adapter, "reconnect") and reconnect_attempts < max_reconnects:
                    reconnect_attempts += 1
                    logger.warning(
                        "Audio provider stream ended unexpectedly mid-call; attempting automatic reconnect (%d/%d)...",
                        reconnect_attempts, max_reconnects,
                    )
                    self.telemetry["reconnect_triggered"] = True
                    self.telemetry["reconnect_attempts"] = reconnect_attempts
                    await self.adapter.reconnect(
                        fallback_model=getattr(self.adapter, "fallback_model", "gpt-realtime-2.1"),
                        locale=self.locale,
                    )
                    continue
                break
            except Exception as exc:
                if self._stop_event.is_set() or isinstance(exc, asyncio.CancelledError):
                    break
                if hasattr(self.adapter, "reconnect") and reconnect_attempts < max_reconnects:
                    reconnect_attempts += 1
                    logger.warning(
                        "Audio provider stream error (%s); automatically reconnecting mid-call (%d/%d)...",
                        type(exc).__name__, reconnect_attempts, max_reconnects,
                    )
                    self.telemetry["reconnect_triggered"] = True
                    self.telemetry["reconnect_attempts"] = reconnect_attempts
                    try:
                        await self.adapter.reconnect(
                            fallback_model=getattr(self.adapter, "fallback_model", "gpt-realtime-2.1"),
                            locale=self.locale,
                        )
                        continue
                    except Exception as rec_err:
                        logger.error("Automatic mid-call reconnect failed: %s", rec_err)
                raise

    async def _send_inbound_audio(self, pcm: bytes) -> None:
        if self.input_paused:
            return
        try:
            await asyncio.wait_for(self.adapter.send_audio(pcm), timeout=self.inbound_audio_timeout)
            self.telemetry["stt_audio_sent"] = True
        except asyncio.TimeoutError:
            self.dropped_inbound_frames += 1

    async def _read_audio(self) -> None:
        while True:
            event = await self.socket.receive_json()
            event_stream_id = event.get("stream_id") or (event.get("media", {}).get("stream_id") if isinstance(event.get("media"), dict) else None)
            if not isinstance(event, dict) or (event_stream_id and event_stream_id != self.stream_id):
                raise InvalidMediaFrame("Media stream mismatch")
            kind = event.get("event")
            if kind == "stop":
                if not self.input_paused:
                    for pcm in self.reorder_buffer.flush():
                        await self._send_inbound_audio(pcm)
                return
            if kind == "dtmf":
                dtmf_digit = str(event.get("digit") or (event.get("dtmf", {}) if isinstance(event.get("dtmf"), dict) else {}).get("digit") or "")
                if dtmf_digit == "*" and self._pin_turn is not None:
                    logger.info("Caller cancelled PIN challenge via DTMF '*' in media stream")
                    await self._finish_pin("cancelled")
                    continue
                await self.interrupt(pause_input=False)
                continue
            if kind == "mark":
                marker = event.get("mark")
                marker_name = str(marker.get("name") or "") if isinstance(marker, dict) else ""
                if isinstance(marker, dict) and (
                    marker_name.startswith("play-")
                    or marker_name.startswith("pin-prompt:")
                ):
                    self.telemetry["outbound_playback_acknowledged"] += 1
                    if marker_name.startswith("play-") and (
                        self._active_play_mark is None or marker_name == self._active_play_mark
                    ):
                        self._active_play_mark = None
                        if self._output.empty() and self.response_id is None:
                            self._set_playback_active(False)
                            if self.phase in {"PLAYING", "SPEAKING", "RECOVERING"}:
                                self._set_phase("LISTENING")
                if self._pin_mark and isinstance(marker, dict) and marker_name == self._pin_mark and not self._pin_started:
                    if self.begin_pin is not None and self._pin_turn is not None:
                        result = await self.begin_pin(self._pin_turn)
                        self._pin_started = True
                        self._pin_deadline = asyncio.get_running_loop().time() + 130
                        if not result.get("success"):
                            await self._finish_pin("refused")
                continue
            if kind in {"connected", "start"}:
                continue
            if kind != "media" or not isinstance(event.get("media"), dict):
                raise InvalidMediaFrame("Invalid media event")
            media = event["media"]
            track = media.get("track")
            if track is not None and track not in ("inbound", "inbound_track"):
                continue
            chunk_raw = media.get("chunk") if media.get("chunk") is not None else event.get("sequence_number")
            chunk = str(chunk_raw if chunk_raw is not None else "")
            if not chunk.isascii() or not chunk.isdigit() or len(chunk) > 10:
                raise InvalidMediaFrame("Invalid media chunk")
            number = int(chunk)
            self._last_chunk = max(self._last_chunk, number)
            if not self.input_paused:
                self.telemetry["inbound_frames"] += 1
                self.telemetry["inbound_audio_ms"] += 20
                pcm_frames = self.reorder_buffer.push(number, self.codec.inbound_pcm(media.get("payload")))
                for pcm in pcm_frames:
                    await self._send_inbound_audio(pcm)

    async def _finish_pin(self, status: str) -> None:
        item_id = self._pin_turn or "pin-result"
        self._pin_turn = None
        self._pin_mark = None
        self._pin_started = False
        self._pin_deadline = None
        self._pin_prompt_spoken = False
        self._pin_prompt_finish_time = None
        self._pin_retry_count = 0
        playing = (
            self.response_id is not None
            or self.pending_epoch is not None
            or not self._output.empty()
            or self.phase == "PLAYING"
        )
        if playing:
            await self.interrupt(reason=f"pin_{status}")
        await self.adapter.clear_input()
        if status == "authenticated":
            await self.authorize()
            pending_query = None
            if self.consume_pending_query is not None:
                pending_query = await self.consume_pending_query()

            if pending_query:
                await self._speak_system(
                    "pin-result:" + hashlib.sha256(str(item_id).encode()).hexdigest()[:24],
                    "Authentification réussie. " if resolve_locale(self.locale).startswith("fr") else "Authentication successful. ",
                )
                await asyncio.sleep(0.3)
                result = await self.execute_turn(f"pending-exec:{item_id}", pending_query)
                if result.get("status") == "success" and isinstance(result.get("answer"), str) and result["answer"].strip():
                    await self._speak_system(
                        f"pending-answer:{item_id}",
                        clean_voice_text(redact_voice_secrets(result["answer"])),
                    )
            else:
                await self._speak_system(
                    "pin-result:" + hashlib.sha256(str(item_id).encode()).hexdigest()[:24],
                    voice_auth_message(self.locale, 1),
                )
        elif status == "cancelled":
            if self.cancel_pin is not None:
                await self.cancel_pin()
            loc = resolve_locale(self.locale).casefold()
            if loc.startswith("fr"):
                cancel_msg = "Saisie du NIP annulée. Vous êtes en mode accueil public. Que puis-je faire pour vous ?"
            elif loc.startswith("es"):
                cancel_msg = "Entrada de PIN cancelada. Está en modo de recepción pública. ¿En qué puedo ayudarle?"
            elif loc.startswith("ro"):
                cancel_msg = "Introducerea codului PIN a fost anulată. Sunteți în modul de primire public. Cu ce vă pot ajuta?"
            else:
                cancel_msg = "PIN entry cancelled. You are in public reception mode. How can I help you?"
            await self._speak_system(
                "pin-result:" + hashlib.sha256(str(item_id).encode()).hexdigest()[:24],
                cancel_msg,
            )
        else:
            if self.cancel_pin is not None:
                await self.cancel_pin()
            loc = resolve_locale(self.locale).casefold()
            if loc.startswith("fr"):
                refused_msg = "Nombre maximal de tentatives atteint. La saisie du NIP est abandonnée. Vous êtes en mode accueil public. Que souhaitez-vous savoir ?"
            elif loc.startswith("es"):
                refused_msg = "Número máximo de intentos alcanzado. Se cancela la entrada de PIN. Está en modo de recepción pública. ¿Qué desea consultar?"
            elif loc.startswith("ro"):
                refused_msg = "Numărul maxim de încercări a fost atins. Introducerea codului PIN este abandonată. Sunteți în modul public. Cu ce vă pot ajuta?"
            else:
                refused_msg = "Maximum attempts reached. PIN entry cancelled. You are in public reception mode. How can I help you?"
            await self._speak_system(
                "pin-result:" + hashlib.sha256(str(item_id).encode()).hexdigest()[:24],
                refused_msg,
            )
        await asyncio.sleep(0.2)
        await self.adapter.clear_input()
        self.input_paused = False

    async def _reprompt_pin(self) -> None:
        if getattr(self, "_pin_reprompting", False):
            return
        self._pin_retry_count += 1
        if self._pin_retry_count > self.max_pin_retries:
            logger.warning(
                "pin_gather_max_retries_exceeded count=%s max=%s",
                self._pin_retry_count,
                self.max_pin_retries,
            )
            await self._finish_pin("refused")
            return
        self._pin_reprompting = True
        try:
            self._pin_started = False
            self._pin_mark = None
            if self.reset_pin_retry is not None:
                await self.reset_pin_retry()
            loc = resolve_locale(self.locale).casefold()
            if loc.startswith("fr"):
                reprompt = "Aucun chiffre n'a été reçu. Veuillez saisir votre code NIP sur le clavier de votre téléphone, ou appuyez sur étoile pour annuler et revenir à l'accueil."
            elif loc.startswith("es"):
                reprompt = "No se recibió ningún dígito. Ingrese su PIN en el teclado de su teléfono, o presione asterisco para cancelar y volver a la recepción."
            elif loc.startswith("ro"):
                reprompt = "Niciun număr nu a fost primit. Vă rugăm să introduceți PIN-ul sau apăsați stea pentru a anula și a reveni la recepție."
            else:
                reprompt = "No digits were received. Please enter your PIN on your phone keypad, or press star to cancel and return to reception."
            new_pin_turn = f"{self._pin_turn or 'pin'}-retry-{self._pin_retry_count}"
            self._pin_turn = new_pin_turn
            item_id = f"pin-reprompt:{new_pin_turn}"
            self._last_spoken_prompt = reprompt
            await self._speak_system(item_id, reprompt)
            self._pin_mark = "pin-prompt:" + hashlib.sha256(item_id.encode()).hexdigest()[:24]
            self._pin_prompt_safe_duration = max(len(reprompt) * 0.075, 4.0)
            if not getattr(self, "_draining_events", False):
                try:
                    self._output.put_nowait((self.epoch, {"event": "mark", "mark": {"name": self._pin_mark}}))
                except asyncio.QueueFull:
                    self.dropped_outbound_frames += 1
                self._pin_prompt_spoken = True
                self._pin_prompt_finish_time = asyncio.get_running_loop().time()
        finally:
            self._pin_reprompting = False

    async def _monitor_pin(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            if self._pin_turn is None:
                continue
            if self._pin_deadline is not None and asyncio.get_running_loop().time() >= self._pin_deadline:
                await self._finish_pin("refused")
                continue
            if not self._pin_started and self.begin_pin is not None and getattr(self, "_pin_prompt_spoken", False):
                finish_time = getattr(self, "_pin_prompt_finish_time", None)
                safe_duration = getattr(self, "_pin_prompt_safe_duration", 4.0)
                if self._output.empty() and finish_time is not None and (asyncio.get_running_loop().time() - finish_time >= safe_duration):
                    result = await self.begin_pin(self._pin_turn)
                    self._pin_started = True
                    if not result.get("success"):
                        await self._finish_pin("refused")
            if self._pin_started and self.poll_pin is not None:
                status = await self.poll_pin()
                if status in {"authenticated", "refused", "cancelled"}:
                    await self._finish_pin(status)
                elif status == "retry_needed":
                    await self._reprompt_pin()

    async def _periodic_auth(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            await self.authorize()
            if self.idle_seconds is not None and time.monotonic() - self._last_activity >= self.idle_seconds:
                self.telemetry["final_state"] = "IDLE_LIMIT"
                await self.request_stop("idle_limit")
                return

    async def run(self) -> None:
        if self.max_session_seconds is None:
            await self._run()
            return
        deadline = asyncio.timeout(self.max_session_seconds)
        try:
            async with deadline:
                await self._run()
        except asyncio.TimeoutError:
            if not deadline.expired():
                raise
            self.telemetry["final_state"] = "DURATION_LIMIT"
            logger.info("Voice media duration limit reached; limit_seconds=%s", self.max_session_seconds)
            await self.request_stop("duration_limit")

    async def request_stop(self, reason: str = "manual") -> None:
        if reason not in {"manual", "duration_limit", "idle_limit"}:
            raise ValueError("Unsupported stop reason")
        self._stop_event.set()
        if self._authorized_session and not self._termination_requested:
            self._termination_requested = True
            logger.info("Authorized Voice media stop requested; reason=%s", reason)
            if self.hangup_call is not None:
                await asyncio.wait_for(self.hangup_call(), timeout=5)

    async def _run(self) -> None:
        try:
            event = await asyncio.wait_for(self.socket.receive_json(), timeout=5)
            if isinstance(event, dict) and event.get("event") == "connected":
                event = await asyncio.wait_for(self.socket.receive_json(), timeout=5)
            if not isinstance(event, dict) or event.get("event") != "start" or not isinstance(event.get("start"), dict):
                raise InvalidMediaFrame("Media start required")
            self.stream_id = event.get("stream_id") or event["start"].get("stream_id")
            self.call_correlation = str(self.stream_id)[:64] if isinstance(self.stream_id, str) else None
            if not isinstance(self.stream_id, str) or not self.stream_id or len(self.stream_id) > 255:
                raise InvalidMediaFrame("Invalid stream identity")
            media_fmt = event["start"].get("media_format") if isinstance(event["start"].get("media_format"), dict) else {}
            raw_enc = str(media_fmt.get("encoding", "")).upper()
            enc = raw_enc.replace("AUDIO/", "").replace("X-", "")
            rate = int(media_fmt.get("sample_rate", 0))
            channels = int(media_fmt.get("channels", 1))
            if enc not in {"PCMU", "MULAW"} or rate not in {8000, 16000} or channels != 1:
                logger.warning("Unsupported media format: raw_enc=%s enc=%s rate=%s channels=%s", raw_enc, enc, rate, channels)
                raise InvalidMediaFrame("Unsupported media format")
            if "client_state" in event and "client_state" not in event["start"]:
                event["start"]["client_state"] = event["client_state"]
            await self.validate_start(event["start"])
            self.telemetry["media_connected"] = True
            await self.authorize()
            self._authorized_session = True
            await self.adapter.open(locale=self.locale)
            self.telemetry["connection_establishment_duration_ms"] = int((time.monotonic() - self._call_start_time) * 1000)
            self.telemetry["active_provider"] = getattr(self.adapter, "provider_id", "unknown")
            self.telemetry["active_model"] = getattr(self.adapter, "model_name", self.realtime_model or "unknown")
            if hasattr(self.adapter, "fallback_occurred"):
                self.telemetry["fallback_occurred"] = getattr(self.adapter, "fallback_occurred", False)
                self.telemetry["fallback_reason"] = getattr(self.adapter, "fallback_reason", None)
            if self.initial_answer:
                self.telemetry["final_state"] = "GREETING"
                try:
                    await self._speak_system("inbound-greeting", self.initial_answer)
                except Exception as exc:
                    self.tts_failures += 1
                    self.telemetry["provider_error"] = type(exc).__name__
                    if self._pending_speech and self._pending_speech[-1][0] == "inbound-greeting":
                        item_id, _epoch, turn_ledger = self._pending_speech.pop()
                        if turn_ledger is not None:
                            turn_ledger.settle(item_id)
                    logger.warning(
                        "Inbound greeting synthesis failed; keeping the answered media session open"
                    )
            reader = asyncio.create_task(self._read_audio())
            self._background = [
                reader,
                asyncio.create_task(self._provider_events()),
                asyncio.create_task(self._write_audio()),
                asyncio.create_task(self._execute_turns()),
                asyncio.create_task(self._periodic_auth()),
                asyncio.create_task(self._stop_event.wait()),
            ]
            if self.poll_pin is not None:
                self._background.append(asyncio.create_task(self._monitor_pin()))
            done, _pending = await asyncio.wait(self._background, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            if hasattr(self.adapter, "fallback_occurred"):
                self.telemetry["fallback_occurred"] = getattr(self.adapter, "fallback_occurred", False)
                self.telemetry["fallback_reason"] = getattr(self.adapter, "fallback_reason", None)
                self.telemetry["fallback_duration_ms"] = getattr(self.adapter, "fallback_duration_ms", None)
                self.telemetry["active_provider"] = getattr(self.adapter, "provider_id", "unknown")
                self.telemetry["active_model"] = getattr(self.adapter, "model_name", self.realtime_model or "unknown")
            logger.info(
                "Call %s session telemetry: call_answered=%s media_connected=%s inbound_frames=%d inbound_audio_ms=%d speech_detected=%s stt_audio_sent=%s transcription_received=%s central_ai_called=%s tts_generated=%s outbound_frames=%d final_state=%s provider_error=%s voice_turns_queued=%d voice_turn_timeouts=%d voice_missing_answers=%d voice_stale_results=%d active_provider=%s active_model=%s connect_ms=%d first_audio_latency_ms=%d fallback=%s fallback_reason=%s crm_failures=%d vad_interruptions=%d",
                self.stream_id,
                self.telemetry.get("call_answered"),
                self.telemetry.get("media_connected"),
                self.telemetry.get("inbound_frames"),
                self.telemetry.get("inbound_audio_ms"),
                self.telemetry.get("speech_detected"),
                self.telemetry.get("stt_audio_sent"),
                self.telemetry.get("transcription_received"),
                self.telemetry.get("central_ai_called"),
                self.telemetry.get("tts_generated"),
                self.telemetry.get("outbound_frames"),
                self.telemetry.get("final_state"),
                self.telemetry.get("provider_error"),
                self.central_ai_replies_queued,
                self.central_ai_timeouts,
                self.central_ai_missing_answers,
                self.central_ai_discarded_epochs,
                self.telemetry.get("active_provider"),
                self.telemetry.get("active_model"),
                self.telemetry.get("connection_establishment_duration_ms"),
                self.telemetry.get("first_audible_response_latency_ms"),
                self.telemetry.get("fallback_occurred"),
                self.telemetry.get("fallback_reason"),
                self.telemetry.get("crm_function_failures"),
                self.telemetry.get("vad_interruptions_count"),
            )
            logger.info(
                "Call %s audio pipeline: phase=%s central_ai_response_ready=%d tts_request_started=%d tts_first_audio_chunk_received=%d tts_audio_bytes_generated=%d audio_encoding_completed=%d outbound_audio_frames_sent=%d outbound_audio_bytes_sent=%d outbound_playback_acknowledged=%d tts_provider_error=%d voice_response_cancelled=%d voice_response_completed=%d speech_started=%d speech_stopped=%d stt_partial=%d stt_final=%d speech_without_transcript=%d stt_rescue_ok=%d barge_in=%d telnyx_clear=%d late_discarded=%d",
                self.call_correlation,
                self.phase,
                self.telemetry.get("central_ai_response_ready"),
                self.telemetry.get("tts_request_started"),
                self.telemetry.get("tts_first_audio_chunk_received"),
                self.telemetry.get("tts_audio_bytes_generated"),
                self.telemetry.get("audio_encoding_completed"),
                self.telemetry.get("outbound_audio_frames_sent"),
                self.telemetry.get("outbound_audio_bytes_sent"),
                self.telemetry.get("outbound_playback_acknowledged"),
                self.telemetry.get("tts_provider_error"),
                self.telemetry.get("voice_response_cancelled"),
                self.telemetry.get("voice_response_completed"),
                self.telemetry.get("speech_started_count", 0),
                self.telemetry.get("speech_stopped_count", 0),
                self.telemetry.get("stt_partial_count", 0),
                self.telemetry.get("stt_final_count", 0),
                self.telemetry.get("speech_stopped_without_transcript", 0),
                self.telemetry.get("stt_rescue_succeeded", 0),
                self.telemetry.get("barge_in_triggered_count", 0),
                self.telemetry.get("telnyx_clear_sent_count", 0),
                self.telemetry.get("late_transcripts_discarded", 0),
            )
            for task in self._background:
                task.cancel()
            await asyncio.gather(*self._background, return_exceptions=True)
            self._clear_all_buffers()
            with suppress(Exception):
                if self.max_session_seconds is None:
                    await self.adapter.close()
                else:
                    await asyncio.wait_for(self.adapter.close(), timeout=5)
            for ledger in self._ledger_history:
                ledger.settle_pending()

    def use_ledger(self, ledger) -> None:
        self.usage = ledger
        if not any(existing is ledger for existing in self._ledger_history):
            self._ledger_history.append(ledger)


class BoundedMediaSocket:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def receive_json(self):
        raw = await self.websocket.receive_text()
        if len(raw) > 65536:
            raise InvalidMediaFrame("Media message too large")
        try:
            return json.loads(raw)
        except ValueError:
            raise InvalidMediaFrame("Invalid media JSON") from None

    async def send_json(self, event):
        try:
            await self.websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass


async def complete_media_hangup(db: Session, settings: Settings, call_id: UUID):
    """Hang up Telnyx media without overwriting terminal booking/transfer statuses."""
    c_call, _cfg, _comp = media_transport_context(
        db, settings, call_id,
        allow_statuses=_HANGUP_MEDIA_STATUSES,
        require_active=False,
    )
    if c_call.telnyx_call_control_id:
        if getattr(settings, "voice_long_calls_enabled", False):
            # Command acceptance is not proof that the phone call ended. Keep the
            # concurrency reservation until a signed Telnyx hangup confirms it.
            await asyncio.wait_for(TelnyxClient(settings).hangup(c_call.telnyx_call_control_id), timeout=5)
            c_call.source_context = {**(c_call.source_context or {}), "stop_requested_at": datetime.now(timezone.utc).isoformat()}
            db.commit()
            return c_call
        from backend.app.voice.sandbox_deadline import is_sandbox_test_call
        if is_sandbox_test_call(c_call, settings):
            await asyncio.wait_for(TelnyxClient(settings).hangup(c_call.telnyx_call_control_id), timeout=5)
        else:
            with suppress(Exception):
                await TelnyxClient(settings).hangup(c_call.telnyx_call_control_id)
    if c_call.status not in {
        "completed", "appointment_booked", "appointment_cancelled",
        "transferred", "blocked_credits", "blocked_announcement",
    }:
        c_call.status = "completed"
    if c_call.ended_at is None:
        c_call.ended_at = datetime.now(timezone.utc)
    db.commit()
    return c_call


def media_audio_available(settings: Settings, locale: str, config: VoiceBusinessConfig | None = None) -> bool:
    if resolve_locale(locale) not in {resolve_locale(item) for item in settings.voice_realtime_supported_locales}:
        return False
    gemini_ok = bool(
        settings.google_ai_api_key
        and (
            config is None
            or bool(getattr(config, "gemini_live_enabled", True))
            or getattr(config, "realtime_provider", "gemini_live") == "gemini_live"
        )
    )
    openai_ok = bool(
        settings.openai_api_key
        and settings.voice_realtime_model
        and settings.voice_stt_model
        and settings.voice_tts_voice
        and settings.voice_tts_model
    )
    return gemini_ok or openai_ok


def resolve_media_socket_context(db: Session, settings: Settings, call_id: UUID) -> tuple:
    """Resolve media scope from server-owned IVR state, not the global public-media flag.

    Telnyx IVR staff calls issue a private media ticket after successful PIN
    verification. With TELNYX_MEDIA_INBOUND_ENABLED=True, always selecting
    public_mode=True instead expects the literal "public" auth epoch and
    rejects the valid staff ticket as a scope mismatch (WebSocket 4403).
    """
    if not settings.telnyx_media_inbound_enabled:
        call, config, company, _user, _permissions, _auth = media_call_context(db, settings, call_id)
        return False, call, config, company

    call, config, company = media_transport_context(db, settings, call_id)
    if (call.source_context or {}).get("ivr_stage") == "staff_authenticated":
        # Caller type, PIN verification, membership, permissions and session
        # expiry must all be revalidated before a private audio stream.
        call, config, company, _user, _permissions, _auth = media_call_context(db, settings, call_id)
        return False, call, config, company
    return True, call, config, company


def media_session_opening_line(
    *,
    public_mode: bool,
    public_greeting: str | None,
    locale: str,
    confirm_authentication: bool,
) -> str | None:
    """Customer calls keep their greeting. Only a verified staff IVR hears the success line."""
    if public_mode:
        return public_greeting
    if confirm_authentication:
        return voice_auth_message(locale, 1)
    return None


def authorize_media_session(
    db: Session,
    settings: Settings,
    call_id: Any,
    plan: str,
    *,
    public_mode: bool = False,
    principal_id: UUID | str | None = None,
    auth_epoch: str | None = None,
    ledger: Optional[VoiceUsageLedger] = None,
    bridge: Optional[Any] = None,
    claim: Optional[Any] = None,
    locale: str = "fr-CA",
    usage_service: Optional[Any] = None,
    on_settlement: Optional[Any] = None,
) -> Tuple[bool, UUID | str | None, str | None, Optional[VoiceUsageLedger]]:
    """Authorize a media stream session, supporting staff continuity, handover revocation, and public fallback."""
    current_call, current_config, current_company = media_transport_context(
        db, settings, call_id, allow_statuses=_SESSION_MEDIA_STATUSES,
    )
    from backend.app.voice.call_policy import check
    check(db, settings, current_call)
    if ModuleEntitlementService(db).get_company_plan(TenantContext(current_company.id)).code.value != plan:
        raise PermissionError("Billing plan changed during media session")
    try:
        _call, _config, _company, current_user, _permissions, current_auth = media_call_context(
            db, settings, call_id, allow_statuses=_SESSION_MEDIA_STATUSES,
        )
    except PermissionError:
        ctx = current_call.source_context or {}
        is_handover_pending = bool(ctx.get("handover_revoked"))
        is_public_fallback = bool(
            ctx.get("public_fallback")
            or ctx.get("handover_cancelled")
            or ctx.get("pin_gather_status") in {"cancelled", "refused"}
        )
        if is_handover_pending or is_public_fallback:
            if is_public_fallback:
                public_mode = True
            if principal_id is not None:
                principal_id = None
                auth_epoch = None
            if ledger is not None:
                ledger.attach_identity(None, None)
            if bridge is not None and hasattr(bridge.adapter, "update_staff_identity"):
                bridge.adapter.update_staff_identity(False, None, None)
        if principal_id is not None or (not public_mode and not is_handover_pending and not is_public_fallback):
            raise
        return public_mode, principal_id, auth_epoch, ledger

    current_epoch = utc(current_auth.authenticated_at).isoformat()
    if principal_id is not None:
        if str(current_user.id) != str(principal_id) or current_epoch != auth_epoch:
            raise PermissionError("Caller authentication changed")
        return public_mode, principal_id, auth_epoch, ledger
    if claim is None:
        return public_mode, principal_id, auth_epoch, ledger
    if current_call.central_conversation_id is None:
        conversation = ConversationService(db).create(
            current_company.id, current_user.id, f"Voice call {current_call.id}", current_call.locale or locale
        )
        current_call.central_conversation_id = conversation.id
        db.commit()
    else:
        ConversationService(db).get(current_company.id, current_user.id, current_call.central_conversation_id)
    principal_id = current_user.id
    auth_epoch = current_epoch
    if ledger is None and usage_service is not None:
        ledger = VoiceUsageLedger(
            usage_service,
            voice_pricing_catalog(settings.ai_model_rate_card),
            company_id=current_company.id,
            user_id=current_user.id,
            conversation_id=current_call.central_conversation_id,
            plan_code=plan,
            request_namespace=call_id,
            on_settlement=on_settlement,
        )
        if bridge is not None:
            bridge.use_ledger(ledger)
    elif ledger is not None:
        ledger.attach_identity(current_user.id, current_call.central_conversation_id)
    if bridge is not None and hasattr(bridge.adapter, "update_staff_identity"):
        user_role = str(getattr(current_user, "role", "Employee"))
        bridge.adapter.update_staff_identity(True, current_user.first_name, user_role)

    return public_mode, principal_id, auth_epoch, ledger


async def telnyx_media_socket(
    websocket: WebSocket, call_id: UUID, db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings), service=Depends(get_central_ai_service),
    prediction_service=Depends(get_prediction_service),
) -> None:
    try:
        public_mode, call, config, company = resolve_media_socket_context(db, settings, call_id)
        call_lang_session = company_call_language_session(db, config, call)
        locale = resolve_locale(call_lang_session.active_locale)
        if not media_audio_available(settings, locale, config) or service.usage_service is None:
            raise PermissionError("Validated audio configuration required")
        plan = ModuleEntitlementService(db).get_company_plan(TenantContext(company.id)).code.value
        service.usage_service.ensure_quota_available(company.id, plan)
    except Exception as exc:
        # Starlette TestClient (and some ASGI servers) block forever if the
        # socket is closed in CONNECTING without accept(). Reject after accept.
        logger.warning(
            "Telnyx media websocket pre-accept rejected (4403) for call_id=%s: %s",
            call_id,
            exc,
            exc_info=True,
        )
        with suppress(Exception):
            await websocket.accept()
        with suppress(Exception):
            await websocket.close(code=4403)
        return

    ledger = None
    claim = None
    principal_id: UUID | str | None = None
    auth_epoch: str | None = None
    public_conversation = PublicInboundConversation(db, settings, call_id)
    from backend.app.voice.audio_preferences import phone_audio_config
    from backend.app.voice.realtime_provider import VoiceRealtimeRouter
    tenant_audio = phone_audio_config(db, settings, config)
    realtime_router = VoiceRealtimeRouter(settings)
    adapter = realtime_router.build_realtime_adapter(
        config,
        tenant_audio,
        fallback_factory=lambda model=None: build_phone_adapter(
            settings,
            lambda: OpenAIRealtimeAudioAdapter(tenant_audio, model or settings.voice_realtime_model),
        ),
    )
    bridge: TelnyxMediaBridge

    async def authorize() -> None:
        nonlocal ledger, principal_id, auth_epoch, public_mode
        public_mode, principal_id, auth_epoch, ledger = authorize_media_session(
            db,
            settings,
            call_id,
            plan,
            public_mode=public_mode,
            principal_id=principal_id,
            auth_epoch=auth_epoch,
            ledger=ledger,
            bridge=bridge,
            claim=claim,
            locale=locale,
            usage_service=service.usage_service,
            on_settlement=record_call_cost,
        )

    async def validate_start(start: dict) -> None:
        nonlocal ledger, claim
        claim = claim_media_start(db, settings, call_id, start, public_mode=public_mode)
        if public_mode:
            current_call, _config, current_company = media_transport_context(db, settings, call_id)
            current_call.source_context = {**(current_call.source_context or {}), "public_conversation_id": str(current_call.id)}
            if current_call.central_conversation_id is None:
                owner_m = db.scalar(
                    select(CompanyMembership).where(
                        CompanyMembership.company_id == current_company.id,
                        CompanyMembership.role == UserRole.OWNER,
                        CompanyMembership.is_active.is_(True),
                    )
                )
                fallback_u = db.scalar(
                    select(User).where(
                        User.company_id == current_company.id,
                        User.is_active.is_(True),
                    )
                )
                conv_uid = owner_m.user_id if owner_m else (fallback_u.id if fallback_u else None)
                if conv_uid is not None:
                    conv = ConversationService(db).create(
                        current_company.id,
                        conv_uid,
                        f"Voice call {current_call.id}",
                        current_call.locale or locale,
                    )
                    current_call.central_conversation_id = conv.id
                    if public_conversation is not None:
                        greeting_text = public_conversation.greeting()
                        ConversationService(db).add_message(
                            current_company.id,
                            conv.id,
                            AIMessageRole.ASSISTANT,
                            greeting_text,
                            provider="openai",
                            model=settings.voice_realtime_model,
                        )
            db.commit()
            ledger = VoiceUsageLedger(service.usage_service, voice_pricing_catalog(settings.ai_model_rate_card),
                company_id=current_company.id, user_id=None, conversation_id=current_call.central_conversation_id, plan_code=plan, request_namespace=current_call.id,
                on_settlement=record_call_cost)
            bridge.use_ledger(ledger)
        await authorize()

    async def execute_turn(item_id: str, transcript: str) -> dict:
        nonlocal ledger, principal_id, auth_epoch, public_mode
        current_call: VoiceCall | None = db.get(VoiceCall, call_id)
        # Synchronize employee identity if session authenticated via PIN
        if principal_id is None:
            if current_call is not None and current_call.authenticated_user_id is not None:
                valid_auth = VoiceCallerAuth(db, settings).valid_session(current_call)
                if valid_auth is not None and valid_auth.caller_type in {"OWNER", "EMPLOYEE"}:
                    principal_id = valid_auth.principal_id
                    auth_epoch = utc(valid_auth.authenticated_at).isoformat()
                    if bridge is not None and hasattr(bridge.adapter, "update_staff_identity"):
                        u_obj = db.get(User, principal_id)
                        if u_obj is not None:
                            bridge.adapter.update_staff_identity(True, u_obj.first_name, str(getattr(u_obj, "role", "Employee")))

        if public_conversation is not None and principal_id is None:
            security_check = public_conversation.security_gate(transcript)
            if security_check is not None:
                return security_check

        if principal_id is not None:
            norm_trans = unicodedata.normalize("NFKD", transcript.casefold())
            norm_trans = "".join(c for c in norm_trans if not unicodedata.combining(c))
            if is_session_retention_intent(norm_trans):
                call_loc = resolve_locale(current_call.locale if current_call and current_call.locale else locale)
                if call_loc.startswith("fr"):
                    retention_msg = "Très bien, votre session reste active. Comment puis-je vous aider ?"
                elif call_loc.startswith("es"):
                    retention_msg = "Entendido, su sesión permanece activa. ¿En qué puedo ayudarle?"
                elif call_loc.startswith("ro"):
                    retention_msg = "Am înțeles, sesiunea dumneavoastră rămâne activă. Cu ce vă pot ajuta?"
                else:
                    retention_msg = "Understood, your session remains active. How can I help you?"
                return {"status": "success", "answer": retention_msg, "authenticated": True}

            if is_handover_positive_intent(norm_trans):
                logger.info(
                    "AUDIT_VOICE_HANDOVER_REVOCATION: call=%s previous_user_id=%s timestamp=%s",
                    call_id, principal_id, datetime.now(timezone.utc).isoformat(),
                )
                current_call = db.get(VoiceCall, call_id)
                if current_call is not None:
                    current_call.authenticated_user_id = None
                    current_call.caller_type = "UNKNOWN"
                    current_call.central_conversation_id = None
                    current_call.verification_attempts = 0
                    current_call.pin_challenge_hash = None
                    current_call.pin_challenge_expires_at = None
                    existing_ctx = dict(current_call.source_context or {})
                    existing_ctx.pop("previous_principal", None)
                    existing_ctx.pop("user_id", None)
                    existing_ctx.pop("user_name", None)
                    existing_ctx["authenticated"] = False
                    existing_ctx["handover_revoked"] = True
                    existing_ctx["handover_count"] = existing_ctx.get("handover_count", 0) + 1
                    existing_ctx["last_handover_at"] = datetime.now(timezone.utc).isoformat()
                    current_call.source_context = existing_ctx
                    db.commit()
                principal_id = None
                auth_epoch = None
                if bridge is not None:
                    bridge._pin_turn = item_id
                    bridge._pin_started = False
                    bridge._pin_deadline = asyncio.get_running_loop().time() + 120
                    if hasattr(bridge.adapter, "update_staff_identity"):
                        bridge.adapter.update_staff_identity(False, None, None)
                if ledger is not None:
                    ledger.attach_identity(None, None)
                call_loc = resolve_locale(current_call.locale if current_call and current_call.locale else locale)
                if call_loc.startswith("fr"):
                    handover_answer = "Session précédente clôturée. Pour des raisons de sécurité, le nouveau collaborateur doit s'authentifier. Veuillez saisir votre NIP sur le clavier de votre téléphone."
                elif call_loc.startswith("es"):
                    handover_answer = "Sesión anterior cerrada. Por motivos de seguridad, el nuevo colaborador debe autenticarse. Por favor, ingrese su PIN en el teclado de su teléfono."
                elif call_loc.startswith("ro"):
                    handover_answer = "Sesiunea anterioară a fost închisă. Din motive de securitate, noul colaborator trebuie să se autentifice. Vă rugăm să introduceți codul PIN pe tastatura telefonului."
                else:
                    handover_answer = "Previous session closed. For security reasons, the new employee must authenticate. Please enter your PIN on your phone keypad."
                return {"status": "success", "answer": handover_answer, "auth_required": True}

            current_call, current_config, current_company, current_user, permissions, _auth = media_call_context(
                db, settings, call_id, allow_statuses=_SESSION_MEDIA_STATUSES,
            )
        else:
            current_call, current_config, current_company = media_transport_context(
                db, settings, call_id, allow_statuses=_SESSION_MEDIA_STATUSES,
            )
            is_handover_pending = bool((current_call.source_context or {}).get("handover_revoked"))
            if is_handover_pending:
                norm_trans = "".join(c for c in unicodedata.normalize("NFKD", transcript.casefold()) if not unicodedata.combining(c))
                if is_pin_challenge_cancellation(norm_trans) or is_session_retention_intent(norm_trans):
                    logger.info("Handover pending cancelled by caller: call=%s length=%d", call_id, len(transcript))
                    if bridge is not None:
                        bridge._pin_turn = None
                        bridge._pin_started = False
                        bridge._pin_deadline = None
                        bridge._pin_retry_count = 0
                        bridge.input_paused = False
                    existing_ctx = dict(current_call.source_context or {})
                    existing_ctx.pop("handover_revoked", None)
                    existing_ctx["handover_cancelled"] = True
                    existing_ctx["public_fallback"] = True
                    existing_ctx["pin_gather_status"] = "cancelled"
                    current_call.pin_challenge_hash = None
                    current_call.pin_challenge_expires_at = None
                    current_call.source_context = existing_ctx
                    db.commit()
                    public_mode = True
                    call_loc = resolve_locale(current_call.locale if current_call and current_call.locale else locale)
                    if call_loc.startswith("fr"):
                        cancel_msg = "Demande de transfert annulée. Vous êtes en mode accueil public. Que puis-je faire pour vous ?"
                    elif call_loc.startswith("es"):
                        cancel_msg = "Solicitud de transferencia cancelada. Está en modo de recepción pública. ¿En qué puedo ayudarle?"
                    elif call_loc.startswith("ro"):
                        cancel_msg = "Cererea de transfer a fost anulată. Sunteți în modul public. Cu ce vă pot ajuta?"
                    else:
                        cancel_msg = "Transfer request cancelled. You are in public reception mode. How can I help you?"
                    return {"status": "success", "answer": cancel_msg, "public": True}

                if public_conversation is not None:
                    sec = public_conversation.security_gate(transcript)
                    if sec is None:
                        existing_ctx = dict(current_call.source_context or {})
                        existing_ctx.pop("handover_revoked", None)
                        existing_ctx["handover_cancelled"] = True
                        existing_ctx["public_fallback"] = True
                        existing_ctx["pin_gather_status"] = "cancelled"
                        current_call.pin_challenge_hash = None
                        current_call.pin_challenge_expires_at = None
                        current_call.source_context = existing_ctx
                        db.commit()
                        public_mode = True
                        if bridge is not None:
                            bridge._pin_turn = None
                            bridge._pin_started = False
                            bridge._pin_deadline = None
                            bridge._pin_retry_count = 0
                            bridge.input_paused = False
                        return public_conversation.public_answer(transcript)

                if bridge is not None:
                    bridge._pin_turn = item_id
                    bridge._pin_started = False
                    bridge._pin_deadline = asyncio.get_running_loop().time() + 120
                call_loc = resolve_locale(current_call.locale if current_call and current_call.locale else locale)
                if call_loc.startswith("fr"):
                    handover_answer = "Veuillez saisir votre code NIP sur le clavier de votre téléphone pour vous identifier, ou dites annuler pour revenir à l'accueil."
                elif call_loc.startswith("es"):
                    handover_answer = "Por favor, ingrese su código PIN en el teclado de su teléfono para identificarse, o diga cancelar para volver a la recepción."
                elif call_loc.startswith("ro"):
                    handover_answer = "Vă rugăm să introduceți codul PIN pe tastatura telefonului pentru a vă autentifica, sau spuneți anulare."
                else:
                    handover_answer = "Please enter your PIN on your phone keypad to authenticate, or say cancel to return to reception."
                return {"status": "success", "answer": handover_answer, "auth_required": True}
            owner_membership = db.scalar(
                select(CompanyMembership)
                .where(
                    CompanyMembership.company_id == current_company.id,
                    CompanyMembership.is_active.is_(True),
                    CompanyMembership.role.in_([UserRole.OWNER, UserRole.ADMIN]),
                )
                .order_by(CompanyMembership.created_at.asc())
            )
            if owner_membership is None:
                owner_membership = db.scalar(
                    select(CompanyMembership)
                    .where(CompanyMembership.company_id == current_company.id, CompanyMembership.is_active.is_(True))
                )
            if owner_membership is None:
                # Fallback: look for active User directly associated with current_company
                fallback_user = db.scalar(
                    select(User)
                    .where(
                        User.company_id == current_company.id,
                        User.is_active.is_(True),
                        User.role.in_([UserRole.OWNER, UserRole.ADMIN]),
                    )
                    .order_by(User.created_at.asc())
                )
                if fallback_user is None:
                    fallback_user = db.scalar(
                        select(User)
                        .where(User.company_id == current_company.id, User.is_active.is_(True))
                        .order_by(User.created_at.asc())
                    )
                if fallback_user is not None:
                    current_user = fallback_user
                else:
                    return {"status": "error", "answer": "Désolé, le service est momentanément indisponible."}
            else:
                current_user = db.get(User, owner_membership.user_id)
                if current_user is None:
                    return {"status": "error", "answer": "Désolé, le service est momentanément indisponible."}
            # Public booking tools still require a live CRM Voice grant.
            permissions = PUBLIC_VOICE_CALLER_PERMISSIONS

        if current_call.central_conversation_id is None:
            conv = ConversationService(db).create(
                current_company.id,
                current_user.id,
                f"Voice call {current_call.id}",
                current_call.locale or locale,
            )
            conv_id = conv.id
            db.execute(
                update(VoiceCall)
                .where(VoiceCall.id == current_call.id)
                .values(central_conversation_id=conv_id)
            )
            db.commit()
            db.refresh(current_call)
            if public_conversation is not None:
                greeting_text = public_conversation.greeting()
                ConversationService(db).add_message(
                    current_company.id,
                    conv_id,
                    AIMessageRole.ASSISTANT,
                    greeting_text,
                    provider="openai",
                    model=settings.voice_realtime_model,
                )

        # Verrouillage linguistique dynamique et anti-dérive par appel
        active_locale = call_lang_session.process_utterance(transcript)
        current_call.locale = active_locale
        bridge.locale = active_locale
        tenant = TenantContext(current_company.id, current_user.id)

        # Contextual telephony disambiguation for 8kHz acoustic confusion (assurances vs accessoires)
        from backend.app.voice.direct_answers import disambiguate_telephony_catalog_query
        active_tenant_mods = set(ModuleEntitlementService(db).get_active_modules(tenant))
        has_acc = False
        try:
            prof = CompanyIntelligenceService(db).get_profile(current_company.id)
            has_acc = any(
                "accessoire" in (str(p.get("category") or p.get("product_category") or "")).lower()
                or "accessory" in (str(p.get("category") or p.get("product_category") or "")).lower()
                or "accessories" in (str(p.get("category") or p.get("product_category") or "")).lower()
                for p in (prof.public_products or [])
                if isinstance(p, dict)
            )
        except Exception:
            pass

        transcript = disambiguate_telephony_catalog_query(
            transcript,
            active_modules=active_tenant_mods,
            company_industry=getattr(current_company, "industry", None),
            company_services=getattr(config, "services", None),
            has_catalog_accessories=has_acc,
        )

        current_call.source_context = {
            **resolve_voice_source_context(db, tenant),
            **(current_call.source_context or {}),
            "call_language_session": call_lang_session.as_dict(),
        }
        db.commit()

        if ledger is None:
            ledger = VoiceUsageLedger(
                service.usage_service,
                voice_pricing_catalog(settings.ai_model_rate_card),
                company_id=current_company.id,
                user_id=current_user.id,
                conversation_id=current_call.central_conversation_id,
                plan_code=plan,
                request_namespace=current_call.id,
                on_settlement=record_call_cost,
            )
            bridge.use_ledger(ledger)
        else:
            ledger.attach_identity(current_user.id, current_call.central_conversation_id)

        def is_hangup_request(text: str) -> bool:
            normalized = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
            patterns = [
                r"\b(au revoir|bonne journee|bonne soiree|a bientot|a la prochaine)\b",
                r"\b(vous pouvez raccrocher|termine l'appel|tu peux raccrocher|raccroche|raccrochez)\b",
                r"\b(c'est tout|ce sera tout)\b",
                r"\b(goodbye|bye bye|bye-bye|\bbye\b|have a great day|have a good day|have a nice day)\b",
                r"\b(you can hang up|hang up now|end the call|hang up the call)\b",
                r"\b(that's all|that is all|that'll be all|that will be all|that's it|that is it)\b",
                r"\b(la revedere|o zi buna|o zi frumoasa|pa pa|\bpa\b|puteti inchide|inchide apelul|inchideti|asta e tot|atat|nu mai am intrebari)\b",
                r"\b(adios|hasta luego|chao|puedes colgar)\b",
                r"\b(auf wiedersehen|tschuss)\b",
                r"\b(arrivederci|puoi riagganciare)\b",
            ]
            return any(re.search(p, normalized) for p in patterns)

        from backend.app.voice.direct_answers import (
            resolve_direct_voice_answer,
            is_language_inquiry,
            is_language_authorized_for_company,
        )
        lang_target = is_language_inquiry(transcript)
        if lang_target and is_language_authorized_for_company(db, current_company.id, lang_target):
            target_locale_map = {"es": "es-ES", "en": "en-US", "fr": "fr-CA", "ro": "ro-RO"}
            target_loc = target_locale_map.get(lang_target)
            if target_loc:
                current_call.locale = target_loc
                bridge.locale = target_loc
                call_lang_session.active_locale = target_loc
                call_lang_session.last_confirmed_locale = target_loc
                call_lang_session.explicit_switch_requested = True
                call_lang_session.language_lock_state = "LOCKED"
                current_call.source_context = {
                    **(current_call.source_context or {}),
                    "call_language_session": call_lang_session.as_dict(),
                }
                db.commit()

        # Contextual objection / correction / attention-check handling:
        # Stop repeating unwanted catalog/answers; either execute embedded reformulation
        # directly or return a crisp, natural clarification while preserving conversation memory.
        call_locale = current_call.locale or locale
        if is_attention_check(transcript) and not is_correction_or_objection(transcript):
            attn_answer = build_correction_clarification(call_locale, is_attention=True)
            if current_call.central_conversation_id is not None:
                ConversationService(db).add_message(
                    current_company.id,
                    current_call.central_conversation_id,
                    AIMessageRole.USER,
                    transcript,
                )
                ConversationService(db).add_message(
                    current_company.id,
                    current_call.central_conversation_id,
                    AIMessageRole.ASSISTANT,
                    attn_answer,
                    provider="central_ai",
                    model=settings.voice_realtime_model,
                )
            return {"status": "success", "answer": attn_answer}

        if is_correction_or_objection(transcript):
            reformulated = extract_reformulation_after_correction(transcript)
            if reformulated:
                transcript = reformulated
            else:
                ctx_obj = dict(current_call.source_context or {})
                last_topic = ctx_obj.get("last_voice_topic")
                ctx_obj.pop("pending_retail_clarification", None)
                current_call.source_context = ctx_obj
                db.commit()
                clarification = build_correction_clarification(call_locale, last_topic=last_topic)
                if current_call.central_conversation_id is not None:
                    ConversationService(db).add_message(
                        current_company.id,
                        current_call.central_conversation_id,
                        AIMessageRole.USER,
                        transcript,
                    )
                    ConversationService(db).add_message(
                        current_company.id,
                        current_call.central_conversation_id,
                        AIMessageRole.ASSISTANT,
                        clarification,
                        provider="central_ai",
                        model=settings.voice_realtime_model,
                    )
                return {"status": "success", "answer": clarification}

        direct_answer = resolve_direct_voice_answer(
            db,
            company_id=current_company.id,
            transcript=transcript,
            authenticated_staff=principal_id is not None,
            staff_role=str(getattr(current_user, "role", "") or "") if principal_id is not None else None,
            locale=current_call.locale or locale,
            user_id=current_user.id if principal_id is not None else None,
            call=current_call,
        )
        if direct_answer:
            db.commit()
            if current_call.central_conversation_id is not None:
                ConversationService(db).add_message(
                    current_company.id,
                    current_call.central_conversation_id,
                    AIMessageRole.USER,
                    transcript,
                )
                ConversationService(db).add_message(
                    current_company.id,
                    current_call.central_conversation_id,
                    AIMessageRole.ASSISTANT,
                    direct_answer,
                    provider="central_ai",
                    model=settings.voice_realtime_model,
                )
            if principal_id is None:
                pin_triggers = (
                    "code nip", "code pin", "votre nip", "votre pin",
                    "su nip", "su pin", "codul pin",
                    "authentifies par nip", "authentifiés par nip",
                    "authenticated with a pin", "autenticados con nip", "autentificati prin pin",
                    "veuillez saisir votre code nip", "please enter your pin",
                    "por favor ingrese su", "va rugam sa introduceti",
                )
                direct_lower = direct_answer.casefold()
                if any(trig in direct_lower for trig in pin_triggers):
                    current_call.source_context = {
                        **(current_call.source_context or {}),
                        "pending_auth_query": transcript,
                    }
                    db.commit()
                    return {"status": "success", "answer": direct_answer, "auth_required": True}
            return {"status": "success", "answer": direct_answer}

        if is_hangup_request(transcript):
            call_loc = resolve_locale(current_call.locale or locale)
            has_unconfirmed = bool(
                (current_call.source_context or {}).get("public_appointment_request")
                and not (current_call.source_context or {}).get("appointment_confirmed")
            )
            farewell = getattr(current_config, "farewell_message", None)
            if not farewell:
                if call_loc.startswith("es"):
                    if has_unconfirmed:
                        farewell = "Tenga en cuenta que su solicitud de cita no ha sido confirmada y no se ha creado ninguna reserva. ¡Muchas gracias por llamar! ¡Adiós y que tenga un buen día!"
                    else:
                        farewell = "¡Muchas gracias por llamar! ¡Adiós y que tenga un buen día!"
                elif call_loc.startswith("ro"):
                    if has_unconfirmed:
                        farewell = "Vă rugăm să rețineți că cererea de programare nu a fost confirmată și nu a fost creată nicio programare. Vă mulțumim pentru apel. La revedere și o zi frumoasă!"
                    else:
                        farewell = "Vă mulțumim pentru apel. La revedere și o zi frumoasă!"
                elif call_loc.startswith("fr"):
                    if has_unconfirmed:
                        farewell = (
                            "Veuillez noter que votre demande de réservation n'a pas été confirmée et aucun rendez-vous n'a été créé. Au revoir et bonne journée !"
                        )
                    else:
                        farewell = (
                            "Merci de votre appel. Au revoir et bonne journée !"
                        )
                else:
                    if has_unconfirmed:
                        farewell = (
                            "Please note that your booking request was not confirmed and no appointment was created. Goodbye and have a great day!"
                        )
                    else:
                        farewell = (
                            "Thank you for calling. Goodbye and have a great day!"
                        )
            return {"status": "success", "answer": farewell, "hangup": True}

        attempts = []
        try:
            result = await service.execute(
                tenant,
                current_user.id,
                current_call.central_conversation_id,
                transcript,
                permissions=permissions,
                capabilities=resolve_tenant_capabilities(db, tenant, prediction_service),
                request_id=ledger.request_id_for(item_id),
                user_language=current_call.locale,
                company_country=current_company.country or "",
                company_currency=current_company.currency_code,
                company_timezone=current_company.timezone or current_config.timezone_name,
                page_context="/voice",
                locale_explicit=False,
                spoken_language_input=True,
                allow_existing_reservation=True,
                attempt_sink=attempts,
            )
            ledger.attribute(item_id, result.selected_agent, result.selected_agent)
            hangup_detected = is_hangup_request(transcript)
            return {"status": result.status, "answer": result.answer, "hangup": hangup_detected}
        except Exception as exc:
            if principal_id is None and public_conversation is not None:
                logger.exception("Central AI execute error for public voice call, falling back: %s", exc)
                fallback_res = public_conversation.public_answer(transcript)
                if current_call.central_conversation_id is not None and isinstance(fallback_res, dict) and fallback_res.get("answer"):
                    conv_service = ConversationService(db)
                    recent_msgs = conv_service.messages(
                        current_company.id,
                        current_call.central_conversation_id,
                        limit=3,
                    )
                    user_already_persisted = any(
                        m.role == AIMessageRole.USER and (m.content or "").strip() == transcript.strip()
                        for m in recent_msgs
                    )
                    if not user_already_persisted:
                        conv_service.add_message(
                            current_company.id,
                            current_call.central_conversation_id,
                            AIMessageRole.USER,
                            transcript,
                        )
                    conv_service.add_message(
                        current_company.id,
                        current_call.central_conversation_id,
                        AIMessageRole.ASSISTANT,
                        str(fallback_res["answer"]),
                        provider="central_ai",
                        model=settings.voice_realtime_model,
                    )
                return fallback_res
            raise
        finally:
            ledger.add_attempts(item_id, attempts)

    async def begin_pin(item_id: str) -> dict:
        if public_conversation is None:
            return {"success": False, "error": "public_mode_disabled"}
        return await public_conversation.begin_pin(item_id)

    async def poll_pin() -> str:
        if public_conversation is None:
            return "refused"
        return public_conversation.pin_state()

    async def reset_pin_retry() -> None:
        if public_conversation is not None:
            public_conversation.reset_pin_retry()

    async def cancel_pin() -> None:
        if public_conversation is not None:
            public_conversation.cancel_pin()

    async def consume_pending_query() -> str | None:
        if public_conversation is None:
            return None
        return public_conversation.consume_pending_auth_query()

    async def hangup_call() -> None:
        await complete_media_hangup(db, settings, call_id)

    def record_call_cost(request_id, attempts):
        if settings.voice_long_calls_enabled:
            from backend.app.voice.call_policy import record_ai_cost
            current = db.get(VoiceCall, call_id)
            record_ai_cost(db, current, request_id, attempts)

    # Ensure started_at is persisted so duration bounds and metering are measured accurately
    if call.started_at is None:
        call.started_at = call.created_at or datetime.now(timezone.utc)
        with suppress(Exception):
            db.commit()

    from backend.app.voice.sandbox_deadline import is_sandbox_test_call, remaining_seconds
    sandbox_duration = None
    if is_sandbox_test_call(call, settings):
        rem = remaining_seconds(call.started_at)
        sandbox_duration = max(1.0, rem) if rem > 0 else 90.0
    from backend.app.services.voice_commercial_controls import managed_order, remaining
    if settings.voice_commercial_enabled and managed_order(db, call):
        comm_rem = remaining(call, settings)
        if comm_rem is not None and comm_rem > 0:
            limit = max(1.0, comm_rem)
            sandbox_duration = min(sandbox_duration, limit) if sandbox_duration is not None else limit
    idle_seconds = None
    if settings.voice_long_calls_enabled:
        from backend.app.voice.call_policy import remaining as policy_remaining, policy_for
        from backend.app.voice.realtime_rotation import RotatingRealtimeAdapter
        policy = policy_for(db, config, settings)
        pol_rem = policy_remaining(call)
        if pol_rem is not None:
            limit = max(1.0, pol_rem)
            sandbox_duration = min(sandbox_duration, limit) if sandbox_duration is not None else limit
        elif policy.max_call_seconds is not None:
            sandbox_duration = min(sandbox_duration, float(policy.max_call_seconds)) if sandbox_duration is not None else float(policy.max_call_seconds)
        idle_seconds = policy.idle_seconds
        adapter = RotatingRealtimeAdapter(
            lambda: realtime_router.build_realtime_adapter(
                config,
                tenant_audio,
                fallback_factory=lambda model=None: build_phone_adapter(
                    settings,
                    lambda: OpenAIRealtimeAudioAdapter(tenant_audio, model or settings.voice_realtime_model),
                ),
            ),
            authorize,
            rotation_seconds=settings.voice_realtime_rotation_seconds,
        )

    # For production-like Sandbox calls (and live calls without a lower synthetic/policy limit),
    # ensure an appropriate bounded session duration based on plan / commercial limits (default 3600s).
    if sandbox_duration is None:
        from backend.app.services.plan_limits_service import PlanLimitsService
        limits = PlanLimitsService(db).limits_for(call.company_id) if call.company_id else None
        plan_code = limits.plan_code if limits else "base"
        bounded_limit = settings.voice_plan_max_call_seconds.get(plan_code, 3600) or settings.voice_commercial_max_call_seconds or 3600
        sandbox_duration = float(bounded_limit)

    use_gemini_live = bool(
        (bool(getattr(config, "gemini_live_enabled", False)) or getattr(config, "realtime_provider", "") == "gemini_live")
        and settings.google_ai_api_key
    )
    active_realtime_model = settings.gemini_live_model if use_gemini_live else settings.voice_realtime_model
    bridge = TelnyxMediaBridge(BoundedMediaSocket(websocket), adapter, locale=locale,
        validate_start=validate_start, authorize=authorize, execute_turn=execute_turn,
        stt_model=settings.voice_stt_model, realtime_model=active_realtime_model,
        initial_answer=media_session_opening_line(
            public_mode=public_mode,
            public_greeting=public_conversation.greeting() if public_conversation is not None else None,
            locale=locale,
            confirm_authentication=(call.source_context or {}).get("ivr_stage") == "staff_authenticated",
        ),
        begin_pin=begin_pin, poll_pin=poll_pin,
        reset_pin_retry=reset_pin_retry,
        cancel_pin=cancel_pin,
        consume_pending_query=consume_pending_query,
        hangup_call=hangup_call,
        max_session_seconds=sandbox_duration,
        idle_seconds=idle_seconds,
        max_output_queue=2000,
        allow_natural_interruptions=bool(getattr(config, "allow_natural_interruptions", True)),
        interruption_manager=realtime_router.interruptions,
        prepare_speech=lambda text, _config=config: apply_spoken_pronunciation(text, _config),
    )
    await websocket.accept()
    try:
        await bridge.run()
        with suppress(Exception):
            await websocket.close(code=1000)
    except WebSocketDisconnect:
        pass
    except PermissionError as exc:
        logger.warning("Telnyx media websocket rejected (4403) for call_id=%s: %s", call_id, exc)
        with suppress(Exception):
            await websocket.close(code=4403)
    except (InvalidMediaFrame, asyncio.TimeoutError) as exc:
        logger.warning("Telnyx media websocket frame/timeout error (4400) for call_id=%s: %s", call_id, exc)
        with suppress(Exception):
            await websocket.close(code=4400)
    except Exception as exc:
        logger.error("Telnyx media websocket unexpected error (1011) for call_id=%s: %s", call_id, exc, exc_info=True)
        with suppress(Exception):
            await websocket.close(code=1011)
    finally:
        db.rollback()
        # Only the socket that claimed the signed media ticket owns the call lifecycle;
        # an unauthenticated socket for a known call_id must not end someone else's call.
        if claim is not None:
            with suppress(Exception):
                release_media_session(db, call_id, claim)
            try:
                current_call = db.get(VoiceCall, call_id)
                if current_call is not None and current_call.ended_at is None and current_call.status in {"answering", "routed", "in_progress"}:
                    if settings.voice_long_calls_enabled or is_sandbox_test_call(current_call, settings):
                        await complete_media_hangup(db, settings, call_id)
                    else:
                        current_call.ended_at = datetime.now(timezone.utc)
                        current_call.status = "completed"
                        db.commit()
            except Exception:
                db.rollback()
                if settings.environment == "sandbox":
                    logger.error("Sandbox media cleanup could not confirm provider hangup; call_id=%s", call_id)
