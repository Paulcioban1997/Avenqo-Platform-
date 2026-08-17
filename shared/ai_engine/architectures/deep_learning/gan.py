"""Candidat GAN (générateur/discriminateur denses adverses).

Entraîne un GAN dense minimal sur les features numériques du dataset (génération de
données synthétiques dans le même espace). Boucle d'entraînement adverse manuelle
(`tf.GradientTape`), car `model.fit` standard ne s'applique pas à un GAN à deux réseaux.
Retourne le générateur entraîné (l'artefact utile pour générer des données synthétiques).

Recherche d'hyperparamètres : Optuna (voir `keras_hyperparameter_search.py`) sur la
dimension latente, les unités cachées (générateur et discriminateur, indépendamment via
des préfixes `generator_`/`discriminator_` pour éviter toute collision de nom), le
learning rate (+ scheduler)/optimiseur/weight decay (également indépendants par réseau),
le nombre d'epochs et la taille de batch. La perte finale du générateur (sur un batch de
validation tenu à l'écart) sert de métrique Optuna à minimiser — un GAN n'a pas de perte
de validation "naturelle" comme un modèle supervisé, donc cette perte adverse est
l'équivalent pragmatique le plus proche disponible pour comparer des essais entre eux.
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


class GANModel(UntrainedModel):
    candidate_id = "gan"
    n_trials = 12

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        features = numeric_feature_matrix(frame)
        input_dim = features.shape[1]
        train_x, val_x = train_test_split(features, test_size=0.2, random_state=42)

        def objective(trial: Any) -> float:
            import tensorflow as tf

            source = ParamSource(trial=trial)
            generator, discriminator, controls = self._build_networks(source, input_dim, len(train_x))
            self._train_loop(source, generator, discriminator, controls, train_x)

            latent_dim = generator.input_shape[-1]
            noise = tf.random.normal((len(val_x), latent_dim))
            fake_batch = generator(noise, training=False)
            fake_predictions = discriminator(fake_batch, training=False)
            loss_fn = tf.keras.losses.BinaryCrossentropy()
            return float(loss_fn(tf.ones_like(fake_predictions), fake_predictions).numpy())

        best_trial = run_keras_hyperparameter_search(objective, n_trials=self.n_trials)
        source = ParamSource(params=best_trial.params)
        generator, discriminator, controls = self._build_networks(source, input_dim, len(features))
        self._train_loop(source, generator, discriminator, controls, features)
        return generator

    def _build_networks(
        self, source: ParamSource, input_dim: int, sample_count: int
    ) -> tuple[Any, Any, Any]:
        import tensorflow as tf

        controls = suggest_training_controls(source, sample_count, with_validation=False)
        latent_dim = source.int("latent_dim", 2, max(2, min(32, input_dim)), log=True)
        generator_hidden = source.int("generator_hidden_units", max(latent_dim, 8), max(latent_dim + 1, input_dim * 2, 16), log=True)
        discriminator_hidden = source.int("discriminator_hidden_units", 8, max(input_dim * 2, 16), log=True)

        generator = tf.keras.Sequential(
            [
                tf.keras.layers.Input(shape=(latent_dim,)),
                tf.keras.layers.Dense(generator_hidden, activation="relu"),
                tf.keras.layers.Dense(input_dim),
            ]
        )
        discriminator = tf.keras.Sequential(
            [
                tf.keras.layers.Input(shape=(input_dim,)),
                tf.keras.layers.Dense(discriminator_hidden, activation="relu"),
                tf.keras.layers.Dense(1, activation="sigmoid"),
            ]
        )
        return generator, discriminator, controls

    def _train_loop(
        self,
        source: ParamSource,
        generator: Any,
        discriminator: Any,
        controls: Any,
        features: Any,
    ) -> None:
        import tensorflow as tf

        generator_optimizer = suggest_optimizer(source, controls, prefix="generator_")
        discriminator_optimizer = suggest_optimizer(source, controls, prefix="discriminator_")
        loss_fn = tf.keras.losses.BinaryCrossentropy()
        latent_dim = generator.input_shape[-1]

        batched_dataset = (
            tf.data.Dataset.from_tensor_slices(features)
            .shuffle(max(len(features), 1))
            .batch(min(controls.batch_size, len(features)))
        )

        for _ in range(controls.epochs):
            for real_batch in batched_dataset:
                batch_size = tf.shape(real_batch)[0]

                noise = tf.random.normal((batch_size, latent_dim))
                with tf.GradientTape() as disc_tape:
                    fake_batch = generator(noise, training=True)
                    real_predictions = discriminator(real_batch, training=True)
                    fake_predictions = discriminator(fake_batch, training=True)
                    disc_loss = loss_fn(
                        tf.ones_like(real_predictions), real_predictions
                    ) + loss_fn(tf.zeros_like(fake_predictions), fake_predictions)
                disc_gradients = disc_tape.gradient(
                    disc_loss, discriminator.trainable_variables
                )
                discriminator_optimizer.apply_gradients(
                    zip(disc_gradients, discriminator.trainable_variables)
                )

                noise = tf.random.normal((batch_size, latent_dim))
                with tf.GradientTape() as gen_tape:
                    fake_batch = generator(noise, training=True)
                    fake_predictions = discriminator(fake_batch, training=True)
                    gen_loss = loss_fn(tf.ones_like(fake_predictions), fake_predictions)
                gen_gradients = gen_tape.gradient(gen_loss, generator.trainable_variables)
                generator_optimizer.apply_gradients(
                    zip(gen_gradients, generator.trainable_variables)
                )
