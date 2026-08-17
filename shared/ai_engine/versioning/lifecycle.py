from __future__ import annotations

from dataclasses import replace

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.versioning.registry import active_version, list_versions as _list_version_strings
from shared.ai_engine.versioning.serializer import load_version_record, save_version_record
from shared.ai_engine.versioning.types import ModelLifecycleState


def reconcile_lifecycle_states(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    promoted_version: str | None = None,
    previous_active_version: str | None = None,
) -> None:
    """Guarantees exactly one PRODUCTION version and archives prior production states."""

    if previous_active_version is None:
        previous_active_version = active_version(registry, tenant, module_code, task_code)

    for version in _list_version_strings(registry, tenant, module_code, task_code):
        try:
            record = load_version_record(registry, tenant, module_code, task_code, version)
        except FileNotFoundError:
            continue

        if promoted_version is not None and version == promoted_version:
            next_state = ModelLifecycleState.PRODUCTION
        elif promoted_version is not None and version != promoted_version:
            next_state = ModelLifecycleState.ARCHIVED
        elif previous_active_version is not None and version == previous_active_version:
            next_state = ModelLifecycleState.ARCHIVED
        elif record.state == ModelLifecycleState.PRODUCTION:
            next_state = ModelLifecycleState.ARCHIVED
        else:
            next_state = record.state

        if next_state != record.state:
            save_version_record(registry, replace(record, state=next_state), tenant)
