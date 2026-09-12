"""Routeur API pour l'observabilité et le contrôle des performances (Phase 17).

Fournit les métriques de cache, l'efficacité des requêtes et l'invalidation explicite.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.core.cache import tenant_cache
from backend.app.dependencies.auth import get_tenant_context
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/performance", tags=["performance"])


@router.get("/metrics")
def get_performance_metrics(
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Retourne la télémétrie du cache et les métriques de performance du serveur."""
    cache_stats = tenant_cache.get_metrics()
    return {
        "status": "healthy",
        "tenant_id": str(tenant.company_id),
        "cache": cache_stats,
        "optimizations": {
            "gzip_compression": True,
            "connection_pooling": True,
            "tenant_memory_cache": True,
        },
    }


@router.post("/cache/invalidate")
def invalidate_tenant_cache(
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Invalide le cache analytique du tenant courant."""
    invalidated_count = tenant_cache.invalidate_tenant(tenant.company_id)
    return {
        "status": "invalidated",
        "tenant_id": str(tenant.company_id),
        "invalidated_entries_count": invalidated_count,
    }
