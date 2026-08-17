from uuid import UUID

import pytest

from shared.ai_engine.contracts import (
    DatasetArtifact,
    DetectedSchema,
    EvaluationResult,
    TenantContext,
)
from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.registry import (
    ExecutionStrategyRegistry,
    build_default_execution_strategy_registry,
)
from shared.ai_engine.engine import AIEngine
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.exceptions import UnsupportedExecutionDomainError


def build_dataset() -> DatasetArtifact:
    return DatasetArtifact(
        tenant=TenantContext(UUID("00000000-0000-0000-0000-000000000001")),
        module_code="retail",
        task_code="demand",
        uri="datasets/demand.csv",
        schema=DetectedSchema(tables={}),
    )


class FakeMetrics:
    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores

    def evaluate(self, model: str, dataset: DatasetArtifact) -> dict[str, float]:
        return {"score": self._scores[model]}


class FakeCandidate:
    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id

    def train(self, dataset: DatasetArtifact) -> str:
        return self.candidate_id


def test_lai_engine_delegue_a_la_strategie_machine_learning_par_defaut() -> None:
    evaluator = EvaluationService(FakeMetrics({"weak": 0.4, "strong": 0.9}), "score")
    engine = AIEngine(evaluator)

    result = engine.run(
        build_dataset(),
        [FakeCandidate("weak"), FakeCandidate("strong")],
    )

    assert result.candidate_id == "strong"
    assert result.evaluation.score == 0.9


def test_le_registre_par_defaut_enregistre_les_douze_familles_ia() -> None:
    evaluator = EvaluationService(FakeMetrics({"only": 1.0}), "score")
    registry = build_default_execution_strategy_registry(evaluator)

    assert set(registry.registered_domains()) == set(ExecutionDomain)


def test_le_registre_leve_une_erreur_interne_pour_un_domaine_non_enregistre() -> None:
    registry = ExecutionStrategyRegistry()

    with pytest.raises(UnsupportedExecutionDomainError):
        registry.resolve(ExecutionDomain.MACHINE_LEARNING)


def test_une_nouvelle_strategie_peut_etre_enregistree_sans_modifier_lai_engine() -> None:
    class FakeVisionStrategy:
        domain = "vision"

        def execute(self, dataset: DatasetArtifact, candidates: object) -> EvaluationResult:
            return EvaluationResult(candidate_id="vision-model", metrics={}, score=1.0)

    registry = ExecutionStrategyRegistry()
    registry.register(FakeVisionStrategy())

    resolved = registry.resolve("vision")  # type: ignore[arg-type]

    assert resolved.execute(build_dataset(), []).candidate_id == "vision-model"
