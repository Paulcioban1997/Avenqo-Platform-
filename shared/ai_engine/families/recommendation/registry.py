"""Catalogue des modèles Recommendation : combine des architectures graphes partagées
(GNN, GraphSAGE, GAT, réutilisées depuis `architectures/deep_learning`) et des modèles
de recommandation classiques propres à cette famille.
"""

from shared.ai_engine.architectures.deep_learning.gat import GATModel
from shared.ai_engine.architectures.deep_learning.gnn import GNNModel
from shared.ai_engine.architectures.deep_learning.graphsage import GraphSAGEModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry
from shared.ai_engine.families.recommendation.models.collaborative_filtering import (
    CollaborativeFilteringModel,
)
from shared.ai_engine.families.recommendation.models.matrix_factorization import (
    MatrixFactorizationModel,
)


def build_recommendation_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("collaborative_filtering", CollaborativeFilteringModel)
    registry.register("matrix_factorization", MatrixFactorizationModel)
    registry.register("gnn", GNNModel)
    registry.register("graphsage", GraphSAGEModel)
    registry.register("gat", GATModel)
    return registry
