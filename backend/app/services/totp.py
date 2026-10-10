"""TOTP RFC 6238 sans dépendance externe."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _normalize_secret(secret: str) -> bytes:
    padded = secret.strip().upper()
    padded += "=" * ((8 - len(padded) % 8) % 8)
    return base64.b32decode(padded, casefold=True)


def totp_code(secret: str, *, for_time: int | None = None, step: int = 30, digits: int = 6) -> str:
    counter = int((for_time if for_time is not None else time.time()) // step)
    digest = hmac.new(_normalize_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % (10 ** digits):0{digits}d}"


def verify_totp(secret: str, code: str, *, window: int = 1) -> bool:
    candidate = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(candidate) != 6:
        return False
    now = int(time.time())
    for drift in range(-window, window + 1):
        if hmac.compare_digest(totp_code(secret, for_time=now + drift * 30), candidate):
            return True
    return False


def provisioning_uri(secret: str, email: str, issuer: str = "Avenqo") -> str:
    return (
        f"otpauth://totp/{issuer}:{email}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    )


def _mfa_fernet():
    import base64
    import hashlib

    from cryptography.fernet import Fernet

    from backend.app.config.settings import get_settings

    material = hashlib.sha256(get_settings().auth_jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_mfa_secret(secret: str) -> str:
    return _mfa_fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_mfa_secret(token: str) -> str:
    return _mfa_fernet().decrypt(token.encode("ascii")).decode("ascii")
