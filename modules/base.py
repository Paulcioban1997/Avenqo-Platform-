"""Agent de base utilisé par les modules pour appeler l'AI Engine partagé."""

from typing import Any, Mapping

from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import ModuleDefinition, TenantContext
from shared.ai_engine.prediction.service import PredictionExecutor, PredictionService


class ModuleAgent:
    """Agent métier léger dont les modèles restent gérés par l'AI Engine."""

    definition: ModuleDefinition

    def __init__(
        self,
        prediction_service: PredictionService,
        access_service: ModuleAccessService,
    ) -> None:
        self._predictions = prediction_service
        self._access = access_service

    def predict(
        self,
        tenant: TenantContext,
        task_code: str,
        features: Mapping[str, Any],
        executor: PredictionExecutor,
    ) -> Any:
        # Authorization always happens before module details are evaluated.
        self._access.require_active(tenant, self.definition.code)

        supported = {item.code for item in self.definition.tasks}
        if task_code not in supported:
            raise ValueError(
                f"Task '{task_code}' is not enabled for module "
                f"'{self.definition.code}'"
            )
        return self._predictions.predict(
            tenant,
            self.definition.code,
            task_code,
            features,
            executor,
        )

