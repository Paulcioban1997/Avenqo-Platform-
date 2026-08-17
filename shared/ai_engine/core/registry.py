"""Registre unique des stratégies d'exécution disponibles pour l'AI Engine."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.strategy import ExecutionStrategy
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.exceptions import UnsupportedExecutionDomainError
from shared.ai_engine.model_selection.service import ModelSelector


class ExecutionStrategyRegistry:
    """Associe chaque domaine d'exécution interne à sa stratégie enregistrée."""

    def __init__(self) -> None:
        self._strategies: dict[ExecutionDomain, ExecutionStrategy] = {}

    def register(self, strategy: ExecutionStrategy) -> None:
        self._strategies[strategy.domain] = strategy

    def resolve(self, domain: ExecutionDomain) -> ExecutionStrategy:
        try:
            return self._strategies[domain]
        except KeyError as exc:
            raise UnsupportedExecutionDomainError(
                f"No execution strategy is registered for domain '{domain.value}'"
            ) from exc

    def registered_domains(self) -> tuple[ExecutionDomain, ...]:
        return tuple(self._strategies)


def build_default_execution_strategy_registry(
    evaluator: EvaluationService,
    selector: ModelSelector | None = None,
) -> ExecutionStrategyRegistry:
    """Construit le registre pré-peuplé avec les 12 familles d'IA de la plateforme.

    Ajouter une future famille métier ne nécessite qu'un nouveau dossier sous
    `shared/ai_engine/families/` et une ligne supplémentaire ici. Machine Learning et
    Deep Learning sont de simples catégories techniques (pas des cas d'usage métier) :
    leurs stratégies vivent directement sous `shared/ai_engine/architectures/`, à côté
    de leurs modèles, sans dossier `families/` dédié. Dans tous les cas, l'AIEngine et
    les familles déjà enregistrées ne sont jamais modifiés.
    """

    from shared.ai_engine.architectures.deep_learning.strategy import DeepLearningStrategy
    from shared.ai_engine.architectures.machine_learning.strategy import MachineLearningStrategy
    from shared.ai_engine.families.anomaly.strategy import AnomalyDetectionStrategy
    from shared.ai_engine.families.audio.strategy import AudioStrategy
    from shared.ai_engine.families.forecasting.strategy import ForecastingStrategy
    from shared.ai_engine.families.llm.strategy import LLMStrategy
    from shared.ai_engine.families.nlp.strategy import NLPStrategy
    from shared.ai_engine.families.ocr.strategy import OCRStrategy
    from shared.ai_engine.families.rag.strategy import RAGStrategy
    from shared.ai_engine.families.recommendation.strategy import RecommendationStrategy
    from shared.ai_engine.families.synthetic.strategy import SyntheticDataStrategy
    from shared.ai_engine.families.vision.strategy import VisionStrategy

    registry = ExecutionStrategyRegistry()
    for strategy_cls in (
        MachineLearningStrategy,
        DeepLearningStrategy,
        ForecastingStrategy,
        NLPStrategy,
        VisionStrategy,
        OCRStrategy,
        RecommendationStrategy,
        AnomalyDetectionStrategy,
        SyntheticDataStrategy,
        LLMStrategy,
        RAGStrategy,
        AudioStrategy,
    ):
        registry.register(strategy_cls(evaluator, selector))
    return registry
