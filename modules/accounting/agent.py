from modules import tasks as task
from modules.base import ModuleAgent
from shared.ai_engine.contracts import ModuleDefinition


class AccountingAI(ModuleAgent):
    definition = ModuleDefinition(
        "accounting",
        "Accounting",
        "AccountingAI",
        (
            task.INVOICE_OCR,
            task.EXPENSE_ANALYSIS,
            task.CASH_FLOW,
            task.FRAUD,
            task.FINANCIAL_FORECAST,
            task.ANOMALY,
        ),
    )
