from uuid import UUID, uuid4
import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.models import Base, User
from backend.app.services.mfa_secret_rotation import rotate_mfa_secrets


def fixture_users(db, key):
    rows = [User(id=UUID(int=(0xa << 124) + index + 1), company_id=uuid4(), first_name='Fixture', last_name='MFA',
        email=f'mfa-{index}@example.invalid', password_hash='unused-test-hash', mfa_enabled=True,
        mfa_recovery_hashes='["fixture-recovery-hash"]',
        mfa_secret_encrypted=Fernet(key).encrypt(b'fixture-totp-material').decode()) for index in range(2)]
    db.add_all(rows); db.commit()
    return rows


def test_mfa_dry_run_and_rotation_preserve_enrollment_and_recovery():
    old,new=(Fernet.generate_key().decode() for _ in range(2))
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        rows=fixture_users(db,old);original=[row.mfa_secret_encrypted for row in rows]
        assert rotate_mfa_secrets(db,[new,old])['needs_rotation']==2
        db.rollback();db.expire_all()
        assert [row.mfa_secret_encrypted for row in rows]==original
        assert rotate_mfa_secrets(db,[new,old],apply=True)['rotated']==2
        db.commit();db.expire_all()
        for row in rows:
            assert row.mfa_enabled and row.mfa_recovery_hashes=='["fixture-recovery-hash"]'
            assert Fernet(new).decrypt(row.mfa_secret_encrypted.encode())==b'fixture-totp-material'
            with pytest.raises(InvalidToken):Fernet(old).decrypt(row.mfa_secret_encrypted.encode())
        assert rotate_mfa_secrets(db,[new],apply=True)['rotated']==0


def test_unreadable_second_mfa_rolls_back_first_update():
    old,new,unrelated=(Fernet.generate_key().decode() for _ in range(3))
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        rows=fixture_users(db,old)
        rows[1].mfa_secret_encrypted=Fernet(unrelated).encrypt(b'other').decode();db.commit()
        before=rows[0].mfa_secret_encrypted
        with pytest.raises(InvalidToken):rotate_mfa_secrets(db,[new,old],apply=True)
        db.rollback();db.expire_all()
        assert rows[0].mfa_secret_encrypted==before
