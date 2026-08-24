"""`PredictiveAITool` — base commune des outils prédictifs Avenqo (Phase 31).

Chaque outil prédictif utilise EXCLUSIVEMENT des modèles déjà entraînés
(`PredictionService` + `resolve_active_model_type`, voir
`shared/ai_engine/prediction/service.py` et
`backend/app/services/prediction_runtime.py`) : aucun réentraînement n'est
jamais déclenché par une question de chat, et aucune prédiction n'est
inventée si le modèle n'existe pas ou si les données du tenant ne le
permettent pas (voir `PortfolioAnalysisUnavailable` -> `ToolUnavailableError`
et la hiérarchie dédiée dans `backend/app/ai/tools/exceptions.py`).

`task_type` documente la tâche générique (`churn`, `segmentation`, `demand`,
`weekly_forecast`, `anomaly`) consommée par le sous-type concret — utilisé
uniquement à des fins d'observabilité/documentation, jamais pour dériver une
décision de sécurité (l'isolation tenant vient uniquement de
`ToolExecutionContext.tenant`, jamais d'un `model_id` fourni par le LLM).

Phase 31.1 ajoute deux garanties supplémentaires, toutes deux appliquées ici
pour rester communes à tous les outils concrets : la compatibilité du schéma
d'entrée du modèle (`ModelInputIncompatibleError`, traduit depuis
`ModelInputIncompatible`, levée par
`backend/app/services/prediction_compatibility.py`) et la fraîcheur du
modèle/de la donnée tenant (`StalePredictionError`, voir
`backend/app/services/prediction_freshness.py`).
"""

from __future__ import annotations

from abc import abstractmethod

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import (
    ModelInputIncompatibleError,
    PredictionUnavailableError,
    StalePredictionError,
)
from backend.app.config.settings import get_settings
from backend.app.services.portfolio_decision_service import PortfolioAnalysisUnavailable
from backend.app.services.prediction_compatibility import ModelInputIncompatible
from backend.app.services.prediction_freshness import (
    FreshnessResult,
    evaluate_freshness,
    policy_from_settings,
    resolve_freshness_inputs,
)


class PredictiveAITool(AITool):
    """Base commune : convertit `PortfolioAnalysisUnavailable` en erreur sûre.

    Les sous-classes implémentent uniquement `build_prediction(context,
    arguments)` — jamais l'appel LLM/outil brut, jamais de logique
    d'isolation tenant (déjà garantie par `context.tenant`, dérivé du JWT).
    """

    task_type: str = ""
    module_code: str = "retail"
    read_only = True
    # `get_prediction_summary` n'exécute aucune inférence pour une tâche
    # unique : la fraîcheur n'a pas de sens pour lui (voir sa sous-classe).
    evaluate_freshness_flag: bool = True

    @abstractmethod
    async def build_prediction(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        raise NotImplementedError

    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        freshness = self._evaluate_freshness_if_applicable(context)
        try:
            result = await self.build_prediction(context, arguments)
        except PortfolioAnalysisUnavailable as exc:
            raise PredictionUnavailableError(str(exc)) from exc
        except ModelInputIncompatible as exc:
            raise ModelInputIncompatibleError(str(exc)) from exc

        if freshness is not None and result.success:
            result.data["freshness"] = freshness.to_safe_dict()
        return result

    def _evaluate_freshness_if_applicable(self, context: ToolExecutionContext) -> FreshnessResult | None:
        session = getattr(self, "_session", None)
        if not self.evaluate_freshness_flag or not self.task_type or session is None:
            return None

        policy = policy_from_settings(get_settings())
        model_trained_at, dataset_updated_at = resolve_freshness_inputs(
            session, context.tenant, self.module_code, self.task_type
        )
        freshness = evaluate_freshness(model_trained_at, dataset_updated_at, policy)
        if freshness.status == "expired" and policy.block_on_expired:
            raise StalePredictionError(
                "This insight is based on a model that is too outdated to use safely for this "
                "tenant's current data; it must be retrained before it can be reused."
            )
        return freshness

