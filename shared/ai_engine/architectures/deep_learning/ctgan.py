"""Candidat CTGAN (alternative Keras native, en attendant `sdv`).

L'implémentation de référence `sdv.single_table.CTGANSynthesizer` (paquet `sdv`/`ctgan`)
n'est pas installée dans cet environnement (installation lourde/fragile sous Windows,
décision volontairement non prise sans confirmation explicite). En attendant, ce candidat
réutilise le GAN dense générique (`GANModel`, même principe adverse générateur/
discriminateur) sur les features tabulaires encodées/normalisées — zéro duplication de la
boucle d'entraînement adverse. Pour brancher la bibliothèque `sdv` de référence, ne
remplacer que le corps de `train` ci-dessous, sans toucher à l'architecture (strategy,
trainer, evaluator, registry).
"""

from __future__ import annotations

from typing import Any

from shared.ai_engine.architectures.deep_learning.gan import GANModel
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel


class CTGANModel(UntrainedModel):
    candidate_id = "ctgan"

    def train(self, dataset: DatasetArtifact) -> Any:
        return GANModel().train(dataset)
