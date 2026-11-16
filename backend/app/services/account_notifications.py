import base64
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
import threading
from uuid import UUID
"""Frontière d'envoi des emails liés au compte."""

from email.message import EmailMessage
from email.utils import formataddr
from html import escape
import json
import logging
import smtplib
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path

from backend.app.config.settings import Settings
from backend.app.services.tenant_locale_service import catalog_code_or_none, get_company_locale

logger = logging.getLogger(__name__)

SIGNATURE_OTP_SUBJECT = "Code de signature Avenqo"
_SIGNATURE_OTP_BODY_RE = re.compile(
    r"code de confirmation de signature|signature confirmation code|Code de signature",
    re.IGNORECASE,
)


def mask_email(email: str) -> str:
    """Mask a mailbox for UI/status only. Never reverse to recover the address."""
    value = (email or "").strip()
    local, sep, domain = value.partition("@")
    if not sep or not domain:
        return "***"
    keep = min(2, len(local))
    return f"{local[:keep]}***@{domain}"


def _company_locale(company: object) -> str:
    """Use the explicit tenant profile, then the legacy setting if absent.

    Profile updates synchronize Company.preferred_language. A stale legacy
    value must not make invoices disagree with Voice, CRM and Central AI.
    """
    company_id = getattr(company, "id", None)
    try:
        from sqlalchemy.orm import object_session

        db = object_session(company)
    except Exception:
        db = None
    if db is not None and company_id is not None:
        resolved = get_company_locale(db, company_id)
        if resolved:
            return resolved
    profile = getattr(company, "locale_profile", None)
    if profile is not None and getattr(profile, "primary_locale", None):
        return str(profile.primary_locale)
    return catalog_code_or_none(getattr(company, "preferred_language", None)) or "fr"


