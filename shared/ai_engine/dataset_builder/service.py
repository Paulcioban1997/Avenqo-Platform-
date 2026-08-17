from shared.ai_engine.contracts import Task, DatasetArtifact
from shared.ai_engine.feature_engineering.registry import FeatureProviderRegistry


class DatasetBuilder:
    """Construit un jeu de données pour chaque tâche choisie par un module."""

    def __init__(self, providers: FeatureProviderRegistry | None = None) -> None:
        self._providers = providers or FeatureProviderRegistry()

    def build(
        self,
        module_code: str,
        task: Task,
        source: DatasetArtifact,
    ) -> DatasetArtifact:
        provider = self._providers.get(module_code)
        return provider.build_features(task, source)

