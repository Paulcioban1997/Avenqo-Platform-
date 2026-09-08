from cryptography.fernet import Fernet
import pytest

from backend.app.services.connector_secret_cipher import (
    ConnectorSecretCipher,
    ConnectorSecretError,
)


def test_connector_credentials_are_encrypted_and_round_trip() -> None:
    cipher = ConnectorSecretCipher([Fernet.generate_key().decode("ascii")])
    credentials = {
        "access_token": "shpat_sensitive",
        "refresh_token": "shprt_sensitive",
    }

    encrypted = cipher.encrypt(credentials)

    assert "shpat_sensitive" not in encrypted
    assert cipher.decrypt(encrypted) == credentials


def test_connector_key_rotation_can_read_previous_ciphertext() -> None:
    previous_key = Fernet.generate_key().decode("ascii")
    current_key = Fernet.generate_key().decode("ascii")
    encrypted = ConnectorSecretCipher([previous_key]).encrypt({"access_token": "token"})

    assert ConnectorSecretCipher([current_key, previous_key]).decrypt(encrypted) == {
        "access_token": "token"
    }


def test_connector_cipher_rejects_missing_or_wrong_keys() -> None:
    with pytest.raises(ConnectorSecretError, match="not configured"):
        ConnectorSecretCipher([])

    encrypted = ConnectorSecretCipher(
        [Fernet.generate_key().decode("ascii")]
    ).encrypt({"access_token": "token"})
    with pytest.raises(ConnectorSecretError, match="cannot be decrypted"):
        ConnectorSecretCipher([Fernet.generate_key().decode("ascii")]).decrypt(encrypted)