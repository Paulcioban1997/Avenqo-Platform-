"""Service cryptographique de génération et validation de jetons de téléchargement sécurisés.

Garantit :
1. Clé de signature dédiée dérivée par HMAC-SHA256 (isolation cryptographique distincte du JWT d'auth).
2. Liaison stricte à l'entreprise (company_id) et à l'utilisateur (user_id).
3. Expiration courte (par défaut 15 minutes / 900 secondes).
4. Protection contre la réutilisation arbitraire ou les accès croisés multi-tenant.
5. Protection contre les attaques par rejeu (consommation unique / nonce tracking).
6. Limites de taille de jeton (protection anti-DDoS / mémoire).
7. Confidentialité des logs (masquage systématique des jetons).
8. Zéro accès S3 public.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from uuid import UUID, uuid4

from backend.app.config.settings import get_settings

logger = logging.getLogger("avenqo.secure_downloads.token")

MAX_TOKEN_LENGTH = 2048
DOWNLOAD_TOKEN_PURPOSE_SALT = b"avenqo-secure-document-download-key-v1"


class SecureTokenError(Exception):
    """Erreur de base pour les jetons de téléchargement sécurisés."""
    pass


class InvalidSecureTokenError(SecureTokenError):
    """Signature invalide, jeton corrompu ou taille excessive."""
    pass


class ExpiredSecureTokenError(SecureTokenError):
    """Le jeton a dépassé sa durée de validité."""
    pass


class UnauthorizedSecureTokenError(SecureTokenError):
    """Tentative d'accès par un autre utilisateur ou un autre tenant."""
    pass


def mask_token(token: str) -> str:
    """Masque un jeton pour journalisation sécurisée sans fuite de secret."""
    if not token or len(token) <= 12:
        return "***"
    return f"{token[:6]}...{token[-6:]}"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def _derive_download_secret(master_secret: str) -> bytes:
    """Dérive cryptographiquement une clé dédiée exclusivement aux téléchargements.
    
    Évite de réutiliser directement le secret JWT principal pour compartimenter l'impact.
    """
    return hmac.new(
        master_secret.encode("utf-8"),
        DOWNLOAD_TOKEN_PURPOSE_SALT,
        hashlib.sha256,
    ).digest()


class SecureDocumentTokenService:
    """Génère et valide des jetons éphémères de téléchargement documentaire."""

    # Registre partagé en mémoire des nonces consommés pour empêcher le rejeu
    _redeemed_nonces: dict[str, float] = {}

    def __init__(self, secret_key: str | None = None) -> None:
        settings = get_settings()
        master = secret_key or settings.auth_jwt_secret
        self._secret = _derive_download_secret(master)

    @classmethod
    def _prune_expired_nonces(cls, now: float) -> None:
        """Nettoie les nonces dont la date d'expiration est révolue."""
        if len(cls._redeemed_nonces) > 500:
            cls._redeemed_nonces = {
                nonce: exp for nonce, exp in cls._redeemed_nonces.items() if exp > now
            }

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

        token = f"{payload_b64}.{sig_b64}"
        logger.debug(
            "download_token_generated company_id=%s doc_id=%s type=%s token=%s",
            company_id,
            doc_id,
            doc_type,
            mask_token(token),
        )
        return token

    def verify_download_token(
        self,
        token: str,
        *,
        current_company_id: UUID,
        current_user_id: UUID,
        mark_as_used: bool = True,
    ) -> dict[str, Any]:
        """Vérifie la validité, l'intégrité et les correspondances de sécurité du jeton.
        
        Garanties :
        - Taille maximale bornée (MAX_TOKEN_LENGTH).
        - Signature cryptographique dédiée vérifiée en temps constant.
        - Vérification d'expiration.
        - Isolation multi-tenant stricte (company_id et user_id).
        - Protection optionnelle anti-rejeu (nonce unique).
        """
        if not token or len(token) > MAX_TOKEN_LENGTH:
            raise InvalidSecureTokenError(f"Taille de jeton invalide (limite {MAX_TOKEN_LENGTH} octets)")

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
        exp = payload.get("exp", 0)
        if exp < now:
            raise ExpiredSecureTokenError("Jeton de téléchargement expiré")

        nonce = payload.get("nonce")
        if not nonce:
            raise InvalidSecureTokenError("Jeton sans identifiant unique (nonce manquant)")

        # Vérification anti-rejeu
        if nonce in self._redeemed_nonces:
            raise InvalidSecureTokenError("Ce jeton de téléchargement a déjà été utilisé (anti-rejeu).")

        token_company_id = payload.get("company_id")
        token_user_id = payload.get("user_id")

        if token_company_id != str(current_company_id):
            raise UnauthorizedSecureTokenError("Jeton non autorisé pour cette entreprise (isolation tenant violée)")

        if token_user_id != str(current_user_id):
            raise UnauthorizedSecureTokenError("Jeton non autorisé pour cet utilisateur")

        if mark_as_used:
            self._prune_expired_nonces(float(now))
            self._redeemed_nonces[nonce] = float(exp)

        try:
            return {
                "company_id": UUID(token_company_id),
                "user_id": UUID(token_user_id),
                "doc_id": UUID(payload["doc_id"]),
                "doc_type": payload["doc_type"],
                "filename": payload.get("filename", "document.pdf"),
                "nonce": nonce,
            }
        except (ValueError, KeyError) as exc:
            raise InvalidSecureTokenError("Identifiants de document invalides dans le jeton") from exc
