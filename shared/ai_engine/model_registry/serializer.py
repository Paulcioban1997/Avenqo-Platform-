"""Sérialiseur générique d'artefacts de modèles, basé sur joblib.

Implémentation par défaut du protocole `ArtifactSerializer` (voir
`shared.ai_engine.contracts`), réutilisable par n'importe quel modèle plutôt
que d'être recodée à chaque appelant de `ModelRegistry.save()`.
"""

from pathlib import Path
from typing import Any

import joblib


class JoblibArtifactSerializer:
    """Sauvegarde et recharge un modèle avec joblib, sans logique métier."""

    def save(self, model: Any, destination: Path) -> None:
        joblib.dump(model, destination)

    def load(self, source: Path) -> Any:
        return joblib.load(source)
