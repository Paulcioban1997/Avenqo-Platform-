"""Rate limiting technique de base (Phase 34).

Fenêtre glissante simple, en mémoire, par processus. Limitation connue et
documentée : non partagé entre plusieurs workers/instances (voir
docs/production-deployment.md § Rate limiting). Suffisant pour ce stade du
produit ; une implémentation distribuée (Redis) pourra être introduite plus
tard si un déploiement multi-instances l'exige.
"""

from __future__ import annotations

import re
import time
from threading import Lock
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status

from backend.app.config.settings import Settings, get_settings

_WINDOW_SECONDS = 60


class RateLimiter(Protocol):
    """Interface minimale qu'une implémentation de limiteur doit respecter.

    Permet d'introduire plus tard un `DistributedRateLimiter` (ex. Redis) sans
    modifier `rate_limit()` ni les routes qui l'utilisent — il suffira de
    fournir une instance conforme à ce protocole via `set_rate_limiter()`.
    """

    def hit(self, bucket: str, key: str, limit: int) -> bool: ...

    def reset(self) -> None: ...


class _FixedWindowLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[tuple[str, str, int], int] = {}

    def hit(self, bucket: str, key: str, limit: int) -> bool:
        window = int(time.time() // _WINDOW_SECONDS)
        bucket_key = (bucket, key, window)
        with self._lock:
            count = self._counts.get(bucket_key, 0) + 1
            self._counts[bucket_key] = count
            if len(self._counts) > 20_000:
                stale = window - 1
                for existing in list(self._counts):
                    if existing[2] < stale:
                        del self._counts[existing]
            return count <= limit

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


_limiter: RateLimiter = _FixedWindowLimiter()


def reset_rate_limiter() -> None:
    """Réinitialise l'état du limiteur (usage : isolation entre tests)."""

    _limiter.reset()


def allow_rate_limit(bucket: str, key: str, limit: int) -> bool:
    return _limiter.hit(bucket, key, limit)


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Remplace le limiteur actif (usage prévu : injection d'un futur
    `DistributedRateLimiter` en production multi-instances). Non utilisé en
    V1 — l'implémentation en mémoire par processus est suffisante pour un
    déploiement single-instance (voir docs/production-deployment.md)."""

    global _limiter
    _limiter = limiter


_CLIENT_IP = re.compile(r"^[0-9A-Fa-f:.]+$")


def _client_key(request: Request) -> str:
    hinted = (request.headers.get("x-avenqo-client-ip") or "").strip()
    if hinted and len(hinted) <= 64 and _CLIENT_IP.fullmatch(hinted):
        return hinted
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


async def _subject_key(request: Request, by_email: bool) -> str:
    """Sépare les personnes qui arrivent par la même adresse de sortie."""

    client = _client_key(request)
    if not by_email:
        return client
    email = ""
    try:
        payload = await request.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        raw = payload.get("email")
        if isinstance(raw, str):
            email = raw.strip().lower()[:320]
    return f"{client}:{email}" if email else client


def rate_limit(bucket: str, limit_attr: str, *, by_email: bool = False):
    """Crée une dépendance FastAPI limitant les requêtes par IP pour `bucket`.

    `limit_attr` est le nom du champ `Settings` fournissant la limite par
    minute (configurable par déploiement, jamais codée en dur ici).
    `by_email` ajoute l'adresse du corps JSON, pour qu'une sortie partagée
    ne bloque pas les autres comptes.
    """

    async def dependency(request: Request, settings: Settings = Depends(get_settings)) -> None:
        if not settings.rate_limit_enabled:
            return
        limit = getattr(settings, limit_attr)
        if not allow_rate_limit(bucket, await _subject_key(request, by_email), limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de requêtes, veuillez réessayer plus tard.",
            )

    return dependency
