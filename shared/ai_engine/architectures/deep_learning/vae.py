"""Candidat VAE (Autoencodeur variationnel), à espace latent probabiliste keras.

Recherche d'hyperparamètres : Optuna (voir `keras_hyperparameter_search.py`) sur la
dimension latente, le nombre de couches/unités de l'encodeur (décodeur symétrique),
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


class VAEModel(UntrainedModel):
    candidate_id = "vae"
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
        latent_dim = source.int("latent_dim", 2, max(2, min(32, input_dim)), log=True)
        hidden = source.int("hidden_units", max(latent_dim, 4), max(latent_dim + 1, input_dim * 2, 8), log=True)

        class Sampling(tf.keras.layers.Layer):
            def call(self, inputs):
                mean, log_var = inputs
                epsilon = tf.random.normal(shape=tf.shape(mean))
                return mean + tf.exp(0.5 * log_var) * epsilon

        encoder_inputs = tf.keras.layers.Input(shape=(input_dim,))
        hidden_layer = tf.keras.layers.Dense(hidden, activation=activation)(encoder_inputs)
        z_mean = tf.keras.layers.Dense(latent_dim)(hidden_layer)
        z_log_var = tf.keras.layers.Dense(latent_dim)(hidden_layer)
        z = Sampling()([z_mean, z_log_var])
        encoder = tf.keras.Model(encoder_inputs, [z_mean, z_log_var, z])

        latent_inputs = tf.keras.layers.Input(shape=(latent_dim,))
        decoder_hidden = tf.keras.layers.Dense(hidden, activation=activation)(latent_inputs)
        decoder_outputs = tf.keras.layers.Dense(input_dim)(decoder_hidden)
        decoder = tf.keras.Model(latent_inputs, decoder_outputs)

        class VAE(tf.keras.Model):
            def __init__(self, encoder, decoder, **kwargs):
                super().__init__(**kwargs)
                self.encoder = encoder
                self.decoder = decoder

            def call(self, inputs):
                z_mean, z_log_var, z = self.encoder(inputs)
                reconstruction = self.decoder(z)
                kl_loss = -0.5 * tf.reduce_mean(
                    1 + z_log_var - tf.square(z_mean) - tf.exp(z_log_var)
                )
                self.add_loss(kl_loss)
                return reconstruction

        vae = VAE(encoder, decoder)
        vae.compile(optimizer=optimizer, loss="mse")
        return vae, controls
