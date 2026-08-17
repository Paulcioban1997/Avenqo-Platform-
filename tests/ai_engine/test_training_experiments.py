from pathlib import Path
from uuid import UUID

import pytest

from shared.ai_engine.engine import AutoMLResult
from shared.ai_engine.contracts import (
    DatasetArtifact,
    DetectedSchema,
    EvaluationResult,
    TenantContext,
)
from shared.ai_engine.experiments import (
    DataPreparationRecord,
    DatasetSnapshot,
    ExperimentRun,
    ExperimentStatus,
    InMemoryExperimentRepository,
    ReproducibilityRecord,
    SearchMethod,
)
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.training import TrainingRunContext, TrainingService


class RecordingExperimentRepository(InMemoryExperimentRepository):
    """Conserve les états successifs pour vérifier le cycle de vie du Run."""

    def __init__(self) -> None:
        super().__init__()
        self.saved: list[ExperimentRun] = []

    def save(self, run: ExperimentRun) -> None:
        self.saved.append(run)
        super().save(run)


def build_dataset() -> DatasetArtifact:
    return DatasetArtifact(
        tenant=TenantContext(
            UUID("00000000-0000-0000-0000-000000000001")
        ),
        module_code="retail",
        task_code="demand",
        uri="datasets/demand.csv",
        schema=DetectedSchema(tables={}),
    )


def build_context() -> TrainingRunContext:
    return TrainingRunContext(
        dataset=DatasetSnapshot(
            dataset_id=UUID("10000000-0000-0000-0000-000000000001"),
            version="dataset-v3",
            fingerprint="sha256:dataset",
            uri="datasets/demand.csv",
            row_count=120,
            column_count=4,
            numerical_columns=("quantity", "price"),
            categorical_columns=("category",),
        ),
        preparation=DataPreparationRecord(
            created_columns=("revenue",),
            feature_engineering=("revenue = quantity * price",),
            imputation_strategy="median",
            encoding_strategy="one_hot",
            scaling_strategy="standard_scaler",
        ),
        reproducibility=ReproducibilityRecord(
            random_seed=42,
            split_strategy="train_test_split",
            split_parameters={"test_size": 0.2},
            python_version="3.11",
            library_versions={"scikit-learn": "1.5"},
            code_version="git:abc123",
        ),
        search_method=SearchMethod.GRID_SEARCH,
        parameter_spaces={
            "random_forest": {
                "n_estimators": [100, 200],
                "max_depth": [4, 8],
            },
            "linear": {"fit_intercept": [True, False]},
        },
        preprocessor_path="models/preprocessor.joblib",
    )


def test_training_cree_et_complete_automatiquement_un_run(
    tmp_path: Path,
) -> None:
    class SelectedModel:
        best_params_ = {"max_depth": 8, "n_estimators": 200}

    class SuccessfulAutoML:
        def run(self, dataset: DatasetArtifact, candidates: object) -> AutoMLResult:
            return AutoMLResult(
                candidate_id="random_forest",
                model=SelectedModel(),
                evaluation=EvaluationResult(
                    candidate_id="random_forest",
                    metrics={"rmse": 1.25, "r2": 0.91},
                    score=0.91,
                ),
            )

    experiments = RecordingExperimentRepository()
    service = TrainingService(
        FileSystemModelRepository(tmp_path),
        experiments,
    )

    _, destination = service.train(
        build_dataset(),
        "model-v7",
        SuccessfulAutoML(),  # type: ignore[arg-type]
        (),
        build_context(),
    )

    assert [run.status for run in experiments.saved] == [
        ExperimentStatus.RUNNING,
        ExperimentStatus.COMPLETED,
    ]
    completed = experiments.saved[-1]
    assert completed.search.model_name == "random_forest"
    assert completed.search.parameter_space == {
        "n_estimators": [100, 200],
        "max_depth": [4, 8],
    }
    assert completed.search.best_parameters == {
        "max_depth": 8,
        "n_estimators": 200,
    }
    assert completed.metrics == {"rmse": 1.25, "r2": 0.91}
    assert completed.model_version == "model-v7"
    assert completed.training_duration_seconds is not None
    assert completed.training_duration_seconds >= 0
    assert {artifact.kind: artifact.uri for artifact in completed.artifacts} == {
        "model": str(destination),
        "preprocessor": "models/preprocessor.joblib",
    }
    assert completed.preparation.feature_engineering == (
        "revenue = quantity * price",
    )


def test_training_marque_le_run_comme_echoue_et_relance_erreur(
    tmp_path: Path,
) -> None:
    class FailingAutoML:
        def run(self, dataset: DatasetArtifact, candidates: object) -> AutoMLResult:
            raise RuntimeError("training failed")

    experiments = RecordingExperimentRepository()
    service = TrainingService(
        FileSystemModelRepository(tmp_path),
        experiments,
    )

    with pytest.raises(RuntimeError, match="training failed"):
        service.train(
            build_dataset(),
            "model-v7",
            FailingAutoML(),  # type: ignore[arg-type]
            (),
            build_context(),
        )

    assert [run.status for run in experiments.saved] == [
        ExperimentStatus.RUNNING,
        ExperimentStatus.FAILED,
    ]
    assert experiments.saved[-1].completed_at is not None
    assert experiments.saved[-1].training_duration_seconds is not None