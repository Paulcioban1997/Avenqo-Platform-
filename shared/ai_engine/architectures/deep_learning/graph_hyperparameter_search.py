"""Recherche d'hyperparamètres partagée pour la famille GNN transductive (GCN/GraphSAGE/GAT).

Les trois architectures (`GNNModel`, `GraphSAGEModel`, `GATModel`) ne diffèrent que par la
couche Keras utilisée (`GCNLayer`/`GraphSAGELayer`/`GATLayer`, voir `graph_layers.py`) ;
cette fonction centralise tout le reste pour qu'aucune des trois ne duplique cette logique :
construction du graphe k-NN, découpage train/validation par masquage de noeuds (le graphe
reste transductif — une seule matrice d'adjacence pour tout le dataset — mais la perte
d'entraînement est calculée uniquement sur les noeuds "train" via `sample_weight`, et la
perte de validation Optuna uniquement sur les noeuds "validation" tenus à l'écart),
recherche Optuna sur le nombre de voisins k-NN, le nombre de couches cachées, les unités
cachées, l'optimiseur, le weight decay, le learning rate (+ scheduler), le nombre d'epochs,
et ré-entraînement final sur l'intégralité des noeuds avec les meilleurs hyperparamètres.

`batch_size` n'est pas recherché ici : l'entraînement transductif reste toujours "full
batch" (un batch = tous les noeuds), comme c'est l'usage standard pour GCN/GraphSAGE/GAT.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from shared.ai_engine.architectures.deep_learning.keras_hyperparameter_search import (
    ParamSource,
    TrainingControls,
    run_keras_hyperparameter_search,
    suggest_optimizer,
)
from shared.ai_engine.core.tabular_dataset import prepare_graph_dataset


def search_and_train_graph_model(
    layer_class: type,
    frame: pd.DataFrame,
    n_trials: int = 12,
) -> Any:
    """Recherche puis entraîne le meilleur modèle de graphe transductif pour `layer_class`."""

    import tensorflow as tf

    node_count = len(frame)
    validation_fraction = 0.2 if node_count >= 10 else 0.0
    if validation_fraction > 0:
        train_idx, val_idx = train_test_split(
            np.arange(node_count), test_size=validation_fraction, random_state=42
        )
    else:
        train_idx, val_idx = np.arange(node_count), np.array([], dtype=int)

    def build(source: ParamSource) -> tuple[Any, Any, Any, str]:
        neighbors = source.int("neighbors", 3, 10)
        features, adjacency, target, output_units, output_activation, loss = prepare_graph_dataset(
            frame, neighbors=min(neighbors, max(1, node_count - 1))
        )
        adjacency_tensor = tf.constant(adjacency)
        hidden_units = source.int("hidden_units", 8, 64, log=True)
        num_hidden_layers = source.int("num_hidden_layers", 1, 2)

        inputs = tf.keras.layers.Input(shape=(features.shape[1],))
        hidden = inputs
        for _ in range(num_hidden_layers):
            hidden = layer_class(hidden_units, adjacency_tensor)(hidden)
        outputs = layer_class(output_units, adjacency_tensor, activation=output_activation)(hidden)
        model = tf.keras.Model(inputs, outputs)
        return model, features, target, loss

    def compile_and_fit(source: ParamSource, model: Any, features: Any, target: Any, loss: str, epochs: int, sample_weight: Any | None) -> None:
        controls = TrainingControls(epochs=epochs, batch_size=len(features), steps_per_epoch=1, callbacks=[])
        optimizer = suggest_optimizer(source, controls)
        model.compile(optimizer=optimizer, loss=loss)
        model.fit(
            features,
            target,
            sample_weight=sample_weight,
            epochs=epochs,
            batch_size=len(features),
            verbose=0,
        )

    def objective(trial: Any) -> float:
        source = ParamSource(trial=trial)
        model, features, target, loss = build(source)
        epochs = source.categorical("epochs", [50, 100, 150, 200])

        sample_weight = np.ones(node_count, dtype="float32")
        if len(val_idx) > 0:
            sample_weight[val_idx] = 0.0
        compile_and_fit(source, model, features, target, loss, epochs, sample_weight)

        # Appel direct du modèle (et non `model.predict`, dont le batch_size par défaut de 32
        # romprait la matrice d'adjacence transductive, dimensionnée pour tous les noeuds).
        predictions = model(features, training=False).numpy()
        loss_fn = tf.keras.losses.get(loss)
        if len(val_idx) == 0:
            return float(np.asarray(loss_fn(target, predictions)).mean())

        validation_loss = loss_fn(
            np.asarray(target)[val_idx], np.asarray(predictions)[val_idx]
        )
        return float(np.asarray(validation_loss).mean())

    best_trial = run_keras_hyperparameter_search(objective, n_trials=n_trials)
    source = ParamSource(params=best_trial.params)
    model, features, target, loss = build(source)
    compile_and_fit(source, model, features, target, loss, best_trial.params["epochs"], sample_weight=None)
    return model
