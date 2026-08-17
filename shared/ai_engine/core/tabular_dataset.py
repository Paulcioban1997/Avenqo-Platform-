"""Chargement pragmatique d'un `DatasetArtifact` pour l'entraînement réel des modèles.

Limitation de contrat connue (documentée aussi dans
`shared/ai_engine/architectures/machine_learning/optimizer.py`) : `DatasetArtifact` ne
transporte ni DataFrame déjà chargé, ni colonne cible explicite, ni structure de graphe.
Faire évoluer ce contrat (ajouter `target_column`, `date_column`, une matrice d'adjacence...)
est une décision produit hors du périmètre d'un ajout de modèle individuel.

En attendant, ce module centralise — une seule fois, pour toute la Phase 4 (Time Series)
et la Phase 5 (Deep Learning) — les heuristiques nécessaires pour que chaque candidat
"réel" puisse s'entraîner directement à partir d'un `DatasetArtifact` :

- `load_dataframe` : lit `dataset.uri` (CSV local uniquement pour l'instant).
- `detect_datetime_column` / `detect_target_column` : heuristiques de repérage de colonnes.
- `build_lag_features` / `build_sequence_windows` : mise en forme série temporelle.
- `numeric_feature_matrix` : mise en forme tabulaire générique (Dense, GAN, VAE, GNN...).
- `knn_adjacency` : graphe de similarité k-NN utilisé comme substitut pragmatique à une
  structure de graphe explicite pour GNN/GraphSAGE/GAT (voir docstring de chaque modèle).

Toute nouvelle "vraie" implémentation de modèle doit réutiliser ces fonctions plutôt que
ré-implémenter sa propre logique de chargement/mise en forme.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from shared.ai_engine.contracts import DatasetArtifact

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_dataframe(dataset: DatasetArtifact) -> pd.DataFrame:
    """Charge `dataset.uri` en DataFrame. Seuls les fichiers CSV locaux sont pris en charge."""

    path = Path(dataset.uri)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(
            f"Entraînement impossible : fichier introuvable pour dataset.uri={dataset.uri!r} "
            f"(résolu en {path}). Seuls les CSV locaux sont pris en charge pour l'instant."
        )
    return pd.read_csv(path)


def detect_datetime_column(frame: pd.DataFrame) -> str | None:
    """Retourne la première colonne qui ressemble à une date/heure, sinon None."""

    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            return column
    for column in frame.columns:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            try:
                pd.to_datetime(frame[column], errors="raise")
                return column
            except (ValueError, TypeError):
                continue
    return None


def detect_target_column(frame: pd.DataFrame, exclude: tuple[str, ...] = ()) -> str:
    """Heuristique : la dernière colonne restante après exclusion est la cible.

    Convention volontairement simple et documentée, en attendant que `DatasetArtifact`
    porte une colonne cible explicite.
    """

    candidates = [column for column in frame.columns if column not in exclude]
    if not candidates:
        raise ValueError("Aucune colonne cible disponible dans le dataset.")
    return candidates[-1]


def build_lag_features(values: pd.Series, lags: int) -> tuple[pd.DataFrame, pd.Series]:
    """Transforme une série temporelle univariée en tableau supervisé (lags -> valeur suivante)."""

    frame = pd.DataFrame({f"lag_{i}": values.shift(i) for i in range(1, lags + 1)})
    frame["target"] = values.values
    frame = frame.dropna().reset_index(drop=True)
    return frame.drop(columns=["target"]), frame["target"]


def build_sequence_windows(values: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Découpe un vecteur 1D en fenêtres glissantes `(samples, window, 1)` -> valeur suivante."""

    values = np.asarray(values, dtype="float32").reshape(-1)
    if len(values) <= window:
        raise ValueError(
            f"Série trop courte ({len(values)} points) pour une fenêtre de {window}."
        )
    x_samples = [values[i : i + window] for i in range(len(values) - window)]
    y_samples = values[window:]
    features = np.array(x_samples, dtype="float32").reshape(-1, window, 1)
    targets = np.array(y_samples, dtype="float32")
    return features, targets


