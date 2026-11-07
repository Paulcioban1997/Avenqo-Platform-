"""Service cryptographique de génération et validation de jetons de téléchargement sécurisés.

Garantit :
1. Clé de signature dédiée dérivée par HMAC-SHA256 (isolation cryptographique distincte du JWT d'auth).
2. Liaison stricte à l'entreprise (company_id) et à l'utilisateur (user_id).
3. Expiration courte (par défaut 15 minutes / 900 secondes).
4. Protection contre la réutilisation arbitraire ou les accès croisés multi-tenant.
5. Protection distribuée contre les attaques par rejeu (consommation unique / nonce tracking en PostgreSQL).
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
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.models.secure_download_nonce import SecureDownloadNonce

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
    """Génère et valide des jetons éphémères de téléchargement documentaire avec anti-rejeu distribué."""

    # Registre mémoire de secours (uniquement si aucune session de base de données n'est passée)
    _in_memory_nonces: dict[str, float] = {}

    def __init__(self, secret_key: str | None = None) -> None:
        settings = get_settings()
        master = secret_key or settings.auth_jwt_secret
        self._secret = _derive_download_secret(master)

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
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Vérifie la validité, l'intégrité et les correspondances de sécurité du jeton.
        
        Ne consomme pas le jeton : la rédemption atomique s'effectue après validation
        complète des droits et préparation du fichier via `redeem_download_nonce_atomic`.
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

        # Pré-vérification anti-rejeu (rapide)
        if db is not None:
            existing = db.scalar(select(SecureDownloadNonce.id).where(SecureDownloadNonce.nonce == nonce))
            if existing is not None:
                raise InvalidSecureTokenError("Ce jeton de téléchargement a déjà été utilisé (anti-rejeu).")
        else:
            if nonce in self._in_memory_nonces:
                raise InvalidSecureTokenError("Ce jeton de téléchargement a déjà été utilisé (anti-rejeu).")

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
                "nonce": nonce,
                "exp": exp,
            }
        except (ValueError, KeyError) as exc:
            raise InvalidSecureTokenError("Identifiants de document invalides dans le jeton") from exc

    def redeem_download_nonce_atomic(
        self,
        db: Session,
        *,
        nonce: str,
        company_id: UUID,
        user_id: UUID,
        doc_id: UUID,
        doc_type: str,
        expires_at: datetime,
    ) -> None:
        """Consomme le jeton de façon atomique et distribuée dans PostgreSQL.

        Garantit :
        - Consommation unique même en cas d'appels simultanés/concurrents.
        - Persistance après redémarrage des instances Railway.
        - Nettoyage automatique des nonces expirés.
        - ZÉRO fallback mémoire sur le chemin de production (DB obligatoire).
        """
        if db is None:
            raise RuntimeError(
                "Une session de base de données PostgreSQL active est strictement requise pour l'anti-rejeu distribué."
            )

        now = datetime.now(timezone.utc)

        # 1. Nettoyage opportuniste des nonces expirés
        try:
            db.execute(delete(SecureDownloadNonce).where(SecureDownloadNonce.expires_at < now))
        except Exception:
            pass  # Ne bloque jamais le flux principal

        # 2. Insertion atomique sous contrainte UNIQUE sur nonce
        record = SecureDownloadNonce(
            nonce=nonce,
            company_id=company_id,
            user_id=user_id,
            doc_id=doc_id,
            doc_type=doc_type,
            expires_at=expires_at,
            redeemed_at=now,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            logger.warning("download_token_replay_blocked nonce=%s", nonce)
            raise InvalidSecureTokenError("Ce jeton de téléchargement a déjà été utilisé (anti-rejeu).") from exc
