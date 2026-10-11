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
            ciphers = [Fernet(key.encode("ascii")) for key in keys]
            self._primary = ciphers[0]
            self._cipher = MultiFernet(ciphers)
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

    def rotate(self, encrypted_payload: str) -> str:
        """Re-encrypt with the primary key, preserving Fernet's original timestamp."""
        original = self.decrypt(encrypted_payload)
        try:
            rotated = self._cipher.rotate(encrypted_payload.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError, ValueError, TypeError):
            raise ConnectorSecretError("Connector credentials cannot be rotated") from None
        if self.decrypt(rotated) != original:
            raise ConnectorSecretError("Connector credential rotation verification failed")
        return rotated

    def uses_primary_key(self, encrypted_payload: str) -> bool:
        try:
            self._primary.decrypt(encrypted_payload.encode("ascii"))
            return True
        except (InvalidToken, UnicodeError, ValueError, TypeError):
            return False
