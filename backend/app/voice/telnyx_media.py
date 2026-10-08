"""Disabled-by-default Telnyx media transport for the existing Voice audio engine."""

from __future__ import annotations

import array
import audioop
import asyncio
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
from typing import Any, Awaitable, Callable, cast
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
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.adapters import OpenAIAudioConfig, OpenAIRealtimeAudioAdapter
from backend.app.voice.auth import VoiceCallerAuth, utc, normalized_phone
from backend.app.voice.usage import VoiceUsageLedger, voice_pricing_catalog
from backend.app.voice.service import resolve_voice_source_context
from backend.app.voice.messages import voice_auth_message, voice_greeting
from backend.app.voice.providers import TelnyxClient
from shared.ai_engine.contracts import TenantContext

from backend.app.voice.auth import redact_voice_secrets
from backend.app.voice.caller_scope import PUBLIC_VOICE_CALLER_PERMISSIONS
from backend.app.voice.language_resolver import CallLanguageSession


class InvalidMediaFrame(ValueError):
    pass


def media_transport_context(db: Session, settings: Settings, call_id: UUID):
    if not settings.telnyx_media_enabled:
        raise PermissionError("Telnyx media transport disabled")
    db.expire_all()
    call = db.get(VoiceCall, call_id)
    if call is None or call.ended_at is not None or call.status not in {"answering", "routed", "in_progress"} or not call.telnyx_call_control_id:
        raise PermissionError("Active tenant call required")
    config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.id == call.config_id, VoiceBusinessConfig.company_id == call.company_id))
    number = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.company_id == call.company_id,
        VoicePhoneNumber.config_id == call.config_id, VoicePhoneNumber.status == "ACTIVE", VoicePhoneNumber.provider == "telnyx"))
    account = db.scalar(select(BillingAccount).where(BillingAccount.company_id == call.company_id))
    company = db.get(Company, call.company_id)
    if config is None or company is None or number is None or number.phone_number != config.telnyx_phone_number or "voice" not in (number.capabilities or []):
        raise PermissionError("Tenant number binding unavailable")
    if not settings.telnyx_voice_connection_id or number.provider_connection_id != settings.telnyx_voice_connection_id:
        raise PermissionError("Verified Voice connection required")
    if account is None or account.status.strip().lower() not in {"active", "trialing"} or not ModuleEntitlementService(db).can_use_module(TenantContext(call.company_id), "voice"):
        raise PermissionError("Voice entitlement unavailable")
    return call, config, company


def media_call_context(db: Session, settings: Settings, call_id: UUID):
    call, config, company = media_transport_context(db, settings, call_id)
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
    if (claims["type"] != "telnyx_media" or claims["call_id"] != str(call.id) or claims["tenant_id"] != str(call.company_id)
        or claims["config_id"] != str(config.id) or claims["auth_epoch"] != auth_epoch
        or start.get("call_control_id") != call.telnyx_call_control_id
        or (normalized_phone(start.get("to")) != normalized_phone(config.telnyx_phone_number) and start.get("to") != config.telnyx_phone_number)):
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


def clean_voice_text(text: str) -> str:
    """Nettoie le texte destiné à la synthèse vocale téléphonique (TTS).
    Supprime la syntaxe markdown (listes à puces, numérotation, astérisques, dièses, crochets),
    pour garantir une lecture orale fluide et naturelle sans artefacts robotiques.
    """
    if not text:
        return ""
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"^\s*\d+[\.\)]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[\-\*•]\s*", "", cleaned, flags=re.MULTILINE)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    cleaned = " ".join(lines)
    return re.sub(r"\s+", " ", cleaned).strip()


