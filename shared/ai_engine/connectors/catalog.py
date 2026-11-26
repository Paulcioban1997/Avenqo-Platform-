"""Canonical metadata for the global Avenqo commerce connector catalog."""

from shared.ai_engine.connectors.commerce import (
    ConnectorAuthMethod,
    ConnectorCapability,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorImplementationStatus,
)

C = ConnectorCapability
S = ConnectorImplementationStatus
A = ConnectorAuthMethod
K = ConnectorCategory

COMMERCE = frozenset({C.ORDERS, C.CUSTOMERS, C.PRODUCTS, C.VARIANTS, C.INVENTORY, C.REFUNDS, C.FULFILLMENTS, C.INCREMENTAL_SYNC})
MARKETPLACE = frozenset({C.ORDERS, C.PRODUCTS, C.VARIANTS, C.INVENTORY, C.REFUNDS, C.FULFILLMENTS, C.INCREMENTAL_SYNC})
POS = frozenset({C.ORDERS, C.CUSTOMERS, C.PRODUCTS, C.VARIANTS, C.INVENTORY, C.LOCATIONS, C.PAYMENTS, C.REFUNDS, C.INCREMENTAL_SYNC})
PAYMENTS = frozenset({C.CUSTOMERS, C.PAYMENTS, C.REFUNDS, C.INCREMENTAL_SYNC})
MARKETING = frozenset({C.INCREMENTAL_SYNC, C.ANALYTICS})
CRM = frozenset({C.CUSTOMERS, C.INCREMENTAL_SYNC})
VOICE = frozenset({C.CUSTOMERS, C.INCREMENTAL_SYNC})
FULFILLMENT = frozenset({C.ORDERS, C.FULFILLMENTS, C.INVENTORY, C.INCREMENTAL_SYNC})


_DOCUMENTATION_KEYS = {
    "adobe_commerce": "adobe-commerce",
    "wix_ecommerce": "wix-ecommerce",
    "squarespace_commerce": "squarespace-commerce",
    "amazon_sp_api": "amazon-seller-central",
    "walmart_marketplace": "walmart-marketplace",
    "tiktok_shop": "tiktok-shop",
    "square_pos": "square",
    "clover_pos": "clover",
    "lightspeed_retail": "lightspeed-retail",
    "stripe": "stripe-commerce",
}


def _definition(
    provider: str,
    display_name: str,
    category: ConnectorCategory,
    *,
    status: ConnectorImplementationStatus = S.COMING_SOON,
    auth_method: ConnectorAuthMethod = A.OAUTH2,
    capabilities: frozenset[ConnectorCapability] = frozenset(),
    configuration_requirements: tuple[str, ...] = (),
    priority: str = "P2",
    scopes: tuple[str, ...] = (),
    webhooks: bool = False,
    incremental: bool = True,
    sandbox: bool = False,
    review: bool = False,
    external_registration: bool = True,
) -> ConnectorDefinition:
    oauth = auth_method in {A.OAUTH1, A.OAUTH2, A.OAUTH2_PKCE, A.PARTNER_AUTHORIZATION}
    return ConnectorDefinition(
        provider=provider,
        display_name=display_name,
        category=category,
        implementation_status=status,
        auth_method=auth_method,
        capabilities=capabilities,
        description_key=f"connector.{provider}.description",
        icon_key=provider,
        configuration_requirements=configuration_requirements,
        documentation_url=f"/docs/connectors/{_DOCUMENTATION_KEYS.get(provider, provider)}.md",
        supports_oauth=oauth,
        supports_webhooks=webhooks,
        supports_incremental_sync=incremental,
        external_registration_required=external_registration,
        callback_urls_required=oauth,
        webhook_urls_required=webhooks,
        scopes_required=scopes,
        review_required=review,
        sandbox_available=sandbox,
        priority=priority,
    )


