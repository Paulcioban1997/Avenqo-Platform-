"""Candidat LSTM, entraîné avec keras.layers.LSTM.

Réutilisé tel quel par la famille Forecasting (voir families/forecasting/registry.py) :
sur une série temporelle univariée, l'entrée est une fenêtre glissante des dernières
valeurs ; sur un dataset tabulaire générique, chaque ligne est traitée comme une séquence
à un seul pas de temps sur les features numériques (voir `prepare_sequence_dataset`).

Recherche d'hyperparamètres : Optuna (voir `keras_hyperparameter_search.py`) sur le
nombre de couches LSTM empilées, les unités par couche, le dropout récurrent,
l'optimiseur, le weight decay, le learning rate (+ scheduler) et le nombre
d'epochs/la taille de batch. Découpage train/validation chronologique (`shuffle=False`)
pour respecter l'ordre temporel des fenêtres glissantes.
"""

from __future__ import annotations

from typing import Any

from sklearn.model_selection import train_test_split

from shared.ai_engine.architectures.deep_learning.keras_hyperparameter_search import (
    ParamSource,
    run_keras_hyperparameter_search,
    suggest_optimizer,
    suggest_training_controls,
)
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel
from shared.ai_engine.core.tabular_dataset import load_dataframe, prepare_sequence_dataset


class LSTMModel(UntrainedModel):
    candidate_id = "lstm"
    n_trials = 12

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        features, target = prepare_sequence_dataset(frame)
        train_x, val_x, train_y, val_y = train_test_split(features, target, test_size=0.2, shuffle=False)

        def objective(trial: Any) -> float:
            source = ParamSource(trial=trial)
            model, controls = self._build_model(source, features.shape[1], features.shape[2], len(train_x))
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
        model, controls = self._build_model(source, features.shape[1], features.shape[2], len(features))
        model.fit(features, target, epochs=controls.epochs, batch_size=controls.batch_size, verbose=0)
        return model

    def _build_model(
        self, source: ParamSource, timesteps: int, feature_count: int, sample_count: int
    ) -> tuple[Any, Any]:
        import tensorflow as tf

        controls = suggest_training_controls(source, sample_count)
        optimizer = suggest_optimizer(source, controls)

        num_layers = source.int("num_layers", 1, 2)
        dropout = source.float("dropout", 0.0, 0.4)

        model = tf.keras.Sequential([tf.keras.layers.Input(shape=(timesteps, feature_count))])
        for layer_index in range(num_layers):
            units = source.int(f"units_{layer_index}", 8, 128, log=True)
            model.add(
                tf.keras.layers.LSTM(
                    units, dropout=dropout, return_sequences=layer_index < num_layers - 1
                )
            )
        model.add(tf.keras.layers.Dense(1))
        model.compile(optimizer=optimizer, loss="mse", metrics=["mae"])
        return model, controls
