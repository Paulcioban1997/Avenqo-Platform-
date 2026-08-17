"""Types partagés de la couche d'explicabilité (usage interne uniquement)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal, Mapping


class ExplanationMethod(StrEnum):
    """Technique utilisée pour l'importance globale principale (`global_importance`)."""

    SHAP_TREE = "shap_tree"
    SHAP_LINEAR = "shap_linear"
    PERMUTATION = "permutation"
    NATIVE = "native"


@dataclass(frozen=True, slots=True)
class ExplanationArtifact:
    """Explication complète et versionnée d'un modèle entraîné.

    Réservé au backend, aux API internes/admin et aux futurs rapports IA :
    jamais renvoyé tel quel à l'utilisateur final.
    """

    model_name: str
    task_type: Literal["classification", "regression"]
    method: ExplanationMethod
    global_importance: Mapping[str, float]
    native_importance: Mapping[str, float]
    permutation_importance: Mapping[str, float]
    shap_importance: Mapping[str, float] | None
    sample_explanations: tuple[Mapping[str, float], ...]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
