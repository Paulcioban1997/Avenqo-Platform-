"""Database-backed, single-use contract signing challenges."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.app.models.contract_signing_challenge import ContractSigningChallenge


class SigningChallengeService:
    TTL_MINUTES = 15
    MAX_ATTEMPTS = 5
    ACTION = "ELECTRONIC_SIGN"

    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def snapshot_hash(value: object) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _code_hash(code: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), 150_000).hex()

    def create_challenge(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        contract_id: UUID,
        contract_version: str,
        content_hash: str,
        commercial_hash: str,
    ) -> tuple[ContractSigningChallenge, str]:
        code = f"{secrets.randbelow(100_000_000):08d}"
        salt = secrets.token_hex(16)
        challenge = ContractSigningChallenge(
            company_id=company_id,
            user_id=user_id,
            contract_id=contract_id,
            contract_version=contract_version,
            content_hash=content_hash,
            commercial_hash=commercial_hash,
            action=self.ACTION,
            code_hash=self._code_hash(code, salt),
            salt=salt,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=self.TTL_MINUTES),
        )
        self._db.add(challenge)
        self._db.flush()
        return challenge, code

    def verify_and_consume_challenge(
        self,
        *,
        challenge_id: UUID,
        code: str,
        company_id: UUID,
        user_id: UUID,
        contract_id: UUID,
        contract_version: str,
        content_hash: str,
        commercial_hash: str,
    ) -> bool:
        challenge = self._db.get(ContractSigningChallenge, challenge_id)
        if challenge is None or not code or not code.isdigit() or len(code) != 8:
            return False
        now = datetime.now(timezone.utc)
        digest = self._code_hash(code, challenge.salt)
        bound = (
            challenge.company_id == company_id
            and challenge.user_id == user_id
            and challenge.contract_id == contract_id
            and challenge.contract_version == contract_version
            and challenge.content_hash == content_hash
            and challenge.commercial_hash == commercial_hash
            and challenge.action == self.ACTION
        )
        if not bound:
            return False
        # The conditional SQL update can succeed only once across PostgreSQL workers.
        stmt = update(ContractSigningChallenge).where(
            ContractSigningChallenge.id == challenge_id,
            ContractSigningChallenge.used_at.is_(None),
            ContractSigningChallenge.expires_at > now,
            ContractSigningChallenge.attempts < self.MAX_ATTEMPTS,
        ).execution_options(synchronize_session=False)
        if secrets.compare_digest(challenge.code_hash, digest):
            result = self._db.execute(stmt.values(used_at=now))
            return result.rowcount == 1
        self._db.execute(stmt.values(attempts=ContractSigningChallenge.attempts + 1))
        self._db.commit()
        return False
