"""Advertising connectors package for Google Ads and Meta Ads."""

from backend.app.connectors.ads.base import (
    AdCampaign,
    AdsConfigurationMissingError,
    AdsConnectionStatus,
    AdsConnectorError,
    AdsPerformanceSummary,
    BaseAdsConnector,
)
from backend.app.connectors.ads.google_ads import GoogleAdsConnector
from backend.app.connectors.ads.meta_ads import MetaAdsConnector

__all__ = [
    "AdCampaign",
    "AdsConfigurationMissingError",
    "AdsConnectionStatus",
    "AdsConnectorError",
    "AdsPerformanceSummary",
    "BaseAdsConnector",
    "GoogleAdsConnector",
    "MetaAdsConnector",
]

