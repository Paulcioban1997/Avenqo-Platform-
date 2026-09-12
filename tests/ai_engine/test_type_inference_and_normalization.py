from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner
from shared.ai_engine.dataset_ingestion.type_inference import (
    SemanticType,
    infer_semantic_type,
)


def test_identifiers_and_contact_fields_are_not_numeric_metrics() -> None:
    assert infer_semantic_type("customer_code", ["000123", "000124"]) == SemanticType.IDENTIFIER
    assert infer_semantic_type("phone", ["+1 514 555 0101"]) == SemanticType.PHONE
    assert infer_semantic_type("postal_code", ["H2X 1Y4"]) == SemanticType.POSTAL_CODE
    assert infer_semantic_type("email", ["luc@example.ca"]) == SemanticType.EMAIL
    assert infer_semantic_type("product_sku", ["AVN-001"]) == SemanticType.SKU
    assert infer_semantic_type("website", ["https://example.ca"]) == SemanticType.URL


def test_currency_numbers_are_normalized_for_common_locales() -> None:
    assert CompanyDatasetCleaner._convert_numeric("$1,499.00") == (1499, True)
    assert CompanyDatasetCleaner._convert_numeric("1.499,00") == (1499, True)
    assert CompanyDatasetCleaner._convert_numeric("1,499") == (1499, True)


def test_ambiguous_numeric_format_is_preserved() -> None:
    assert CompanyDatasetCleaner._convert_numeric("1,2,34") == ("1,2,34", False)