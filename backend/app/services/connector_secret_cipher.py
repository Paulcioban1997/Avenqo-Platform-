"""Authenticated encryption for backend-only connector credentials."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class ConnectorSecretError(RuntimeError):
    pass


class ConnectorSecretCipher:
    """Encrypt with the first key and decrypt with any configured rotation key."""

    def __init__(self, keys: Sequence[str]) -> None:
        if not keys:
            raise ConnectorSecretError("Connector encryption is not configured")
        try:
            self._cipher = MultiFernet([Fernet(key.encode("ascii")) for key in keys])
        except (ValueError, UnicodeEncodeError) as exc:
            raise ConnectorSecretError("Connector encryption key is invalid") from exc

    def encrypt(self, payload: Mapping[str, Any]) -> str:
        serialized = json.dumps(
            dict(payload),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return self._cipher.encrypt(serialized).decode("ascii")

    def decrypt(self, encrypted_payload: str) -> dict[str, Any]:
        try:
            serialized = self._cipher.decrypt(encrypted_payload.encode("ascii"))
            payload = json.loads(serialized.decode("utf-8"))
        except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
            raise ConnectorSecretError("Connector credentials cannot be decrypted") from exc
        if not isinstance(payload, dict):
            raise ConnectorSecretError("Connector credentials have an invalid format")
        return payload