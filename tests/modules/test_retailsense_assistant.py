from uuid import uuid4

import pytest

from modules.entitlements import InMemoryModuleEntitlements, ModuleAccessDenied, ModuleAccessService
from modules.retailsense.assistant import BusinessReadiness, RetailAssistantService
from shared.ai_engine.contracts import TenantContext


class BusinessContextStub:
    def __init__(self, readiness_by_company) -> None:
        self._readiness_by_company = readiness_by_company

    def readiness(self, tenant: TenantContext) -> BusinessReadiness:
        return self._readiness_by_company[tenant.company_id]


def _service(tenant: TenantContext, readiness: BusinessReadiness) -> RetailAssistantService:
    entitlements = InMemoryModuleEntitlements()
    entitlements.activate(tenant, "retail")
    return RetailAssistantService(
        ModuleAccessService(entitlements),
        BusinessContextStub({tenant.company_id: readiness}),
    )


@pytest.mark.parametrize(
    ("readiness", "expected_text"),
    [
        (BusinessReadiness.NEEDS_CONNECTION, "connectez d'abord vos ventes"),
        (BusinessReadiness.PREPARING, "prépare vos premières analyses"),
        (BusinessReadiness.READY, "Vos analyses sont prêtes"),
    ],
)
def test_assistant_uses_business_readiness(readiness, expected_text) -> None:
    tenant = TenantContext(uuid4())

    reply = _service(tenant, readiness).answer(tenant, "Pourquoi les ventes baissent ?")

    assert expected_text in reply.answer
    forbidden = ("dataset", "accuracy", "pipeline", "sklearn", "artefact")
    assert not any(word in reply.answer.lower() for word in forbidden)


def test_assistant_rejects_company_without_retail_access() -> None:
    tenant = TenantContext(uuid4())
    service = RetailAssistantService(
        ModuleAccessService(InMemoryModuleEntitlements()),
        BusinessContextStub({tenant.company_id: BusinessReadiness.READY}),
    )

    with pytest.raises(ModuleAccessDenied):
        service.answer(tenant, "Compare ce mois avec le précédent.")