class PublicInboundConversation:
    def __init__(self, db: Session, settings: Settings, call_id: UUID, telnyx=None):
        self.db = db
        self.settings = settings
        self.call_id = call_id
        self.telnyx = telnyx or TelnyxClient(settings)

    def context(self):
        if not self.settings.telnyx_media_inbound_enabled:
            raise PermissionError("Public inbound media disabled")
        return media_transport_context(self.db, self.settings, self.call_id)

    def greeting(self) -> str:
        _call, config, _company = self.context()
        if resolve_locale(config.preferred_language).startswith("fr"):
            return f"Bonjour, vous êtes bien chez {config.business_name}. Comment puis-je vous aider ?"
        return f"Hello, you've reached {config.business_name}. How can I help you?"

    def portal_message(self) -> str:
        _call, config, _company = self.context()
        if resolve_locale(config.preferred_language).startswith("fr"):
            return "Créez ou modifiez votre NIP Voice depuis votre espace Avenqo authentifié, dans Voice AI, Sécurité. Ne dites jamais votre NIP à voix haute."
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
        french = resolve_locale(call.locale or config.preferred_language).startswith("fr")

        # 1. PIN creation/configuration/management instructions
        if re.search(r"(creer|configur|changer|modifier|reinitialis|oubli|create|change|set|reset).{0,30}\b(nip|pin)\b", normalized):
            return {"status": "success", "answer": self.portal_message(), "public": True}

        # 2. Inquiries specifically about PIN authentication / secure authentication
        pin_inquiry = re.search(
            r"\b(authentifi|authentification|identifier|connexion|login)\b.{0,30}\b(nip|pin|securis)\b"
            r"|\b(nip|pin)\b.{0,30}\b(securis|authentifi)\b"
            r"|\b(entrer|composer|saisir|fournir|taper)\b.{0,20}\b(nip|pin)\b"
            r"|\b(code nip|code pin)\b",
            normalized,
        )

        # 3. Requests for confidential business, financial or inventory data
        private_data = re.search(
            r"\b(commande|commandes|order|orders)\b.{0,25}\b(recu|recues|aujourd'hui|jour|du jour|recent|recentes|total|nombre|recents|derniere|dernieres|today)\b"
            r"|\b(combien de commandes|combien de ventes|combien de transactions|combien d'argent)\b"
            r"|\b(chiffre d'affaires|ventes du jour|ventes d'aujourd'hui|ventes aujourd'hui|produits vendus|commandes internes|mes clients|autres clients|internal|internes)\b"
            r"|\b(proprietaire|owner|employe|employee|patron|manager|metriques|metrics|revenus|revenue|credits|abonnement|subscription|retail|comptabilite|accounting|dashboard|factures|invoices|ventes|sales)\b"
            r"|\b(niveau de stock|etat des stocks|stock restant)\b",
            normalized,
        )

        if pin_inquiry or private_data:
            has_pin = self.has_configured_pin(call)
            if has_pin:
                # Save the pending query for automatic execution post-authentication
                call.source_context = {**(call.source_context or {}), "pending_auth_query": safe}
                self.db.commit()

                if pin_inquiry:
                    prompt = (
                        "Oui, l'accès sécurisé s'effectue par NIP à l'aide des touches de votre téléphone. "
                        "Veuillez saisir votre code NIP sur le clavier de votre téléphone, suivi du carré. "
                        "Ne prononcez jamais votre NIP à voix haute."
                        if french
                        else "Yes, secure authentication is available using your phone keypad. "
                        "Please enter your PIN on your phone keypad, followed by pound. "
                        "Never say your PIN aloud."
                    )
                else:
                    prompt = (
                        "Pour accéder aux données de votre entreprise, veuillez saisir votre NIP "
                        "à l'aide des touches de votre téléphone. Ne prononcez jamais votre NIP à voix haute."
                        if french
                        else "To access your business data, please enter your PIN using your phone keypad. "
                        "Never say your PIN aloud."
                    )
                return {"status": "success", "answer": prompt, "auth_required": True, "public": True}
            else:
                if pin_inquiry:
                    answer = (
                        "L'authentification par NIP est disponible, mais aucun NIP n'est configuré pour ce numéro. "
                        + self.portal_message()
                        if french
                        else "PIN authentication is available, but no PIN is configured for this number. "
                        + self.portal_message()
                    )
                else:
                    answer = (
                        "L'accès aux données de votre entreprise nécessite la configuration d'un NIP. "
                        + self.portal_message()
                        if french
                        else "Accessing company data requires configuring a PIN. "
                        + self.portal_message()
                    )
                return {"status": "success", "answer": answer, "public": True}

        if re.search(r"mes rendez.vous|my appointments|mon dossier client|my record", normalized):
            answer = "Une vérification de votre identité client est nécessaire pour accéder à vos données personnelles ou modifier un rendez-vous." if french else "Customer identity verification is required to access personal information or change an appointment."
            return {"status": "success", "answer": answer, "customer_verification_required": True, "public": True}
        return None

    def public_answer(self, transcript: str) -> dict:
        call, config, _company = self.context()
        safe = redact_voice_secrets(transcript)
        normalized = "".join(character for character in unicodedata.normalize("NFKD", safe.casefold()) if not unicodedata.combining(character))
        french = resolve_locale(call.locale or config.preferred_language).startswith("fr")
        if re.search(r"(creer|configur|changer|create|change|set).{0,30}\b(nip|pin)\b", normalized):
            return {"status": "success", "answer": self.portal_message(), "public": True}
        private = re.search(r"\b(proprietaire|owner|employe|employee|patron|manager|metriques|metrics|revenus|revenue|credits|abonnement|subscription|retail|comptabilite|accounting|dashboard|factures|invoices|ventes|sales)\b|chiffre d'affaires|produits vendus|commandes internes|mes clients|autres clients|internal|internes", normalized)
        if private:
            prompt = voice_auth_message(call.locale or config.preferred_language, 0)
            return {"status": "success", "answer": prompt + " " + self.portal_message(), "auth_required": True, "public": True}
        if re.search(r"mes rendez.vous|my appointments|mon dossier|my record|annuler|cancel|deplacer|reschedule", normalized):
            answer = "Une vérification de votre identité client est nécessaire pour accéder à vos données personnelles ou modifier un rendez-vous." if french else "Customer identity verification is required to access personal information or change an appointment."
            return {"status": "success", "answer": answer, "customer_verification_required": True, "public": True}
        if re.search(r"rendez.vous|appointment|booking|reservation|disponibilit|disponible|availability|available", normalized):
            answer = "Pour demander un rendez-vous, indiquez le service et la date souhaités. Aucune réservation n'est encore confirmée." if french else "For an appointment request, please provide the service and desired date. No booking is confirmed yet."
            call.source_context = {**(call.source_context or {}), "public_appointment_request": True}
            self.db.commit()
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"heures|horaires|hours|ouvert|opening", normalized):
            hours = {day: {key: value[key] for key in ("open", "close") if key in value}
                for day, value in config.opening_hours.items() if day in {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"} and isinstance(value, dict)}
            if hours:
                summary = ", ".join(f"{day}: {hours[day].get('open', '')} - {hours[day].get('close', '')}" for day in hours)
                answer = ("Nos heures d'ouverture: " if french else "Our opening hours: ") + summary
            else:
                answer = "Les heures d'ouverture ne sont pas encore renseignées." if french else "Opening hours have not been supplied yet."
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"services|prix|price|tarif", normalized):
            services = [{key: value[key] for key in ("name", "duration_minutes", "price", "currency") if key in value} for value in config.services if isinstance(value, dict)]
            if services:
                summary = ", ".join(f"{s.get('name', '')} ({s.get('price', '')} {s.get('currency', '')})".strip() for s in services)
                answer = ("Nos services: " if french else "Our services: ") + summary
            else:
                answer = "Les services publics ne sont pas encore renseignés." if french else "Public services have not been supplied yet."
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"commande|order|produit|product|stock|inventaire|inventory|magasin|boutique|retail", normalized):
            answer = "Pour toute question sur vos commandes, nos produits ou notre inventaire, je peux vous renseigner. Que souhaitez-vous savoir ?" if french else "For questions about orders, products, or inventory, I can help. What would you like to know?"
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"parler|quelqu.un|agent|humain|reception|personne|speak|someone|representative|human", normalized):
            answer = "Je peux prendre votre message ou vous renseigner sur nos services, horaires et rendez-vous. Comment puis-je vous aider ?" if french else "I can take a message or assist with services, hours, and appointments. How can I help you?"
            return {"status": "success", "answer": answer, "public": True}
        if re.search(r"^\s*(bonjour|salut|allo|bon matin|bonsoir|oui bonjour|hello|hi|hey)\b", normalized):
            return {"status": "success", "answer": "Bonjour ! Comment puis-je vous aider aujourd'hui ?" if french else "Hello! How can I help you today?", "public": True}
        answer = "Je peux vous renseigner sur nos heures d'ouverture, nos services ou pour une demande de rendez-vous. Comment puis-je vous aider ?" if french else "I can help with our opening hours, services, or an appointment request. How can I help you?"
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
        if call.pin_challenge_hash or call.verification_attempts >= maximum:
            return {"success": False, "error": "caller_authentication_failed"}
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
        if (call.source_context or {}).get("pin_gather_status") == "authenticated":
            auth = VoiceCallerAuth(self.db, self.settings).valid_session(call)
            return "authenticated" if auth is not None and auth.caller_type in {"OWNER", "EMPLOYEE"} else "refused"
        return "refused"


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


