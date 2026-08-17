"""Définitions de tâches réutilisables par les modules métiers."""

from shared.ai_engine.contracts import Task

BAD_REVIEW = Task("bad_review", "Bad Review Prediction")
DEMAND = Task("demand", "Demand Prediction")
WEEKLY_FORECAST = Task("weekly_forecast", "Weekly Forecast")
PRICE = Task("price", "Price Prediction")
SEGMENTATION = Task("segmentation", "Customer Segmentation")
RECOMMENDATION = Task("recommendation", "Recommendation System")
SENTIMENT = Task("sentiment", "Sentiment Analysis")
SYNTHETIC_DATA = Task("synthetic_data", "Synthetic Data Generation")
ANOMALY = Task("anomaly", "Anomaly Detection")
INVOICE_OCR = Task("invoice_ocr", "Invoice OCR")
EXPENSE_ANALYSIS = Task("expense_analysis", "Expense Analysis")
CASH_FLOW = Task("cash_flow", "Cash Flow Forecast")
FRAUD = Task("fraud", "Fraud Detection")
FINANCIAL_FORECAST = Task("financial_forecast", "Financial Forecast")
LEAD_SCORING = Task("lead_scoring", "Lead Scoring")
CHURN = Task("churn", "Churn Prediction")
LIFETIME_VALUE = Task("lifetime_value", "Customer Lifetime Value")
EMAIL_CLASSIFICATION = Task("email_classification", "Email Classification")
