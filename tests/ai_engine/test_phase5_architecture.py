from pathlib import Path
from uuid import UUID

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.ingestion.csv_loader import CSVLoader
from shared.ai_engine.mapping.manual_mapper import ManualMapper
from shared.ai_engine.mapping.semantic_mapper import SemanticMapper
from shared.ai_engine.mapping.synonym_mapper import SynonymMapper
from shared.ai_engine.pipelines.retail_pipeline import RetailPipeline
from shared.ai_engine.registry.registry import ModelRegistry


def test_csv_loader_delegates_to_injected_reader() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def reader(location: str, **options: object) -> list[dict[str, object]]:
        calls.append((location, options))
        return [{"external_id": 1}]

    result = CSVLoader(reader).load("customers.csv", delimiter=";")

    assert result == [{"external_id": 1}]
    assert calls == [("customers.csv", {"delimiter": ";"})]


def test_manual_mapping_is_source_agnostic() -> None:
    mapper = ManualMapper({"external_id": "customer_id"})

    assert mapper.map_columns(("external_id", "amount")) == {
        "external_id": "customer_id"
    }


def test_synonym_and_semantic_mapping_are_extensible() -> None:
    synonym = SynonymMapper({"customer_id": {"client_id"}})
    semantic = SemanticMapper(lambda source, target: 0.95 if source == "buyer" else 0.0)

    assert synonym.map_columns(("client_id",), ("customer_id",))["client_id"] == "customer_id"
    assert semantic.map_columns(("buyer",), ("customer_id",), threshold=0.9) == {
        "buyer": "customer_id"
    }


def test_registry_paths_are_isolated_by_company(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    company_a = TenantContext(UUID("00000000-0000-0000-0000-000000000001"))
    company_b = TenantContext(UUID("00000000-0000-0000-0000-000000000002"))

    path_a = registry.model_directory(company_a, "retail", "demand", "v1")
    path_b = registry.model_directory(company_b, "retail", "demand", "v1")

    assert path_a != path_b
    assert path_a == tmp_path / str(company_a.company_id) / "retail" / "demand" / "v1"


def test_retail_pipeline_declares_generic_engine_stages() -> None:
    pipeline = RetailPipeline()

    assert pipeline.module_code == "retail"
    assert pipeline.stages[0] == "ingestion"
    assert pipeline.stages[-1] == "registry"
