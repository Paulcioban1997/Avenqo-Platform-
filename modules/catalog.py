"""Catalogue des modules réutilisables actuellement disponibles."""

from modules.accounting.agent import AccountingAI
from modules.crm.agent import CRMAI
from modules.retailsense.agent import RetailSenseAI
from shared.ai_engine.contracts import ModuleDefinition

MODULES: tuple[ModuleDefinition, ...] = tuple(
    agent.definition
    for agent in (
        RetailSenseAI,
        AccountingAI,
        CRMAI,
    )
)

MODULES_BY_CODE = {module.code: module for module in MODULES}
