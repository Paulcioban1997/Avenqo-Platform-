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

from backend.app.config.settings import Settings

logger = logging.getLogger(__name__)
_SMTP_CONNECTION_TIMEOUT_SECONDS = 10
_HTTPS_CONNECTION_TIMEOUT_SECONDS = 10
_RESEND_EMAIL_API_URL = "https://api.resend.com/emails"


class AccountNotifier(Protocol):
    email_delivery_configured: bool

    def send_email_verification(self, email: str, token: str) -> None: ...
    def send_password_reset(self, email: str, token: str) -> None: ...

    def send_new_company(self, company: object, user: object, request: object) -> None: ...


class EmailTransport(Protocol):
    def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None: ...


class LoggingAccountNotifier:
    """Adaptateur local lorsque la livraison d'email n'est pas configurée."""

    email_delivery_configured = False

    def send_email_verification(self, email: str, token: str) -> None:
        logger.info("Email de vérification demandé")

    def send_password_reset(self, email: str, token: str) -> None:
        logger.info("Réinitialisation de mot de passe demandée")

    def send_new_company(self, company: object, user: object, request: object) -> None:
        logger.info("Nouvelle entreprise Avenqo enregistrée")


class AccountNotificationService:
    """Construit les notifications de compte indépendamment du transport."""

    email_delivery_configured = True

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

    def _account_link(self, path: str, token: str) -> str:
        base_url = self._settings.frontend_url.rstrip("/")
        return f"{base_url}{path}?{urlencode({'token': token})}"

    def _send(self, recipient: str, subject: str, body: str) -> None:
        html_body = "<p>" + escape(body).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
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
    ) -> None:
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

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
        self._api_key = settings.email_api_key
        self._from_email = settings.email_from_email
        self._from_name = settings.email_from_name

    def send(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        payload = json.dumps(
            {
                "from": formataddr((self._from_name, self._from_email)),
                "to": [recipient],
                "subject": subject,
                "text": text_body,
                "html": html_body,
            }
        ).encode("utf-8")
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
                if not 200 <= status_code < 300:
                    raise RuntimeError("Transactional email API rejected the request")
        except (HTTPError, URLError, OSError, RuntimeError) as exc:
            logger.warning(
                "HTTPS email delivery failed status=%s error_type=%s",
                getattr(exc, "code", None),
                type(exc).__name__,
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


class HTTPSAccountNotifier(AccountNotificationService):
    """Notifications de compte livrées par API HTTPS transactionnelle."""

    def __init__(self, settings: Settings) -> None:
        if not settings.https_email_delivery_configured:
            raise ValueError(
                "API email HTTPS non configurée : définir la clé et l'expéditeur"
            )
        super().__init__(settings, ResendHTTPSEmailTransport(settings))
