"""Couche d'explicabilité (XAI) — interne, admin/API uniquement.

Fournit, pour chaque modèle entraîné par `shared.ai_engine.training`, une
explication versionnée (`ExplanationArtifact`) enregistrée dans le
`ModelRegistry` existant, à côté de l'artefact du modèle.

Ce module ne doit JAMAIS être importé depuis un chemin visible par
l'utilisateur final : ni les noms de techniques (SHAP, permutation
importance, feature importance, attention weights...) ni les scores bruts
qu'il produit ne doivent apparaître dans une réponse API publique ou une UI.

Point d'entrée public : `service.explain_supervised` / `service.explain_neural_network`.
"""

from shared.ai_engine.explainability.types import ExplanationArtifact, ExplanationMethod

__all__ = ["ExplanationArtifact", "ExplanationMethod"]
