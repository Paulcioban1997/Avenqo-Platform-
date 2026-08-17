"""Candidat GraphSAGE, entraîné avec une agrégation de voisinage Keras native (`GraphSAGELayer`).

Voir la docstring de `graph_layers.py` pour la limitation de contrat (graphe transductif
construit par similarité k-NN, en l'absence de structure de graphe explicite dans
`DatasetArtifact`) et le choix Keras natif plutôt que `torch_geometric`.

Recherche d'hyperparamètres : voir `graph_hyperparameter_search.py` (nombre de voisins
k-NN, nombre de couches cachées, unités cachées, optimiseur, weight decay, learning rate
+ scheduler, epochs) — autorité unique partagée avec `GNNModel`/`GATModel`.
"""

from __future__ import annotations

from typing import Any

from shared.ai_engine.architectures.deep_learning.graph_hyperparameter_search import (
    search_and_train_graph_model,
)
from shared.ai_engine.architectures.deep_learning.graph_layers import GraphSAGELayer
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel
from shared.ai_engine.core.tabular_dataset import load_dataframe


class GraphSAGEModel(UntrainedModel):
    candidate_id = "graphsage"
    n_trials = 12

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        return search_and_train_graph_model(GraphSAGELayer, frame, n_trials=self.n_trials)
