"""Sauvegarde locale des modèles et préprocesseurs sklearn."""

from dataclasses import dataclass
from pathlib import Path

import joblib
from sklearn.pipeline import Pipeline


@dataclass(frozen=True, slots=True)
class SavedModelPaths:
    model: Path
    preprocessor: Path


def save_model(pipeline: Pipeline, destination: Path) -> SavedModelPaths:
    """Sauvegarde le Pipeline complet et une copie de son préprocesseur."""

    destination.mkdir(parents=True, exist_ok=True)
    model_path = destination / "model.joblib"
    preprocessor_path = destination / "preprocessor.joblib"
    joblib.dump(pipeline, model_path)
    joblib.dump(pipeline.named_steps["preprocessor"], preprocessor_path)
    return SavedModelPaths(model=model_path, preprocessor=preprocessor_path)