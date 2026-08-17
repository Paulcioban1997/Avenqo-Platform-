"""Assistant mÃ©tier RetailSense sans exposition de la mÃ©canique interne."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext


class BusinessReadiness(str, Enum):
    NEEDS_CONNECTION = "needs_connection"
    PREPARING = "preparing"
    READY = "ready"


class RetailBusinessContextReader(Protocol):
    def readiness(self, tenant: TenantContext) -> BusinessReadiness: ...


@dataclass(frozen=True)
class AssistantReply:
    answer: str
    suggested_actions: tuple[str, ...]


class RetailAssistantService:
    """RÃ©pond selon l'Ã©tat mÃ©tier rÃ©el de l'entreprise, sans rÃ©sultat fictif."""

    def __init__(
        self,
        access: ModuleAccessService,
        context: RetailBusinessContextReader,
    ) -> None:
        self._access = access
        self._context = context

    def answer(self, tenant: TenantContext, question: str) -> AssistantReply:
        self._access.require_active(tenant, "retail")
        if not question.strip():
            raise ValueError("Votre question ne peut pas Ãªtre vide.")

        readiness = self._context.readiness(tenant)
        if readiness is BusinessReadiness.NEEDS_CONNECTION:
            return AssistantReply(
                answer=(
                    "Pour rÃ©pondre Ã  cette question Ã  partir de votre entreprise, "
                    "connectez d'abord vos ventes. Je pourrai ensuite comparer les "
                    "pÃ©riodes et vous proposer des actions concrÃ¨tes."
                ),
                suggested_actions=("Connecter mes ventes",),
            )
        if readiness is BusinessReadiness.PREPARING:
            return AssistantReply(
                answer=(
                    "Vos informations commerciales sont bien connectées. Avenqo prépare "
                    "vos premières analyses; vos réponses personnalisées seront bientôt disponibles."
                ),
                suggested_actions=("Voir mes connexions",),
            )
        return AssistantReply(
            answer=(
                "Vos analyses sont prêtes. Cette question nécessite le service conversationnel "
                "personnalisé de votre entreprise, qui sera relié dans la prochaine Ã©tape."
            ),
            suggested_actions=("Voir mes recommandations",),
        )