def numeric_feature_matrix(frame: pd.DataFrame, exclude: tuple[str, ...] = ()) -> np.ndarray:
    """Mise en forme tabulaire générique : encode les catégorielles, impute par la moyenne."""

    columns = [column for column in frame.columns if column not in exclude]
    encoded = pd.get_dummies(frame[columns], drop_first=False)
    encoded = encoded.apply(pd.to_numeric, errors="coerce")
    encoded = encoded.fillna(encoded.mean(numeric_only=True)).fillna(0.0)
    return encoded.to_numpy(dtype="float32")


def knn_adjacency(features: np.ndarray, k: int = 5) -> np.ndarray:
    """Construit une matrice d'adjacence dense (normalisée) à partir d'un graphe de similarité k-NN.

    Substitut pragmatique à une structure de graphe explicite (absente de `DatasetArtifact`) :
    chaque échantillon est relié à ses `k` plus proches voisins dans l'espace des features. Une
    approche standard en apprentissage semi-supervisé sur graphe quand aucun graphe n'est fourni.
    """

    from sklearn.neighbors import NearestNeighbors

    n_samples = features.shape[0]
    k = max(1, min(k, n_samples - 1))
    neighbors = NearestNeighbors(n_neighbors=k + 1).fit(features)
    _, indices = neighbors.kneighbors(features)

    adjacency = np.zeros((n_samples, n_samples), dtype="float32")
    for row, neighbor_indices in enumerate(indices):
        for col in neighbor_indices:
            if col != row:
                adjacency[row, col] = 1.0
                adjacency[col, row] = 1.0

    adjacency += np.eye(n_samples, dtype="float32")
    degree = adjacency.sum(axis=1, keepdims=True)
    degree[degree == 0] = 1.0
    return adjacency / degree


def prepare_sequence_dataset(
    frame: pd.DataFrame, window: int = 10
) -> tuple[np.ndarray, np.ndarray]:
    """Prépare un jeu de données séquentiel `(samples, timesteps, features)` pour LSTM/GRU/Transformer.

    Réutilisé tel quel par la famille Forecasting et par Deep Learning générique :
    - dataset "série temporelle univariée" (colonne date détectée + une seule colonne
      numérique restante) -> fenêtres glissantes des dernières valeurs (cas Forecasting) ;
    - dataset tabulaire générique -> chaque ligne devient une séquence à un seul pas de
      temps sur l'ensemble des features numériques (cas Deep Learning générique).
    """

    datetime_column = detect_datetime_column(frame)
    remaining = [column for column in frame.columns if column != datetime_column]

    if datetime_column is not None and len(remaining) == 1:
        ordered = frame.sort_values(datetime_column)
        series = ordered[remaining[0]].astype("float64").to_numpy()
        window = min(window, max(2, len(series) // 2))
        return build_sequence_windows(series, window=window)

    exclude = (datetime_column,) if datetime_column else ()
    target_column = detect_target_column(frame, exclude=exclude)
    features = numeric_feature_matrix(frame, exclude=exclude + (target_column,))
    x = features.reshape(features.shape[0], 1, features.shape[1])
    y = frame[target_column].astype("float64").to_numpy()
    return x, y


def prepare_graph_dataset(
    frame: pd.DataFrame, neighbors: int = 5
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, str | None, str]:
    """Prépare un jeu de données transductif pour GNN/GraphSAGE/GAT.

    Retourne `(features, adjacency, target, output_units, output_activation, loss)`, avec la
    cible encodée pour une régression (colonne numérique à forte cardinalité) ou une
    classification (sinon). Réutilisé à l'identique par GNNModel/GraphSAGEModel/GATModel pour
    éviter de dupliquer trois fois la même détection cible/adjacence.
    """

    target_column = detect_target_column(frame)
    features = numeric_feature_matrix(frame, exclude=(target_column,))
    adjacency = knn_adjacency(features, k=neighbors)
    target = frame[target_column]

    if pd.api.types.is_numeric_dtype(target) and target.nunique() > 20:
        return features, adjacency, target.astype("float64").to_numpy(), 1, None, "mse"

    encoded, uniques = pd.factorize(target)
    output_units = max(2, len(uniques))
    return features, adjacency, encoded, output_units, "softmax", "sparse_categorical_crossentropy"

