"""Architectures IA : unique source de vérité pour tous les algorithmes de la plateforme.

Chaque sous-dossier regroupe une catégorie technique d'architectures IA (Machine
Learning, Deep Learning, LLM, Vision, Audio, OCR). Un modèle donné (ex : CTGAN, LSTM,
GNN, ResNet) n'existe qu'à UN seul endroit dans tout le projet, sous forme d'une
sous-classe de `shared.ai_engine.core.model_stub.UntrainedModel`.

Les familles métier (`shared.ai_engine.families`) ne possèdent jamais leur propre copie
d'un modèle partagé : elles importent la classe depuis `architectures/` et l'enregistrent
comme candidat dans leur propre `registry.py`. Un modèle peut ainsi être réutilisé par
plusieurs familles (ex : LSTM par Forecasting ET par le domaine Deep Learning générique)
sans jamais être dupliqué.

Ajouter un nouveau modèle : créer un seul fichier dans la catégorie technique
correspondante, puis l'enregistrer dans le(s) registry.py qui en ont besoin. Aucun
autre fichier n'est modifié.
"""
