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


class LoggingAccountNotifier:
    """Adaptateur local lorsque SMTP n'est pas configurÃ©."""

    def send_email_verification(self, email: str, token: str) -> None:
        logger.info("Email de vÃ©rification demandÃ© pour %s", email)

    def send_password_reset(self, email: str, token: str) -> None:
        logger.info("RÃ©initialisation de mot de passe demandÃ©e pour %s", email)


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
