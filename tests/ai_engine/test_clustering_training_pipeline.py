from pathlib import Path

import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.datasets import make_blobs

from shared.ai_engine.experiments import (
    ExperimentStatus,
    InMemoryExperimentRepository,
)
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.training import TrainingService

from tests.ai_engine.test_training_experiments import build_context, build_dataset


def test_clustering_recherche_plusieurs_familles_et_garde_le_meilleur(
    tmp_path: Path,
) -> None:
    values, _ = make_blobs(
        n_samples=60,
        centers=3,
        cluster_std=0.25,
        random_state=42,
    )
    data = pd.DataFrame(values, columns=["recency", "monetary"])
    data["channel"] = ["web", "store"] * 30
    experiments = InMemoryExperimentRepository()
    service = TrainingService(
        FileSystemModelRepository(tmp_path),
        experiments,
    )

    result = service.train_clustering(
        data=data,
        dataset=build_dataset(),
        version="clustering-v1",
        run_context=build_context(),
        estimators={
            "kmeans": KMeans(random_state=42, n_init=10),
            "dbscan": DBSCAN(),
        },
        parameter_spaces={
            "kmeans": {"n_clusters": [2, 3, 4]},
            "dbscan": {"eps": [0.3, 0.6, 1.0], "min_samples": [2, 4]},
        },
    )

    assert result.model_name in {"kmeans", "dbscan"}
    assert result.metrics["cluster_count"] >= 2
    assert len(result.labels) == len(data)
    assert result.model_path.is_file()
    assert result.preprocessor_path.is_file()

    runs = experiments.list_for_task(build_dataset().tenant, "retail", "demand")
    assert len(runs) == 1
    assert runs[0].status is ExperimentStatus.COMPLETED
    assert runs[0].search.model_name == result.model_name
