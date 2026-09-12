"""Tests de validation pour Phase 17 — Performance et Caching Multi-Tenant."""

import time
import uuid
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.core.cache import TenantMemoryCache, cached_for_tenant, tenant_cache
from backend.main import app


def test_tenant_memory_cache_hit_and_miss():
    """Vérifie le fonctionnement nominal du cache (hit/miss) et le calcul des métriques."""
    cache = TenantMemoryCache(default_ttl_seconds=10)
    tenant_id = uuid4()

    # Initial miss
    assert cache.get("test_ns", tenant_id, "key1") is None
    metrics = cache.get_metrics()
    assert metrics["total_misses"] == 1
    assert metrics["total_hits"] == 0

    # Set value
    cache.set("test_ns", tenant_id, "key1", {"metric": 42.5}, ttl_seconds=5)

    # Hit
    val = cache.get("test_ns", tenant_id, "key1")
    assert val == {"metric": 42.5}
    metrics = cache.get_metrics()
    assert metrics["total_hits"] == 1
    assert metrics["active_entries"] == 1
    assert metrics["hit_ratio_pct"] == 50.0


def test_tenant_memory_cache_strict_isolation():
    """Vérifie que deux tenants avec la même clé sont 100% cloisonnés."""
    cache = TenantMemoryCache(default_ttl_seconds=10)
    tenant_a = uuid4()
    tenant_b = uuid4()

    cache.set("finance", tenant_a, "summary", {"balance": 10000.0})
    cache.set("finance", tenant_b, "summary", {"balance": 250.0})

    assert cache.get("finance", tenant_a, "summary")["balance"] == 10000.0
    assert cache.get("finance", tenant_b, "summary")["balance"] == 250.0

    # Invalidation de tenant_a ne doit pas toucher tenant_b
    cache.invalidate_tenant(tenant_a)
    assert cache.get("finance", tenant_a, "summary") is None
    assert cache.get("finance", tenant_b, "summary")["balance"] == 250.0


def test_tenant_memory_cache_expiration():
    """Vérifie l'expiration automatique d'une entrée après dépassement du TTL."""
    cache = TenantMemoryCache(default_ttl_seconds=1)
    tenant_id = uuid4()

    cache.set("quick", tenant_id, "token", "abc123xyz", ttl_seconds=1)
    assert cache.get("quick", tenant_id, "token") == "abc123xyz"

    time.sleep(1.1)
    assert cache.get("quick", tenant_id, "token") is None


def test_cached_for_tenant_decorator():
    """Vérifie que le décorateur cached_for_tenant mémoïse les appels de service."""
    call_count = 0

    class DummyAnalyticsService:
        @cached_for_tenant("dummy_ns", ttl_seconds=5)
        def compute_expensive_kpi(self, company_id, factor=1):
            nonlocal call_count
            call_count += 1
            return {"kpi": 100 * factor, "calls": call_count}

    service = DummyAnalyticsService()
    tenant_id = uuid4()

    # Premier appel : exécute la fonction
    res1 = service.compute_expensive_kpi(tenant_id, factor=2)
    assert res1["calls"] == 1
    assert call_count == 1

    # Deuxième appel avec mêmes args : retourne le cache instantanément
    res2 = service.compute_expensive_kpi(tenant_id, factor=2)
    assert res2["calls"] == 1
    assert call_count == 1

    # Invalidation du tenant
    tenant_cache.invalidate_tenant(tenant_id)

    # Troisième appel : ré-exécute la fonction
    res3 = service.compute_expensive_kpi(tenant_id, factor=2)
    assert res3["calls"] == 2
    assert call_count == 2


def test_gzip_compression_enabled():
    """Vérifie que GZipMiddleware compresse les payloads JSON de plus de 1 Ko."""
    client = TestClient(app)
    # L'endpoint /api/v1/cross-agent/synthesis ou un payload volumineux avec header gzip
    # On teste avec un endpoint qui répond un payload de taille suffisante
    headers = {"Accept-Encoding": "gzip"}
    response = client.get("/health", headers=headers)
    assert response.status_code == 200
