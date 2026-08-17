"""Persistance des `ExplanationArtifact` — via le `ModelRegistry` existant, sans le modifier.

`shared.ai_engine.registry.registry.ModelRegistry` sait déjà enregistrer un
artefact arbitraire sous le répertoire versionné d'un modèle via
`.save(objet, tenant, module_code, task_code, version, filename=...)`. Ce
module centralise uniquement le NOM DE FICHIER conventionnel utilisé pour les
explications, afin qu'aucun appelant n'ait à le deviner ou le dupliquer —
c'est la seule source de vérité pour "comment/où une explication est stockée".
"""

from __future__ import annotations

from pathlib import Path

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.explainability.types import ExplanationArtifact
from shared.ai_engine.registry.registry import ModelRegistry

EXPLANATION_FILENAME = "explanation.joblib"


def save_explanation(
    registry: ModelRegistry,
    explanation: ExplanationArtifact,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> Path:
    """Enregistre l'explication dans le `ModelRegistry`, à côté du modèle versionné."""

    return registry.save(
        explanation,
        tenant,
        module_code,
        task_code,
        version,
        filename=EXPLANATION_FILENAME,
    )


def load_explanation(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> ExplanationArtifact:
    """Recharge l'explication précédemment enregistrée pour cette version de modèle."""

    import joblib

    directory = registry.model_directory(tenant, module_code, task_code, version)
    path = directory / EXPLANATION_FILENAME
    if not path.exists():
        raise FileNotFoundError(path)
    return joblib.load(path)
