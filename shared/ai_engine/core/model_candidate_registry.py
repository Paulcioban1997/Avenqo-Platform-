"""Registre générique des modèles candidats pré-intégrés dans une famille IA.

Distinct du Model Registry (`shared/ai_engine/model_registry/`) : celui-ci catalogue
les modèles *disponibles* (non entraînés) d'une famille, l'autre versionne et active
les modèles *déjà entraînés* propres à chaque entreprise. Le Model Registry ne décide
jamais quel modèle est le meilleur ; ce registre-ci ne conserve aucune version.
"""

from typing import Callable, Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.core.model_candidate import ModelCandidate


class ModelCandidateRegistry:
    """Associe chaque identifiant de modèle à sa fabrique, pour une famille donnée."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], object]] = {}

    def register(self, candidate_id: str, factory: Callable[[], object]) -> None:
        self._factories[candidate_id] = factory

    def build_all(self) -> Sequence[TrainingCandidate]:
        """Instancie un candidat entraînable pour chaque modèle enregistré."""

        return tuple(
            ModelCandidate(candidate_id=candidate_id, factory=factory)
            for candidate_id, factory in self._factories.items()
        )

    def available_models(self) -> tuple[str, ...]:
        return tuple(self._factories)
