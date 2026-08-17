"""Point d'extension pour la sélection automatique de la famille IA adaptée (étape 6).

Aujourd'hui toutes les tâches sont orientées vers Machine Learning, exactement comme
l'ancien AutoMLService. Une résolution basée sur les métadonnées de la tâche (modalité,
objectif métier...) pourra être branchée plus tard en implémentant `FamilyResolver`,
sans modifier l'AIEngine ni les stratégies existantes.
"""

from typing import Protocol, runtime_checkable

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.execution_domain import ExecutionDomain


@runtime_checkable
class FamilyResolver(Protocol):
    def resolve(self, dataset: DatasetArtifact) -> ExecutionDomain: ...


class StaticFamilyResolver:
    """Résolveur par défaut : renvoie toujours le même domaine (comportement historique)."""

    def __init__(self, domain: ExecutionDomain) -> None:
        self._domain = domain

    def resolve(self, dataset: DatasetArtifact) -> ExecutionDomain:
        return self._domain
