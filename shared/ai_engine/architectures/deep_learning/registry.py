"""Catalogue des modèles Deep Learning : unique source de vérité, réutilisée par
l'AI Engine pour son domaine générique et par toute famille métier (ex : Recommendation
importe GNNModel/GraphSAGEModel/GATModel directement d'ici, Synthetic importe
GANModel/CTGANModel/TVAEModel, Forecasting importe LSTMModel/GRUModel/TransformerModel).
Les architectures spécifiquement dédiées à la vision (CNN, ResNet, EfficientNet, ViT)
vivent dans `shared.ai_engine.architectures.vision`.
"""

from shared.ai_engine.architectures.deep_learning.autoencoder import AutoencoderModel
from shared.ai_engine.architectures.deep_learning.ctgan import CTGANModel
from shared.ai_engine.architectures.deep_learning.gan import GANModel
from shared.ai_engine.architectures.deep_learning.gat import GATModel
from shared.ai_engine.architectures.deep_learning.gnn import GNNModel
from shared.ai_engine.architectures.deep_learning.graphsage import GraphSAGEModel
from shared.ai_engine.architectures.deep_learning.gru import GRUModel
from shared.ai_engine.architectures.deep_learning.lstm import LSTMModel
from shared.ai_engine.architectures.deep_learning.mlp import MLPModel
from shared.ai_engine.architectures.deep_learning.transformer import TransformerModel
from shared.ai_engine.architectures.deep_learning.tvae import TVAEModel
from shared.ai_engine.architectures.deep_learning.vae import VAEModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry


def build_deep_learning_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("mlp", MLPModel)
    registry.register("lstm", LSTMModel)
    registry.register("gru", GRUModel)
    registry.register("transformer", TransformerModel)
    registry.register("autoencoder", AutoencoderModel)
    registry.register("vae", VAEModel)
    registry.register("gan", GANModel)
    registry.register("ctgan", CTGANModel)
    registry.register("tvae", TVAEModel)
    registry.register("gnn", GNNModel)
    registry.register("graphsage", GraphSAGEModel)
    registry.register("gat", GATModel)
    return registry
