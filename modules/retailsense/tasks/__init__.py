"""Tâches exécutées par l'agent principal RetailSenseAI."""

from modules.retailsense.tasks.anomaly_detection import TASK as ANOMALY_DETECTION
from modules.retailsense.tasks.bad_review_prediction import TASK as BAD_REVIEW_PREDICTION
from modules.retailsense.tasks.churn_prediction import TASK as CHURN_PREDICTION
from modules.retailsense.tasks.customer_segmentation import TASK as CUSTOMER_SEGMENTATION
from modules.retailsense.tasks.demand_prediction import TASK as DEMAND_PREDICTION
from modules.retailsense.tasks.price_prediction import TASK as PRICE_PREDICTION
from modules.retailsense.tasks.recommendation import TASK as RECOMMENDATION
from modules.retailsense.tasks.sentiment_analysis import TASK as SENTIMENT_ANALYSIS
from modules.retailsense.tasks.synthetic_data_generation import TASK as SYNTHETIC_DATA_GENERATION
from modules.retailsense.tasks.weekly_forecast import TASK as WEEKLY_FORECAST

TASKS = (
    BAD_REVIEW_PREDICTION,
    DEMAND_PREDICTION,
    WEEKLY_FORECAST,
    PRICE_PREDICTION,
    CUSTOMER_SEGMENTATION,
    RECOMMENDATION,
    SENTIMENT_ANALYSIS,
    SYNTHETIC_DATA_GENERATION,
    ANOMALY_DETECTION,
    CHURN_PREDICTION,
)

__all__ = ["TASKS"]
