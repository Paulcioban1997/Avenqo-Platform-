from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.dependencies.ai_memory import get_memory_service
from backend.app.models.base import UserRole
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.ai_memory import AIEnterpriseMemory, MemoryScope, MemoryType
from backend.app.ai.memory.service import AvenqoMemoryService
from backend.main import app
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_phase7_enterprise_memory import (
    company_a,
    company_b,
    db_engine,
    db_session,
    temp_memory_dir,
    test_settings,
    user_a1,
    user_a2,
    user_b1,
)


class MockMembership:
    def __init__(self, role="owner"):
        self.role = role
        self.is_active = True


def test_memory_api_crud_and_cross_tenant_security(db_session, test_settings, company_a, company_b, user_a1, user_b1):
    service = AvenqoMemoryService(db_session, test_settings)

    ca_id = company_a.id
    ua1_id = user_a1.id
    cb_id = company_b.id
    ub1_id = user_b1.id

    # Setup dependency overrides for Company A Admin
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(company_id=ca_id, user_id=ua1_id)
    app.dependency_overrides[get_current_identity] = lambda: CurrentIdentity(
        auth_session=None,  # type: ignore[arg-type]
        user=user_a1,
        raw_token="mock_token",
    )
    app.dependency_overrides[get_active_ai_membership] = lambda: MockMembership(role="owner")
    app.dependency_overrides[get_memory_service] = lambda: service

    client = TestClient(app)

    # 1. Config check
    cfg_resp = client.get("/api/v1/ai/memories/config")
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["enabled"] is True

    # 2. Create company-shared memory
    create_payload = {
        "content": "Company A standard discount threshold is 15% for annual contracts.",
        "scope": "company",
        "memory_type": "decision",
        "source_module": "central",
    }
    create_resp = client.post("/api/v1/ai/memories", json=create_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    memory_id = created_data["id"]
    assert created_data["memory_scope"] == "company"
    assert "15% for annual contracts" in created_data["content"]

    # 3. List memories
    list_resp = client.get("/api/v1/ai/memories")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(m["id"] == memory_id for m in list_data["memories"])

    # 4. Search memories
    search_resp = client.post("/api/v1/ai/memories/search", json={"query": "discount threshold"})
    assert search_resp.status_code == 200
    search_results = search_resp.json()
    assert len(search_results) >= 1
    assert search_results[0]["id"] == memory_id

    # 5. Update / correct memory
    patch_resp = client.patch(
        f"/api/v1/ai/memories/{memory_id}",
        json={"content": "Company A standard discount threshold updated to 20% for annual contracts."},
    )
    assert patch_resp.status_code == 200
    assert "20% for annual contracts" in patch_resp.json()["content"]

    # 6. Cross-Tenant Security Check: Switch context to Company B
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(company_id=cb_id, user_id=ub1_id)
    app.dependency_overrides[get_current_identity] = lambda: CurrentIdentity(
        auth_session=None,  # type: ignore[arg-type]
        user=user_b1,
        raw_token="mock_token",
    )
    # Company B tries to get Company A memory by ID
    get_forbidden = client.get(f"/api/v1/ai/memories/{memory_id}")
    assert get_forbidden.status_code == 404

    # Company B searches with exact query
    b_search = client.post("/api/v1/ai/memories/search", json={"query": "discount threshold"})
    assert b_search.status_code == 200
    assert len(b_search.json()) == 0

    # 7. Switch back to Company A and delete memory
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(company_id=ca_id, user_id=ua1_id)
    app.dependency_overrides[get_current_identity] = lambda: CurrentIdentity(
        auth_session=None,  # type: ignore[arg-type]
        user=user_a1,
        raw_token="mock_token",
    )
    del_resp = client.delete(f"/api/v1/ai/memories/{memory_id}")
    assert del_resp.status_code == 204

    # Confirm deleted
    get_deleted = client.get(f"/api/v1/ai/memories/{memory_id}")
    assert get_deleted.status_code == 404

    # Clean overrides
    app.dependency_overrides.clear()
