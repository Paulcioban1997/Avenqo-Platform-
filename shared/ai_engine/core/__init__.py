"""Couche générique partagée par toutes les familles d'intelligence artificielle.

Rien ici ne connaît un modèle concret (Random Forest, CNN, Transformer...). Cette
couche définit uniquement les contrats et l'algorithme commun (entraîner, évaluer,
sélectionner) que chaque famille sous `shared/ai_engine/families/` réutilise.
"""
