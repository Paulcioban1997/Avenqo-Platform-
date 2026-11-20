"""Rate limiting technique de base (Phase 34).

Fenêtre glissante simple, en mémoire, par processus. Limitation connue et
documentée : non partagé entre plusieurs workers/instances (voir
docs/production-deployment.md § Rate limiting). Suffisant pour ce stade du
produit ; une implémentation distribuée (Redis) pourra être introduite plus
tard si un déploiement multi-instances l'exige.
"""

from __future__ import annotations

import logging
import re
import time
from threading import Lock
from typing import Any, Protocol

from fastapi import Depends, HTTPException, Request, status

from backend.app.config.settings import Settings, get_settings

logger = logging.getLogger("avenqo.core.rate_limit")

_WINDOW_SECONDS = 60


class RateLimiter(Protocol):
    """Interface minimale qu'une implémentation de limiteur doit respecter.

    Permet d'introduire un `DistributedRateLimiter` (ex. Redis) sans
    modifier `rate_limit()` ni les routes qui l'utilisent.
    """

    def hit(self, bucket: str, key: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> bool: ...

    def is_limited(self, bucket: str, key: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> bool: ...

    def get_count(self, bucket: str, key: str, window_seconds: int = _WINDOW_SECONDS) -> int: ...

    def record_hit(self, bucket: str, key: str, window_seconds: int = _WINDOW_SECONDS) -> int: ...

    def reset(self) -> None: ...


class _FixedWindowLimiter:
    """Limite par fenêtre fixe en mémoire, thread-safe par processus."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[tuple[str, str, int], int] = {}

    def hit(self, bucket: str, key: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> bool:
        """Incrémente le compteur et retourne True si count <= limit."""
        window = int(time.time() // window_seconds)
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

    def is_limited(self, bucket: str, key: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> bool:
        """Vérifie si le quota est dépassé SANS incrémenter le compteur."""
        window = int(time.time() // window_seconds)
        bucket_key = (bucket, key, window)
        with self._lock:
            count = self._counts.get(bucket_key, 0)
            return count >= limit

    def get_count(self, bucket: str, key: str, window_seconds: int = _WINDOW_SECONDS) -> int:
        """Consulte la valeur actuelle du compteur pour la fenêtre sans l'incrémenter."""
        window = int(time.time() // window_seconds)
        bucket_key = (bucket, key, window)
        with self._lock:
            return self._counts.get(bucket_key, 0)

    def record_hit(self, bucket: str, key: str, window_seconds: int = _WINDOW_SECONDS) -> int:
        """Incrémente le compteur et retourne la nouvelle valeur."""
        window = int(time.time() // window_seconds)
        bucket_key = (bucket, key, window)
        with self._lock:
            count = self._counts.get(bucket_key, 0) + 1
            self._counts[bucket_key] = count
            return count

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


class RedisRateLimiter:
    """Limiteur distribué multi-instances via Redis avec opérations atomiques (INCR + EXPIRE).

    Sécurité et tolérance aux pannes :
    - Ne dépend d'aucune dépendance obligatoire au démarrage : vérifie la présence du package redis.
    - Si REDIS_URL est absent ou inaccessible, bascule immédiatement sur le limiteur en mémoire local.
    - Ne bloque jamais un flux métier ou une authentification en cas de panne réseau Redis.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        redis_client: Any = None,
        fallback: RateLimiter | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._client = redis_client
        self._fallback: RateLimiter = fallback or _FixedWindowLimiter()
        self._checked_connection = False
        self._is_ready = False
        self._lock = Lock()

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._redis_url:
            return None
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                import importlib
                redis = importlib.import_module("redis")
                self._client = redis.from_url(
                    self._redis_url,
                    socket_connect_timeout=1.5,
                    socket_timeout=1.5,
                    decode_responses=True,
                )
                self._client.ping()
                self._is_ready = True
                logger.info("RedisRateLimiter: connected successfully to Redis for distributed rate limiting")
            except Exception as exc:
                logger.warning("RedisRateLimiter: Redis unconfigured or unavailable (%s), using local fallback", exc)
                self._client = None
                self._is_ready = False
            return self._client

    def hit(self, bucket: str, key: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> bool:
        client = self._ensure_client()
        if client is None:
            return self._fallback.hit(bucket, key, limit, window_seconds)
        try:
            window = int(time.time() // window_seconds)
            redis_key = f"rl:{bucket}:{key}:{window}"
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds * 2)
            results = pipe.execute()
            count = int(results[0])
            return count <= limit
        except Exception as exc:
            logger.warning("RedisRateLimiter.hit error (%s), delegating to local fallback", exc)
            return self._fallback.hit(bucket, key, limit, window_seconds)

    def is_limited(self, bucket: str, key: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> bool:
        client = self._ensure_client()
        if client is None:
            return self._fallback.is_limited(bucket, key, limit, window_seconds)
        try:
            window = int(time.time() // window_seconds)
            redis_key = f"rl:{bucket}:{key}:{window}"
            val = client.get(redis_key)
            count = int(val) if val is not None else 0
            return count >= limit
        except Exception as exc:
            logger.warning("RedisRateLimiter.is_limited error (%s), delegating to local fallback", exc)
            return self._fallback.is_limited(bucket, key, limit, window_seconds)

    def get_count(self, bucket: str, key: str, window_seconds: int = _WINDOW_SECONDS) -> int:
        client = self._ensure_client()
        if client is None:
            return self._fallback.get_count(bucket, key, window_seconds)
        try:
            window = int(time.time() // window_seconds)
            redis_key = f"rl:{bucket}:{key}:{window}"
            val = client.get(redis_key)
            return int(val) if val is not None else 0
        except Exception as exc:
            return self._fallback.get_count(bucket, key, window_seconds)

    def record_hit(self, bucket: str, key: str, window_seconds: int = _WINDOW_SECONDS) -> int:
        client = self._ensure_client()
        if client is None:
            return self._fallback.record_hit(bucket, key, window_seconds)
        try:
            window = int(time.time() // window_seconds)
            redis_key = f"rl:{bucket}:{key}:{window}"
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds * 2)
            results = pipe.execute()
            return int(results[0])
        except Exception as exc:
            return self._fallback.record_hit(bucket, key, window_seconds)

    def reset(self) -> None:
        self._fallback.reset()
        client = self._ensure_client()
        if client is not None:
            try:
                cursor = 0
                while True:
                    cursor, keys = client.scan(cursor=cursor, match="rl:*", count=200)
                    if keys:
                        client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception:
                pass


def create_rate_limiter(settings: Settings | None = None) -> RateLimiter:
    """Instancie le limiteur approprié selon la configuration de déploiement."""
    if settings is not None and getattr(settings, "redis_url", None):
        return RedisRateLimiter(redis_url=settings.redis_url)
    return _FixedWindowLimiter()


_shared_voice_rate_limiter: RateLimiter | None = None
_shared_voice_limiter_lock = Lock()


def get_voice_auth_rate_limiter(settings: Settings | None = None) -> RateLimiter:
    """Retourne le limiteur d'authentification vocal partagé (singleton thread-safe).

    - Si REDIS_URL est configuré et que redis est disponible, réutilise une instance
      unique de RedisRateLimiter avec son pool de connexions (zéro reconnexion par appel).
    - Sinon, réutilise l'instance singleton _FixedWindowLimiter locale.
    - Thread-safe, résistant aux pannes avec fallback automatique.
    """
    global _shared_voice_rate_limiter
    if _shared_voice_rate_limiter is not None:
        return _shared_voice_rate_limiter

    with _shared_voice_limiter_lock:
        if _shared_voice_rate_limiter is not None:
            return _shared_voice_rate_limiter

        if settings is None:
            try:
                settings = get_settings()
            except Exception:
                settings = None

        redis_url = getattr(settings, "redis_url", None) if settings else None
        if redis_url:
            _shared_voice_rate_limiter = RedisRateLimiter(redis_url=redis_url)
        else:
            _shared_voice_rate_limiter = _FixedWindowLimiter()
        return _shared_voice_rate_limiter or _FixedWindowLimiter()


def reset_voice_auth_rate_limiter(limiter: RateLimiter | None = None) -> None:
    """Réinitialise ou remplace le limiteur d'authentification vocal partagé (usage : tests)."""
    global _shared_voice_rate_limiter
    with _shared_voice_limiter_lock:
        if _shared_voice_rate_limiter is not None:
            _shared_voice_rate_limiter.reset()
        _shared_voice_rate_limiter = limiter


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