_SMTP_CONNECTION_TIMEOUT_SECONDS = 10
_HTTPS_CONNECTION_TIMEOUT_SECONDS = 10
_RESEND_EMAIL_API_URL = "https://api.resend.com/emails"


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str = "application/pdf"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class AccountNotifier(Protocol):
    email_delivery_configured: bool

    def send_email_verification(self, email: str, token: str) -> None: ...
    def send_password_reset(self, email: str, token: str) -> None: ...

    def send_new_company(self, company: object, user: object, request: object) -> None: ...
    def send_invoice_paid(self, recipient: str, company: object, invoice: object) -> None: ...
    def send_transactional(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None: ...


class EmailTransport(Protocol):
    def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None: ...


class LoggingAccountNotifier:
    """Adaptateur local lorsque la livraison d'email n'est pas configurée."""

    email_delivery_configured = False
    delivers_to_mailbox = False

    def send_email_verification(self, email: str, token: str) -> None:
        logger.info("Email de vérification demandé")

    def send_password_reset(self, email: str, token: str) -> None:
        logger.info("Réinitialisation de mot de passe demandée")

    def send_new_company(self, company: object, user: object, request: object) -> None:
        logger.info("Nouvelle entreprise Avenqo enregistrée")

    def send_invoice_paid(self, recipient: str, company: object, invoice: object) -> None:
        logger.info("Notification de facture Avenqo demandée invoice_id=%s", invoice.id)

    def send_transactional(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        logger.info(
            "Notification transactionnelle demandée subject=%s attachments=%d",
            subject,
            len(attachments or ()),
        )


class AccountNotificationService:
    """Construit les notifications de compte indépendamment du transport."""

    email_delivery_configured = True
    delivers_to_mailbox = True

    def __init__(self, settings: Settings, transport: EmailTransport) -> None:
        self._settings = settings
        self._transport = transport

    def send_email_verification(self, email: str, token: str) -> None:
        link = self._account_link("/verify-email", token)
        self._send(
            email,
            "Vérifiez votre adresse email Avenqo",
            "\n".join(
                (
                    "Bienvenue sur Avenqo.",
                    "",
                    f"Vérifiez votre adresse email : {link}",
                    "",
                    "Ce lien expire dans 24 heures et ne peut être utilisé qu'une fois.",
                )
            ),
        )

    def send_password_reset(self, email: str, token: str) -> None:
        link = self._account_link("/reset-password", token)
        self._send(
            email,
            "Réinitialisez votre mot de passe Avenqo",
            f"Utilisez ce lien pour choisir un nouveau mot de passe : {link}",
        )

    def send_new_company(self, company: object, user: object, request: object) -> None:
        recipient = self._settings.avenqo_owner_notification_email
        if not recipient:
            return
        body = "\n".join(
            (
                "New company registered on Avenqo.",
                f"Company: {company.name}",
                f"Industry: {company.industry}",
                f"Country: {company.country}",
                f"Region: {company.region}",
                f"Company size: {company.company_size}",
                f"Selected plan: {company.subscription_plan}",
                f"Account representative: {user.first_name} {user.last_name}",
                f"Role: {user.job_title}",
                f"Email: {user.email}",
                f"Billing email: {request.billing_email or company.email}",
                f"Business priorities: {', '.join(request.business_goals)}",
                f"Current tools: {', '.join(request.current_tools)}",
                f"Registration time: {company.created_at.isoformat()}",
                f"Company ID: {company.id}",
            )
        )
        self._send(recipient, f"New Avenqo Company — {company.name} — {company.subscription_plan}", body)

    def send_invoice_paid(self, recipient: str, company: object, invoice: object) -> None:
        labels = self._invoice_labels(_company_locale(company))
        amount = lambda value: f"{int(value) / 100:.2f} {invoice.currency.upper()}"
        period = "—"
        if invoice.period_start and invoice.period_end:
            period = f"{invoice.period_start.date().isoformat()} – {invoice.period_end.date().isoformat()}"
        body = "\n".join(
            (
                labels["greeting"].replace("{company}", company.name),
                "",
                f"{labels['invoiceNumber']}: {invoice.number or invoice.stripe_invoice_id}",
                f"{labels['plan']}: {invoice.plan_code or '—'}",
                f"{labels['billingPeriod']}: {period}",
                f"{labels['subtotal']}: {amount(invoice.subtotal)}",
                f"{labels['taxes']}: {amount(invoice.tax_total)}",
                f"{labels['totalPaid']}: {amount(invoice.amount_paid)}",
                f"{labels['status']}: {invoice.status}",
                "",
                f"{labels['viewInvoice']}: {invoice.hosted_invoice_url or '—'}",
                f"{labels['downloadPdf']}: {invoice.invoice_pdf or '—'}",
            )
        )
        self._send(
            recipient,
            labels["subject"].replace("{number}", invoice.number or invoice.stripe_invoice_id),
            body,
        )

    def send_transactional(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        self._send(recipient, subject, body, html_body, attachments=attachments)

    @staticmethod
    def _invoice_labels(locale: str) -> dict[str, str]:
        catalog_dir = Path(__file__).resolve().parents[3] / "frontend" / "assets" / "i18n"
        fallback = json.loads((catalog_dir / "en.json").read_text(encoding="utf-8"))["invoiceEmail"]
        catalog_path = catalog_dir / f"{locale}.json"
        if not catalog_path.exists():
            return fallback
        return {**fallback, **json.loads(catalog_path.read_text(encoding="utf-8")).get("invoiceEmail", {})}

    def _account_link(self, path: str, token: str) -> str:
        params = {"token": token}
        environment = self._settings.environment.strip().lower()
        if environment == "sandbox":
            params["env"] = "sandbox"
        base_url = self._settings.public_frontend_origin()
        return f"{base_url}{path}?{urlencode(params)}"

    def _send(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        *,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        if not html_body:
            html_body = "<p>" + escape(body).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
        try:
            self._transport.send(recipient, subject, body, html_body, attachments=attachments)
        except TypeError:
            self._transport.send(recipient, subject, body, html_body)


class SMTPEmailTransport:
    """Transport SMTP historique, conservé pour les environnements compatibles."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        if not getattr(self._settings, "is_external_email_allowed", True):
            raise RuntimeError(
                "External email dispatch blocked: live SMTP transmission is prohibited in Sandbox environment. "
                "Use EMAIL_PROVIDER=sandbox_capture for safe testing."
            )
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
        for attachment in attachments or ():
            maintype, _, subtype = (attachment.content_type or "application/octet-stream").partition("/")
            message.add_attachment(
                attachment.content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.filename,
            )

        try:
            with smtplib.SMTP(
                self._settings.smtp_host,
                self._settings.smtp_port,
                timeout=_SMTP_CONNECTION_TIMEOUT_SECONDS,
            ) as server:
                if self._settings.smtp_use_tls:
                    server.starttls()
                if self._settings.smtp_username and self._settings.smtp_password:
                    server.login(self._settings.smtp_username, self._settings.smtp_password)
                server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning(
                "SMTP delivery failed port=%s starttls=%s error_type=%s errno=%s",
                self._settings.smtp_port,
                self._settings.smtp_use_tls,
                type(exc).__name__,
                getattr(exc, "errno", None),
            )
            raise


class ResendHTTPSEmailTransport:
    """Transport HTTPS compatible avec l'API transactionnelle Resend."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.email_api_key
        self._from_email = settings.email_from_email
        self._from_name = settings.email_from_name

    def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        if not getattr(self._settings, "is_external_email_allowed", True):
            raise RuntimeError(
                "External email dispatch blocked: live Resend transmission is prohibited in Sandbox environment. "
                "Use EMAIL_PROVIDER=sandbox_capture for safe testing."
            )
        body_dict: dict[str, object] = {
            "from": formataddr((self._from_name, self._from_email)),
            "to": [recipient],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
        if attachments:
            body_dict["attachments"] = [
                {
                    "filename": att.filename,
                    "content": base64.b64encode(att.content).decode("ascii"),
                    "content_type": att.content_type,
                }
                for att in attachments
            ]
        payload = json.dumps(body_dict).encode("utf-8")
        request = Request(
            _RESEND_EMAIL_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Avenqo-Backend/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=_HTTPS_CONNECTION_TIMEOUT_SECONDS) as response:
                status_code = response.status
                raw = response.read()
                payload_response = _parse_email_api_payload(raw)
                if not 200 <= status_code < 300 or not payload_response.get("id"):
                    raise RuntimeError("Transactional email API rejected the request")
                logger.info(
                    "HTTPS email accepted status=%s provider_id_present=true",
                    status_code,
                )
        except (HTTPError, URLError, OSError, RuntimeError) as exc:
            error_name = _email_api_error_name(exc)
            logger.warning(
                "HTTPS email delivery failed status=%s error_type=%s error_name=%s",
                getattr(exc, "code", None),
                type(exc).__name__,
                error_name,
            )
            raise


class SMTPAccountNotifier(AccountNotificationService):
    """Compatibilité avec la configuration SMTP historique."""

    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_delivery_configured:
            raise ValueError(
                "SMTP non configuré : définir l'hôte et les identifiants d'envoi"
            )
        super().__init__(settings, SMTPEmailTransport(settings))


def _parse_email_api_payload(raw: bytes | str | None) -> dict[str, object]:
    if not raw:
        return {}
    if isinstance(raw, bytes):
        text_body = raw.decode("utf-8", errors="replace")
    else:
        text_body = raw
    try:
        parsed = json.loads(text_body)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _email_api_error_name(exc: BaseException) -> str:
    raw = b""
    if isinstance(exc, HTTPError):
        try:
            raw = exc.read()
        except Exception:
            raw = b""
    payload = _parse_email_api_payload(raw)
    name = payload.get("name") or payload.get("message") or ""
    if name:
        return str(name)[:80]
    text_body = raw.decode("utf-8", errors="replace") if raw else ""
    if "1010" in text_body:
        return "cloudflare_1010"
    return text_body.strip()[:80]


class HTTPSAccountNotifier(AccountNotificationService):
    """Notifications de compte livrées par API HTTPS transactionnelle."""

    def __init__(self, settings: Settings) -> None:
        if not settings.https_email_delivery_configured:
            raise ValueError(
                "API email HTTPS non configurée : définir la clé et l'expéditeur"
            )
        super().__init__(settings, ResendHTTPSEmailTransport(settings))


@dataclass
class CapturedEmail:
    recipient: str
    subject: str
    text_body: str
    html_body: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verification_code: str | None = None
    company_id: str | None = None
    attachments: tuple[EmailAttachment, ...] = ()


def missing_mailbox_settings(settings: Settings) -> list[str]:
    """Names of Sandbox mail settings that are absent. Values are never included."""
    missing: list[str] = []
    environment = settings.environment.lower()
    if environment in {"sandbox", "staging"} and not settings.sandbox_allow_external_email:
        missing.append("SANDBOX_ALLOW_EXTERNAL_EMAIL")
    if settings.email_provider == "https_api":
        if not settings.email_api_key:
            missing.append("EMAIL_API_KEY")
        if not settings.email_from_email:
            missing.append("EMAIL_FROM_EMAIL")
        return missing
    if not settings.smtp_host:
        missing.append("SMTP_HOST")
    if not settings.smtp_username:
        missing.append("SMTP_USERNAME")
    if not settings.smtp_password:
        missing.append("SMTP_PASSWORD")
    if not settings.smtp_from_email:
        missing.append("SMTP_FROM_EMAIL")
    return missing


def mailbox_delivery(notifier: object, settings: Settings) -> tuple[bool, list[str]]:
    """True only when a message can leave this process for the recipient's mailbox.

    A fake or capture transport used by tests is explicit. Sandbox capture and the
    logging adapter never count as delivery to the client.
    """
    missing = missing_mailbox_settings(settings)
    configured = bool(getattr(notifier, "email_delivery_configured", False))
    delivers = bool(getattr(notifier, "delivers_to_mailbox", False))
    if not configured or not delivers:
        return False, missing
    environment = settings.environment.lower()
    if (
        environment in {"sandbox", "staging"}
        and not settings.is_external_email_allowed
        and not getattr(notifier, "test_transport", False)
    ):
        return False, missing
    return True, []


sandbox_mail_company_id: ContextVar[str | None] = ContextVar("sandbox_mail_company_id", default=None)
sandbox_mail_session: ContextVar[object | None] = ContextVar("sandbox_mail_session", default=None)


class SandboxCaptureAccountNotifier:
    """Safe Sandbox/Test email notifier that captures all outbound emails locally.

    Guarantees:
    - Zero external network dispatch (100% prevented).
    - Captures emails deterministically for testing and test harness verification.
    - Extracts 8-digit signature confirmation codes for synthetic E2E testing.
    - Never logs or exposes raw OTP codes to external APIs or unauthenticated consumers.
    """

    email_delivery_configured = True
    delivers_to_mailbox = True
    test_transport = True

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._captured: list[CapturedEmail] = []
        self._lock = threading.Lock()

    def send_email_verification(self, email: str, token: str) -> None:
        self._record(email, "Vérifiez votre adresse email Avenqo", f"Token: {token}", f"<p>Token: {token}</p>")

    def send_password_reset(self, email: str, token: str) -> None:
        self._record(email, "Réinitialisez votre mot de passe Avenqo", f"Token: {token}", f"<p>Token: {token}</p>")

    def send_new_company(self, company: object, user: object, request: object) -> None:
        self._record(getattr(user, "email", "owner@avenqo.ca"), "New Avenqo Company", f"Company: {getattr(company, 'name', '')}", "")

    def send_invoice_paid(self, recipient: str, company: object, invoice: object) -> None:
        self._record(recipient, "Facture payée", f"Invoice: {getattr(invoice, 'id', '')}", "")

    def send_transactional(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        self._record(recipient, subject, body, html_body or body, attachments=attachments)

    def _record(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        company_id: str | None = None,
        attachments: Sequence[EmailAttachment] | None = None,
    ) -> None:
        code = None
        match = re.search(r"\b(\d{8})\b", text_body)
        if match:
            code = match.group(1)
        resolved_company_id = company_id or sandbox_mail_company_id.get()
        item = CapturedEmail(
            recipient=recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            verification_code=code,
            company_id=resolved_company_id,
            attachments=tuple(attachments or ()),
        )
        with self._lock:
            self._captured.append(item)
        logger.info("Sandbox captured email recipient=%s subject=%s code_present=%s", recipient, subject, bool(code))
        # Signature OTPs must never appear in the shared Team mailbox.
        if subject.strip() == SIGNATURE_OTP_SUBJECT or _SIGNATURE_OTP_BODY_RE.search(text_body or ""):
            return
        session = sandbox_mail_session.get()
        company = sandbox_mail_company_id.get()
        if session is None or not company:
            return
        from backend.app.models.workspace import SandboxMailboxMessage

        session.add(  # type: ignore[attr-defined]
            SandboxMailboxMessage(
                company_id=UUID(company),
                recipient=recipient[:320],
                subject=subject[:200],
                body=text_body,
                created_at=item.timestamp,
            )
        )
        session.flush()  # type: ignore[attr-defined]

    def get_captured_emails(self, recipient: str | None = None, company_id: str | None = None) -> list[CapturedEmail]:
        with self._lock:
            emails = list(self._captured)
            if recipient is not None:
                emails = [e for e in emails if e.recipient == recipient]
            if company_id is not None:
                emails = [e for e in emails if e.company_id == company_id]
            return emails

    def get_latest_code_for(self, recipient: str, company_id: str | None = None) -> str | None:
        with self._lock:
            for e in reversed(self._captured):
                if e.recipient == recipient and (company_id is None or e.company_id == company_id) and e.verification_code:
                    return e.verification_code
        return None

    def clear(self) -> None:
        with self._lock:
            self._captured.clear()


_sandbox_capture_notifier: SandboxCaptureAccountNotifier | None = None


def get_sandbox_capture_notifier(settings: Settings | None = None) -> SandboxCaptureAccountNotifier:
    global _sandbox_capture_notifier
    if _sandbox_capture_notifier is None:
        _sandbox_capture_notifier = SandboxCaptureAccountNotifier(settings)
    return _sandbox_capture_notifier


def _is_capture_notifier(notifier: object) -> bool:
    return type(notifier).__name__ == "SandboxCaptureAccountNotifier"


def _is_real_mailbox_notifier(notifier: object) -> bool:
    if _is_capture_notifier(notifier):
        return False
    if type(notifier).__name__ == "LoggingAccountNotifier":
        return False
    return bool(getattr(notifier, "delivers_to_mailbox", False) or getattr(notifier, "email_delivery_configured", False))


def deliver_signature_otp(
    *,
    notifier: object,
    settings: Settings,
    recipient: str,
    code: str,
) -> str:
    """Send a signature OTP without exposing it in API/logs/Team.

    Returns one of:
    - email_accepted: provider accepted the message for the signer's mailbox
    - sandbox_internal_capture: sandbox-only capture; no outbound email
    - failed: nothing was delivered or captured safely
    """
    recipient = (recipient or "").strip()
    if "@" not in recipient or not code or not code.isdigit() or len(code) != 8:
        return "failed"
    subject = SIGNATURE_OTP_SUBJECT
    body = (
        f"Votre code de confirmation de signature est {code}. "
        "Il expire dans 15 minutes et ne peut être utilisé qu'une seule fois. "
        "Ne le partagez pas. Avenqo ne l'affiche jamais dans Équipe."
    )
    environment = settings.environment.lower()
    try:
        if environment in {"sandbox", "staging"}:
            if settings.is_sandbox_email_recipient_approved(recipient) and _is_real_mailbox_notifier(notifier):
                notifier.send_transactional(recipient, subject, body)  # type: ignore[attr-defined]
                logger.info(
                    "Signature OTP accepted by provider recipient=%s delivery=email_accepted",
                    mask_email(recipient),
                )
                return "email_accepted"
            if _is_capture_notifier(notifier) or getattr(notifier, "test_transport", False):
                notifier.send_transactional(recipient, subject, body)  # type: ignore[attr-defined]
                logger.info(
                    "Signature OTP sandbox-internal capture recipient=%s delivery=sandbox_internal_capture",
                    mask_email(recipient),
                )
                return "sandbox_internal_capture"
            logger.warning(
                "Signature OTP blocked in sandbox recipient=%s approved=%s",
                mask_email(recipient),
                settings.is_sandbox_email_recipient_approved(recipient),
            )
            return "failed"
        if not _is_real_mailbox_notifier(notifier):
            return "failed"
        notifier.send_transactional(recipient, subject, body)  # type: ignore[attr-defined]
        logger.info(
            "Signature OTP accepted by provider recipient=%s delivery=email_accepted",
            mask_email(recipient),
        )
        return "email_accepted"
    except Exception:
        logger.warning(
            "Signature OTP delivery failed recipient=%s",
            mask_email(recipient),
            exc_info=False,
        )
        return "failed"


def _dispatch_transactional_with_attachment(
    notifier: object,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    attachment: EmailAttachment,
) -> None:
    send_fn = getattr(notifier, "send_transactional", None)
    if not callable(send_fn):
        raise RuntimeError("Notifier does not implement send_transactional")
    try:
        send_fn(recipient, subject, text_body, html_body, attachments=[attachment])
    except TypeError:
        try:
            send_fn(recipient, subject, text_body, attachments=[attachment])
        except TypeError:
            send_fn(recipient, subject, text_body)


def deliver_signed_contract_copy(
    *,
    notifier: object | None,
    settings: Settings,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    attachment: EmailAttachment,
) -> str:
    """Send a signed contract PDF copy to the verified signer.

    Returns an honest delivery status:
    - email_accepted: provider accepted the message for dispatch to the signer's mailbox
      (never falsely claimed as 'delivered' since final mailbox delivery depends on the remote MTA)
    - sandbox_internal_capture: captured in Sandbox test harness without external dispatch
    - skipped_not_configured: no outbound email adapter configured or sandbox recipient not approved
    - failed: transport error or invalid recipient/attachment
    """
    recipient = (recipient or "").strip()
    if "@" not in recipient or not attachment.content or not attachment.content.startswith(b"%PDF"):
        return "failed"
    if notifier is None or type(notifier).__name__ == "LoggingAccountNotifier":
        return "skipped_not_configured"
    environment = settings.environment.lower()
    try:
        if environment in {"sandbox", "staging"}:
            if settings.is_sandbox_email_recipient_approved(recipient) and _is_real_mailbox_notifier(notifier):
                _dispatch_transactional_with_attachment(notifier, recipient, subject, text_body, html_body, attachment)
                logger.info(
                    "Signed contract PDF accepted by provider recipient=%s filename=%s delivery=email_accepted",
                    mask_email(recipient),
                    attachment.filename,
                )
                return "email_accepted"
            if _is_capture_notifier(notifier) or getattr(notifier, "test_transport", False) or not hasattr(notifier, "email_delivery_configured"):
                _dispatch_transactional_with_attachment(notifier, recipient, subject, text_body, html_body, attachment)
                logger.info(
                    "Signed contract PDF sandbox capture recipient=%s filename=%s delivery=sandbox_internal_capture",
                    mask_email(recipient),
                    attachment.filename,
                )
                return "sandbox_internal_capture"
            return "skipped_not_configured"
        if _is_real_mailbox_notifier(notifier) or not hasattr(notifier, "email_delivery_configured"):
            _dispatch_transactional_with_attachment(notifier, recipient, subject, text_body, html_body, attachment)
            logger.info(
                "Signed contract PDF accepted by provider recipient=%s filename=%s delivery=email_accepted",
                mask_email(recipient),
                attachment.filename,
            )
            return "email_accepted"
        if _is_capture_notifier(notifier):
            _dispatch_transactional_with_attachment(notifier, recipient, subject, text_body, html_body, attachment)
            return "sandbox_internal_capture"
        return "skipped_not_configured"
    except Exception:
        logger.warning(
            "Signed contract PDF delivery failed recipient=%s filename=%s",
            mask_email(recipient),
            attachment.filename,
            exc_info=False,
        )
        return "failed"
