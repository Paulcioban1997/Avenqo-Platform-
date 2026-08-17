"""Catalogue des modèles Forecasting : combine des architectures partagées
(XGBoost, LightGBM, LSTM, GRU, Transformer, réutilisées depuis `architectures/`) et des
modèles de séries temporelles propres à cette famille (ARIMA, SARIMA, Prophet, N-BEATS, TFT).
"""

from shared.ai_engine.architectures.deep_learning.gru import GRUModel
from shared.ai_engine.architectures.deep_learning.lstm import LSTMModel
from shared.ai_engine.architectures.deep_learning.transformer import TransformerModel
from shared.ai_engine.architectures.machine_learning.lightgbm import LightGBMModel
from shared.ai_engine.architectures.machine_learning.xgboost import XGBoostModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry
from shared.ai_engine.families.forecasting.models.arima import ARIMAModel
from shared.ai_engine.families.forecasting.models.nbeats import NBeatsModel
from shared.ai_engine.families.forecasting.models.prophet import ProphetModel
from shared.ai_engine.families.forecasting.models.sarima import SARIMAModel
from shared.ai_engine.families.forecasting.models.tft import TFTModel


def build_forecasting_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("prophet", ProphetModel)
    registry.register("arima", ARIMAModel)
    registry.register("sarima", SARIMAModel)
    registry.register("xgboost", XGBoostModel)
    registry.register("lightgbm", LightGBMModel)
    registry.register("lstm", LSTMModel)
    registry.register("gru", GRUModel)
    registry.register("transformer", TransformerModel)
    registry.register("tft", TFTModel)
    registry.register("nbeats", NBeatsModel)
    return registry
