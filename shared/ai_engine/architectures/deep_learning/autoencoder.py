"""Candidat Autoencodeur, entraîné avec un keras.Model encodeur/décodeur symétrique.

Entraînement non supervisé : reconstruit les features numériques du dataset (aucune
colonne cible n'est utilisée), ce qui produit une représentation latente compressée
réutilisable (détection d'anomalies, réduction de dimension, etc.).

Recherche d'hyperparamètres : Optuna (voir `keras_hyperparameter_search.py`) sur la
dimension latente, le nombre de couches et unités de l'encodeur (décodeur symétrique),
l'activation, le dropout, l'optimiseur, le weight decay, le learning rate (+ scheduler)
et le nombre d'epochs/la taille de batch. `_build_model` est appelée à l'identique
pendant la recherche et le ré-entraînement final (`ParamSource`).
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
from shared.ai_engine.core.tabular_dataset import load_dataframe, numeric_feature_matrix


class AutoencoderModel(UntrainedModel):
    candidate_id = "autoencoder"
    n_trials = 12

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        features = numeric_feature_matrix(frame)
        input_dim = features.shape[1]
        train_x, val_x = train_test_split(features, test_size=0.2, random_state=42)

        def objective(trial: Any) -> float:
            source = ParamSource(trial=trial)
            model, controls = self._build_model(source, input_dim, len(train_x))
            history = model.fit(
                train_x,
                train_x,
                validation_data=(val_x, val_x),
                epochs=controls.epochs,
                batch_size=controls.batch_size,
                callbacks=controls.callbacks,
                verbose=0,
            )
            return float(min(history.history["val_loss"]))

        best_trial = run_keras_hyperparameter_search(objective, n_trials=self.n_trials)
        source = ParamSource(params=best_trial.params)
        model, controls = self._build_model(source, input_dim, len(features))
        model.fit(features, features, epochs=controls.epochs, batch_size=controls.batch_size, verbose=0)
        return model

    def _build_model(self, source: ParamSource, input_dim: int, sample_count: int) -> tuple[Any, Any]:
        import tensorflow as tf

        controls = suggest_training_controls(source, sample_count)
        optimizer = suggest_optimizer(source, controls)

        activation = source.categorical("activation", ["relu", "tanh", "elu"])
        dropout = source.float("dropout", 0.0, 0.4)
        latent_dim = source.int("latent_dim", 2, max(2, min(32, input_dim)), log=True)
        num_layers = source.int("num_layers", 1, 2)

        hidden_low = max(latent_dim, 4)
        hidden_high = max(hidden_low + 1, input_dim * 2, 8)
        hidden_units = [
            source.int(f"units_{i}", hidden_low, hidden_high, log=True) for i in range(num_layers)
        ]

        inputs = tf.keras.layers.Input(shape=(input_dim,))
        encoded = inputs
        for units in hidden_units:
            encoded = tf.keras.layers.Dense(units, activation=activation)(encoded)
            if dropout > 0:
                encoded = tf.keras.layers.Dropout(dropout)(encoded)
        latent = tf.keras.layers.Dense(latent_dim, activation=activation)(encoded)

        decoded = latent
        for units in reversed(hidden_units):
            decoded = tf.keras.layers.Dense(units, activation=activation)(decoded)
            if dropout > 0:
                decoded = tf.keras.layers.Dropout(dropout)(decoded)
        outputs = tf.keras.layers.Dense(input_dim)(decoded)

        model = tf.keras.Model(inputs, outputs)
        model.compile(optimizer=optimizer, loss="mse")
        return model, controls
