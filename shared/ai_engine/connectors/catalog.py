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
        documentation_url=f"/docs/connectors/{provider}.md",
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


COMMERCE_CONNECTOR_CATALOG: tuple[ConnectorDefinition, ...] = (
    _definition("shopify", "Shopify", K.ECOMMERCE, status=S.AVAILABLE, priority="P0", capabilities=COMMERCE | {C.DISCOUNTS, C.WEBHOOKS}, configuration_requirements=("shop_domain",), scopes=("read_orders", "read_customers", "read_products", "read_inventory", "read_fulfillments"), webhooks=True, sandbox=True),
    _definition("woocommerce", "WooCommerce", K.ECOMMERCE, status=S.AVAILABLE, auth_method=A.STORE_URL_PLUS_KEYS, priority="P0", capabilities=COMMERCE | {C.WEBHOOKS}, configuration_requirements=("store_url",), webhooks=True, external_registration=False),
    _definition("bigcommerce", "BigCommerce", K.ECOMMERCE, priority="P0", capabilities=COMMERCE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True, sandbox=True),
    _definition("adobe-commerce", "Adobe Commerce / Magento", K.ECOMMERCE, auth_method=A.STORE_URL_PLUS_KEYS, priority="P0", capabilities=COMMERCE, configuration_requirements=("store_url", "access_token")),
    _definition("wix-ecommerce", "Wix eCommerce", K.ECOMMERCE, priority="P0", capabilities=COMMERCE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True),
    _definition("squarespace-commerce", "Squarespace Commerce", K.ECOMMERCE, priority="P1", capabilities=COMMERCE, configuration_requirements=("client_id", "client_secret")),
    _definition("prestashop", "PrestaShop", K.ECOMMERCE, auth_method=A.STORE_URL_PLUS_KEYS, priority="P1", capabilities=COMMERCE, configuration_requirements=("store_url", "api_key")),
    _definition("ecwid", "Ecwid", K.ECOMMERCE, priority="P1", capabilities=COMMERCE, configuration_requirements=("client_id", "client_secret")),
    _definition("shopware", "Shopware", K.ECOMMERCE, auth_method=A.CLIENT_CREDENTIALS, priority="P1", capabilities=COMMERCE, configuration_requirements=("store_url", "client_id", "client_secret")),
    _definition("salesforce-commerce-cloud", "Salesforce Commerce Cloud", K.ECOMMERCE, auth_method=A.CLIENT_CREDENTIALS, capabilities=COMMERCE, configuration_requirements=("tenant_id", "client_id", "client_secret")),
    _definition("commercetools", "commercetools", K.ECOMMERCE, auth_method=A.CLIENT_CREDENTIALS, capabilities=COMMERCE, configuration_requirements=("project_key", "client_id", "client_secret")),
    _definition("vtex", "VTEX", K.ECOMMERCE, auth_method=A.CLIENT_CREDENTIALS, capabilities=COMMERCE, configuration_requirements=("account_name", "client_id", "client_secret")),
    _definition("amazon-seller-central", "Amazon Seller Central / SP-API", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE, configuration_requirements=("lwa_client_id", "lwa_client_secret", "aws_role_arn"), review=True, sandbox=True),
    _definition("ebay", "eBay", K.MARKETPLACE, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True, sandbox=True),
    _definition("etsy", "Etsy", K.MARKETPLACE, auth_method=A.OAUTH2_PKCE, priority="P0", capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("client_id",), webhooks=True),
    _definition("walmart-marketplace", "Walmart Marketplace", K.MARKETPLACE, auth_method=A.CLIENT_CREDENTIALS, priority="P1", capabilities=MARKETPLACE, configuration_requirements=("client_id", "client_secret"), sandbox=True),
    _definition("tiktok-shop", "TikTok Shop", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("app_key", "app_secret"), webhooks=True, review=True, sandbox=True),
    _definition("meta-commerce", "Meta Commerce / Facebook & Instagram Shops", K.MARKETPLACE, capabilities=frozenset({C.CATALOG, C.PRODUCTS, C.INVENTORY}), configuration_requirements=("app_id", "app_secret"), review=True),
    _definition("mercado-libre", "Mercado Libre", K.MARKETPLACE, capabilities=MARKETPLACE | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True),
    _definition("mirakl", "Mirakl", K.MARKETPLACE, auth_method=A.API_KEY, capabilities=MARKETPLACE, configuration_requirements=("operator_url", "api_key")),
    _definition("shopee", "Shopee", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, capabilities=MARKETPLACE, configuration_requirements=("partner_id", "partner_key"), review=True, sandbox=True),
    _definition("lazada", "Lazada", K.MARKETPLACE, auth_method=A.PARTNER_AUTHORIZATION, capabilities=MARKETPLACE, configuration_requirements=("app_key", "app_secret"), review=True),
    _definition("square", "Square", K.POS, status=S.CONFIGURATION_REQUIRED, priority="P0", capabilities=POS | {C.WEBHOOKS}, configuration_requirements=("application_id", "application_secret"), webhooks=True, sandbox=True),
    _definition("lightspeed-retail", "Lightspeed Retail", K.POS, priority="P1", capabilities=POS, configuration_requirements=("client_id", "client_secret")),
    _definition("clover", "Clover", K.POS, priority="P1", capabilities=POS, configuration_requirements=("app_id", "app_secret"), sandbox=True),
    _definition("shopify-pos", "Shopify POS", K.POS, capabilities=POS | {C.WEBHOOKS}, configuration_requirements=("shop_domain",), webhooks=True),
    _definition("stripe-commerce", "Stripe", K.PAYMENTS, capabilities=PAYMENTS | {C.WEBHOOKS}, configuration_requirements=("client_id",), webhooks=True, sandbox=True),
    _definition("paypal", "PayPal", K.PAYMENTS, auth_method=A.CLIENT_CREDENTIALS, capabilities=PAYMENTS | {C.WEBHOOKS}, configuration_requirements=("client_id", "client_secret"), webhooks=True, sandbox=True),
    _definition("google-merchant-center", "Google Merchant Center", K.CATALOG, priority="P1", capabilities=frozenset({C.CATALOG, C.PRODUCTS, C.INVENTORY, C.INCREMENTAL_SYNC}), configuration_requirements=("client_id", "client_secret")),
    _definition("shipstation", "ShipStation", K.FULFILLMENT, auth_method=A.API_KEY, capabilities=frozenset({C.ORDERS, C.FULFILLMENTS, C.INVENTORY, C.INCREMENTAL_SYNC}), configuration_requirements=("api_key", "api_secret")),
)