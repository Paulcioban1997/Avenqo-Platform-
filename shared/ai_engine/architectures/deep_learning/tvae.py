"""Candidat TVAE (alternative Keras native, en attendant `sdv`).

L'implémentation de référence `sdv.single_table.TVAESynthesizer` (paquet `sdv`/`ctgan`)
n'est pas installée dans cet environnement (même raison que `ctgan.py`, voir sa docstring).
En attendant, ce candidat réutilise le VAE dense générique (`VAEModel`) sur les features
tabulaires encodées/normalisées — zéro duplication de la logique d'espace latent
probabiliste. Pour brancher la bibliothèque `sdv` de référence, ne remplacer que le corps
de `train` ci-dessous, sans toucher à l'architecture (strategy, trainer, evaluator, registry).
"""

from __future__ import annotations

from typing import Any

from shared.ai_engine.architectures.deep_learning.vae import VAEModel
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel


class TVAEModel(UntrainedModel):
    candidate_id = "tvae"

    def train(self, dataset: DatasetArtifact) -> Any:
        return VAEModel().train(dataset)
