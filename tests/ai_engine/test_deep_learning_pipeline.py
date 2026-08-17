from pathlib import Path

import pandas as pd

from shared.ai_engine.experiments import (
    ExperimentStatus,
    InMemoryExperimentRepository,
)
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.training import TrainingService

from tests.ai_engine.test_training_experiments import build_context, build_dataset


def test_reseau_neuronal_entraine_sauvegarde_et_journalise(
    tmp_path: Path,
) -> None:
    data = pd.DataFrame(
        {
            "quantity": list(range(1, 41)),
            "channel": ["web", "store"] * 20,
            "revenue": [value * 2.5 for value in range(1, 41)],
        }
    )
    experiments = InMemoryExperimentRepository()
    service = TrainingService(
        FileSystemModelRepository(tmp_path),
        experiments,
    )

    result = service.train_neural_regressor(
        data=data,
        target_column="revenue",
        dataset=build_dataset(),
        version="dense-v1",
        run_context=build_context(),
        hidden_units=(8,),
        epochs=2,
        batch_size=8,
        random_seed=42,
    )

    assert result.model_path.suffix == ".keras"
    assert result.model_path.is_file()
    assert result.preprocessor_path.is_file()
    assert result.numerical_columns == ("quantity",)
    assert result.categorical_columns == ("channel",)
    assert {"mae", "rmse", "r2"} <= set(result.metrics)
    assert len(result.history["loss"]) == 2

    runs = experiments.list_for_task(build_dataset().tenant, "retail", "demand")
    assert len(runs) == 1
    assert runs[0].status is ExperimentStatus.COMPLETED
    assert runs[0].search.model_name == "dense_neural_network"