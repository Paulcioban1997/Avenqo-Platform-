"""Structure de données du Recommendation Engine (filtrage collaboratif item-item).

Objet simple, sérialisable via joblib (comme les pipelines sklearn des
autres familles) : aucune dépendance à une base de données ou à une session
active au moment de la recommandation — tout ce qui est nécessaire est
calculé une fois à l'entraînement et stocké ici.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True, slots=True)
class ItemBasedRecommender:
    """Similarité item-item + historique utilisateur, propres à UNE entreprise.

    - `item_similarity` : matrice carrée (articles x articles), valeurs de
      similarité cosine entre 0 et 1.
    - `user_history` : pour chaque client, l'ensemble des articles avec
      lesquels il a déjà interagi (jamais recommandés à nouveau).
    - `item_popularity` : articles triés du plus au moins populaire, utilisé
      uniquement en secours pour un client inconnu ("cold start").
    - `n_neighbors` : nombre d'articles similaires considérés par article vu,
      hyperparamètre choisi par la recherche (voir `train_recommender.py`).
    """

    item_similarity: pd.DataFrame
    user_history: dict[str, set[str]]
    item_popularity: tuple[str, ...]
    n_neighbors: int

    def recommend(self, user_id: str, top_k: int, exclude: set[str] | None = None) -> list[str]:
        """Renvoie jusqu'à `top_k` identifiants d'articles recommandés pour ce client."""

        seen = set(self.user_history.get(user_id, set()))
        if exclude:
            seen = seen | exclude

        if user_id not in self.user_history:
            return [item for item in self.item_popularity if item not in seen][:top_k]

        scores = self._score_items(seen)
        ranked = scores.sort_values(ascending=False)
        return [item for item in ranked.index if item not in seen][:top_k]

    def _score_items(self, seen: set[str]) -> pd.Series:
        """Additionne, pour chaque article, sa similarité aux `n_neighbors`
        articles les plus proches parmi ceux déjà vus par le client."""

        known_seen = [item for item in seen if item in self.item_similarity.index]
        if not known_seen:
            return pd.Series(dtype=float)

        scores = pd.Series(0.0, index=self.item_similarity.columns)
        for item in known_seen:
            row = self.item_similarity.loc[item].sort_values(ascending=False)
            top_neighbors = row.iloc[: self.n_neighbors]
            scores = scores.add(top_neighbors, fill_value=0.0)
        return scores
