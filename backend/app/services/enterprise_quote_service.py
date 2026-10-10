"""Demandes de devis Enterprise : validation, persistance, envoi et file de réessai."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
import re
from time import sleep
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.core.rate_limit import allow_rate_limit
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.billing import EnterpriseQuote, EnterpriseQuoteDelivery
from backend.app.services.resend_client import (
    PermanentEmailDeliveryError,
    TemporaryEmailDeliveryError,
)

logger = logging.getLogger(__name__)

DEFAULT_QUOTE_RECIPIENTS = ("info@avenqo.ca", "paulmircea15@gmail.com")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9+().\s-]{6,40}$")
_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_IMMEDIATE_RETRIES = 2
_RETRY_BACKOFF_SECONDS = (0.2, 0.6)


class QuoteMailerUnavailable(Exception):
    """Aucun transporteur transactionnel n'est configuré."""


@dataclass(frozen=True)
class QuoteSubmission:
    source: str
    contact_name: str
    contact_email: str
    company_name: str
    contact_phone: str | None
    need: str | None
    message: str
    requested_modules: list[str]
    estimated_users: int | None
    monthly_volume: str | None
    required_integrations: list[str]
    company_id: UUID | None = None
    user_id: UUID | None = None
    website: str | None = None


class EnterpriseQuoteService:
    def __init__(self, db: Session, settings: Settings, mailer) -> None:
        self._db = db
        self._settings = settings
        self._mailer = mailer

    def submit(self, submission: QuoteSubmission, client_key: str) -> EnterpriseQuote:
        self._reject_spam(submission)
        self._validate(submission)
        self._enforce_limits(submission, client_key)
        now = datetime.now(timezone.utc)
        idempotency_key = self._request_fingerprint(submission)
        existing = self._db.scalar(
            select(EnterpriseQuote).where(EnterpriseQuote.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.notification_status == "sent":
                return existing
            self._ensure_delivery_jobs(existing)
            self.dispatch_pending(quote=existing)
            return existing

        quote = EnterpriseQuote(
            reference_id=f"EQ-{uuid4().hex[:8].upper()}",
            company_id=submission.company_id,
            user_id=submission.user_id,
            source=submission.source,
            company_name=submission.company_name,
            contact_name=submission.contact_name,
            contact_email=submission.contact_email.lower(),
            contact_phone=submission.contact_phone,
            need=submission.need,
            requested_modules=submission.requested_modules,
            estimated_users=submission.estimated_users,
            monthly_volume=submission.monthly_volume,
            required_integrations=submission.required_integrations,
            notes=submission.message,
            status="received",
            notification_status="pending",
            acknowledgment_status="pending",
            idempotency_key=idempotency_key,
            submitted_at=now,
        )
        self._db.add(quote)
        self._db.flush()
        self._ensure_delivery_jobs(quote)
        self._db.add(
            AuditLogEntry(
                actor_user_id=submission.user_id,
                action="billing.enterprise_quote_requested",
                target_type="enterprise_quote",
                target_id=quote.reference_id,
                company_id=submission.company_id,
                safe_metadata={
                    "reference_id": quote.reference_id,
                    "company_name": quote.company_name,
                    "requester_name": quote.contact_name,
                    "requester_email": quote.contact_email,
                    "contact_phone": quote.contact_phone,
                    "need": quote.need,
                    "source": quote.source,
                    "submitted_at": now.isoformat(),
                },
                created_at=now,
            )
        )
        self._db.commit()
        self._db.refresh(quote)
        self.dispatch_pending(quote=quote)
        return quote

    def mark_delivered(
        self,
        reference_id: str,
        deliveries: list[dict[str, str]],
    ) -> EnterpriseQuote:
        quote = self._require_quote(reference_id)
        for item in deliveries:
            job = self._job_for(quote, item["kind"], item["recipient"])
            if job is None or job.status == "sent":
                continue
            job.status = "sent"
            job.provider_message_id = item.get("provider_message_id")
            job.last_error = None
            job.next_retry_at = None
        self._refresh_quote_status(quote)
        if quote.notification_status == "sent" and quote.acknowledgment_status != "sent":
            self.dispatch_pending(quote=quote, kinds=("acknowledgment",))
        self._db.commit()
        self._db.refresh(quote)
        return quote

    def dispatch_pending(
        self,
        quote: EnterpriseQuote | None = None,
        kinds: tuple[str, ...] | None = None,
    ) -> int:
        now = datetime.now(timezone.utc)
        query = select(EnterpriseQuoteDelivery).where(EnterpriseQuoteDelivery.status != "sent")
        if quote is not None:
            query = query.where(EnterpriseQuoteDelivery.quote_id == quote.id)
        if kinds:
            query = query.where(EnterpriseQuoteDelivery.kind.in_(kinds))
        jobs = list(self._db.scalars(query).all())
        sent = 0

        def _deliver_kind(kind: str) -> None:
            nonlocal sent
            selected = [
                job
                for job in jobs
                if job.kind == kind and not (job.next_retry_at and job.next_retry_at > now)
            ]
            if not selected:
                return
            parent = quote or selected[0].quote
            if kind == "acknowledgment" and parent.notification_status != "sent":
                return
            if kind == "owner":
                if self._deliver_batch(selected, parent):
                    sent += 1
                return
            for job in selected:
                if self._deliver_batch([job], parent):
                    sent += 1

        _deliver_kind("owner")
        if quote is not None:
            self._refresh_quote_status(quote)
        else:
            for parent in {job.quote for job in jobs}:
                self._refresh_quote_status(parent)
        _deliver_kind("acknowledgment")
        if quote is not None:
            self._refresh_quote_status(quote)
        else:
            for parent in {job.quote for job in jobs}:
                self._refresh_quote_status(parent)
        self._db.commit()
        return sent

    def _deliver_batch(self, jobs: list[EnterpriseQuoteDelivery], quote: EnterpriseQuote) -> bool:
        if not jobs:
            return False
        if self._mailer is None:
            for job in jobs:
                job.last_error = "Transactional email API is not configured"
                job.status = "failed"
                job.attempts += 1
            return False
        subject, text_body, html_body = self._message_for(jobs[0], quote)
        recipients = [job.recipient for job in jobs]
        idempotency_key = (
            f"eq-{quote.reference_id}-{jobs[0].kind}"
            if jobs[0].kind == "owner"
            else jobs[0].idempotency_key
        )
        last_error: Exception | None = None
        for job in jobs:
            job.attempts += 1
        for attempt in range(_IMMEDIATE_RETRIES + 1):
            try:
                message_id = self._mailer.send(
                    to=recipients,
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                    idempotency_key=idempotency_key,
                )
                for job in jobs:
                    job.status = "sent"
                    job.provider_message_id = message_id
                    job.last_error = None
                    job.next_retry_at = None
                return True
            except TemporaryEmailDeliveryError as exc:
                last_error = exc
                if attempt < _IMMEDIATE_RETRIES:
                    sleep(_RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)])
                    continue
                for job in jobs:
                    job.status = "pending"
                    job.last_error = str(exc)[:500]
                    job.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=min(15, 2 ** job.attempts))
                return False
            except PermanentEmailDeliveryError as exc:
                for job in jobs:
                    job.status = "failed"
                    job.last_error = str(exc)[:500]
                    job.next_retry_at = None
                return False
        if last_error is not None:
            for job in jobs:
                job.status = "pending"
                job.last_error = str(last_error)[:500]
        return False

    def _ensure_delivery_jobs(self, quote: EnterpriseQuote) -> None:
        recipients = self._owner_recipients()
        for recipient in recipients:
            self._add_job(quote, "owner", recipient)
        if quote.contact_email:
            self._add_job(quote, "acknowledgment", quote.contact_email)

    def _add_job(self, quote: EnterpriseQuote, kind: str, recipient: str) -> None:
        recipient = recipient.strip().lower()
        idempotency_key = f"eq-{quote.reference_id}-{kind}-{recipient}"
        existing = self._db.scalar(
            select(EnterpriseQuoteDelivery).where(
                EnterpriseQuoteDelivery.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return
        self._db.add(
            EnterpriseQuoteDelivery(
                quote_id=quote.id,
                kind=kind,
                recipient=recipient,
                idempotency_key=idempotency_key,
                status="pending",
            )
        )
        self._db.flush()

    def _refresh_quote_status(self, quote: EnterpriseQuote) -> None:
        jobs = list(
            self._db.scalars(
                select(EnterpriseQuoteDelivery).where(EnterpriseQuoteDelivery.quote_id == quote.id)
            ).all()
        )
        owner_jobs = [job for job in jobs if job.kind == "owner"]
        ack_jobs = [job for job in jobs if job.kind == "acknowledgment"]
        if owner_jobs and all(job.status == "sent" for job in owner_jobs):
            quote.notification_status = "sent"
        elif any(job.status == "failed" for job in owner_jobs) and not any(
            job.status in {"pending", "sent"} for job in owner_jobs
        ):
            quote.notification_status = "failed"
        else:
            quote.notification_status = "pending"
        if ack_jobs and all(job.status == "sent" for job in ack_jobs):
            quote.acknowledgment_status = "sent"
        elif any(job.status == "failed" for job in ack_jobs):
            quote.acknowledgment_status = "failed"
        else:
            quote.acknowledgment_status = "pending"

    def _owner_recipients(self) -> list[str]:
        configured = [item.strip().lower() for item in self._settings.enterprise_quote_recipients if item.strip()]
        return configured or list(DEFAULT_QUOTE_RECIPIENTS)

    def _validate(self, submission: QuoteSubmission) -> None:
        name = submission.contact_name.strip()
        email = submission.contact_email.strip()
        company = submission.company_name.strip()
        message = submission.message.strip()
        if len(name) < 2 or len(name) > 120:
            raise HTTPException(status_code=400, detail="Le nom du contact est requis.")
        if not _EMAIL_RE.match(email) or len(email) > 254:
            raise HTTPException(status_code=400, detail="L'adresse email fournie n'est pas valide.")
        if len(company) < 2 or len(company) > 200:
            raise HTTPException(status_code=400, detail="Le nom de l'entreprise est requis.")
        if len(message) < 10 or len(message) > 4000:
            raise HTTPException(status_code=400, detail="Le message doit contenir entre 10 et 4000 caractères.")
        if submission.contact_phone and not _PHONE_RE.match(submission.contact_phone.strip()):
            raise HTTPException(status_code=400, detail="Le numéro de téléphone n'est pas valide.")
        if submission.need and len(submission.need) > 255:
            raise HTTPException(status_code=400, detail="Le besoin indiqué est trop long.")

    def _reject_spam(self, submission: QuoteSubmission) -> None:
        if (submission.website or "").strip():
            raise HTTPException(status_code=400, detail="La demande n'a pas pu être acceptée.")
        if len(_URL_RE.findall(submission.message or "")) > 5:
            raise HTTPException(status_code=400, detail="La demande n'a pas pu être acceptée.")

    def _enforce_limits(self, submission: QuoteSubmission, client_key: str) -> None:
        if not self._settings.rate_limit_enabled:
            return
        per_minute = self._settings.rate_limit_quote_per_minute
        if not allow_rate_limit("enterprise_quote_ip", client_key, per_minute):
            raise HTTPException(status_code=429, detail="Trop de demandes, veuillez réessayer plus tard.")
        email_key = submission.contact_email.strip().lower()
        hour_window = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        submitted = self._db.scalar(
            select(func.count()).select_from(EnterpriseQuote).where(
                func.lower(EnterpriseQuote.contact_email) == email_key,
                EnterpriseQuote.submitted_at >= hour_window,
            )
        ) or 0
        if submitted >= self._settings.rate_limit_quote_per_email_per_hour:
            raise HTTPException(status_code=429, detail="Trop de demandes pour cette adresse, réessayez plus tard.")

    def _request_fingerprint(self, submission: QuoteSubmission) -> str:
        hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        raw = "|".join(
            (
                submission.source,
                submission.contact_email.strip().lower(),
                submission.company_name.strip().lower(),
                (submission.need or "").strip().lower(),
                submission.message.strip(),
                hour,
            )
        )
        return sha256(raw.encode("utf-8")).hexdigest()

    def _message_for(self, job: EnterpriseQuoteDelivery, quote: EnterpriseQuote) -> tuple[str, str, str]:
        submitted = (quote.submitted_at or quote.created_at).isoformat()
        if job.kind == "acknowledgment":
            subject = f"Avenqo a bien reçu votre demande {quote.reference_id}"
            text = "\n".join(
                (
                    f"Bonjour {quote.contact_name or ''},",
                    "",
                    "Nous avons bien reçu votre demande de devis Enterprise.",
                    f"Référence : {quote.reference_id}",
                    "Notre équipe vous répondra sous 24 heures ouvrées.",
                    "",
                    "Avenqo",
                )
            )
            return subject, text, f"<p>{text.replace(chr(10), '<br>')}</p>"
        subject = f"Nouvelle demande Enterprise {quote.reference_id} — {quote.company_name}"
        text = "\n".join(
            (
                f"Référence : {quote.reference_id}",
                f"Source : {quote.source}",
                f"Nom : {quote.contact_name}",
                f"Entreprise : {quote.company_name}",
                f"Courriel : {quote.contact_email}",
                f"Téléphone : {quote.contact_phone or 'Non renseigné'}",
                f"Besoins : {quote.need or ', '.join(quote.requested_modules) or 'Non renseigné'}",
                f"Utilisateurs estimés : {quote.estimated_users or '—'}",
                f"Volume : {quote.monthly_volume or '—'}",
                f"Intégrations : {', '.join(quote.required_integrations) or '—'}",
                f"Date de soumission : {submitted}",
                "",
                "Message :",
                quote.notes or "",
            )
        )
        return subject, text, f"<pre>{text}</pre>"

    def _job_for(self, quote: EnterpriseQuote, kind: str, recipient: str) -> EnterpriseQuoteDelivery | None:
        recipient = recipient.strip().lower()
        for job in quote.deliveries:
            if job.kind == kind and job.recipient == recipient:
                return job
        return None

    def _require_quote(self, reference_id: str) -> EnterpriseQuote:
        quote = self._db.scalar(select(EnterpriseQuote).where(EnterpriseQuote.reference_id == reference_id))
        if quote is None:
            raise HTTPException(status_code=404, detail="Demande introuvable.")
        return quote

    @staticmethod
    def _delivery_error_detail(quote: EnterpriseQuote) -> str:
        return (
            f"La demande {quote.reference_id} a été enregistrée, mais l'envoi "
            "aux destinataires Avenqo n'a pas été confirmé. Réessayez plus tard."
        )
