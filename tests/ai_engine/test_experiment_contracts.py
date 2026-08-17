from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.experiments import (
    ArtifactReference,
    DataPreparationRecord,
    DatasetSnapshot,
    ExperimentRun,
    ReproducibilityRecord,
    SearchMethod,
    SearchRecord,
)


def build_run(company_id: str) -> ExperimentRun:
    """Construit un Run complet sans dépendre d'un framework ML."""

    return ExperimentRun(
        tenant=TenantContext(UUID(company_id)),
        module_code="retail",
        task_code="demand",
        dataset=DatasetSnapshot(
            dataset_id=UUID("10000000-0000-0000-0000-000000000001"),
            version="v1",
            fingerprint="sha256:dataset",
            uri="datasets/v1.csv",
            row_count=100,
            column_count=3,
            numerical_columns=("amount",),
            categorical_columns=("category",),
        ),
        preparation=DataPreparationRecord(
            mapping={"external_amount": "amount"},
            dropped_columns=("unused",),
            created_columns=("amount_log",),
            cleaning_strategy="standard",
            imputation_strategy="median",
            encoding_strategy="one_hot",
            scaling_strategy="standard_scaler",
        ),
        search=SearchRecord(
            model_name="candidate",
            method=SearchMethod.GRID_SEARCH,
            parameter_space={"depth": [2, 4, 8]},
            best_parameters={"depth": 4},
        ),
        reproducibility=ReproducibilityRecord(
            random_seed=42,
            split_strategy="train_test_split",
            split_parameters={"test_size": 0.2},
            python_version="3.11",
            library_versions={"example_ml": "1.0"},
            code_version="git:abc123",
        ),
        model_version="v1",
        metrics={"rmse": 1.2},
        artifacts=(
            ArtifactReference("model", "models/model.bin", "sha256:model"),
            ArtifactReference("preprocessor", "models/preprocessor.bin"),
        ),
    )


def test_run_contient_les_informations_de_reproductibilite() -> None:
    run = build_run("00000000-0000-0000-0000-000000000001")

    assert run.dataset.fingerprint == "sha256:dataset"
    assert run.search.best_parameters == {"depth": 4}
    assert run.reproducibility.random_seed == 42
    assert run.reproducibility.code_version == "git:abc123"
    assert {artifact.kind for artifact in run.artifacts} == {
        "model",
        "preprocessor",
    }


def test_run_est_isole_par_contexte_entreprise() -> None:
    company_a = build_run("00000000-0000-0000-0000-000000000001")
    company_b = build_run("00000000-0000-0000-0000-000000000002")

    assert company_a.tenant != company_b.tenant
    assert company_a.module_code == company_b.module_code == "retail"


def test_run_est_immuable_apres_sa_creation() -> None:
    run = build_run("00000000-0000-0000-0000-000000000001")

    with pytest.raises(FrozenInstanceError):
        run.model_version = "v2"  # type: ignore[misc]