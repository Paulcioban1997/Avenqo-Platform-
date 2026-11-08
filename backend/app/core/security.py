"""Primitives de sécurité courtes et indépendantes de FastAPI."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from backend.app.config.settings import get_settings

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hache un mot de passe avec Argon2."""

    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Compare un mot de passe sans exposer son empreinte."""

    return _password_hash.verify(password, password_hash)


def generate_token() -> str:
    """Génère un secret suffisamment long pour une session ou un email."""

    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Retourne l'empreinte persistable d'un jeton brut."""

    return sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: UUID,
    company_id: UUID,
    session_id: UUID,
) -> tuple[str, datetime]:
    """Signe un JWT court lié à un utilisateur, un tenant et une session."""

    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.auth_access_minutes)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(company_id),
        "session_id": str(session_id),
        "jti": str(uuid4()),
        "iat": now,
        "exp": expires_at,
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "type": "access",
    }
    token = jwt.encode(
        payload,
        settings.auth_jwt_secret,
        algorithm=settings.auth_jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(token: str) -> dict[str, object]:
    """Valide la signature, l'expiration et le type d'un JWT d'accès.

    Supporte la rotation zéro-downtime via auth_jwt_secret_fallback :
    si le secret principal échoue, la clé de repli est vérifiée.
    """

    settings = get_settings()
    secrets_to_try = [settings.auth_jwt_secret]
    fallback = getattr(settings, "auth_jwt_secret_fallback", None)
    if fallback and fallback.strip() and fallback.strip() != settings.auth_jwt_secret:
        secrets_to_try.append(fallback.strip())

    last_error: Exception | None = None
    for secret in secrets_to_try:
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[settings.auth_jwt_algorithm],
                issuer=settings.auth_jwt_issuer,
                audience=settings.auth_jwt_audience,
                options={
                    "require": [
                        "sub",
                        "tenant_id",
                        "session_id",
                        "iat",
                        "exp",
                        "iss",
                        "aud",
                        "type",
                    ]
                },
            )
            if payload.get("type") != "access":
                raise ValueError("Type de jeton invalide")
            return payload
        except InvalidTokenError as exc:
            last_error = exc

    raise ValueError("Jeton d'accès invalide ou expiré") from last_error