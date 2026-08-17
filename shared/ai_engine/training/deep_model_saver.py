"""Sauvegarde des réseaux Keras et de leur préprocesseur sklearn."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib


@dataclass(frozen=True, slots=True)
class SavedDeepModelPaths:
    model: Path
    preprocessor: Path


def save_deep_model(
    model: Any,
    preprocessor: Any,
    destination: Path,
) -> SavedDeepModelPaths:
    """Écrit le modèle au format Keras et le preprocessing avec joblib."""

    destination.mkdir(parents=True, exist_ok=True)
    model_path = destination / "model.keras"
    preprocessor_path = destination / "preprocessor.joblib"
    model.save(model_path)
    joblib.dump(preprocessor, preprocessor_path)
    return SavedDeepModelPaths(model_path, preprocessor_path)