class TelnyxAudioCodec:
    def __init__(self) -> None:
        self._input_state = None
        self._output_state = None

    def reset(self) -> None:
        self._input_state = None
        self._output_state = None

    @staticmethod
    def decode_payload(payload: object, maximum: int) -> bytes:
        if not isinstance(payload, str) or len(payload) > ((maximum + 2) // 3) * 4:
            raise InvalidMediaFrame("Invalid audio payload")
        try:
            raw = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error):
            raise InvalidMediaFrame("Invalid audio payload") from None
        if not raw or len(raw) > maximum:
            raise InvalidMediaFrame("Invalid audio payload")
        return raw

    def inbound_pcm(self, payload: object) -> bytes:
        raw = self.decode_payload(payload, 1600)
        pcm = audioop.ulaw2lin(raw, 2)
        converted, self._input_state = audioop.ratecv(pcm, 2, 1, 8000, 24000, self._input_state)
        return converted

    @staticmethod
    def _anti_alias_filter(pcm: bytes) -> bytes:
        """7-tap symmetric FIR low-pass filter (cutoff ~3600 Hz at 24000 Hz).
        Attenuates energy above 4 kHz before 3:1 downsampling, preventing severe harmonic aliasing.
        """
        if len(pcm) < 16:
            return pcm
        samples = array.array("h", pcm)
        n = len(samples)
        out = array.array("h", [0] * n)
        # Scaled coefficients [36, 97, 195, 368, 195, 97, 36] / 1024
        for i in range(3, n - 3):
            val = (
                36 * (samples[i - 3] + samples[i + 3])
                + 97 * (samples[i - 2] + samples[i + 2])
                + 195 * (samples[i - 1] + samples[i + 1])
                + 368 * samples[i]
            ) >> 10
            out[i] = max(-32768, min(32767, val))
        for i in (0, 1, 2):
            out[i] = samples[i]
        for i in (n - 3, n - 2, n - 1):
            out[i] = samples[i]
        return out.tobytes()

    def outbound_pcm(self, payload: object) -> bytes:
        pcm = self.decode_payload(payload, 48000)
        if len(pcm) % 2:
            raise InvalidMediaFrame("Invalid PCM frame")
        filtered = self._anti_alias_filter(pcm)
        converted, self._output_state = audioop.ratecv(filtered, 2, 1, 24000, 8000, self._output_state)
        return audioop.lin2ulaw(converted, 2)


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
        consume_pending_query: Callable[[], Awaitable[str | None]] | None = None,
        max_output_queue: int = 64,
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
        self.consume_pending_query: Callable[[], Awaitable[str | None]] | None = consume_pending_query
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
        self._pin_turn = None
        self._pin_mark = None
        self._pin_started = False
        self._pin_deadline = None
        # Backpressure & health metrics (no raw audio)
        self.dropped_inbound_frames = 0
        self.dropped_outbound_frames = 0
        self.central_ai_timeouts = 0
        self.tts_failures = 0
        self.tts_timeout = 10.0
        self.central_ai_timeout = 15.0
        self.inbound_audio_timeout = 5.0
        # Safe call telemetry (no raw audio, no secrets)
        self.telemetry: dict[str, Any] = {
            "call_answered": True,
            "media_connected": False,
            "inbound_frames": 0,
            "inbound_audio_ms": 0,
            "speech_detected": False,
            "stt_audio_sent": False,
            "transcription_received": False,
            "central_ai_called": False,
            "tts_generated": False,
            "outbound_frames": 0,
            "final_state": "CONNECTING",
            "provider_error": None,
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

    async def interrupt(self, *, pause_input: bool = False) -> None:
        cancel_response = self.response_id is not None or self.pending_epoch is not None
        self.epoch += 1
        self.pending_epoch = None
        self.response_epoch = None
        self.response_id = None
        self._remainder = b""
        self.codec.reset()
        self.reorder_buffer.reset()
        while not self._turns.empty():
            item_id, _transcript, _epoch = self._turns.get_nowait()
            if self.usage is not None:
                self.usage.settle(item_id)
        while not self._output.empty():
            self._output.get_nowait()
        while self._pending_speech:
            item_id, _epoch, turn_ledger = self._pending_speech.popleft()
            if turn_ledger is not None:
                turn_ledger.settle(item_id)
        for _resp_id, (item_id, _resp_epoch, resp_ledger) in list(self._responses.items()):
            if resp_ledger is not None:
                resp_ledger.settle(item_id)
        self._responses.clear()
        async with self._send_lock:
            await self.socket.send_json({"event": "clear"})
        if cancel_response:
            await self.adapter.interrupt()
        if pause_input:
            self.input_paused = True
            await self.adapter.clear_input()

    async def _execute(self, item_id: str, transcript: str, epoch: int) -> None:
        requested_audio = False
        turn_ledger = self.usage
        try:
            if epoch != self.epoch or self.input_paused:
                return
            if not transcript or not transcript.strip():
                return
            await self.authorize()
            self.telemetry["central_ai_called"] = True
            try:
                result = await asyncio.wait_for(
                    self.execute_turn(item_id, redact_voice_secrets(transcript)),
                    timeout=self.central_ai_timeout
                )
            except asyncio.TimeoutError:
                self.central_ai_timeouts += 1
                return
            if epoch != self.epoch:
                return
            if result.get("auth_required"):
                if self.begin_pin is None or self.poll_pin is None:
                    raise PermissionError("Keypad authentication unavailable")
                await self.interrupt(pause_input=True)
                epoch = self.epoch
                self._pin_turn = item_id
                self._pin_started = False
                self._pin_deadline = asyncio.get_running_loop().time() + 30
            elif self.input_paused:
                return
            if result.get("status") == "success" and isinstance(result.get("answer"), str) and result["answer"].strip():
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
                self.telemetry["final_state"] = "RESPONDING"
                try:
                    await asyncio.wait_for(
                        self.adapter.speak(clean_voice_text(redact_voice_secrets(result["answer"]))),
                        timeout=self.tts_timeout
                    )
                except Exception:
                    self.tts_failures += 1
                    requested_audio = False
                    if self._pending_speech and self._pending_speech[-1][0] == item_id:
                        self._pending_speech.pop()
                    if turn_ledger is not None:
                        turn_ledger.settle(item_id)
        finally:
            if turn_ledger is not None and not requested_audio:
                turn_ledger.settle(item_id)

    async def _execute_turns(self) -> None:
        while True:
            item_id, transcript, epoch = await self._turns.get()
            await self._execute(item_id, transcript, epoch)

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
                        await self.socket.send_json({"event": "media", "media": {"payload": base64.b64encode(raw).decode("ascii")}})
                        self.telemetry["outbound_frames"] += 1
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

    async def _provider_events(self) -> None:
        async for event in self.adapter.events():
            kind = getattr(event, "type", "")
            if kind == "session.updated":
                logger.info("Realtime session configured successfully (model=%s, stt=%s)", self.realtime_model, self.stt_model)
                self.telemetry["final_state"] = "LISTENING"
            elif kind == "input_audio_buffer.speech_started" and not self.input_paused:
                logger.info("Caller speech started (epoch=%s)", self.epoch)
                self.telemetry["speech_detected"] = True
                self.telemetry["final_state"] = "USER_SPEAKING"
                await self.interrupt()
                item_id = getattr(event, "item_id", "")
                if self.usage is not None and isinstance(item_id, str) and item_id:
                    if not self.usage.reserve(item_id):
                        raise PermissionError("Voice usage quota unavailable")
            elif kind == "input_audio_buffer.speech_stopped" and not self.input_paused:
                logger.info("Caller speech stopped (epoch=%s)", self.epoch)
                self.telemetry["final_state"] = "PROCESSING"
            elif kind == "conversation.item.input_audio_transcription.completed" and not self.input_paused:
                item_id = getattr(event, "item_id", "")
                transcript = getattr(event, "transcript", "")
                logger.info("Caller speech transcribed (item_id=%s, length=%d)", item_id, len(transcript) if isinstance(transcript, str) else 0)
                if not isinstance(item_id, str) or not item_id or len(item_id) > 255 or not isinstance(transcript, str) or len(transcript) > 12000:
                    raise InvalidMediaFrame("Invalid transcription event")
                if item_id in self._seen_items or not transcript.strip():
                    continue
                if len(self._seen_items) >= 1000:
                    raise InvalidMediaFrame("Call turn capacity exceeded")
                self._seen_items.add(item_id)
                self.telemetry["transcription_received"] = True
                self.telemetry["final_state"] = "PROCESSING"
                if self.usage is not None:
                    if not self.usage.reserve(item_id):
                        raise PermissionError("Voice usage quota unavailable")
                    self.usage.record_transcription(item_id, event, model=self.stt_model)
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
                else:
                    self.response_epoch = None
                self.pending_epoch = None
            elif kind == "response.output_audio.delta":
                if self.response_epoch == self.epoch and self.response_id == getattr(event, "response_id", None):
                    self._enqueue(self.codec.outbound_pcm(getattr(event, "delta", None)))
            elif kind == "response.done":
                self.telemetry["final_state"] = "LISTENING"
                completed_id = getattr(getattr(event, "response", None), "id", None)
                completed = self._responses.pop(completed_id, None)
                if completed is not None and completed[2] is not None:
                    completed[2].record_realtime_response(completed[0], event, model=self.realtime_model)
                    completed[2].settle(completed[0])
                if self.response_epoch == self.epoch and self.response_id == getattr(getattr(event, "response", None), "id", None):
                    self._enqueue(b"", final=True)
                    if completed is not None and completed[0] == self._pin_turn and self._pin_turn is not None:
                        self._pin_mark = "pin-prompt:" + hashlib.sha256(self._pin_turn.encode()).hexdigest()[:24]
                        try:
                            self._output.put_nowait((self.epoch, {"event": "mark", "mark": {"name": self._pin_mark}}))
                        except asyncio.QueueFull:
                            self.dropped_outbound_frames += 1
                    self.response_id = None
                    self.response_epoch = None
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
            if not isinstance(event, dict) or event.get("stream_id") != self.stream_id:
                raise InvalidMediaFrame("Media stream mismatch")
            kind = event.get("event")
            if kind == "stop":
                if not self.input_paused:
                    for pcm in self.reorder_buffer.flush():
                        await self._send_inbound_audio(pcm)
                return
            if kind == "dtmf":
                await self.interrupt(pause_input=True)
                continue
            if kind == "mark":
                marker = event.get("mark")
                if self._pin_mark and isinstance(marker, dict) and marker.get("name") == self._pin_mark and not self._pin_started:
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

    async def _speak_system(self, item_id: str, answer: str) -> None:
        if self.usage is not None and not self.usage.reserve(item_id):
            raise PermissionError("Voice usage quota unavailable")
        self.pending_epoch = self.epoch
        self._pending_speech.append((item_id, self.epoch, self.usage))
        self.telemetry["tts_generated"] = True
        await self.adapter.speak(redact_voice_secrets(answer))

    async def _finish_pin(self, status: str) -> None:
        item_id = self._pin_turn or "pin-result"
        self._pin_turn = None; self._pin_mark = None; self._pin_started = False; self._pin_deadline = None
        await self.adapter.clear_input()
        await self.authorize()
        pending_query = None
        if status == "authenticated" and self.consume_pending_query is not None:
            pending_query = await self.consume_pending_query()

        if status == "authenticated":
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
        else:
            await self._speak_system(
                "pin-result:" + hashlib.sha256(str(item_id).encode()).hexdigest()[:24],
                voice_auth_message(self.locale, 2),
            )
        await asyncio.sleep(0.2)
        await self.adapter.clear_input()
        self.input_paused = False

    async def _monitor_pin(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            if self._pin_turn is None:
                continue
            if self._pin_deadline is not None and asyncio.get_running_loop().time() >= self._pin_deadline:
                await self._finish_pin("refused")
                continue
            if self._pin_started and self.poll_pin is not None:
                status = await self.poll_pin()
                if status in {"authenticated", "refused"}:
                    await self._finish_pin(status)

    async def _periodic_auth(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            await self.authorize()

    async def run(self) -> None:
        try:
            event = await asyncio.wait_for(self.socket.receive_json(), timeout=5)
            if isinstance(event, dict) and event.get("event") == "connected":
                event = await asyncio.wait_for(self.socket.receive_json(), timeout=5)
            if not isinstance(event, dict) or event.get("event") != "start" or not isinstance(event.get("start"), dict):
                raise InvalidMediaFrame("Media start required")
            self.stream_id = event.get("stream_id")
            if not isinstance(self.stream_id, str) or not self.stream_id or len(self.stream_id) > 255:
                raise InvalidMediaFrame("Invalid stream identity")
            media_fmt = event["start"].get("media_format") if isinstance(event["start"].get("media_format"), dict) else {}
            enc = str(media_fmt.get("encoding", "")).upper()
            rate = int(media_fmt.get("sample_rate", 0))
            channels = int(media_fmt.get("channels", 1))
            if enc != "PCMU" or rate != 8000 or channels != 1:
                raise InvalidMediaFrame("Unsupported media format")
            await self.validate_start(event["start"])
            self.telemetry["media_connected"] = True
            await self.authorize()
            await self.adapter.open(locale=self.locale)
            if self.initial_answer:
                self.telemetry["final_state"] = "GREETING"
                await self._speak_system("inbound-greeting", self.initial_answer)
            reader = asyncio.create_task(self._read_audio())
            self._background = [reader, asyncio.create_task(self._provider_events()), asyncio.create_task(self._write_audio()), asyncio.create_task(self._execute_turns()), asyncio.create_task(self._periodic_auth())]
            if self.poll_pin is not None:
                self._background.append(asyncio.create_task(self._monitor_pin()))
            done, _pending = await asyncio.wait(self._background, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            logger.info(
                "Call %s session telemetry: call_answered=%s media_connected=%s inbound_frames=%d inbound_audio_ms=%d speech_detected=%s stt_audio_sent=%s transcription_received=%s central_ai_called=%s tts_generated=%s outbound_frames=%d final_state=%s provider_error=%s",
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
            )
            for task in self._background:
                task.cancel()
            await asyncio.gather(*self._background, return_exceptions=True)
            self._clear_all_buffers()
            with suppress(Exception):
                await self.adapter.close()
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
        await self.websocket.send_json(event)


def media_audio_available(settings: Settings, locale: str) -> bool:
    return bool(settings.openai_api_key and settings.voice_realtime_provider == "openai" and settings.voice_realtime_model
        and settings.voice_stt_provider == "openai" and settings.voice_stt_model
        and settings.voice_tts_provider == "openai" and settings.voice_tts_voice and settings.voice_tts_model
        and resolve_locale(locale) in {resolve_locale(item) for item in settings.voice_realtime_supported_locales})


async def telnyx_media_socket(
    websocket: WebSocket, call_id: UUID, db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings), service=Depends(get_central_ai_service),
    prediction_service=Depends(get_prediction_service),
) -> None:
    public_mode = settings.telnyx_media_inbound_enabled
    try:
        if public_mode:
            call, config, company = media_transport_context(db, settings, call_id)
        else:
            call, config, company, _user, _permissions, _auth = media_call_context(db, settings, call_id)
        locale = resolve_locale(call.locale or config.preferred_language)
        if not media_audio_available(settings, locale) or service.usage_service is None:
            raise PermissionError("Validated audio configuration required")
        plan = ModuleEntitlementService(db).get_company_plan(TenantContext(company.id)).code.value
        service.usage_service.ensure_quota_available(company.id, plan)
    except Exception:
        await websocket.close(code=4403)
        return

    ledger = None
    claim = None
    principal_id = None
    auth_epoch = None
    public_conversation = PublicInboundConversation(db, settings, call_id) if public_mode else None
    call_lang_session = CallLanguageSession(
        tenant_id=company.id,
        call_session_id=str(call.id),
        primary_locale=call.locale or config.preferred_language or locale,
        active_locale=call.locale or config.preferred_language or locale,
        allowed_locales=tuple((call.source_context or {}).get("allowed_locales", ())) or (
            resolve_locale(call.locale or config.preferred_language or locale),
            "en-US", "fr-CA", "es-ES", "ro-RO",
        ),
    )
    saved_lang_state = (call.source_context or {}).get("call_language_session")
    if isinstance(saved_lang_state, dict) and saved_lang_state.get("active_locale"):
        call_lang_session.active_locale = resolve_locale(saved_lang_state["active_locale"])
        call_lang_session.last_confirmed_locale = call_lang_session.active_locale
    adapter = OpenAIRealtimeAudioAdapter(OpenAIAudioConfig(settings.openai_api_key, settings.voice_stt_model,
        settings.voice_tts_model, settings.voice_tts_voice), settings.voice_realtime_model)
    bridge: TelnyxMediaBridge

    async def authorize() -> None:
        nonlocal ledger, principal_id, auth_epoch
        current_call, current_config, current_company = media_transport_context(db, settings, call_id)
        if ModuleEntitlementService(db).get_company_plan(TenantContext(current_company.id)).code.value != plan:
            raise PermissionError("Billing plan changed during media session")
        try:
            _call, _config, _company, current_user, _permissions, current_auth = media_call_context(db, settings, call_id)
        except PermissionError:
            if not public_mode or principal_id is not None:
                raise
            return
        current_epoch = utc(current_auth.authenticated_at).isoformat()
        if principal_id is not None:
            if current_user.id != principal_id or current_epoch != auth_epoch:
                raise PermissionError("Caller authentication changed")
            return
        if claim is None:
            return
        if current_call.central_conversation_id is None:
            conversation = ConversationService(db).create(current_company.id, current_user.id, f"Voice call {current_call.id}", current_call.locale or locale)
            current_call.central_conversation_id = conversation.id
            db.commit()
        else:
            ConversationService(db).get(current_company.id, current_user.id, current_call.central_conversation_id)
        principal_id = current_user.id
        auth_epoch = current_epoch
        ledger = VoiceUsageLedger(service.usage_service, voice_pricing_catalog(settings.ai_model_rate_card),
            company_id=current_company.id, user_id=current_user.id, conversation_id=current_call.central_conversation_id,
            plan_code=plan, request_namespace=call_id if public_mode else None)
        bridge.use_ledger(ledger)

    async def validate_start(start: dict) -> None:
        nonlocal ledger, claim
        claim = claim_media_start(db, settings, call_id, start, public_mode=public_mode)
        if public_mode:
            current_call, _config, current_company = media_transport_context(db, settings, call_id)
            current_call.source_context = {**(current_call.source_context or {}), "public_conversation_id": str(current_call.id)}
            db.commit()
            ledger = VoiceUsageLedger(service.usage_service, voice_pricing_catalog(settings.ai_model_rate_card),
                company_id=current_company.id, user_id=None, conversation_id=None, plan_code=plan, request_namespace=current_call.id)
            bridge.use_ledger(ledger)
        await authorize()

    async def execute_turn(item_id: str, transcript: str) -> dict:
        nonlocal ledger
        if public_conversation is not None and principal_id is None:
            security_check = public_conversation.security_gate(transcript)
            if security_check is not None:
                return security_check

        if principal_id is not None:
            current_call, current_config, current_company, current_user, permissions, _auth = media_call_context(db, settings, call_id)
        else:
            current_call, current_config, current_company = media_transport_context(db, settings, call_id)
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
                    owner_membership = CompanyMembership(
                        company_id=current_company.id,
                        user_id=fallback_user.id,
                        role=fallback_user.role if fallback_user.role in [UserRole.OWNER, UserRole.ADMIN] else UserRole.ADMIN,
                        is_active=True,
                    )
                    db.add(owner_membership)
                    db.commit()
                    db.refresh(owner_membership)
                    current_user = fallback_user
                else:
                    return {"status": "error", "answer": "Désolé, le service est momentanément indisponible."}
            else:
                current_user = db.get(User, owner_membership.user_id)
                if current_user is None:
                    return {"status": "error", "answer": "Désolé, le service est momentanément indisponible."}
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
        current_call.source_context = {
            **resolve_voice_source_context(db, tenant),
            **(current_call.source_context or {}),
            "call_language_session": call_lang_session.as_dict(),
        }
        db.commit()

        if ledger is None or ledger._user_id is None or ledger._conversation_id is None:
            ledger = VoiceUsageLedger(
                service.usage_service,
                voice_pricing_catalog(settings.ai_model_rate_card),
                company_id=current_company.id,
                user_id=current_user.id,
                conversation_id=current_call.central_conversation_id,
                plan_code=plan,
                request_namespace=current_call.id,
            )
            bridge.use_ledger(ledger)

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
            return {"status": result.status, "answer": result.answer}
        except Exception as exc:
            if principal_id is None and public_conversation is not None:
                logger.exception("Central AI execute error for public voice call, falling back: %s", exc)
                return public_conversation.public_answer(transcript)
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

    async def consume_pending_query() -> str | None:
        if public_conversation is None:
            return None
        return public_conversation.consume_pending_auth_query()

    bridge = TelnyxMediaBridge(BoundedMediaSocket(websocket), adapter, locale=locale,
        validate_start=validate_start, authorize=authorize, execute_turn=execute_turn,
        stt_model=settings.voice_stt_model, realtime_model=settings.voice_realtime_model,
        initial_answer=public_conversation.greeting() if public_conversation is not None else None,
        begin_pin=begin_pin if public_mode else None, poll_pin=poll_pin if public_mode else None,
        consume_pending_query=consume_pending_query if public_mode else None,
        max_output_queue=2000)
    await websocket.accept()
    try:
        await bridge.run()
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        pass
    except PermissionError:
        await websocket.close(code=4403)
    except (InvalidMediaFrame, asyncio.TimeoutError):
        await websocket.close(code=4400)
    except Exception:
        await websocket.close(code=1011)
    finally:
        db.rollback()
        if claim is not None:
            with suppress(Exception):
                release_media_session(db, call_id, claim)
        try:
            current_call = db.get(VoiceCall, call_id)
            if current_call is not None and current_call.ended_at is None and current_call.status in {"answering", "routed", "in_progress"}:
                current_call.ended_at = datetime.now(timezone.utc)
                current_call.status = "completed"
                db.commit()
        except Exception:
            db.rollback()