# 22 Connecteurs Canoniques Avenqo — strict alignement avec connections-view.tsx
CANONICAL_22_DEFINITIONS: tuple[ConnectorDefinition, ...] = (
    # 1-7 E-Commerce
    _definition("shopify", "Shopify", K.ECOMMERCE, status=S.AVAILABLE, priority="P0", capabilities=COMMERCE | {C.DISCOUNTS, C.WEBHOOKS}, configuration_requirements=("shop_domain",), scopes=("read_orders", "read_customers", "read_products", "read_inventory", "read_fulfillments"), webhooks=True, sandbox=True),
    _definition("woocommerce", "WooCommerce", K.ECOMMERCE, status=S.AVAILABLE, auth_method=A.STORE_URL_PLUS_KEYS, priority="P0", capabilities=COMMERCE | {C.WEBHOOKS}, configuration_requirements=("store_url",), webhooks=True, external_registration=False),
    _definition("bigcommerce", "BigCommerce", K.ECOMMERCE, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=COMMERCE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True, sandbox=True),
    _definition("adobe_commerce", "Adobe Commerce (Magento)", K.ECOMMERCE, status=S.CONFIGURATION_REQUIRED, auth_method=A.STORE_URL_PLUS_KEYS, priority="P0", capabilities=COMMERCE, configuration_requirements=("store_url", "access_token")),
    _definition("wix_ecommerce", "Wix eCommerce", K.ECOMMERCE, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=COMMERCE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True),
    _definition("squarespace_commerce", "Squarespace Commerce", K.ECOMMERCE, status=S.CONFIGURATION_REQUIRED, priority="P1", capabilities=COMMERCE, configuration_requirements=("api_key",)),
    _definition("prestashop", "PrestaShop", K.ECOMMERCE, status=S.CONFIGURATION_REQUIRED, auth_method=A.STORE_URL_PLUS_KEYS, priority="P1", capabilities=COMMERCE, configuration_requirements=("store_url", "api_key")),

    # 8-12 Places de marché
    _definition("amazon_sp_api", "Amazon Seller Central (SP-API)", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE, configuration_requirements=("lwa_client_id", "lwa_client_secret", "aws_role_arn"), review=True, sandbox=True),
    _definition("ebay", "eBay", K.MARKETPLACE, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True, sandbox=True),
    _definition("etsy", "Etsy", K.MARKETPLACE, auth_method=A.OAUTH2_PKCE, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("client_id",), webhooks=True),
    _definition("walmart_marketplace", "Walmart Marketplace", K.MARKETPLACE, auth_method=A.CLIENT_CREDENTIALS, status=S.CONFIGURATION_REQUIRED, priority="P1", capabilities=MARKETPLACE, configuration_requirements=("client_id", "client_secret"), sandbox=True),
    _definition("tiktok_shop", "TikTok Shop", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("app_key", "app_secret"), webhooks=True, review=True, sandbox=True),

    # 13-15 Points de vente (POS)
    _definition("square_pos", "Square POS", K.POS, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=POS | {C.WEBHOOKS}, configuration_requirements=("application_id", "application_secret"), webhooks=True, sandbox=True),
    _definition("clover_pos", "Clover POS", K.POS, status=S.CONFIGURATION_REQUIRED, priority="P1", capabilities=POS, configuration_requirements=("app_id", "app_secret"), sandbox=True),
    _definition("lightspeed_retail", "Lightspeed Retail", K.POS, status=S.CONFIGURATION_REQUIRED, priority="P1", capabilities=POS, configuration_requirements=("client_id", "client_secret")),

    # 16-17 CRM & Calendriers
    _definition("google_calendar", "Google Calendar", K.CRM, status=S.AVAILABLE, priority="P0", capabilities=CRM, configuration_requirements=()),
    _definition("outlook_calendar", "Outlook Calendar", K.CRM, status=S.AVAILABLE, priority="P0", capabilities=CRM, configuration_requirements=()),

    # 18-19 Marketing & Publicité
    _definition("google_ads", "Google Ads", K.MARKETING, status=S.CONFIGURATION_REQUIRED, priority="P1", capabilities=MARKETING, configuration_requirements=("developer_token", "client_id", "client_secret")),
    _definition("meta_ads", "Meta Ads (Facebook & Instagram)", K.MARKETING, status=S.CONFIGURATION_REQUIRED, priority="P1", capabilities=MARKETING, configuration_requirements=("app_id", "app_secret", "access_token")),

    # 20 Voix & Téléphonie
    _definition("telnyx", "Telnyx Voice AI", K.VOICE, status=S.AVAILABLE, auth_method=A.CUSTOM, priority="P0", capabilities=VOICE, configuration_requirements=()),

    # 21 Facturation & Paiements
    _definition("stripe", "Stripe Facturation & Paiements", K.BILLING, status=S.AVAILABLE, auth_method=A.API_KEY, priority="P0", capabilities=PAYMENTS | {C.WEBHOOKS}, configuration_requirements=("api_key",), webhooks=True, sandbox=True),

    # 22 Logistique & Expédition
    _definition("shipstation", "ShipStation", K.FULFILLMENT, status=S.CONFIGURATION_REQUIRED, auth_method=A.API_KEY, priority="P1", capabilities=FULFILLMENT, configuration_requirements=("api_key", "api_secret")),
)

