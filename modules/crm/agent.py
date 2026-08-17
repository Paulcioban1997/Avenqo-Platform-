from modules import tasks as task
from modules.base import ModuleAgent
from shared.ai_engine.contracts import ModuleDefinition


class CRMAI(ModuleAgent):
    definition = ModuleDefinition(
        "crm",
        "CRM",
        "CRMAI",
        (
            task.LEAD_SCORING,
            task.SEGMENTATION,
            task.CHURN,
            task.LIFETIME_VALUE,
            task.EMAIL_CLASSIFICATION,
            task.SENTIMENT,
        ),
    )
