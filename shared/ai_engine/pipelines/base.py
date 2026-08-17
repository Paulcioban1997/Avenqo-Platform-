from typing import Any, Mapping, Protocol


class PipelineStage(Protocol):
    def run(self, context: Any) -> Any: ...


class IndustryPipeline:
    """Pipeline ordonné et réutilisable composé d'étapes injectées."""

    module_code = "generic"
    stages = (
        "ingestion",
        "schema_detection",
        "mapping",
        "cleaning",
        "feature_engineering",
        "preprocessing",
        "automl",
        "model_selection",
        "training",
        "evaluation",
        "registry",
    )

    def __init__(self, implementations: Mapping[str, PipelineStage] | None = None) -> None:
        self._implementations = dict(implementations or {})

    def run(self, context: Any) -> Any:
        for stage_name in self.stages:
            stage = self._implementations.get(stage_name)
            if stage is not None:
                context = stage.run(context)
        return context
