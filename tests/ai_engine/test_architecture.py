from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from modules.catalog import MODULES_BY_CODE
from modules.entitlements import (
    InMemoryModuleEntitlements,
    ModuleAccessDenied,
    ModuleAccessService,
)
from modules.retailsense.agent import RetailSenseAI
from shared.ai_engine.column_mapping.service import AliasColumnMapper
from shared.ai_engine.container import AIEngineContainer
from shared.ai_engine.contracts import (
    ColumnProfile,
    DetectedSchema,
    SourceKind,
    TenantContext,
)
from shared.ai_engine.model_registry.repository import FileSystemModelRepository


class RecordingPredictionService:
    """Enregistre les appels de prÃ©diction sans charger de modÃ¨le rÃ©el."""

    def __init__(self) -> None:
        self.calls = 0

    def predict(self, *args: Any, **kwargs: Any) -> str:
        self.calls += 1
        return "prediction"


def test_model_paths_are_isolated_by_company(tmp_path: Path) -> None:
    repository = FileSystemModelRepository(tmp_path)
    company_a = TenantContext(UUID("00000000-0000-0000-0000-000000000001"))
    company_b = TenantContext(UUID("00000000-0000-0000-0000-000000000002"))

    path_a = repository.artifact_directory(company_a, "retail", "demand", "v1")
    path_b = repository.artifact_directory(company_b, "retail", "demand", "v1")

    assert path_a != path_b
    assert str(company_a.company_id) in path_a.parts
    assert str(company_b.company_id) in path_b.parts


def test_model_path_rejects_traversal(tmp_path: Path) -> None:
    repository = FileSystemModelRepository(tmp_path)
    tenant = TenantContext(UUID("00000000-0000-0000-0000-000000000001"))

    with pytest.raises(ValueError):
        repository.artifact_directory(tenant, "../other-company", "demand", "v1")


def test_column_mapping_aliases_are_extensible() -> None:
    mapper = AliasColumnMapper({"customer_id": {"client_id", "id_client"}})
    schema = DetectedSchema(
        tables={
            "customers": (
                ColumnProfile("customerIdentifier", "string", False),
                ColumnProfile("id_client", "string", False),
            )
        }
    )
    mapper.register_aliases("customer_id", {"customerIdentifier"})

    results = mapper.map_columns(schema, ("customer_id",))

    assert {result.source_column for result in results} == {
        "customerIdentifier",
        "id_client",
    }


def test_catalogue_contient_uniquement_les_modules_reutilisables() -> None:
    assert set(MODULES_BY_CODE) == {"retail", "accounting", "crm"}


def test_retailsense_est_un_module_natif_avenqo() -> None:
    retail = MODULES_BY_CODE["retail"]

    assert retail.name == "RetailSenseAI"
    assert retail.agent_name == "RetailSenseAI"
    assert retail.tasks


def test_module_agent_blocks_company_without_entitlement() -> None:
    tenant = TenantContext(UUID("00000000-0000-0000-0000-000000000001"))
    predictions = RecordingPredictionService()
    access = ModuleAccessService(InMemoryModuleEntitlements())
    agent = RetailSenseAI(predictions, access)  # type: ignore[arg-type]

    with pytest.raises(ModuleAccessDenied):
        agent.predict(tenant, "demand", {}, object())  # type: ignore[arg-type]

    assert predictions.calls == 0


def test_module_agent_allows_company_with_active_entitlement() -> None:
    tenant = TenantContext(UUID("00000000-0000-0000-0000-000000000001"))
    entitlements = InMemoryModuleEntitlements()
    entitlements.activate(tenant, "retail")
    predictions = RecordingPredictionService()
    agent = RetailSenseAI(
        predictions,  # type: ignore[arg-type]
        ModuleAccessService(entitlements),
    )

    result = agent.predict(tenant, "demand", {}, object())  # type: ignore[arg-type]

    assert result == "prediction"
    assert predictions.calls == 1


def test_container_builds_without_external_ml_dependencies() -> None:
    container = AIEngineContainer()

    plan = container.pipeline_orchestrator().plan("retail", "demand")

    assert plan.module_code == "retail"
    assert plan.task_code == "demand"
    assert "automl" in plan.stages
    assert container.connectors.get(SourceKind.CSV).kind is SourceKind.CSV

