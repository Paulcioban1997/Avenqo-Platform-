"""Vocabulaire métier canonique de RetailSenseAI (Phase 26).

Ce vocabulaire est volontairement restreint : il ne couvre que les champs
métier réellement consommés par les capacités RetailSenseAI existantes
(`modules/retailsense/training_specs.py`, `shared/ai_engine/task_resolution`),
et non une nomenclature ERP générique inventée.
"""

from __future__ import annotations

from shared.ai_engine.dataset_ingestion.type_inference import SemanticType

# Champ canonique -> alias connus (noms de colonnes déjà observés ou
# plausibles chez des entreprises clientes différentes). Chaque alias est
# comparé après normalisation (minuscules, sans ponctuation).
CANONICAL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "customer_id": (
        "customer_id", "user_id", "client_id", "client_number", "buyer_id",
        "buyer_uuid", "client_ref", "customer_number", "customer",
    ),
    "order_id": (
        "order_id", "order_number", "sale_number", "transaction_ref",
        "transaction_id", "invoice_number", "purchase_id", "checkout_id",
    ),
    "product_id": (
        "product_id", "item_id", "sku", "product_code", "article_id",
        "item_code", "product_sku", "id_produit",
    ),
    "seller_id": (
        "seller_id", "merchant_id", "vendor_id", "store_id", "shop_id",
        "seller_code", "merchant_code", "vendor_code",
    ),
    "payment_id": (
        "payment_id", "payment_reference", "payment_ref", "transaction_payment_id",
        "receipt_id",
    ),
    "review_id": (
        "review_id", "feedback_id", "rating_id", "comment_id",
    ),
    "product_name": (
        "product", "product_name", "item_name", "article", "produit",
    ),
    "product_category": (
        "category", "product_category", "item_category", "categorie",
        "categorie_produit",
    ),
    "inventory_level": (
        "stock", "stock_level", "inventory", "inventory_level",
        "quantity_in_stock", "stock_quantity",
    ),
    "order_timestamp": (
        "date", "order_date", "created_at", "timestamp", "datetime",
        "period", "sale_date", "purchased_at", "purchase_date",
        "purchase_timestamp", "order_created_at", "transaction_date",
    ),
    "delivery_timestamp": (
        "delivery_date", "delivered_at", "delivery_timestamp",
        "fulfilled_at", "fulfillment_date", "shipped_at", "shipping_date",
    ),
    "quantity": (
        "quantity", "units", "units_sold", "quantity_ordered",
        "sales_quantity", "qty",
    ),
    "unit_price": (
        "price", "unit_price", "selling_price", "sale_price", "item_price",
    ),
    "total_amount": (
        "revenue", "total", "amount_paid", "sales", "total_amount",
        "amount", "order_total", "payment_value", "transaction_total",
        "gross_amount", "gross_total", "payment_amount", "invoice_total",
        "net_amount", "net_total",
    ),
    "freight_amount": (
        "freight", "freight_value", "freight_amount", "shipping_cost",
        "shipping_amount", "delivery_cost",
    ),
    "payment_method": (
        "payment", "payment_type", "payment_method", "payment_channel",
        "payment_provider", "tender_type",
    ),
    "review_text": (
        "comment", "review", "feedback_message", "customer_comment",
        "review_text", "review_comment",
    ),
    "review_score": (
        "rating", "review_score", "stars", "score",
    ),
    "churn_flag": (
        "churn", "is_churn", "churned",
    ),
}

# Type sémantique attendu pour chaque champ canonique (utilisé par le
# `SemanticColumnMapper` comme garde-fou contre les faux positifs de simple
# similarité de nom, ex. `customer_id` vs `customer_review`).
CANONICAL_FIELD_SEMANTIC_TYPE: dict[str, tuple[SemanticType, ...]] = {
    "customer_id": (SemanticType.IDENTIFIER,),
    "order_id": (SemanticType.IDENTIFIER,),
    "product_id": (SemanticType.IDENTIFIER,),
    "seller_id": (SemanticType.IDENTIFIER,),
    "payment_id": (SemanticType.IDENTIFIER,),
    "review_id": (SemanticType.IDENTIFIER,),
    "product_name": (SemanticType.TEXT, SemanticType.CATEGORICAL),
    "product_category": (SemanticType.TEXT, SemanticType.CATEGORICAL),
    "inventory_level": (SemanticType.INTEGER, SemanticType.FLOAT),
    "order_timestamp": (SemanticType.DATETIME,),
    "delivery_timestamp": (SemanticType.DATETIME,),
    "quantity": (SemanticType.INTEGER, SemanticType.FLOAT),
    "unit_price": (SemanticType.CURRENCY, SemanticType.FLOAT, SemanticType.INTEGER),
    "total_amount": (SemanticType.CURRENCY, SemanticType.FLOAT, SemanticType.INTEGER),
    "freight_amount": (SemanticType.CURRENCY, SemanticType.FLOAT, SemanticType.INTEGER),
    "payment_method": (SemanticType.TEXT, SemanticType.CATEGORICAL),
    "review_text": (SemanticType.TEXT,),
    "review_score": (SemanticType.INTEGER, SemanticType.FLOAT, SemanticType.PERCENTAGE),
    "churn_flag": (SemanticType.BOOLEAN, SemanticType.CATEGORICAL),
}

CANONICAL_FIELDS: tuple[str, ...] = tuple(CANONICAL_FIELD_ALIASES)
