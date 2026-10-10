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
        "key": "google_calendar",
        "name": "Google Calendar",
        "category": "calendar",
        "availability": "available",
        "route": "/crm",
    },
    {
        "key": "stripe",
        "name": "Stripe Billing",
        "category": "billing",
        "availability": "available",
        "route": "/billing",
    },
    {
        "key": "telnyx",
        "name": "Telnyx Voice",
        "category": "voice",
        "availability": "available",
        "route": "/voice",
    },
    {
        "key": "etsy",
        "name": "Etsy",
        "category": "commerce",
        "availability": "coming_soon",
        "route": None,
    },
    {
        "key": "outlook_calendar",
        "name": "Outlook Calendar",
        "category": "calendar",
        "availability": "coming_soon",
        "route": None,
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
