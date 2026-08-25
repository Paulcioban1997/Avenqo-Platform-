"""FrontiÃ¨re d'envoi des emails liÃ©s au compte."""

from email.message import EmailMessage
import logging
import smtplib
from typing import Protocol
from urllib.parse import urlencode

from backend.app.config.settings import Settings

logger = logging.getLogger(__name__)


class AccountNotifier(Protocol):
    def send_email_verification(self, email: str, token: str) -> None: ...
    def send_password_reset(self, email: str, token: str) -> None: ...

    def send_new_company(self, company: object, user: object, request: object) -> None: ...


class LoggingAccountNotifier:
    """Adaptateur local lorsque SMTP n'est pas configurÃ©."""

    def send_email_verification(self, email: str, token: str) -> None:
        logger.info("Email de vÃ©rification demandÃ© pour %s", email)

    def send_password_reset(self, email: str, token: str) -> None:
        logger.info("RÃ©initialisation de mot de passe demandÃ©e pour %s", email)

    def send_new_company(self, company: object, user: object, request: object) -> None:
        logger.info("Nouvelle entreprise Avenqo enregistrÃ©e")


class SMTPAccountNotifier:
    """Envoie les liens de compte avec le serveur SMTP configurÃ©."""

    def __init__(self, settings: Settings) -> None:
        if settings.smtp_host is None:
            raise ValueError("SMTP_HOST est requis")
        self._settings = settings

    def send_email_verification(self, email: str, token: str) -> None:
        link = self._account_link("/verify-email", token)
        self._send(
            email,
            "VÃ©rifiez votre adresse email Avenqo",
            f"Bienvenue sur Avenqo. VÃ©rifiez votre adresse email : {link}",
        )

    def send_password_reset(self, email: str, token: str) -> None:
        link = self._account_link("/reset-password", token)
        self._send(
            email,
            "RÃ©initialisez votre mot de passe Avenqo",
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
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port) as server:
            if self._settings.smtp_use_tls:
                server.starttls()
            if self._settings.smtp_username and self._settings.smtp_password:
                server.login(self._settings.smtp_username, self._settings.smtp_password)
            server.send_message(message)