# Alias map for backwards compatibility
CONNECTOR_ALIASES: dict[str, str] = {
    "adobe-commerce": "adobe_commerce",
    "wix-ecommerce": "wix_ecommerce",
    "squarespace-commerce": "squarespace_commerce",
    "amazon-seller-central": "amazon_sp_api",
    "amazon_seller_central": "amazon_sp_api",
    "walmart-marketplace": "walmart_marketplace",
    "tiktok-shop": "tiktok_shop",
    "square": "square_pos",
    "clover": "clover_pos",
    "lightspeed-retail": "lightspeed_retail",
    "google-calendar": "google_calendar",
    "outlook-calendar": "outlook_calendar",
    "google-ads": "google_ads",
    "meta-ads": "meta_ads",
    "meta-commerce": "meta_ads",
    "stripe-commerce": "stripe",
}

# Rétrocompatibilité totale : COMMERCE_CONNECTOR_CATALOG contient les 22 canoniques + les alias legacy
COMMERCE_CONNECTOR_CATALOG: tuple[ConnectorDefinition, ...] = (
    *CANONICAL_22_DEFINITIONS,
    # Alias legacy pour ne casser aucun test existant
    _definition("adobe-commerce", "Adobe Commerce / Magento", K.ECOMMERCE, auth_method=A.STORE_URL_PLUS_KEYS, priority="P0", capabilities=COMMERCE, configuration_requirements=("store_url", "access_token")),
    _definition("wix-ecommerce", "Wix eCommerce", K.ECOMMERCE, priority="P0", capabilities=COMMERCE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True),
    _definition("squarespace-commerce", "Squarespace Commerce", K.ECOMMERCE, priority="P1", capabilities=COMMERCE, configuration_requirements=("client_id", "client_secret")),
    _definition("amazon-seller-central", "Amazon Seller Central / SP-API", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE, configuration_requirements=("lwa_client_id", "lwa_client_secret", "aws_role_arn"), review=True, sandbox=True),
    _definition("walmart-marketplace", "Walmart Marketplace", K.MARKETPLACE, auth_method=A.CLIENT_CREDENTIALS, priority="P1", capabilities=MARKETPLACE, configuration_requirements=("client_id", "client_secret"), sandbox=True),
    _definition("tiktok-shop", "TikTok Shop", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("app_key", "app_secret"), webhooks=True, review=True, sandbox=True),
    _definition("square", "Square", K.POS, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=POS | {C.WEBHOOKS}, configuration_requirements=("application_id", "application_secret"), webhooks=True, sandbox=True),
    _definition("clover", "Clover", K.POS, priority="P1", capabilities=POS, configuration_requirements=("app_id", "app_secret"), sandbox=True),
    _definition("lightspeed-retail", "Lightspeed Retail", K.POS, priority="P1", capabilities=POS, configuration_requirements=("client_id", "client_secret")),
    _definition("stripe-commerce", "Stripe", K.BILLING, capabilities=PAYMENTS | {C.WEBHOOKS}, configuration_requirements=("client_id",), webhooks=True, sandbox=True),
)