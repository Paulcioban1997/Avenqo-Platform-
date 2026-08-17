"""Couches Graph Neural Network minimales, Keras natif (alternative à torch_geometric).

`torch_geometric`/`dgl` (implémentations de référence pour GNN/GraphSAGE/GAT) ne sont pas
installés dans cet environnement (installation lourde/fragile sous Windows, décision
volontairement non prise sans confirmation explicite). Ces couches implémentent les mêmes
idées d'agrégation de voisinage, sur un graphe transductif complet — la matrice d'adjacence
est fixe pour tout le jeu de données, construite une seule fois via
`shared.ai_engine.core.tabular_dataset.knn_adjacency` (substitut pragmatique à une structure
de graphe explicite, absente de `DatasetArtifact`) — directement avec des opérations
TensorFlow/Keras, pour rester dans la pile déjà installée (tensorflow/keras).

Limitation connue : `GATLayer` calcule des scores d'attention sur toutes les paires de
noeuds (O(n²)), une simplification acceptable pour des graphes de taille modeste mais qui
ne remplace pas une implémentation d'attention de graphe creuse (sparse) à grande échelle.
"""

from __future__ import annotations

import tensorflow as tf


class GCNLayer(tf.keras.layers.Layer):
    """Convolution de graphe générique : H' = activation(A_norm @ X @ W + b)."""

    def __init__(self, units: int, adjacency: tf.Tensor, activation: str | None = "relu", **kwargs):
        super().__init__(**kwargs)
        self.units = units
        self.adjacency = adjacency
        self.activation = tf.keras.activations.get(activation)

    def build(self, input_shape):
        self.kernel = self.add_weight(
            shape=(input_shape[-1], self.units),
            initializer="glorot_uniform",
            trainable=True,
            name="kernel",
        )
        self.bias = self.add_weight(shape=(self.units,), initializer="zeros", trainable=True, name="bias")

    def call(self, inputs):
        aggregated = tf.matmul(self.adjacency, inputs)
        return self.activation(tf.matmul(aggregated, self.kernel) + self.bias)


class GraphSAGELayer(tf.keras.layers.Layer):
    """GraphSAGE (agrégation moyenne) : H' = activation([X ; A_mean @ X] @ W + b)."""

    def __init__(self, units: int, adjacency: tf.Tensor, activation: str | None = "relu", **kwargs):
        super().__init__(**kwargs)
        self.units = units
        self.adjacency = adjacency
        self.activation = tf.keras.activations.get(activation)

    def build(self, input_shape):
        self.kernel = self.add_weight(
            shape=(input_shape[-1] * 2, self.units),
            initializer="glorot_uniform",
            trainable=True,
            name="kernel",
        )
        self.bias = self.add_weight(shape=(self.units,), initializer="zeros", trainable=True, name="bias")

    def call(self, inputs):
        neighbor_mean = tf.matmul(self.adjacency, inputs)
        combined = tf.concat([inputs, neighbor_mean], axis=-1)
        return self.activation(tf.matmul(combined, self.kernel) + self.bias)


class GATLayer(tf.keras.layers.Layer):
    """Attention de graphe simplifiée (un seul head) : coefficients appris entre voisins."""

    def __init__(self, units: int, adjacency: tf.Tensor, activation: str | None = "relu", **kwargs):
        super().__init__(**kwargs)
        self.units = units
        self.adjacency_mask = tf.cast(adjacency > 0, dtype="float32")
        self.activation = tf.keras.activations.get(activation)

    def build(self, input_shape):
        self.kernel = self.add_weight(
            shape=(input_shape[-1], self.units),
            initializer="glorot_uniform",
            trainable=True,
            name="kernel",
        )
        self.attention_kernel = self.add_weight(
            shape=(2 * self.units, 1),
            initializer="glorot_uniform",
            trainable=True,
            name="attention_kernel",
        )
        self.bias = self.add_weight(shape=(self.units,), initializer="zeros", trainable=True, name="bias")

    def call(self, inputs):
        projected = tf.matmul(inputs, self.kernel)
        n = tf.shape(projected)[0]
        repeated_i = tf.repeat(projected, repeats=n, axis=0)
        tiled_j = tf.tile(projected, multiples=[n, 1])
        pairs = tf.concat([repeated_i, tiled_j], axis=-1)
        scores = tf.reshape(tf.matmul(pairs, self.attention_kernel), (n, n))
        scores = tf.nn.leaky_relu(scores)

        negative_infinity = tf.fill(tf.shape(scores), tf.constant(-1e9, dtype=scores.dtype))
        masked_scores = tf.where(self.adjacency_mask > 0, scores, negative_infinity)
        attention = tf.nn.softmax(masked_scores, axis=-1)

        aggregated = tf.matmul(attention, projected)
        return self.activation(aggregated + self.bias)
