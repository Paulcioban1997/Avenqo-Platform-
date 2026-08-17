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
    """Valide la signature, l'expiration et le type d'un JWT d'accès."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
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
    except InvalidTokenError as exc:
        raise ValueError("Jeton d'accès invalide ou expiré") from exc
    if payload.get("type") != "access":
        raise ValueError("Type de jeton invalide")
    return payload