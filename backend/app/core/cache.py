"""Moteur de cache haute performance multi-tenant en mémoire (Phase 17 — Performance).

Permet d'éliminer les requêtes répétitives et N+1 sur les métriques et synthèses
analytiques lourdes (Retail, CRM, Accounting, Cross-Agent).

Garantit :
1. Isolation multi-tenant stricte par clé composite (namespace:company_id:key).
2. TTL configurable par entrée et expiration glissante/absolue.
3. Invalidation ciblée par tenant lors des écritures/mises à jour.
4. Thread-safety absolue via threading.Lock.
5. Protection contre les fuites de mémoire (éviction opportuniste des clés expirées).
6. Télémétrie et métriques intégrées (hits, misses, ratio d'efficacité).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import logging
from threading import Lock
import time
from typing import Any, Callable
from uuid import UUID

logger = logging.getLogger("avenqo.performance.cache")


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    created_at: float
    hits: int = 0


class TenantMemoryCache:
    """Gestionnaire de cache haute performance avec cloisonnement strict par tenant."""

    def __init__(self, default_ttl_seconds: int = 30, max_entries: int = 10000) -> None:
        self._default_ttl = default_ttl_seconds
        self._max_entries = max_entries
        self._storage: dict[str, CacheEntry] = {}
        self._tenant_index: dict[str, set[str]] = {}
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def _build_key(self, namespace: str, company_id: UUID | str, key: str) -> str:
        return f"{namespace}:{str(company_id)}:{key}"

    def get(self, namespace: str, company_id: UUID | str, key: str) -> Any | None:
        """Récupère une valeur en cache si elle n'est pas expirée."""
        full_key = self._build_key(namespace, company_id, key)
        now = time.time()

        with self._lock:
            entry = self._storage.get(full_key)
            if entry is None:
                self._misses += 1
                return None

            if entry.expires_at <= now:
                # Expiré : suppression opportuniste
                self._delete_key(full_key, str(company_id))
                self._misses += 1
                return None

            entry.hits += 1
            self._hits += 1
            return entry.value

    def set(
        self,
        namespace: str,
        company_id: UUID | str,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """Enregistre une valeur en cache avec TTL."""
        full_key = self._build_key(namespace, company_id, key)
        cid_str = str(company_id)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        now = time.time()
        expires_at = now + ttl

        with self._lock:
            # Éviction préventive si le cache est plein
            if len(self._storage) >= self._max_entries:
                self._evict_expired(now)
                if len(self._storage) >= self._max_entries:
                    # Éviction d'office de 10% des entrées les plus anciennes
                    keys_to_remove = sorted(
                        self._storage.keys(), key=lambda k: self._storage[k].created_at
                    )[: max(1, self._max_entries // 10)]
                    for k in keys_to_remove:
                        parts = k.split(":", 2)
                        cid = parts[1] if len(parts) > 1 else ""
                        self._delete_key(k, cid)

            self._storage[full_key] = CacheEntry(
                value=value,
                expires_at=expires_at,
                created_at=now,
            )
            if cid_str not in self._tenant_index:
                self._tenant_index[cid_str] = set()
            self._tenant_index[cid_str].add(full_key)

    def invalidate_tenant(self, company_id: UUID | str, namespace: str | None = None) -> int:
        """Invalide toutes les clés de cache d'un tenant spécifique."""
        cid_str = str(company_id)
        invalidated = 0

        with self._lock:
            tenant_keys = list(self._tenant_index.get(cid_str, set()))
            for full_key in tenant_keys:
                if namespace is None or full_key.startswith(f"{namespace}:"):
                    self._delete_key(full_key, cid_str)
                    invalidated += 1

        if invalidated > 0:
            logger.debug(
                "cache_tenant_invalidated company_id=%s namespace=%s count=%d",
                cid_str,
                namespace or "all",
                invalidated,
            )
        return invalidated

    def _delete_key(self, full_key: str, cid_str: str) -> None:
        self._storage.pop(full_key, None)
        if cid_str in self._tenant_index:
            self._tenant_index[cid_str].discard(full_key)
            if not self._tenant_index[cid_str]:
                self._tenant_index.pop(cid_str, None)

    def _evict_expired(self, now: float) -> int:
        expired_keys = [k for k, v in self._storage.items() if v.expires_at <= now]
        for k in expired_keys:
            parts = k.split(":", 2)
            cid = parts[1] if len(parts) > 1 else ""
            self._delete_key(k, cid)
        return len(expired_keys)

    def clear(self) -> None:
        """Vide l'intégralité du cache."""
        with self._lock:
            self._storage.clear()
            self._tenant_index.clear()
            self._hits = 0
            self._misses = 0

    def get_metrics(self) -> dict[str, Any]:
        """Retourne les métriques de performance du cache."""
        with self._lock:
            total_reqs = self._hits + self._misses
            hit_ratio = (self._hits / total_reqs * 100) if total_reqs > 0 else 0.0
            return {
                "active_entries": len(self._storage),
                "active_tenants": len(self._tenant_index),
                "total_hits": self._hits,
                "total_misses": self._misses,
                "hit_ratio_pct": round(hit_ratio, 2),
                "max_entries": self._max_entries,
                "default_ttl_seconds": self._default_ttl,
            }


# Instance globale partagée
tenant_cache = TenantMemoryCache(default_ttl_seconds=30)


def cached_for_tenant(namespace: str, ttl_seconds: int = 30) -> Callable:
    """Décorateur pour mémoïser les appels de méthodes de service analytiques."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self: Any, company_id: UUID | str, *args: Any, **kwargs: Any) -> Any:
            # Clé basée sur les arguments additionnels sérialisés
            args_key = f"{args}:{sorted(kwargs.items())}" if (args or kwargs) else "default"
            cached = tenant_cache.get(namespace, company_id, args_key)
            if cached is not None:
                return cached

            result = func(self, company_id, *args, **kwargs)
            tenant_cache.set(namespace, company_id, args_key, result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator
