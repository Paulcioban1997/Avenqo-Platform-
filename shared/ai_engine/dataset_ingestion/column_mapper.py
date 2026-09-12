"""Mapping sémantique multi-signal des colonnes vers le vocabulaire canonique (Phase 26 / Auto-Mapping).

Combine délibérément PLUSIEURS signaux :
1. Normalisation avancée du nom (gestion des espaces, casse, tirets, etc.)
2. Correspondance avec les alias connus du domaine e-commerce / Retail
3. Type sémantique détecté à partir du contenu réel des valeurs
4. Profilage des valeurs observées (codes ISO devise, emails, entiers, etc.)
5. Contexte global du dataset (présence d'autres colonnes e-commerce)
6. Garde-fous stricts contre les faux mappings incompatibles (ex. currency ≠ payment_id)

Principe fondamental : NO MAPPING est préférable à WRONG MAPPING.
Les colonnes ambiguës ou non reconnues sont conservées brutes (unmapped/unresolved)
sans jamais bloquer le client ni le pipeline.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Any

from shared.ai_engine.dataset_ingestion.canonical_fields import (
    CANONICAL_FIELD_ALIASES,
    CANONICAL_FIELD_SEMANTIC_TYPE,
    CANONICAL_FIELDS,
)
from shared.ai_engine.dataset_ingestion.type_inference import SemanticType, infer_semantic_type

_NORMALIZE = re.compile(r"[^a-z0-9]")
_WORD_BOUNDARY = re.compile(r"[_\-\s]+")


class MappingConfidence(str, Enum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNRESOLVED = "unresolved"


class MappingProvenance(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ColumnMappingSuggestion:
    original_column: str
    suggested_field: str | None
    confidence: MappingConfidence
    score: float
    alternatives: tuple[str, ...]
    reason: str


class SemanticColumnMapper:
    """Propose un auto-mapping robuste, multi-signal et non bloquant vers les champs canoniques."""

    def __init__(self, name_similarity_threshold: float = 0.65) -> None:
        self._threshold = name_similarity_threshold

    def suggest(
        self,
        columns: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
    ) -> tuple[ColumnMappingSuggestion, ...]:
        normalized_cols = {self._normalize(c) for c in columns}
        context = self._detect_dataset_context(normalized_cols)

        suggestions = []
        for column in columns:
            values = [row.get(column) for row in rows]
            column_type = infer_semantic_type(column, values)
            suggestions.append(
                self._suggest_for_column(column, column_type, values, context)
            )
        return tuple(suggestions)

    def _suggest_for_column(
        self,
        column: str,
        column_type: SemanticType,
        values: Sequence[Any],
        context: dict[str, bool],
    ) -> ColumnMappingSuggestion:
        cleaned_name = column.strip()
        normalized_column = self._normalize(cleaned_name)

        # 1. Vérification d'un alias exact direct
        exact_field = self._exact_alias_match(normalized_column)
        if exact_field is not None and not self._is_hard_incompatible(cleaned_name, exact_field, column_type):
            return ColumnMappingSuggestion(
                original_column=column,
                suggested_field=exact_field,
                confidence=MappingConfidence.EXACT,
                score=1.0,
                alternatives=(),
                reason=(
                    f"Alias exact reconnu pour '{exact_field}' "
                    f"(type détecté : {column_type.value})."
                ),
            )

        # 2. Contexte spécifique e-commerce pour colonnes ambiguës usuelles
        context_field = self._resolve_context_ambiguity(normalized_column, column_type, context)
        if context_field is not None:
            return ColumnMappingSuggestion(
                original_column=column,
                suggested_field=context_field,
                confidence=MappingConfidence.HIGH,
                score=0.95,
                alternatives=(),
                reason=f"Mapping contextuel résolu vers '{context_field}' (type : {column_type.value}).",
            )

        # 3. Évaluation multi-signal pour chaque champ canonique
        scored: list[tuple[str, float, str]] = []
        for field in CANONICAL_FIELDS:
            if self._is_hard_incompatible(cleaned_name, field, column_type):
                continue

            score, reason = self._compute_multi_signal_score(
                cleaned_name, normalized_column, field, column_type, values, context
            )
            if score >= 0.50:
                scored.append((field, score, reason))

        scored.sort(key=lambda item: item[1], reverse=True)

        if not scored or scored[0][1] < self._threshold:
            # Règle d'or : NO MAPPING est préférable à WRONG MAPPING.
            # Ne jamais inventer un mauvais mapping pour une colonne inconnue ou trop faible.
            return ColumnMappingSuggestion(
                original_column=column,
                suggested_field=None,
                confidence=MappingConfidence.UNRESOLVED,
                score=scored[0][1] if scored else 0.0,
                alternatives=tuple(field for field, _, _ in scored[:3]),
                reason="Conservé brut sans mapping métier (score insuffisant pour décision automatique).",
            )

        best_field, best_score, best_reason = scored[0]
        alternatives = tuple(field for field, _, _ in scored[1:4])

        if best_score >= 0.85:
            confidence = MappingConfidence.HIGH
        elif best_score >= 0.65:
            confidence = MappingConfidence.MEDIUM
        else:
            # En dessous de 0.65, laisser unmapped
            return ColumnMappingSuggestion(
                original_column=column,
                suggested_field=None,
                confidence=MappingConfidence.LOW,
                score=best_score,
                alternatives=alternatives,
                reason="Score trop faible : conservé sans mapping pour éviter toute erreur métier.",
            )

        return ColumnMappingSuggestion(
            original_column=column,
            suggested_field=best_field,
            confidence=confidence,
            score=round(best_score, 4),
            alternatives=alternatives,
            reason=best_reason,
        )

    def _is_hard_incompatible(
        self,
        column_name: str,
        target_field: str,
        column_type: SemanticType,
    ) -> bool:
        """Garde-fous absolus empêchant les faux mappings absurdes (ex: currency -> payment_id)."""
        lowered = column_name.lower().strip()

        # Règle 1 : La devise (currency) ne peut JAMAIS être un identifiant, ni une date, ni un montant
        if "currency" in lowered or "devise" in lowered or column_type == SemanticType.CURRENCY_CODE:
            if target_field != "currency":
                return True

        # Règle 2 : L'email client ne peut JAMAIS être un identifiant (customer_id, payment_id, product_id)
        if "email" in lowered or "courriel" in lowered or column_type == SemanticType.EMAIL:
            if target_field != "customer_email":
                return True

        # Règle 3 : Un statut de livraison ou commande (catégoriel) ne peut JAMAIS être une date/horodatage
        if any(s in lowered for s in ("status", "statut", "fulfillment", "state")):
            if target_field in ("delivery_timestamp", "order_timestamp"):
                return True

        # Règle 4 : Un champ date/horodatage ne peut JAMAIS correspondre à un montant, quantité ou identifiant
        if column_type == SemanticType.DATETIME:
            if target_field in (
                "unit_price", "total_amount", "quantity", "inventory_level",
                "customer_id", "order_id", "product_id", "payment_id", "currency"
            ):
                return True

        # Règle 5 : Les identifiants purs ne doivent pas matcher avec des champs purement textuels ou monétaires
        if column_type == SemanticType.IDENTIFIER and target_field in (
            "unit_price", "total_amount", "currency", "review_text"
        ):
            return True

        return False

    def _compute_multi_signal_score(
        self,
        column_name: str,
        normalized_column: str,
        field: str,
        column_type: SemanticType,
        values: Sequence[Any],
        context: dict[str, bool],
    ) -> tuple[float, str]:
        # 1. Alias score
        alias_score = 0.0
        aliases = CANONICAL_FIELD_ALIASES.get(field, ())
        normalized_aliases = {self._normalize(a) for a in aliases} | {self._normalize(field)}
        if normalized_column in normalized_aliases:
            alias_score = 1.0
        elif any(normalized_column.endswith(a) or normalized_column.startswith(a) for a in normalized_aliases if len(a) >= 4):
            alias_score = 0.80

        # 2. Name similarity
        name_score = self._best_name_similarity(normalized_column, field)

        # 3. Type compatibility
        expected_types = CANONICAL_FIELD_SEMANTIC_TYPE.get(field, ())
        if column_type in expected_types:
            type_score = 1.0
        elif column_type in (SemanticType.TEXT, SemanticType.CATEGORICAL) and any(
            t in (SemanticType.TEXT, SemanticType.CATEGORICAL) for t in expected_types
        ):
            type_score = 0.70
        elif column_type in (SemanticType.INTEGER, SemanticType.FLOAT) and any(
            t in (SemanticType.INTEGER, SemanticType.FLOAT, SemanticType.CURRENCY) for t in expected_types
        ):
            type_score = 0.75
        else:
            type_score = 0.20

        # 4. Value profile score
        value_score = 0.50
        present = [v for v in values if v is not None and str(v).strip() != ""]
        if present:
            if field == "currency" and column_type == SemanticType.CURRENCY_CODE:
                value_score = 1.0
            elif field == "customer_email" and column_type == SemanticType.EMAIL:
                value_score = 1.0
            elif field in ("quantity", "inventory_level") and column_type == SemanticType.INTEGER:
                value_score = 0.90
            elif field in ("unit_price", "total_amount") and column_type in (SemanticType.CURRENCY, SemanticType.FLOAT):
                value_score = 0.90
            elif field == "customer_country" and column_type == SemanticType.COUNTRY:
                value_score = 1.0

        # 5. Context score
        context_score = 0.50
        if field in ("inventory_level", "stock_quantity") and context.get("is_inventory"):
            context_score = 0.90
        elif field in ("quantity", "total_amount", "order_id") and context.get("is_orders"):
            context_score = 0.90
        elif field in ("customer_email", "customer_country") and context.get("has_customer_info"):
            context_score = 0.90

        # Formule multi-signal pondérée
        total = (
            0.35 * alias_score +
            0.25 * name_score +
            0.20 * type_score +
            0.10 * value_score +
            0.10 * context_score
        )

        reason = (
            f"Score multi-signal ({total:.2f}) [alias={alias_score:.2f}, nom={name_score:.2f}, "
            f"type={type_score:.2f}, profil={value_score:.2f}] pour '{field}'."
        )
        return total, reason

    def _resolve_context_ambiguity(
        self,
        normalized_column: str,
        column_type: SemanticType,
        context: dict[str, bool],
    ) -> str | None:
        """Résout intelligemment les cas ambigus selon le contexte du dataset."""
        # 'quantity' vs 'inventory_level'
        if normalized_column in ("quantity", "qty"):
            if context.get("is_inventory") and not context.get("is_orders"):
                return "inventory_level"
            return "quantity"

        if normalized_column in ("stock", "inventory", "stockquantity", "inventoryquantity"):
            return "inventory_level"

        # 'email'
        if normalized_column in ("email", "mail", "courriel") or column_type == SemanticType.EMAIL:
            return "customer_email"

        # 'country'
        if normalized_column in ("country", "pays") or column_type == SemanticType.COUNTRY:
            return "customer_country"

        # 'currency'
        if normalized_column in ("currency", "currencycode", "devise", "curr") or column_type == SemanticType.CURRENCY_CODE:
            return "currency"

        # 'sku'
        if normalized_column in ("sku", "itemcode", "productsku"):
            return "sku"

        # 'price'
        if normalized_column in ("price", "unitprice", "itemprice", "prix"):
            return "unit_price"

        # 'order_total' / 'total'
        if normalized_column in ("total", "ordertotal", "totalamount", "amount", "montanttotal"):
            return "total_amount"

        # 'name' / 'title'
        if normalized_column in ("name", "title", "producttitle", "itemname", "nom"):
            if context.get("is_inventory") or not context.get("has_customer_info"):
                return "product_name"

        return None

    def _detect_dataset_context(self, normalized_columns: set[str]) -> dict[str, bool]:
        is_inventory = bool(normalized_columns & {
            "stock", "inventory", "sku", "productid", "product", "productname",
            "stockquantity", "price", "unitprice"
        })
        is_orders = bool(normalized_columns & {"orderid", "ordernumber", "orders", "total", "totalamount", "revenue"})
        has_customer_info = bool(normalized_columns & {"customerid", "customer", "clientid", "email", "country"})
        return {
            "is_inventory": is_inventory,
            "is_orders": is_orders,
            "has_customer_info": has_customer_info,
        }

    def _exact_alias_match(self, normalized_column: str) -> str | None:
        for field, aliases in CANONICAL_FIELD_ALIASES.items():
            normalized_aliases = {self._normalize(alias) for alias in aliases} | {self._normalize(field)}
            if normalized_column in normalized_aliases:
                return field
        return None

    def _best_name_similarity(self, normalized_column: str, field: str) -> float:
        candidates = {self._normalize(alias) for alias in CANONICAL_FIELD_ALIASES.get(field, ())}
        candidates.add(self._normalize(field))
        return max(SequenceMatcher(None, normalized_column, candidate).ratio() for candidate in candidates)

    @staticmethod
    def _normalize(value: str) -> str:
        # Enlever les espaces superflus, normaliser les délimiteurs, basculer en minuscules
        val = value.strip().lower()
        # Remplacer les délimiteurs par rien pour comparer
        return _NORMALIZE.sub("", val)
