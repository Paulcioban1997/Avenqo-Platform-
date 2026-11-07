"""Service cryptographique de génération et validation de jetons de téléchargement sécurisés.

Garantit :
1. Signature HMAC-SHA256 inviolable basée sur auth_jwt_secret.
2. Liaison stricte à l'entreprise (company_id) et à l'utilisateur (user_id).
3. Expiration courte (par défaut 15 minutes / 900 secondes).
4. Protection contre la réutilisation arbitraire ou les accès croisés multi-tenant.
5. Zéro accès S3 public.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID, uuid4

from backend.app.config.settings import get_settings


class SecureTokenError(Exception):
    """Erreur de base pour les jetons de téléchargement sécurisés."""
    pass


class InvalidSecureTokenError(SecureTokenError):
    """Signature invalide ou jeton corrompu."""
    pass


class ExpiredSecureTokenError(SecureTokenError):
    """Le jeton a dépassé sa durée de validité."""
    pass


class UnauthorizedSecureTokenError(SecureTokenError):
    """Tentative d'accès par un autre utilisateur ou un autre tenant."""
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


class SecureDocumentTokenService:
    """Génère et valide des jetons éphémères de téléchargement documentaire."""

    def __init__(self, secret_key: str | None = None) -> None:
        settings = get_settings()
        self._secret = (secret_key or settings.auth_jwt_secret).encode("utf-8")

    def generate_download_token(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        doc_id: UUID,
        doc_type: str,
        filename: str,
        expires_in_seconds: int = 900,
    ) -> str:
        """Génère un jeton HMAC-SHA256 signé pour un document donné."""
        now = int(time.time())
        payload = {
            "company_id": str(company_id),
            "user_id": str(user_id),
            "doc_id": str(doc_id),
            "doc_type": doc_type,
            "filename": filename,
            "iat": now,
            "exp": now + expires_in_seconds,
            "nonce": uuid4().hex,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = _b64url_encode(payload_bytes)

        signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        sig_b64 = _b64url_encode(signature)

        return f"{payload_b64}.{sig_b64}"

    def verify_download_token(
        self,
        token: str,
        *,
        current_company_id: UUID,
        current_user_id: UUID,
    ) -> dict[str, Any]:
        """Vérifie la validité, l'intégrité et les correspondances de sécurité du jeton.
        
        Lève :
            InvalidSecureTokenError : si la signature est incorrecte.
            ExpiredSecureTokenError : si le jeton a expiré.
            UnauthorizedSecureTokenError : si company_id ou user_id ne correspondent pas.
        """
        parts = token.split(".")
        if len(parts) != 2:
            raise InvalidSecureTokenError("Format de jeton invalide")

        payload_b64, sig_b64 = parts[0], parts[1]

        try:
            payload_bytes = _b64url_decode(payload_b64)
            provided_sig = _b64url_decode(sig_b64)
        except Exception as exc:
            raise InvalidSecureTokenError("Décodage de jeton impossible") from exc

        expected_sig = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise InvalidSecureTokenError("Signature de jeton invalide")

        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:
            raise InvalidSecureTokenError("Charge utile JSON corrompue") from exc

        now = int(time.time())
        if payload.get("exp", 0) < now:
            raise ExpiredSecureTokenError("Jeton de téléchargement expiré")

        token_company_id = payload.get("company_id")
        token_user_id = payload.get("user_id")

        if token_company_id != str(current_company_id):
            raise UnauthorizedSecureTokenError("Jeton non autorisé pour cette entreprise (isolation tenant violée)")

        if token_user_id != str(current_user_id):
            raise UnauthorizedSecureTokenError("Jeton non autorisé pour cet utilisateur")

        try:
            return {
                "company_id": UUID(token_company_id),
                "user_id": UUID(token_user_id),
                "doc_id": UUID(payload["doc_id"]),
                "doc_type": payload["doc_type"],
                "filename": payload.get("filename", "document.pdf"),
            }
        except (ValueError, KeyError) as exc:
            raise InvalidSecureTokenError("Identifiants de document invalides dans le jeton") from exc
