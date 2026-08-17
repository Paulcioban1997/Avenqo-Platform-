"""Recensement des versions d'une tâche — lecture seule, jamais destructif.

`ModelRegistry`/`FileSystemModelRepository` (AI Engine, stabilisés) ne savent
retrouver qu'UNE version à la fois (`model_directory`) ou la version active
(`resolve_active`) : ils n'exposent aucune capacité de listage. Ce module
l'ajoute sans les modifier, en réutilisant le même repère de répertoire de
tâche que `retraining/history.py` (`.model_directory(...).parent`).
"""

from __future__ import annotations

from pathlib import Path

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.exceptions import ModelNotFoundError
from shared.ai_engine.registry.registry import ModelRegistry

# Segment de version "factice" — jamais réellement écrit à cet emplacement,
# uniquement utilisé pour obtenir `.parent` via l'API existante de
# `ModelRegistry` (même trick que `retraining/history.py`, chaque module
# garde volontairement sa propre constante locale plutôt qu'une dépendance
# croisée entre Phase 8 et Phase 9).
_TASK_LEVEL_PLACEHOLDER_VERSION = "taskroot"


def task_directory(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> Path:
    return registry.model_directory(
        tenant, module_code, task_code, _TASK_LEVEL_PLACEHOLDER_VERSION
    ).parent


def list_versions(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> tuple[str, ...]:
    """Liste toutes les versions existantes pour cette tâche, triées chronologiquement.

    Le format de version existant (`%Y%m%d%H%M%S%f`, largeur fixe) trie déjà
    correctement en ordre alphabétique — aucun tri numérique n'est requis.
    Ne lève jamais : une tâche jamais entraînée retourne simplement `()`.
    """

    directory = task_directory(registry, tenant, module_code, task_code)
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(entry.name for entry in directory.iterdir() if entry.is_dir())
    )


def next_version_number(existing_versions: tuple[str, ...], current_version: str) -> int:
    """Numéro humain séquentiel (1, 2, 3...) — cosmétique, jamais l'identifiant réel.

    Exclut explicitement `current_version` des versions déjà existantes : au
    moment de l'appel, le répertoire de la version courante peut déjà exister
    sur disque (le modèle/preprocessor y sont sauvegardés par
    `TrainingService` avant que la fiche de version ne soit écrite).
    """

    previous = [v for v in existing_versions if v != current_version]
    return len(previous) + 1


def active_version(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> str | None:
    """Version actuellement active, ou `None` si aucun modèle n'est encore actif."""

    try:
        return registry.resolve_active(tenant, module_code, task_code).version
    except ModelNotFoundError:
        return None
