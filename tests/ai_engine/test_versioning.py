"""Tests unitaires du Model Versioning Enterprise (Phase 9).

Vérifie : le listage/numérotation des versions, la persistance de la fiche
de version et de l'historique via le `ModelRegistry` existant, la
comparaison (délégation à la Phase 8, aucune duplication), le rollback (sans
réentraînement, aucune suppression), et le caractère "never-raise" de
`service.record_version`.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.drift.types import DriftSeverity
from shared.ai_engine.exceptions import ModelNotFoundError
from shared.ai_engine.experiments import DatasetSnapshot, SearchMethod
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.versioning.comparison import compare_versions
from shared.ai_engine.versioning.history import (
    VersionHistory,
    VersionHistoryEntry,
    append_version_history_entry,
    load_version_history,
)
from shared.ai_engine.versioning.registry import active_version, list_versions, next_version_number
from shared.ai_engine.versioning.rollback import rollback_to_version
from shared.ai_engine.versioning.serializer import load_version_record, save_version_record
from shared.ai_engine.versioning.service import (
    compare,
    get_version,
    list_versions as list_version_summaries,
    record_version,
    rollback,
)
from shared.ai_engine.versioning.types import ModelLifecycleState, VersionEventType, VersionRecord


def _registry(tmp_path: Path) -> ModelRegistry:
    return ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())


def _tenant() -> TenantContext:
    return TenantContext(uuid4())


def _dataset(row_count: int = 100) -> DatasetSnapshot:
    return DatasetSnapshot(
        dataset_id=uuid4(),
        version="v1",
        fingerprint="abc123",
        uri="s3://bucket/dataset.csv",
        row_count=row_count,
        column_count=5,
    )


def _make_record(version: str, version_number: int = 1, metrics=None) -> VersionRecord:
    return VersionRecord(
        version=version,
        version_number=version_number,
        parent_version=None,
        module_code="retail",
        task_code="bad_review",
        family="classification",
        model_type="classification",
        model_name="RandomForestClassifier",
        dataset_id=str(uuid4()),
        dataset_row_count=100,
        dataset_fingerprint="abc123",
        dataset_uri="s3://bucket/dataset.csv",
        hyperparameters={"n_estimators": 100},
        search_method=SearchMethod.RANDOMIZED_SEARCH,
        metrics=metrics or {"accuracy": 0.8},
    )


class TestRegistryListing:
    def test_list_versions_empty_when_never_trained(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        assert list_versions(registry, tenant, "retail", "bad_review") == ()

    def test_list_versions_returns_created_directories(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        registry.model_directory(tenant, "retail", "bad_review", "20240101000000000000").mkdir(
            parents=True
        )
        registry.model_directory(tenant, "retail", "bad_review", "20240201000000000000").mkdir(
            parents=True
        )
        assert list_versions(registry, tenant, "retail", "bad_review") == (
            "20240101000000000000",
            "20240201000000000000",
        )

    def test_next_version_number_excludes_current(self) -> None:
        existing = ("v1", "v2", "v3")
        assert next_version_number(existing, "v3") == 3
        assert next_version_number(existing, "v4") == 4
        assert next_version_number((), "v1") == 1

    def test_active_version_none_when_nothing_active(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        assert active_version(registry, tenant, "retail", "bad_review") is None

    def test_active_version_reflects_activation(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        registry.model_directory(tenant, "retail", "bad_review", "20240101000000000000").mkdir(
            parents=True
        )
        registry.activate(tenant, "retail", "bad_review", "20240101000000000000")
        assert active_version(registry, tenant, "retail", "bad_review") == "20240101000000000000"


class TestSerializer:
    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        record = _make_record("20240101000000000000")
        save_version_record(registry, record, tenant)
        reloaded = load_version_record(registry, tenant, "retail", "bad_review", "20240101000000000000")
        assert reloaded == record

    def test_load_missing_raises_file_not_found(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        registry.model_directory(tenant, "retail", "bad_review", "20240101000000000000").mkdir(
            parents=True
        )
        with pytest.raises(FileNotFoundError):
            load_version_record(registry, tenant, "retail", "bad_review", "20240101000000000000")


class TestHistory:
    def test_load_history_missing_returns_empty(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        assert load_version_history(registry, tenant, "retail", "bad_review") == VersionHistory()

    def test_append_and_reload_history(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        append_version_history_entry(
            registry,
            tenant,
            "retail",
            "bad_review",
            VersionHistoryEntry(event=VersionEventType.CREATED, version="v1", version_number=1),
        )
        append_version_history_entry(
            registry,
            tenant,
            "retail",
            "bad_review",
            VersionHistoryEntry(event=VersionEventType.ACTIVATED, version="v1", version_number=1),
        )
        history = load_version_history(registry, tenant, "retail", "bad_review")
        assert len(history.entries) == 2
        assert history.entries[0].event == VersionEventType.CREATED
        assert history.entries[1].event == VersionEventType.ACTIVATED


class TestComparison:
    def test_candidate_better(self) -> None:
        record_a = _make_record("v1", 1, {"accuracy": 0.80})
        record_b = _make_record("v2", 2, {"accuracy": 0.90})
        result = compare_versions(record_a, record_b)
        assert result.version_a == "v1"
        assert result.version_b == "v2"
        assert result.b_is_better is True

    def test_candidate_worse(self) -> None:
        record_a = _make_record("v1", 1, {"accuracy": 0.90})
        record_b = _make_record("v2", 2, {"accuracy": 0.60})
        result = compare_versions(record_a, record_b)
        assert result.b_is_better is False

    def test_blocked_by_critical_drift(self) -> None:
        import dataclasses

        record_a = _make_record("v1", 1, {"accuracy": 0.80})
        record_b = dataclasses.replace(
            _make_record("v2", 2, {"accuracy": 0.95}), drift_severity=DriftSeverity.CRITICAL
        )
        result = compare_versions(record_a, record_b)
        assert result.blocked_by_drift is True
        assert result.b_is_better is False


class TestRollback:
    def test_rollback_activates_target_without_retraining(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        for version in ("v1", "v2"):
            registry.model_directory(tenant, "retail", "bad_review", version).mkdir(parents=True)
            save_version_record(registry, _make_record(version), tenant)
        registry.activate(tenant, "retail", "bad_review", "v2")

        result = rollback_to_version(registry, tenant, "retail", "bad_review", "v1")

        assert result.previous_active_version == "v2"
        assert result.target_version == "v1"
        assert result.activated is True
        assert active_version(registry, tenant, "retail", "bad_review") == "v1"
        assert load_version_record(registry, tenant, "retail", "bad_review", "v1").state == ModelLifecycleState.PRODUCTION
        assert load_version_record(registry, tenant, "retail", "bad_review", "v2").state == ModelLifecycleState.ARCHIVED

        history = load_version_history(registry, tenant, "retail", "bad_review")
        assert history.entries[-1].event == VersionEventType.ROLLED_BACK

    def test_rollback_missing_version_raises(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        registry.model_directory(tenant, "retail", "bad_review", "v1").mkdir(parents=True)
        save_version_record(registry, _make_record("v1"), tenant)
        registry.activate(tenant, "retail", "bad_review", "v1")

        with pytest.raises(ModelNotFoundError):
            rollback_to_version(registry, tenant, "retail", "bad_review", "v99")

    def test_no_version_is_ever_deleted(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        for version in ("v1", "v2", "v3"):
            registry.model_directory(tenant, "retail", "bad_review", version).mkdir(parents=True)
            save_version_record(registry, _make_record(version), tenant)
        registry.activate(tenant, "retail", "bad_review", "v3")

        rollback_to_version(registry, tenant, "retail", "bad_review", "v1")

        assert list_versions(registry, tenant, "retail", "bad_review") == ("v1", "v2", "v3")


class TestService:
    def test_record_version_persists_and_numbers_sequentially(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()

        first = record_version(
            registry,
            tenant,
            "retail",
            "bad_review",
            "v1",
            family="classification",
            model_type="classification",
            model_name="LogisticRegression",
            dataset=_dataset(),
            hyperparameters={"C": 1.0},
            search_method=SearchMethod.RANDOMIZED_SEARCH,
            metrics={"accuracy": 0.8},
            parent_version=None,
            activated=True,
        )
        second = record_version(
            registry,
            tenant,
            "retail",
            "bad_review",
            "v2",
            family="classification",
            model_type="classification",
            model_name="RandomForestClassifier",
            dataset=_dataset(),
            hyperparameters={"n_estimators": 200},
            search_method=SearchMethod.RANDOMIZED_SEARCH,
            metrics={"accuracy": 0.85},
            parent_version="v1",
            activated=True,
        )

        assert first is not None and first.version_number == 1
        assert second is not None and second.version_number == 2
        assert second.parent_version == "v1"

        reloaded_first = get_version(registry, tenant, "retail", "bad_review", "v1")
        reloaded_second = get_version(registry, tenant, "retail", "bad_review", "v2")
        assert reloaded_first.model_name == "LogisticRegression"
        assert reloaded_first.state == ModelLifecycleState.ARCHIVED
        assert reloaded_second.state == ModelLifecycleState.PRODUCTION

    def test_record_version_never_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import shared.ai_engine.versioning.service as service_module

        def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(service_module, "save_version_record", _boom)
        registry = _registry(tmp_path)
        tenant = _tenant()

        result = record_version(
            registry,
            tenant,
            "retail",
            "bad_review",
            "v1",
            family="classification",
            model_type="classification",
            model_name="LogisticRegression",
            dataset=_dataset(),
            hyperparameters={},
            search_method=SearchMethod.FIXED,
            metrics={"accuracy": 0.8},
            parent_version=None,
            activated=True,
        )
        assert result is None

    def test_list_versions_reports_active_flag(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        for version in ("v1", "v2"):
            record_version(
                registry,
                tenant,
                "retail",
                "bad_review",
                version,
                family="classification",
                model_type="classification",
                model_name="RandomForestClassifier",
                dataset=_dataset(),
                hyperparameters={},
                search_method=SearchMethod.RANDOMIZED_SEARCH,
                metrics={"accuracy": 0.8},
                parent_version=None,
                activated=(version == "v2"),
            )
        registry.activate(tenant, "retail", "bad_review", "v2")

        summaries = list_version_summaries(registry, tenant, "retail", "bad_review")
        assert len(summaries) == 2
        by_version = {summary.version: summary for summary in summaries}
        assert by_version["v1"].is_active is False
        assert by_version["v2"].is_active is True
        assert by_version["v1"].state == ModelLifecycleState.ARCHIVED
        assert by_version["v2"].state == ModelLifecycleState.PRODUCTION

    def test_compare_and_rollback_via_service(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path)
        tenant = _tenant()
        record_version(
            registry, tenant, "retail", "bad_review", "v1",
            family="classification", model_type="classification", model_name="A",
            dataset=_dataset(), hyperparameters={}, search_method=SearchMethod.FIXED,
            metrics={"accuracy": 0.9}, parent_version=None, activated=True,
        )
        record_version(
            registry, tenant, "retail", "bad_review", "v2",
            family="classification", model_type="classification", model_name="B",
            dataset=_dataset(), hyperparameters={}, search_method=SearchMethod.FIXED,
            metrics={"accuracy": 0.6}, parent_version="v1", activated=False,
        )
        registry.activate(tenant, "retail", "bad_review", "v1")

        comparison = compare(registry, tenant, "retail", "bad_review", "v1", "v2")
        assert comparison.b_is_better is False

        result = rollback(registry, tenant, "retail", "bad_review", "v1")
        assert result.activated is True
        assert active_version(registry, tenant, "retail", "bad_review") == "v1"
