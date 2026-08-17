"""Module Retail natif de Avenqo utilisant les modÃ¨les propres Ã  l'entreprise."""

from modules.base import ModuleAgent
from modules.retailsense.tasks import TASKS
from shared.ai_engine.contracts import ModuleDefinition


class RetailSenseAI(ModuleAgent):
    """Agent Retail natif sans modÃ¨le intÃ©grÃ© ni prÃ©entraÃ®nÃ©."""

    definition = ModuleDefinition(
        code="retail",
        name="RetailSenseAI",
        agent_name="RetailSenseAI",
        tasks=TASKS,
    )


