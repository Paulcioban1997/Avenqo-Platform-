"""Service de défis et jetons de signature électronique à usage unique (anti-rejeu)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import BaseModel


class SigningChallenge(BaseModel):
    challenge_id: str
    company_id: UUID
    user_id: UUID
    contract_type: str
    code: str
    expires_at: datetime
    used: bool = False


# Cache mémoire sécurisé pour les défis de signature de session
_CHALLENGES: dict[str, SigningChallenge] = {}


class SigningChallengeService:
    """Émet et valide les jetons de signature électronique à usage unique."""

    TTL_MINUTES = 15

    @classmethod
    def create_challenge(
        cls,
        company_id: UUID,
        user_id: UUID,
        contract_type: str,
    ) -> SigningChallenge:
        # Purge des défis expirés
        now = datetime.now(timezone.utc)
        expired_keys = [k for k, c in _CHALLENGES.items() if c.expires_at < now or c.used]
        for k in expired_keys:
            _CHALLENGES.pop(k, None)

        challenge_id = secrets.token_urlsafe(24)
        # Code de confirmation à 6 chiffres
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = now + timedelta(minutes=cls.TTL_MINUTES)

        challenge = SigningChallenge(
            challenge_id=challenge_id,
            company_id=company_id,
            user_id=user_id,
            contract_type=contract_type,
            code=code,
            expires_at=expires_at,
            used=False,
        )
        _CHALLENGES[challenge_id] = challenge
        return challenge

    @classmethod
    def verify_and_consume_challenge(
        cls,
        challenge_id: str,
        code: str,
        company_id: UUID,
        user_id: UUID,
        contract_type: str,
    ) -> bool:
        challenge = _CHALLENGES.get(challenge_id)
        if not challenge:
            return False

        now = datetime.now(timezone.utc)
        if challenge.expires_at < now:
            _CHALLENGES.pop(challenge_id, None)
            return False

        if challenge.used:
            return False

        # Vérification stricte des correspondances d'identité
        if (
            challenge.company_id != company_id
            or challenge.user_id != user_id
            or challenge.contract_type != contract_type
            or not secrets.compare_digest(challenge.code, code.strip())
        ):
            return False

        # Consommation immédiate (anti-rejeu)
        challenge.used = True
        return True
