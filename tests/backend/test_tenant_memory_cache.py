from uuid import uuid4

from backend.app.core.cache import TenantMemoryCache


def test_tenant_cache_never_returns_foreign_company_values() -> None:
    cache = TenantMemoryCache(default_ttl_seconds=60)
    company_a, company_b = uuid4(), uuid4()
    cache.set("retail_kpis", company_a, "overview", {"revenue": 10})
    cache.set("retail_kpis", company_b, "overview", {"revenue": 99})

    assert cache.get("retail_kpis", company_a, "overview") == {"revenue": 10}
    assert cache.get("retail_kpis", company_b, "overview") == {"revenue": 99}
    cache.invalidate_tenant(company_a)
    assert cache.get("retail_kpis", company_a, "overview") is None
    assert cache.get("retail_kpis", company_b, "overview") == {"revenue": 99}
