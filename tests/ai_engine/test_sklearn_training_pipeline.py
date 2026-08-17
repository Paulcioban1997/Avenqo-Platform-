from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from shared.ai_engine.experiments import (
    ExperimentStatus,
    InMemoryExperimentRepository,
)
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.training import TrainingService

from tests.ai_engine.test_training_experiments import build_context, build_dataset


def test_pipeline_classification_entraine_sauvegarde_et_journalise(
    tmp_path: Path,
) -> None:
    data = pd.DataFrame(
        {
            "age": [22, 25, 28, 31, 35, 38, 42, 46, 50, 54, 58, 62],
            "segment": ["A", "B"] * 6,
            "client": [f"C{index}" for index in range(12)],
            "churn": [0, 1] * 6,
        }
    )
    experiments = InMemoryExperimentRepository()
    service = TrainingService(
        FileSystemModelRepository(tmp_path),
        experiments,
    )

    result = service.train_classifier(
        data=data,
        target_column="churn",
        dataset=build_dataset(),
        version="model-v8",
        run_context=build_context(),
        estimators={
            "logistic_regression": LogisticRegression(
                max_iter=500,
                random_state=42,
            )
        },
        parameter_spaces={"logistic_regression": {"C": [0.1, 1.0]}},
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
    assert runs[0].search.model_name == "logistic_regression"
    assert runs[0].search.best_parameters == {"C": 0.1}
    assert result.numerical_columns == ("age",)
    assert result.categorical_columns == ("segment", "client")
    assert "accuracy" in result.metrics
    train_data, _ = train_test_split(
        data,
        test_size=0.25,
        random_state=42,
        stratify=data["churn"],
    )
    assert set(result.feature_importance) == {
        "numerical__age",
        "categorical__segment_A",
        "categorical__segment_B",
        *{
            f"categorical__client_{client}"
            for client in train_data["client"]
        },
    }
    assert set(result.permutation_importance) == {"age", "segment", "client"}
    assert result.model_path.is_file()
    assert result.preprocessor_path.is_file()