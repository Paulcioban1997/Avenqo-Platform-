"""Client Resend pour les envois transactionnels Avenqo."""

from __future__ import annotations

from email.utils import formataddr
import json
import logging
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.app.config.settings import Settings

logger = logging.getLogger(__name__)

RESEND_EMAIL_API_URL = "https://api.resend.com/emails"
_HTTPS_TIMEOUT_SECONDS = 12
TEMPORARY_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class TemporaryEmailDeliveryError(Exception):
    """Erreur d'envoi temporaire : la file peut réessayer sans créer de doublon."""


class PermanentEmailDeliveryError(Exception):
    """Le fournisseur a rejeté l'envoi de façon définitive."""


class QuoteMailer(Protocol):
    def send(
        self,
        *,
        to: list[str],
        subject: str,
        text_body: str,
        html_body: str,
        idempotency_key: str,
    ) -> str: ...


class ResendQuoteMailer:
    """Envoie un email via l'API HTTPS Resend et exige une acceptation 2xx."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.transactional_email_api_key
        self._from_email = settings.email_from_email
        self._from_name = settings.email_from_name

    def send(
        self,
        *,
        to: list[str],
        subject: str,
        text_body: str,
        html_body: str,
        idempotency_key: str,
    ) -> str:
        if not self._api_key:
            raise PermanentEmailDeliveryError("Transactional email API is not configured")
        payload = json.dumps(
            {
                "from": formataddr((self._from_name, self._from_email)),
                "to": to,
                "subject": subject,
                "text": text_body,
                "html": html_body,
            }
        ).encode("utf-8")
        request = Request(
            RESEND_EMAIL_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key[:256],
                "User-Agent": "Avenqo-Backend/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=_HTTPS_TIMEOUT_SECONDS) as response:
                status_code = response.status
                raw = response.read()
        except HTTPError as exc:
            self._raise_http_error(exc)
        except (URLError, OSError, TimeoutError) as exc:
            logger.warning("Resend transport failed error_type=%s", type(exc).__name__)
            raise TemporaryEmailDeliveryError("Transactional email API is temporarily unavailable") from exc

        if not 200 <= status_code < 300:
            if status_code in TEMPORARY_STATUS_CODES:
                raise TemporaryEmailDeliveryError(f"Transactional email API returned {status_code}")
            raise PermanentEmailDeliveryError(f"Transactional email API rejected the request ({status_code})")
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise PermanentEmailDeliveryError("Transactional email API returned an invalid payload") from exc
        message_id = str(body.get("id") or "").strip()
        if not message_id:
            raise PermanentEmailDeliveryError("Transactional email API did not confirm a message id")
        return message_id

    @staticmethod
    def _raise_http_error(exc: HTTPError) -> None:
        status_code = int(getattr(exc, "code", 0) or 0)
        logger.warning("Resend HTTP error status=%s", status_code)
        if status_code in TEMPORARY_STATUS_CODES or status_code == 0:
            raise TemporaryEmailDeliveryError(f"Transactional email API returned {status_code}") from exc
        raise PermanentEmailDeliveryError(f"Transactional email API rejected the request ({status_code})") from exc
