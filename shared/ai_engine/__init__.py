"""Contrats et services de l'AI Engine isolés par entreprise."""

from typing import TYPE_CHECKING
from shared.ai_engine.contracts import Task, ModuleDefinition, TenantContext

if TYPE_CHECKING:
    from shared.ai_engine.container import AIEngineContainer


def __getattr__(name: str):
    if name == "AIEngineContainer":
        from shared.ai_engine.container import AIEngineContainer
        return AIEngineContainer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["AIEngineContainer", "ModuleDefinition", "Task", "TenantContext"]

