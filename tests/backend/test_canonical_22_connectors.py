"""Tests de validation P1 : Matrice canonique des 22 connecteurs Avenqo.

Vérifie :
1. Parité exacte avec les 22 cartes de `connections-view.tsx`.
2. Absence des anciens noms ERP/comptables obsolètes (Salesforce, SAP, Oracle, QuickBooks, Xero, HubSpot).
3. Résolution transparente des alias (ex. `adobe-commerce` -> `adobe_commerce`, `square` -> `square_pos`).
4. Répartition des catégories : 7 e-commerce, 5 marketplace, 3 pos, 2 crm, 2 marketing, 1 voice, 1 billing, 1 fulfillment = 22 connecteurs.
5. Fonctionnement de l'endpoint `GET /api/v1/connectors/catalog`.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from backend.app.routers.commerce import canonical_connectors_catalog
from backend.app.services.canonical_connectors import (
    CANONICAL_22_CONNECTORS,
    get_canonical_connector,
    resolve_canonical_key,
)
from shared.ai_engine.connectors.catalog import COMMERCE_CONNECTOR_CATALOG, CONNECTOR_ALIASES
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry

EXPECTED_22_KEYS = [
    "shopify",
    "woocommerce",
    "bigcommerce",
    "adobe_commerce",
    "wix_ecommerce",
    "squarespace_commerce",
    "prestashop",
    "amazon_sp_api",
    "ebay",
    "etsy",
    "walmart_marketplace",
    "tiktok_shop",
    "square_pos",
    "clover_pos",
    "lightspeed_retail",
    "google_calendar",
    "outlook_calendar",
    "google_ads",
    "meta_ads",
    "telnyx",
    "stripe",
    "shipstation",
]

OBSOLETE_ERP_KEYS = [
    "salesforce_commerce",
    "sap_commerce",
    "oracle_commerce",
    "quickbooks",
    "xero",
    "hubspot",
]


def test_canonical_22_keys_and_count():
    assert len(CANONICAL_22_CONNECTORS) == 22
    actual_keys = [c["key"] for c in CANONICAL_22_CONNECTORS]
    assert actual_keys == EXPECTED_22_KEYS

    # Verify absence of outdated ERP/accounting placeholders
    for obsolete in OBSOLETE_ERP_KEYS:
        assert obsolete not in actual_keys


def test_canonical_22_categories_breakdown():
    categories = {}
    for c in CANONICAL_22_CONNECTORS:
        cat = c["category"]
        categories[cat] = categories.get(cat, 0) + 1

    assert categories["commerce"] == 7
    assert categories["marketplace"] == 5
    assert categories["pos"] == 3
    assert categories["crm"] == 2
    assert categories["marketing"] == 2
    assert categories["voice"] == 1
    assert categories["billing"] == 1
    assert categories["fulfillment"] == 1
    assert sum(categories.values()) == 22


def test_alias_resolution():
    assert resolve_canonical_key("adobe-commerce") == "adobe_commerce"
    assert resolve_canonical_key("amazon-seller-central") == "amazon_sp_api"
    assert resolve_canonical_key("square") == "square_pos"
    assert resolve_canonical_key("clover") == "clover_pos"
    assert resolve_canonical_key("wix-ecommerce") == "wix_ecommerce"
    assert resolve_canonical_key("squarespace-commerce") == "squarespace_commerce"
    assert resolve_canonical_key("tiktok-shop") == "tiktok_shop"
    assert resolve_canonical_key("stripe-commerce") == "stripe"

    # Direct canonical keys resolve to themselves
    assert resolve_canonical_key("shopify") == "shopify"
    assert resolve_canonical_key("telnyx") == "telnyx"
    assert resolve_canonical_key("shipstation") == "shipstation"

    # get_canonical_connector retrieves the definition
    adobe = get_canonical_connector("adobe-commerce")
    assert adobe is not None
    assert adobe["name"] == "Adobe Commerce (Magento)"
    assert adobe["category"] == "commerce"


def test_registry_resolves_canonical_and_aliases():
    registry = CommerceConnectorRegistry()

    # Canonical keys
    shopify = registry.definition("shopify")
    assert shopify.provider == "shopify"

    adobe_can = registry.definition("adobe_commerce")
    assert adobe_can.provider == "adobe_commerce"

    # Hyphenated aliases
    adobe_alias = registry.definition("adobe-commerce")
    assert adobe_alias.provider in {"adobe_commerce", "adobe-commerce"}

    amazon_alias = registry.definition("amazon-seller-central")
    assert amazon_alias is not None


def test_canonical_connectors_catalog_endpoint():
    mock_identity = MagicMock()
    mock_tenant = MagicMock()

    result = canonical_connectors_catalog(identity=mock_identity, __=mock_tenant)
    assert result["total_count"] == 22
    assert len(result["connectors"]) == 22
    assert result["categories"]["commerce"] == 7
    assert result["categories"]["marketplace"] == 5
    assert result["categories"]["pos"] == 3
    assert result["categories"]["crm"] == 2
    assert result["categories"]["marketing"] == 2
    assert result["categories"]["voice"] == 1
    assert result["categories"]["billing"] == 1
    assert result["categories"]["fulfillment"] == 1
