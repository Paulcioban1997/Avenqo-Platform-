"""Candidat Transformer, entraîné avec keras.layers.MultiHeadAttention.

Bloc encodeur minimal (attention multi-têtes + connexions résiduelles + normalisation +
réseau feed-forward), réutilisé tel quel par la famille Forecasting comme par Deep Learning
générique via `prepare_sequence_dataset` (même convention d'entrée que LSTM/GRU).

Recherche d'hyperparamètres : Optuna (voir `keras_hyperparameter_search.py`) sur le
nombre de blocs encodeurs, le nombre de têtes d'attention, la dimension de clé, les
unités feed-forward, le dropout, l'optimiseur, le weight decay, le learning rate (+
scheduler) et le nombre d'epochs/la taille de batch. Découpage train/validation
chronologique (`shuffle=False`) pour respecter l'ordre temporel des fenêtres glissantes.
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


class TransformerModel(UntrainedModel):
    candidate_id = "transformer"
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

        num_blocks = source.int("num_blocks", 1, 2)
        num_heads = source.int("num_heads", 1, 4)
        key_dim = source.int("key_dim", 8, 32, log=True)
        feed_forward_units = source.int("feed_forward_units", 16, 128, log=True)
        dropout = source.float("dropout", 0.0, 0.3)

        inputs = tf.keras.layers.Input(shape=(timesteps, feature_count))
        hidden = tf.keras.layers.Dense(feed_forward_units)(inputs)
        for _ in range(num_blocks):
            attention_output = tf.keras.layers.MultiHeadAttention(
                num_heads=num_heads, key_dim=key_dim, dropout=dropout
            )(hidden, hidden)
            residual = tf.keras.layers.LayerNormalization()(hidden + attention_output)
            feed_forward = tf.keras.layers.Dense(feed_forward_units, activation="relu")(residual)
            feed_forward = tf.keras.layers.Dropout(dropout)(feed_forward)
            feed_forward = tf.keras.layers.Dense(feed_forward_units)(feed_forward)
            hidden = tf.keras.layers.LayerNormalization()(residual + feed_forward)
        pooled = tf.keras.layers.GlobalAveragePooling1D()(hidden)
        outputs = tf.keras.layers.Dense(1)(pooled)

        model = tf.keras.Model(inputs, outputs)
        model.compile(optimizer=optimizer, loss="mse", metrics=["mae"])
        return model, controls
