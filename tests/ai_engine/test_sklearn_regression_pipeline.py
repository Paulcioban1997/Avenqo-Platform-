from pathlib import Path

import pandas as pd
from sklearn.linear_model import LinearRegression

from shared.ai_engine.experiments import (
    ExperimentStatus,
    InMemoryExperimentRepository,
)
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.training import TrainingService

from tests.ai_engine.test_training_experiments import build_context, build_dataset


def test_pipeline_regression_entraine_sauvegarde_et_journalise(tmp_path: Path) -> None:
    data = pd.DataFrame(
        {
            "quantity": [10, 12, 15, 18, 20, 22, 25, 28, 30, 33, 36, 40],
            "category": ["A", "B"] * 6,
            "store": [f"S{index}" for index in range(12)],
            "revenue": [120, 145, 180, 210, 240, 265, 300, 330, 360, 395, 430, 470],
        }
    )
    experiments = InMemoryExperimentRepository()
    service = TrainingService(
        FileSystemModelRepository(tmp_path),
        experiments,
    )

    result = service.train_regressor(
        data=data,
        target_column="revenue",
        dataset=build_dataset(),
        version="model-v9",
        run_context=build_context(),
        estimators={"linear_regression": LinearRegression()},
        parameter_spaces={"linear_regression": {"fit_intercept": [True, False]}},
        test_size=0.25,
        random_seed=42,
    )

    runs = experiments.list_for_task(
        build_dataset().tenant,
        "retail",
        "demand",
    )
    assert len(runs) == 1
    assert runs[0].status is ExperimentStatus.COMPLETED
    assert runs[0].search.model_name == "linear_regression"
    assert result.numerical_columns == ("quantity",)
    assert result.categorical_columns == ("category", "store")
    assert "mae" in result.metrics
    assert "rmse" in result.metrics
    assert "r2" in result.metrics
    assert set(result.permutation_importance) == {"quantity", "category", "store"}
    assert result.model_path.is_file()
    assert result.preprocessor_path.is_file()
