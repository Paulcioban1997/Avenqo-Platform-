"""Catalogue Marketplace : disponibilité réelle uniquement."""

from __future__ import annotations

from modules.registry import BUSINESS_MODULE_REGISTRY, ModuleAvailability


CONNECTORS = (
    {
        "key": "shopify",
        "name": "Shopify",
        "category": "commerce",
        "availability": "available",
        "route": "/connections",
    },
    {
        "key": "woocommerce",
        "name": "WooCommerce",
        "category": "commerce",
        "availability": "available",
        "route": "/connections",
    },
    {
        "key": "bigcommerce",
        "name": "BigCommerce",
        "category": "commerce",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "adobe_commerce",
        "name": "Adobe Commerce (Magento)",
        "category": "commerce",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "wix_ecommerce",
        "name": "Wix eCommerce",
        "category": "commerce",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "squarespace_commerce",
        "name": "Squarespace Commerce",
        "category": "commerce",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "prestashop",
        "name": "PrestaShop",
        "category": "commerce",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "amazon_sp_api",
        "name": "Amazon Seller Central (SP-API)",
        "category": "marketplace",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "ebay",
        "name": "eBay",
        "category": "marketplace",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "etsy",
        "name": "Etsy",
        "category": "marketplace",
        "availability": "partner_approval_pending",
        "route": "/connections",
    },
    {
        "key": "walmart_marketplace",
        "name": "Walmart Marketplace",
        "category": "marketplace",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "tiktok_shop",
        "name": "TikTok Shop",
        "category": "marketplace",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "square_pos",
        "name": "Square POS",
        "category": "pos",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "clover_pos",
        "name": "Clover POS",
        "category": "pos",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "lightspeed_retail",
        "name": "Lightspeed Retail",
        "category": "pos",
        "availability": "configuration_required",
        "route": "/connections",
    },
    {
        "key": "google_calendar",
        "name": "Google Calendar",
        "category": "calendar",
        "availability": "available",
        "route": "/crm",
    },
    {
        "key": "outlook_calendar",
        "name": "Outlook Calendar",
        "category": "calendar",
        "availability": "available",
        "route": "/crm",
    },
    {
        "key": "google_ads",
        "name": "Google Ads",
        "category": "marketing",
        "availability": "configuration_required",
        "route": "/marketing",
    },
    {
        "key": "meta_ads",
        "name": "Meta Ads",
        "category": "marketing",
        "availability": "configuration_required",
        "route": "/marketing",
    },
    {
        "key": "telnyx",
        "name": "Telnyx Voice",
        "category": "voice",
        "availability": "available",
        "route": "/voice",
    },
    {
        "key": "stripe",
        "name": "Stripe Billing",
        "category": "billing",
        "availability": "available",
        "route": "/billing",
    },
    {
        "key": "shipstation",
        "name": "ShipStation",
        "category": "fulfillment",
        "availability": "configuration_required",
        "route": "/connections",
    },
)


def marketplace_catalog() -> dict:
    modules = [
        {
            "key": module.key,
            "name": module.display_name,
            "description": module.description,
            "category": module.category,
            "availability": module.availability.value,
            "premium": module.premium,
            "installable": module.availability == ModuleAvailability.AVAILABLE,
        }
        for module in BUSINESS_MODULE_REGISTRY
    ]
    return {
        "modules": modules,
        "connectors": list(CONNECTORS),
        "categories": sorted({item["category"] for item in modules + list(CONNECTORS)}),
    }
