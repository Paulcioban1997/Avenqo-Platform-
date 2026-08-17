"""Candidat Perceptron multicouche (Dense), entraîné avec keras.Sequential / Dense.

Recherche d'hyperparamètres : Optuna (voir `keras_hyperparameter_search.py`) sur le
nombre de couches, les unités par couche, le dropout, l'activation, l'optimiseur, le
weight decay, le learning rate (+ scheduler cosine decay optionnel), le nombre d'epochs
et la taille de batch. Réutilise `build_dense_network` (autorité unique de construction
des réseaux denses, déjà utilisée par `shared.ai_engine.training.train_neural_network`)
pour la construction du réseau — zéro duplication de la boucle de couches. `_build_model`
est appelée à l'identique pendant la recherche (via `ParamSource(trial=...)`) et pendant
le ré-entraînement final (via `ParamSource(params=...)`) : zéro duplication entre les deux.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

from shared.ai_engine.architectures.deep_learning.keras_dense_builder import build_dense_network
from shared.ai_engine.architectures.deep_learning.keras_hyperparameter_search import (
    ParamSource,
    run_keras_hyperparameter_search,
    suggest_optimizer,
    suggest_training_controls,
)
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel
from shared.ai_engine.core.tabular_dataset import (
    detect_target_column,
    load_dataframe,
    numeric_feature_matrix,
)


class MLPModel(UntrainedModel):
    candidate_id = "mlp"
    n_trials = 15

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        target_column = detect_target_column(frame)
        features = numeric_feature_matrix(frame, exclude=(target_column,))
        target = frame[target_column]

        if pd.api.types.is_numeric_dtype(target) and target.nunique() > 20:
            task_type = "regression"
            output_size = 1
            y = target.astype("float64").to_numpy()
            stratify = None
        else:
            task_type = "classification"
            encoded, uniques = pd.factorize(target)
            output_size = max(2, len(uniques))
            y = encoded
            stratify = y if pd.Series(y).value_counts().min() >= 2 else None

        train_x, val_x, train_y, val_y = train_test_split(
            features, y, test_size=0.2, random_state=42, stratify=stratify
        )

        def objective(trial: Any) -> float:
            source = ParamSource(trial=trial)
            model, controls = self._build_model(source, features.shape[1], task_type, output_size, len(train_x))
            history = model.fit(
                train_x,
                train_y,
                validation_data=(val_x, val_y),
                epochs=controls.epochs,
                batch_size=controls.batch_size,
                callbacks=controls.callbacks,
                verbose=0,
            )
            return float(min(history.history["val_loss"]))

        best_trial = run_keras_hyperparameter_search(objective, n_trials=self.n_trials)
        source = ParamSource(params=best_trial.params)
        model, controls = self._build_model(source, features.shape[1], task_type, output_size, len(features))
        model.fit(features, y, epochs=controls.epochs, batch_size=controls.batch_size, verbose=0)
        return model

    def _build_model(
        self,
        source: ParamSource,
        input_size: int,
        task_type: str,
        output_size: int,
        sample_count: int,
    ) -> tuple[Any, Any]:
        controls = suggest_training_controls(source, sample_count)
        optimizer = suggest_optimizer(source, controls)
        activation = source.categorical("activation", ["relu", "tanh", "elu"])
        dropout = source.float("dropout", 0.0, 0.5)
        num_layers = source.int("num_layers", 1, 3)
        hidden_units = tuple(source.int(f"units_{i}", 16, 256, log=True) for i in range(num_layers))

        model = build_dense_network(
            input_size=input_size,
            task_type=task_type,
            output_size=output_size,
            hidden_units=hidden_units,
            learning_rate=0.0,  # ignoré : `optimizer` est déjà configuré
            activation=activation,
            dropout=dropout,
            optimizer=optimizer,
        )
        return model, controls
