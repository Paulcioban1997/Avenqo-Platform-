"""Separate MFA encryption from JWT signing without losing enrolled accounts."""
from types import SimpleNamespace
import secrets
import pytest
from cryptography.fernet import Fernet, InvalidToken
from backend.app.services import totp
from backend.app.config.settings import Settings


def test_explicit_mfa_ring_preserves_legacy_and_allows_jwt_rotation(monkeypatch):
    import base64
    import hashlib
    signing = secrets.token_urlsafe(48)
    legacy = base64.urlsafe_b64encode(hashlib.sha256(signing.encode()).digest()).decode()
    next_key = Fernet.generate_key().decode()
    current = SimpleNamespace(auth_jwt_secret=signing, mfa_encryption_keys=[])
    monkeypatch.setattr('backend.app.config.settings.get_settings', lambda: current)
    secret = totp.generate_totp_secret()
    old_token = totp.encrypt_mfa_secret(secret)
    current.auth_jwt_secret = secrets.token_urlsafe(48)
    current.mfa_encryption_keys = [next_key, legacy]
    assert totp.decrypt_mfa_secret(old_token) == secret
    rotated = totp.rotate_mfa_secret(old_token)
    assert Fernet(next_key).decrypt(rotated.encode()).decode() == secret
    with pytest.raises(InvalidToken):
        Fernet(legacy).decrypt(rotated.encode())
    current.mfa_encryption_keys = [next_key]
    assert totp.decrypt_mfa_secret(rotated) == secret
    with pytest.raises(InvalidToken):
        totp.decrypt_mfa_secret(old_token)


def test_mfa_rotation_requires_explicit_ring(monkeypatch):
    current = SimpleNamespace(auth_jwt_secret=secrets.token_urlsafe(48), mfa_encryption_keys=[])
    monkeypatch.setattr('backend.app.config.settings.get_settings', lambda: current)
    with pytest.raises(ValueError, match='Explicit MFA'):
        totp.rotate_mfa_secret(totp.encrypt_mfa_secret(totp.generate_totp_secret()))


@pytest.mark.parametrize('encoding', ['csv', 'json'])
def test_mfa_settings_accept_rotation_key_ring(encoding):
    import json
    keys = [Fernet.generate_key().decode(), Fernet.generate_key().decode()]
    encoded = ','.join(keys) if encoding == 'csv' else json.dumps(keys)
    settings = Settings(_env_file=None, ENVIRONMENT='test', MFA_ENCRYPTION_KEYS=encoded)
    assert settings.mfa_encryption_keys == keys
