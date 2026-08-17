from typing import Any, Mapping, Protocol


class PredictiveModel(Protocol):
    def predict(self, features: Any) -> Any: ...


class Predictor:
    """Exécute les prédictions avec un adaptateur de modèle entraîné."""

    def predict(self, model: PredictiveModel, features: Any) -> Any:
        return model.predict(features)
