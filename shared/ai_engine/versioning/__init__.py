"""Model Versioning Enterprise (Phase 9) â€” usage interne uniquement.

Chaque entraÃ®nement/rÃ©entraÃ®nement crÃ©e automatiquement une nouvelle version
traÃ§able (date, module, tÃ¢che, famille, dataset, hyperparamÃ¨tres, mÃ©thode de
recherche, mÃ©triques, drift, XAI, raison du rÃ©entraÃ®nement, lignÃ©e
parent/actuelle). Aucune version n'est jamais supprimÃ©e. Jamais exposÃ© au
frontend : ni "version", ni "rollback", ni UUID technique, ni aucun terme de
`ModelRegistry`/XAI/Drift/Hyperparameter Search.

Comparable Ã  Vertex AI Model Registry, SageMaker Model Registry et Azure ML
Model Versioning â€” mais entiÃ¨rement interne Ã  Avenqo.
"""

from shared.ai_engine.versioning.comparison import compare_versions
from shared.ai_engine.versioning.history import (
    VersionHistory,
    VersionHistoryEntry,
    append_version_history_entry,
    load_version_history,
)
from shared.ai_engine.versioning.registry import (
    active_version,
    list_versions,
    next_version_number,
    task_directory,
)
from shared.ai_engine.versioning.rollback import rollback_to_version
from shared.ai_engine.versioning.serializer import load_version_record, save_version_record
from shared.ai_engine.versioning.service import (
    compare,
    get_history,
    get_version,
    record_version,
    rollback,
)
from shared.ai_engine.versioning.service import list_versions as list_version_summaries
from shared.ai_engine.versioning.types import (
    RollbackResult,
    VersionComparisonResult,
    VersionEventType,
    VersionRecord,
    VersionSummary,
)

__all__ = [
    "RollbackResult",
    "VersionComparisonResult",
    "VersionEventType",
    "VersionHistory",
    "VersionHistoryEntry",
    "VersionRecord",
    "VersionSummary",
    "active_version",
    "append_version_history_entry",
    "compare",
    "compare_versions",
    "get_history",
    "get_version",
    "list_version_summaries",
    "list_versions",
    "load_version_history",
    "load_version_record",
    "next_version_number",
    "record_version",
    "rollback",
    "rollback_to_version",
    "save_version_record",
    "task_directory",
]

