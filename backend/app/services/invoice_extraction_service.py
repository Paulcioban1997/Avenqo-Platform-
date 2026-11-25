"""Service déterministe d'extraction structurée de factures en `Decimal` et vérification mathématique.

Conçu pour éliminer définitivement toute perte de montants sur les factures Excel multi-feuilles
(ex: factures de transport formatées en grille non-tabulaire, cellules fusionnées, formules Excel
avec ou sans cache), PDF, DOCX, CSV et OCR.

Règles strictes :
- ZÉRO calcul en `float` : tous les montants utilisent exclusivement `decimal.Decimal`.
- Provenance obligatoire (`file_name`, `sheet_name`, `cell_ref`, `raw_value`, `normalized_value`,
  `data_type`, `extracted_at`, `confidence`, `verification_status`).
- Désambiguïsation stricte :
  * Ne confond JAMAIS prix unitaire vs total, sous-total vs total TTC, solde antérieur vs total facturé,
    montant payé vs solde dû, dates (`2026-11-21`, `21 novembre 2026`) vs montants, numéros de facture/PO
    (`PO Nr. 17175`, `INV-2026-001`) vs montants, taux de taxe (`5%`, `9,975%`) ou numéros TPS/TVQ
    (`RT0001`, `TQ0001`) vs montants, ni quantités physiques (`lbs`, `kg`, `km`, `palettes`) vs montants.
  * Ne traite JAMAIS une formule Excel sans cache (`=SUM(...)` avec `cached_value=None`) comme un montant.
- Vérification mathématique : `sum(line_items) - discount + tax_total == total_amount`
  avec tolérance d'arrondi documentée (`Decimal("0.02")`), gestion des prix taxes incluses et notes de crédit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
import unicodedata
from typing import Any

from .document_extraction import (
    CellProvenance,
    DocumentExtractionBundle,
    ExtractedSheet,
    bundle_from_extracted_text,
    extract_document_bundle,
)

ROUNDING_TOLERANCE = Decimal("0.02")
TWO_PLACES = Decimal("0.01")

KNOWN_CURRENCIES = frozenset({"CAD", "USD", "EUR", "GBP", "CHF"})

_FRENCH_MONTHS: dict[str, int] = {
    "janvier": 1,
    "janv": 1,
    "fevrier": 2,
    "fevr": 2,
    "mars": 3,
    "avril": 4,
    "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "juil": 7,
    "aout": 8,
    "septembre": 9,
    "sept": 9,
    "octobre": 10,
    "oct": 10,
    "novembre": 11,
    "nov": 11,
    "decembre": 12,
    "dec": 12,
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Unités physiques qui ne sont JAMAIS des montants monétaires
_PHYSICAL_UNIT_PATTERN = re.compile(
    r"\b(?:kg|kgs|lbs|lb|km|kms|miles|palettes?|pallets?|heures?|hours?|hrs?)\b",
    re.IGNORECASE,
)

# Numéros d'enregistrement fiscal canadiens (ex: 123456789 RT0001 / 1234567890 TQ0001)
_TAX_REG_CLEAN_PATTERN = re.compile(
    r"\b\d{9,10}\s*(?:RT|TQ|RC|RP)\s*\d{0,4}\b",
    re.IGNORECASE,
)

# Taux de pourcentage entre parenthèses ou accolés aux taxes : (5%), 9,975 %, 14.975%
_PERCENT_CLEAN_PATTERN = re.compile(
    r"\(?\s*\d{1,2}(?:[.,]\d{1,4})?\s*%\s*\)?"
)

# Dates ISO ou JJ/MM/AAAA ou textes "21 novembre 2026"
_ISO_OR_SLASH_DATE_RE = re.compile(
    r"\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b"
)
_TEXTUAL_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+([A-Za-zéèêëàâîïôùûç\.]{3,12})\s+(\d{4})\b"
    r"|\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)


def _fold_text(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text.casefold())
    cleaned = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", cleaned).strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_decimal_fr(amount: Decimal) -> str:
    """Formate un `Decimal` en style français lisible (`1 250,50`) sans perte."""
    q = amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    sign = "-" if q < 0 else ""
    abs_q = abs(q)
    int_str, frac_str = format(abs_q, "f").split(".")
    groups: list[str] = []
    while int_str:
        groups.append(int_str[-3:])
        int_str = int_str[:-3]
    grouped_int = " ".join(reversed(groups))
    return f"{sign}{grouped_int},{frac_str}"


@dataclass(frozen=True, slots=True)
class ParsedMonetaryValue:
    amount: Decimal
    currency: str | None
    raw_matched: str


@dataclass(frozen=True, slots=True)
class ProvenancedAmount:
    """Montant monétaire `Decimal` assorti de sa provenance cellule/page certifiée."""

    amount: Decimal
    currency: str | None
    label: str
    file_name: str
    sheet_name: str | None
    cell_ref: str
    coordinate: str
    raw_value: Any
    normalized_value: str
    formula: str | None
    uncached_formula: bool
    data_type: str
    extracted_at: str
    confidence: float
    verification_status: str
    is_hidden_sheet: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount": format(self.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f"),
            "amount_formatted_fr": format_decimal_fr(self.amount),
            "currency": self.currency,
            "label": self.label,
            "file_name": self.file_name,
            "sheet_name": self.sheet_name,
            "cell_ref": self.cell_ref,
            "coordinate": self.coordinate,
            "raw_value": str(self.raw_value) if isinstance(self.raw_value, Decimal) else self.raw_value,
            "normalized_value": self.normalized_value,
            "formula": self.formula,
            "uncached_formula": self.uncached_formula,
            "is_hidden_sheet": self.is_hidden_sheet,
            "data_type": self.data_type,
            "extracted_at": self.extracted_at,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
        }


@dataclass(frozen=True, slots=True)
class TaxBreakdownItem:
    tax_type: str  # TPS, TVQ, GST, QST, HST, TAX
    rate_percent: Decimal | None
    amount: Decimal
    currency: str | None
    sheet_name: str | None
    cell_ref: str
    raw_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tax_type": self.tax_type,
            "rate_percent": format(self.rate_percent, "f") if self.rate_percent is not None else None,
            "amount": format(self.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f"),
            "currency": self.currency,
            "sheet_name": self.sheet_name,
            "cell_ref": self.cell_ref,
            "raw_label": self.raw_label,
        }


@dataclass(frozen=True, slots=True)
class InvoiceLineItem:
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    line_total: Decimal
    currency: str | None
    sheet_name: str | None
    cell_ref: str
    unit_price_ref: str | None = None
    quantity_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "quantity": format(self.quantity.normalize(), "f") if self.quantity is not None else None,
            "unit_price": format(self.unit_price.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f")
            if self.unit_price is not None
            else None,
            "line_total": format(self.line_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f"),
            "currency": self.currency,
            "sheet_name": self.sheet_name,
            "cell_ref": self.cell_ref,
            "unit_price_ref": self.unit_price_ref,
            "quantity_ref": self.quantity_ref,
        }


@dataclass(frozen=True, slots=True)
class ExtractedInvoice:
    file_name: str
    sheet_name: str | None
    invoice_number: str | None
    invoice_number_ref: str | None
    po_number: str | None
    po_number_ref: str | None
    issue_date: str | None
    issue_date_ref: str | None
    due_date: str | None
    due_date_ref: str | None
    vendor: str | None
    vendor_ref: str | None
    customer: str | None
    customer_ref: str | None
    description: str | None
    is_credit_note: bool
    tax_included: bool
    line_items: tuple[InvoiceLineItem, ...]
    subtotal: ProvenancedAmount | None
    discount: ProvenancedAmount | None
    taxes: tuple[TaxBreakdownItem, ...]
    tax_total: Decimal
    total_amount: ProvenancedAmount | None
    prior_balance: ProvenancedAmount | None
    amount_paid: ProvenancedAmount | None
    balance_due: ProvenancedAmount | None
    currency: str | None
    detected_currencies: tuple[str, ...]
    currency_conflict: bool
    payment_method: str | None
    document_refs: tuple[str, ...]
    uncached_formulas: tuple[dict[str, Any], ...]
    ambiguous_candidates: tuple[ProvenancedAmount, ...]
    math_verified: bool
    math_verification_detail: str
    rounding_tolerance: Decimal
    verification_status: str
    grounding_status: str
    direct_statement_fr: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "sheet_name": self.sheet_name,
            "invoice_number": self.invoice_number,
            "invoice_number_ref": self.invoice_number_ref,
            "po_number": self.po_number,
            "po_number_ref": self.po_number_ref,
            "issue_date": self.issue_date,
            "issue_date_ref": self.issue_date_ref,
            "due_date": self.due_date,
            "due_date_ref": self.due_date_ref,
            "vendor": self.vendor,
            "vendor_ref": self.vendor_ref,
            "customer": self.customer,
            "customer_ref": self.customer_ref,
            "description": self.description,
            "is_credit_note": self.is_credit_note,
            "tax_included": self.tax_included,
            "line_items": [item.to_dict() for item in self.line_items],
            "subtotal": self.subtotal.to_dict() if self.subtotal else None,
            "discount": self.discount.to_dict() if self.discount else None,
            "taxes": [t.to_dict() for t in self.taxes],
            "tax_total": format(self.tax_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f"),
            "total_amount": self.total_amount.to_dict() if self.total_amount else None,
            "prior_balance": self.prior_balance.to_dict() if self.prior_balance else None,
            "amount_paid": self.amount_paid.to_dict() if self.amount_paid else None,
            "balance_due": self.balance_due.to_dict() if self.balance_due else None,
            "currency": self.currency,
            "detected_currencies": list(self.detected_currencies),
            "currency_conflict": self.currency_conflict,
            "payment_method": self.payment_method,
            "document_refs": list(self.document_refs),
            "uncached_formulas": list(self.uncached_formulas),
            "ambiguous_candidates": [c.to_dict() for c in self.ambiguous_candidates],
            "math_verified": self.math_verified,
            "math_verification_detail": self.math_verification_detail,
            "rounding_tolerance": format(self.rounding_tolerance, "f"),
            "verification_status": self.verification_status,
            "grounding_status": self.grounding_status,
            "direct_statement_fr": self.direct_statement_fr,
        }


@dataclass(frozen=True, slots=True)
class InvoiceExtractionReport:
    """Rapport complet sur l'ensemble d'un document ou classeur multi-onglets."""

    file_name: str
    full_source_read: bool
    sheet_names: tuple[str, ...]
    primary_invoice: ExtractedInvoice | None
    invoices: tuple[ExtractedInvoice, ...]
    ambiguous_candidates: tuple[ProvenancedAmount, ...]
    uncached_formulas: tuple[dict[str, Any], ...]
    verification_status: str
    grounding_status: str
    certified_grounding: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "full_source_read": self.full_source_read,
            "sheet_names": list(self.sheet_names),
            "invoice_count": len(self.invoices),
            "primary_invoice": self.primary_invoice.to_dict() if self.primary_invoice else None,
            "invoices": [inv.to_dict() for inv in self.invoices],
            "ambiguous_candidates": [c.to_dict() for c in self.ambiguous_candidates],
            "uncached_formulas": list(self.uncached_formulas),
            "verification_status": self.verification_status,
            "grounding_status": self.grounding_status,
            "certified_grounding": self.certified_grounding,
            "warnings": list(self.warnings),
        }


def parse_textual_or_iso_date(raw: str) -> str | None:
    """Extrait et normalise une date (`YYYY-MM-DD`) en français, anglais ou ISO."""
    text = raw.strip()
    if not text:
        return None
    m_iso = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if m_iso:
        y, mo, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if 1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    m_dmy = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", text)
    if m_dmy:
        a, b, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        if 1990 <= y <= 2100:
            if a > 12 and 1 <= b <= 12:
                return f"{y:04d}-{b:02d}-{a:02d}"
            if 1 <= a <= 31 and 1 <= b <= 12:
                return f"{y:04d}-{b:02d}-{a:02d}"
            if 1 <= a <= 12 and 1 <= b <= 31:
                return f"{y:04d}-{a:02d}-{b:02d}"

    for m_txt in _TEXTUAL_DATE_RE.finditer(text):
        if m_txt.group(1):
            day_i = int(m_txt.group(1))
            month_key = _fold_text(m_txt.group(2)).rstrip(".")
            year_i = int(m_txt.group(3))
        else:
            month_key = _fold_text(m_txt.group(4)).rstrip(".")
            day_i = int(m_txt.group(5))
            year_i = int(m_txt.group(6))
        month_i = _FRENCH_MONTHS.get(month_key)
        if month_i and 1 <= day_i <= 31 and 1990 <= year_i <= 2100:
            return f"{year_i:04d}-{month_i:02d}-{day_i:02d}"
    return None


def _detect_currency_code(text: str, hint: str | None = None) -> str | None:
    upper = text.upper()
    for code in ("CAD", "USD", "EUR", "GBP", "CHF"):
        if re.search(rf"\b{code}\b", upper):
            return code
    if "CA$" in upper or "C$" in upper or "$CA" in upper:
        return "CAD"
    if "US$" in upper or "$US" in upper:
        return "USD"
    if "€" in text:
        return "EUR"
    if "£" in text:
        return "GBP"
    if hint in KNOWN_CURRENCIES:
        return hint
    return None


def parse_decimal_amount(
    raw: Any,
    *,
    currency_hint: str | None = None,
    allow_bare_integer: bool = True,
) -> ParsedMonetaryValue | None:
    """Analyse déterministe d'un montant en `Decimal` (zéro `float` math).

    Rejette systématiquement :
    - Les formules Excel (`=SUM(...)`)
    - Les dates (`2026-11-21`, `21/11/2026`, `21 novembre 2026`)
    - Les pourcentages seuls (`5%`, `9,975%`)
    - Les identifiants purs (`INV-2026-001`, `PO Nr. 17175`)
    - Les mesures physiques (`18 500 lbs`, `450 km`)
    """
    if raw is None or isinstance(raw, (bool, date, datetime)):
        return None
    if isinstance(raw, Decimal):
        return ParsedMonetaryValue(amount=raw, currency=currency_hint if currency_hint in KNOWN_CURRENCIES else None, raw_matched=format(raw, "f"))
    if isinstance(raw, int):
        if not allow_bare_integer:
            return None
        return ParsedMonetaryValue(amount=Decimal(raw), currency=currency_hint if currency_hint in KNOWN_CURRENCIES else None, raw_matched=str(raw))
    if isinstance(raw, float):
        if raw != raw:  # NaN
            return None
        dec = Decimal(str(raw)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).normalize()
        return ParsedMonetaryValue(amount=dec, currency=currency_hint if currency_hint in KNOWN_CURRENCIES else None, raw_matched=format(dec, "f"))

    text = str(raw).strip()
    if not text or text.startswith("="):
        return None

    # Exclure les dates pures
    if parse_textual_or_iso_date(text) is not None and not re.search(r"[$€£]|\b(?:CAD|USD|EUR|GBP)\b", text, re.IGNORECASE):
        # Si toute la chaîne est essentiellement une date
        stripped_date = _ISO_OR_SLASH_DATE_RE.sub("", _TEXTUAL_DATE_RE.sub("", text)).strip(" :,-")
        if not stripped_date or not any(ch.isdigit() for ch in stripped_date):
            return None

    # Exclure les mesures physiques sans symbole monétaire
    has_explicit_money = bool(re.search(r"[$€£]|\b(?:CAD|USD|EUR|GBP|CHF)\b", text, re.IGNORECASE))
    if _PHYSICAL_UNIT_PATTERN.search(text) and not has_explicit_money:
        return None

    # Nettoyer les numéros d'enregistrement TPS/TVQ et taux en % pour extraire uniquement le montant
    cleaned = _TAX_REG_CLEAN_PATTERN.sub(" ", text)
    cleaned = _PERCENT_CLEAN_PATTERN.sub(" ", cleaned)
    # Retirer les dates présentes sur la même ligne si un montant suit
    cleaned = _ISO_OR_SLASH_DATE_RE.sub(" ", cleaned)
    cleaned = _TEXTUAL_DATE_RE.sub(" ", cleaned)

    # Retirer les identifiants type Facture #INV-2026-01 ou PO #17175 lorsqu'ils précèdent un montant
    cleaned = re.sub(
        r"\b(?:po\s*(?:nr\.?|no\.?|#)?|bon\s+de\s+commande\s*#?|invoice\s*(?:no\.?|#)?|facture\s*(?:no\.?|n°|#)?)\s*[:.]?\s*[A-Z0-9\-]+\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    ccy = _detect_currency_code(text, currency_hint)

    # Rechercher les candidats numériques (supportant espaces insécables FR, virgules, points, parenthèses comptables)
    # On prend le DERNIER candidat monétaire sur une ligne libellée (ex: "TPS 5% : 62,53 $")
    num_pattern = re.compile(
        r"(?<![A-Za-z0-9\-/])"
        r"(\(\s*[$€£]?\s*\d[\d\s\u00a0\u202f.,]*\d\s*[$€£]?\s*\)"
        r"|[-+]?\s*[$€£]?\s*\d{1,3}(?:[\s\u00a0\u202f.,]\d{3})+(?:[.,]\d{1,4})?\s*[$€£]?"
        r"|[-+]?\s*[$€£]?\s*\d+[.,]\d{1,4}\s*[$€£]?"
        r"|[-+]?\s*[$€£]\s*\d+\b"
        r"|[-+]?\s*\d+\s*[$€£]"
        r"|[-+]?\b\d+\b)"
        r"(?![A-Za-z0-9\-/%])"
    )

    matches = list(num_pattern.finditer(cleaned))
    if not matches:
        return None

    # Préférer un candidat avec décimales ou symbole monétaire
    chosen_raw: str | None = None
    for m in reversed(matches):
        cand = m.group(1).strip()
        cand_has_sep_or_sym = any(ch in cand for ch in (".", ",", "$", "€", "£")) or ccy is not None
        if cand_has_sep_or_sym:
            chosen_raw = cand
            break
    if chosen_raw is None:
        if not allow_bare_integer:
            return None
        chosen_raw = matches[-1].group(1).strip()
    if not chosen_raw:
        return None

    dec = _normalize_numeric_token_to_decimal(chosen_raw)
    if dec is None:
        return None
    if not allow_bare_integer and "." not in chosen_raw and "," not in chosen_raw and not has_explicit_money:
        return None
    return ParsedMonetaryValue(amount=dec, currency=ccy, raw_matched=chosen_raw)


def _normalize_numeric_token_to_decimal(token: str) -> Decimal | None:
    s = token.strip()
    is_paren_neg = s.startswith("(") and s.endswith(")")
    if is_paren_neg:
        s = s[1:-1].strip()
    s = re.sub(r"[$€£\s\u00a0\u202f]", "", s)
    if not s:
        return None

    sign = ""
    if s[0] in "+-":
        sign = "-" if s[0] == "-" else ""
        s = s[1:]
    if is_paren_neg:
        sign = "-"

    if not s or not any(ch.isdigit() for ch in s):
        return None

    if "," in s and "." in s:
        # Le dernier séparateur est le séparateur décimal (ex: 1,250.50 vs 1.250,50)
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in {1, 2, 3, 4} and len(parts[1]) != 3:
            s = f"{parts[0]}.{parts[1]}"
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # Ambiguïté 1,250 -> séparateur de milliers anglais (pas de centimes)
            s = "".join(parts)
        elif len(parts) > 2:
            s = "".join(parts)
        else:
            s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2:
            s = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return Decimal(f"{sign}{s}")
    except InvalidOperation:
        return None


def classify_financial_label(text: str) -> tuple[str | None, str | None, Decimal | None]:
    """Classifie un libellé financier sans confusion sémantique.

    Retourne `(role, tax_code, tax_rate_percent)` où `role` est l'un de :
    - `"prior_balance"`
    - `"amount_paid"`
    - `"balance_due"`
    - `"subtotal"`
    - `"discount"`
    - `"tax"` (avec `tax_code` = TPS/TVQ/GST/QST/HST/TAX)
    - `"tax_total"`
    - `"grand_total"`
    - `"unit_price_header"` / `"quantity_header"` / `"line_total_header"`
    - `None`
    """
    folded = _fold_text(text)
    if not folded or len(folded) > 140:
        return None, None, None

    # Exclure les totaux physiques (poids, palettes, heures, km, quantités)
    if re.search(
        r"\b(?:total|nombre)\s+(?:de\s+|des\s+)?(?:poids|weight|lbs?|kg|palettes?|pallets?|km|miles|heures?|hours?|unites?|units?|qte|quantite|colis|articles?|items?)\b",
        folded,
    ):
        return None, None, None

    # Extraire un taux éventuel (ex: 5%, 9,975%)
    rate_dec: Decimal | None = None
    m_rate = re.search(r"(\d{1,2}(?:[.,]\d{1,4})?)\s*%", text)
    if m_rate:
        try:
            rate_dec = Decimal(m_rate.group(1).replace(",", "."))
        except InvalidOperation:
            rate_dec = None

    # 1. Solde antérieur (JAMAIS confondu avec le total de la facture)
    if any(
        kw in folded
        for kw in (
            "solde anterieur",
            "solde precedent",
            "report anterieur",
            "prior balance",
            "previous balance",
            "opening balance",
            "balance forward",
        )
    ):
        return "prior_balance", None, None

    # 2. Montant payé / acompte (JAMAIS confondu avec le total ni le solde dû)
    if any(
        kw in folded
        for kw in (
            "montant paye",
            "deja paye",
            "acompte",
            "depot recu",
            "paiement recu",
            "versement",
            "amount paid",
            "less paid",
            "paid to date",
            "deposit paid",
        )
    ):
        return "amount_paid", None, None

    # 3. Sous-total (JAMAIS confondu avec le total TTC)
    if any(
        kw in folded
        for kw in (
            "sous-total",
            "sous total",
            "subtotal",
            "sub-total",
            "total ht",
            "montant ht",
            "hors taxes",
            "avant taxes",
            "before tax",
        )
    ):
        return "subtotal", None, None

    # 4. Remise / escompte
    if any(kw in folded for kw in ("remise", "rabais", "escompte", "discount", "reduction commerciale")):
        return "discount", None, None

    # 5. Total des taxes (agrégé)
    if any(
        kw in folded
        for kw in (
            "total des taxes",
            "total taxes",
            "montant des taxes",
            "tax total",
            "total tax",
        )
    ):
        return "tax_total", None, None

    # 6. Taxes individuelles (TPS, TVQ, GST, QST, HST, TAX)
    # Attention à ne pas matcher une phrase narrative longue
    if len(folded) <= 85 and not any(
        kw in folded for kw in ("avant taxes", "hors taxes", "taxes incluses", "tax included", "including tax", "excl tax")
    ):
        if re.search(r"\btps\b|taxe sur les produits et services", folded):
            return "tax", "TPS", rate_dec
        if re.search(r"\btvq\b|taxe de vente du quebec", folded):
            return "tax", "TVQ", rate_dec
        if re.search(r"\bgst\b|goods and services tax", folded):
            return "tax", "GST", rate_dec
        if re.search(r"\bqst\b|quebec sales tax", folded):
            return "tax", "QST", rate_dec
        if re.search(r"\bhst\b|\btvh\b|harmonized sales tax", folded):
            return "tax", "HST", rate_dec
        if re.match(r"^(?:taxe|taxes|tax|tva|vat|sales tax)\b", folded):
            return "tax", "TAX", rate_dec

    # 7. Solde dû / Balance due
    if any(
        kw in folded
        for kw in (
            "solde du",
            "solde a payer",
            "reste a payer",
            "balance due",
            "amount due",
            "total due",
            "montant du",
        )
    ):
        return "balance_due", None, None

    # 8. En-têtes de colonnes de lignes d'articles (pour ne JAMAIS promouvoir un prix unitaire en total)
    if folded in {
        "prix unitaire",
        "p.u.",
        "pu",
        "unit price",
        "taux unitaire",
        "rate",
        "tarif unitaire",
        "prix",
        "price",
    }:
        return "unit_price_header", None, None

    if folded in {"qte", "quantite", "qty", "quantity", "heures", "hours"}:
        return "quantity_header", None, None

    # 9. Total facturé / Grand total / Net à payer
    if any(
        kw in folded
        for kw in (
            "grand total",
            "total facture",
            "montant total",
            "net a payer",
            "total a payer",
            "total ttc",
            "montant ttc",
            "invoice total",
            "total general",
            "total de la facture",
        )
    ):
        return "grand_total", None, None

    # Libellé court "TOTAL", "MONTANT", "AMOUNT", "TOTAL CAD", "TOTAL ($)" ou en ligne "TOTAL: 105,00 $"
    if re.match(
        r"^(?:total|montant|amount)(?:\s*(?:\(\s*[$€£A-Za-z]{1,4}\s*\)|cad|usd|eur|gbp|\$|€|:))?\s*$",
        folded,
    ) or re.match(
        r"^(?:total|montant|amount)(?:\s*(?:\(\s*[$€£a-z]{1,4}\s*\)|cad|usd|eur|gbp))?\s*(?:[:=]\s*[$€£\-\+(]?\s*\d|[$€£]\s*\d|\d+[.,]\d{2}\s*(?:[$€£]|cad|usd|eur|gbp)\b)",
        folded,
    ):
        return "grand_total", None, None

    return None, None, None


class InvoiceExtractionService:
    """Extracteur déterministe multi-feuilles / multi-formats en `Decimal`."""

    def __init__(self, *, rounding_tolerance: Decimal = ROUNDING_TOLERANCE) -> None:
        self._tolerance = rounding_tolerance

    def extract_from_bytes(
        self,
        filename: str,
        content: bytes,
        *,
        image_ocr=None,
        sheet_filter: str | None = None,
        invoice_filter: str | None = None,
    ) -> InvoiceExtractionReport:
        bundle = extract_document_bundle(filename, content, image_ocr=image_ocr)
        return self.extract_from_bundle(bundle, sheet_filter=sheet_filter, invoice_filter=invoice_filter)

    def extract_from_text(
        self,
        filename: str,
        extracted_text: str,
        *,
        sheet_filter: str | None = None,
        invoice_filter: str | None = None,
    ) -> InvoiceExtractionReport:
        bundle = bundle_from_extracted_text(filename, extracted_text)
        return self.extract_from_bundle(bundle, sheet_filter=sheet_filter, invoice_filter=invoice_filter)

    def extract_from_bundle(
        self,
        bundle: DocumentExtractionBundle,
        *,
        sheet_filter: str | None = None,
        invoice_filter: str | None = None,
    ) -> InvoiceExtractionReport:
        warnings = list(bundle.warnings)
        sheet_names = tuple(s.sheet_name for s in bundle.sheets)

        if not bundle.sheets and not bundle.full_text.strip():
            return InvoiceExtractionReport(
                file_name=bundle.file_name,
                full_source_read=bundle.extraction_mode != "pdf_scanned_unreadable",
                sheet_names=(),
                primary_invoice=None,
                invoices=(),
                ambiguous_candidates=(),
                uncached_formulas=(),
                verification_status="no_amount_found",
                grounding_status="missing_after_full_read" if bundle.extraction_mode != "pdf_scanned_unreadable" else "uncertain_candidates",
                certified_grounding=False,
                warnings=tuple(warnings),
            )

        is_workbook = bundle.file_format in {"xlsx", "xlsm", "xls"}
        candidate_sheets = list(bundle.sheets)
        if sheet_filter:
            folded_filter = _fold_text(sheet_filter)
            candidate_sheets = [s for s in candidate_sheets if _fold_text(s.sheet_name) == folded_filter]

        extracted_invoices: list[ExtractedInvoice] = []

        if is_workbook:
            # Chaque onglet pertinent d'un classeur peut contenir une facture complète ou un récapitulatif
            for sheet in candidate_sheets:
                inv = self._extract_invoice_from_cells(
                    file_name=bundle.file_name,
                    sheet_name=sheet.sheet_name,
                    cells=sheet.cells,
                    full_text=sheet.rendered_text,
                )
                if self._invoice_has_meaningful_financial_signal(inv):
                    extracted_invoices.append(inv)
        else:
            # PDF, DOCX (paragraphes + tableaux combinés), CSV, TXT, Image OCR :
            # un seul document logique combinant toutes ses sections/pages/tableaux
            combined_cells = tuple(c for s in candidate_sheets for c in s.cells)
            combined_text = "\n\n".join(s.rendered_text for s in candidate_sheets) if sheet_filter else bundle.full_text
            inv = self._extract_invoice_from_cells(
                file_name=bundle.file_name,
                sheet_name=candidate_sheets[0].sheet_name if len(candidate_sheets) == 1 else None,
                cells=combined_cells,
                full_text=combined_text,
            )
            if self._invoice_has_meaningful_financial_signal(inv):
                extracted_invoices.append(inv)

        if invoice_filter:
            f_inv = invoice_filter.strip().casefold()
            extracted_invoices = [
                inv
                for inv in extracted_invoices
                if (inv.invoice_number and f_inv in inv.invoice_number.casefold())
                or (inv.po_number and f_inv in inv.po_number.casefold())
            ]

        all_uncached = [u for inv in extracted_invoices for u in inv.uncached_formulas]
        if not all_uncached and bundle.has_uncached_formulas:
            for ref in bundle.uncached_formula_refs:
                cell_match = next((c for c in bundle.cells if c.cell_ref == ref), None)
                if cell_match is not None:
                    all_uncached.append(cell_match.to_dict())

        is_incomplete_source = bool(
            getattr(bundle, "is_incomplete_source", False)
            or bundle.extraction_mode in {"pdf_scanned_unreadable", "pdf_mixed_partial_ocr", "legacy_partial_text"}
        )

        if not extracted_invoices:
            if all_uncached:
                return InvoiceExtractionReport(
                    file_name=bundle.file_name,
                    full_source_read=not is_incomplete_source,
                    sheet_names=sheet_names,
                    primary_invoice=None,
                    invoices=(),
                    ambiguous_candidates=(),
                    uncached_formulas=tuple(all_uncached),
                    verification_status="uncached_formula",
                    grounding_status="uncertain_candidates",
                    certified_grounding=False,
                    warnings=tuple(warnings),
                )
            if is_incomplete_source:
                return InvoiceExtractionReport(
                    file_name=bundle.file_name,
                    full_source_read=False,
                    sheet_names=sheet_names,
                    primary_invoice=None,
                    invoices=(),
                    ambiguous_candidates=(),
                    uncached_formulas=(),
                    verification_status="incomplete_source",
                    grounding_status="uncertain_candidates",
                    certified_grounding=False,
                    warnings=tuple(warnings),
                )
            return InvoiceExtractionReport(
                file_name=bundle.file_name,
                full_source_read=True,
                sheet_names=sheet_names,
                primary_invoice=None,
                invoices=(),
                ambiguous_candidates=(),
                uncached_formulas=(),
                verification_status="no_amount_found",
                grounding_status="missing_after_full_read",
                certified_grounding=False,
                warnings=tuple(warnings),
            )

        # Résolution multi-onglets : distinguer onglet principal de facture vs onglet d'annexe/détail
        primary, top_ambiguous, overall_status, overall_grounding = self._select_primary_or_flag_ambiguity(
            extracted_invoices
        )
        if is_incomplete_source:
            overall_status = "incomplete_source"
            overall_grounding = "uncertain_candidates"
            certified = False
        else:
            certified = overall_grounding in {"math_verified", "extracted_structured"} and not bool(top_ambiguous)

        return InvoiceExtractionReport(
            file_name=bundle.file_name,
            full_source_read=not is_incomplete_source,
            sheet_names=sheet_names,
            primary_invoice=primary,
            invoices=tuple(extracted_invoices),
            ambiguous_candidates=top_ambiguous,
            uncached_formulas=tuple(all_uncached),
            verification_status=overall_status,
            grounding_status=overall_grounding,
            certified_grounding=certified,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _invoice_has_meaningful_financial_signal(inv: ExtractedInvoice) -> bool:
        return bool(
            inv.total_amount is not None
            or inv.balance_due is not None
            or inv.subtotal is not None
            or inv.taxes
            or inv.line_items
            or inv.uncached_formulas
            or inv.ambiguous_candidates
        )

    def _select_primary_or_flag_ambiguity(
        self, invoices: list[ExtractedInvoice]
    ) -> tuple[ExtractedInvoice | None, tuple[ProvenancedAmount, ...], str, str]:
        if len(invoices) == 1:
            inv = invoices[0]
            return inv, inv.ambiguous_candidates, inv.verification_status, inv.grounding_status

        # Filtrer les onglets qui portent un vrai total ou une formule non cachée
        with_totals = [inv for inv in invoices if inv.total_amount is not None or inv.uncached_formulas or inv.ambiguous_candidates]
        if len(with_totals) == 1:
            inv = with_totals[0]
            return inv, inv.ambiguous_candidates, inv.verification_status, inv.grounding_status

        if not with_totals:
            inv = invoices[0]
            return inv, inv.ambiguous_candidates, inv.verification_status, inv.grounding_status

        # S'il y a un onglet visible de facture/sommaire vérifié mathématiquement et que TOUS les autres onglets
        # sont des sous-composantes réconciliées positivement avec la facture principale (ex: annexe égale à une ligne ou au sous-total),
        # alors la facture principale gagne sans ambiguïté. Un onglet caché non réconcilié ou un onglet ambigu bloque cette certification.
        verified = [inv for inv in with_totals if inv.verification_status == "math_verified" and inv.total_amount is not None]
        if len(verified) == 1:
            winner = verified[0]
            others = [o for o in with_totals if o is not winner]
            line_amounts = {li.line_total for li in winner.line_items}
            all_others_resolved = all(
                o.total_amount is not None
                and not o.uncached_formulas
                and not o.ambiguous_candidates
                and o.verification_status in {"math_verified", "extracted_unverified_math"}
                for o in others
            )
            if all_others_resolved and others:
                individually_reconciled = all(
                    o.total_amount is not None
                    and (
                        o.total_amount.amount in line_amounts
                        or (winner.subtotal is not None and abs(o.total_amount.amount - winner.subtotal.amount) <= self._tolerance)
                    )
                    for o in others
                )
                sum_others = sum((o.total_amount.amount for o in others if o.total_amount is not None), Decimal("0.00"))
                target_sub = winner.subtotal.amount if winner.subtotal is not None else (winner.total_amount.amount if winner.total_amount is not None else Decimal("-1"))
                collectively_reconciled = abs(sum_others - target_sub) <= self._tolerance
                if individually_reconciled or collectively_reconciled:
                    return winner, (), winner.verification_status, winner.grounding_status

        # Vérifier si un onglet "Sommaire" / "Récapitulatif" consolide exactement la somme des factures individuelles
        for cand in with_totals:
            if cand.total_amount is None:
                continue
            folded_sheet = _fold_text(cand.sheet_name or "")
            if any(k in folded_sheet for k in ("sommaire", "summary", "recap", "consolide")):
                other_totals = [
                    o.total_amount.amount
                    for o in with_totals
                    if o is not cand and o.total_amount is not None
                ]
                if other_totals and abs(sum(other_totals, Decimal("0.00")) - cand.total_amount.amount) <= self._tolerance:
                    return cand, (), cand.verification_status, cand.grounding_status

        # Sinon : plusieurs totaux distincts coexistent dans le même classeur sans filtre utilisateur -> ambiguïté honnête!
        distinct_totals: list[ProvenancedAmount] = []
        seen_amounts_sheets: set[tuple[Decimal, str | None]] = set()
        for inv in with_totals:
            if inv.total_amount is not None:
                key = (inv.total_amount.amount.quantize(TWO_PLACES), inv.sheet_name)
                if key not in seen_amounts_sheets:
                    seen_amounts_sheets.add(key)
                    distinct_totals.append(inv.total_amount)
            for amb in inv.ambiguous_candidates:
                key = (amb.amount.quantize(TWO_PLACES), amb.sheet_name)
                if key not in seen_amounts_sheets:
                    seen_amounts_sheets.add(key)
                    distinct_totals.append(amb)

        if any(inv.verification_status == "uncached_formula" for inv in with_totals) and not distinct_totals:
            return None, (), "uncached_formula", "uncertain_candidates"

        return None, tuple(distinct_totals), "ambiguous_candidates", "uncertain_candidates"

    def _extract_invoice_from_cells(
        self,
        *,
        file_name: str,
        sheet_name: str | None,
        cells: tuple[CellProvenance, ...],
        full_text: str,
    ) -> ExtractedInvoice:
        rows_map: dict[tuple[str | None, int], list[CellProvenance]] = {}
        for c in cells:
            rows_map.setdefault((c.sheet_name, c.row), []).append(c)
        for row_cells in rows_map.values():
            row_cells.sort(key=lambda item: item.column)

        sorted_row_keys = sorted(rows_map.keys(), key=lambda k: (k[0] or "", k[1]))

        # Métadonnées textuelles d'en-tête
        invoice_number: str | None = None
        invoice_number_ref: str | None = None
        po_number: str | None = None
        po_number_ref: str | None = None
        issue_date: str | None = None
        issue_date_ref: str | None = None
        due_date: str | None = None
        due_date_ref: str | None = None
        vendor: str | None = None
        vendor_ref: str | None = None
        customer: str | None = None
        customer_ref: str | None = None
        payment_method: str | None = None
        doc_refs: list[str] = []
        if sheet_name:
            doc_refs.append(sheet_name)

        folded_full = _fold_text(full_text)
        is_credit_note = any(
            kw in folded_full for kw in ("note de credit", "credit note", "avoir commercial", "facture d'avoir")
        )
        tax_included = any(
            kw in folded_full for kw in ("taxes incluses", "taxe incluse", "tax included", "taxes included", "prix ttc")
        )

        explicit_currencies: list[str] = []
        for code in ("CAD", "USD", "EUR", "GBP", "CHF"):
            if re.search(rf"\b{code}\b", full_text, re.IGNORECASE):
                explicit_currencies.append(code)
        for c in cells:
            if c.currency_hint in KNOWN_CURRENCIES and c.currency_hint not in explicit_currencies:
                explicit_currencies.append(c.currency_hint)

        # Détecter tableau de lignes d'articles ou table multi-enregistrements par ligne d'en-tête
        table_header_row: tuple[str | None, int] | None = None
        header_row_keys: set[tuple[str | None, int]] = set()
        col_roles: dict[int, str] = {}
        is_invoice_document = any(
            kw in folded_full
            for kw in (
                "facture",
                "invoice",
                "sous-total",
                "subtotal",
                "tps",
                "tvq",
                "gst",
                "qst",
                "hst",
                "net a payer",
                "total a payer",
                "total facture",
                "solde du",
                "balance due",
                "bon de commande",
                "po nr",
            )
        )

        for rk in sorted_row_keys:
            rcells = rows_map[rk]
            if len(rcells) < 2:
                continue
            temp_roles: dict[int, str] = {}
            text_header_count = 0
            has_record_id_col = False
            for cell in rcells:
                f_val = _fold_text(str(cell.normalized_value or cell.raw_value or ""))
                if f_val and not any(ch.isdigit() for ch in f_val):
                    text_header_count += 1
                if f_val in {"order_id", "customer_id", "transaction_id", "product_id", "employee_id"}:
                    has_record_id_col = True
                if any(k in f_val for k in ("description", "designation", "service", "trajet", "article", "item", "detail")):
                    temp_roles[cell.column] = "description"
                elif f_val in {"qte", "quantite", "qty", "quantity", "heures", "hours", "unites", "units"}:
                    temp_roles[cell.column] = "quantity"
                elif any(k in f_val for k in ("prix unitaire", "p.u", "unit price", "taux", "tarif", "rate")) or (
                    f_val in {"prix", "price"} and len(rcells) >= 3
                ):
                    temp_roles[cell.column] = "unit_price"
                elif f_val in {"montant", "total", "amount", "line total", "extension", "montant ht"}:
                    temp_roles[cell.column] = "line_total"
            # Marquer toute ligne d'en-tête tabulaire pour empêcher qu'un nom de colonne ("amount"/"total")
            # sur la ligne 1 soit confondu avec un libellé de pied de facture vertical!
            if "line_total" in temp_roles.values() and text_header_count >= 2:
                header_row_keys.add(rk)
                if table_header_row is None and not has_record_id_col and (
                    "description" in temp_roles.values()
                    or "unit_price" in temp_roles.values()
                    or is_invoice_document
                ):
                    table_header_row = rk
                    col_roles = temp_roles
                    break

        # Extraction des métadonnées (numéro de facture, PO, dates, fournisseur, client, mode de paiement)
        self._extract_header_metadata(
            rows_map=rows_map,
            sorted_row_keys=sorted_row_keys,
            meta_out=(
                meta := {
                    "invoice_number": None,
                    "invoice_number_ref": None,
                    "po_number": None,
                    "po_number_ref": None,
                    "issue_date": None,
                    "issue_date_ref": None,
                    "due_date": None,
                    "due_date_ref": None,
                    "vendor": None,
                    "vendor_ref": None,
                    "customer": None,
                    "customer_ref": None,
                    "payment_method": None,
                }
            ),
        )
        invoice_number = meta["invoice_number"]
        invoice_number_ref = meta["invoice_number_ref"]
        po_number = meta["po_number"]
        po_number_ref = meta["po_number_ref"]
        issue_date = meta["issue_date"]
        issue_date_ref = meta["issue_date_ref"]
        due_date = meta["due_date"]
        due_date_ref = meta["due_date_ref"]
        vendor = meta["vendor"]
        vendor_ref = meta["vendor_ref"]
        customer = meta["customer"]
        customer_ref = meta["customer_ref"]
        payment_method = meta["payment_method"]

        # Extraction des lignes d'articles ET des totaux/taxes
        line_items: list[InvoiceLineItem] = []
        subtotal_candidates: list[ProvenancedAmount] = []
        discount_candidates: list[ProvenancedAmount] = []
        taxes: list[TaxBreakdownItem] = []
        explicit_tax_total: ProvenancedAmount | None = None
        grand_total_candidates: list[ProvenancedAmount] = []
        prior_balance_candidates: list[ProvenancedAmount] = []
        amount_paid_candidates: list[ProvenancedAmount] = []
        balance_due_candidates: list[ProvenancedAmount] = []
        uncached_formulas: list[dict[str, Any]] = []

        default_ccy = explicit_currencies[0] if len(explicit_currencies) == 1 else None
        in_line_items = False

        for idx_rk, rk in enumerate(sorted_row_keys):
            rcells = rows_map[rk]
            if table_header_row is not None and rk == table_header_row:
                in_line_items = True
                continue
            if rk in header_row_keys:
                continue

            # Examiner si la ligne porte un libellé récapitulatif (Total, Sous-total, TPS, TVQ, Solde...)
            row_summary_matched = False
            for c_pos, cell in enumerate(rcells):
                if cell.uncached_formula:
                    continue
                cell_text = str(cell.normalized_value or cell.raw_value or "").strip()
                if not cell_text:
                    continue

                role, tax_code, rate_dec = classify_financial_label(cell_text)
                if role in {"unit_price_header", "quantity_header", "line_total_header"} or role is None:
                    continue

                # Chercher la valeur associée :
                # 1) Cellule à droite sur la même ligne (en tenant compte des plages fusionnées!)
                # 2) Dans la même cellule après le libellé (ex: "TOTAL : 1 437,77 $ CAD")
                # 3) Juste en dessous dans la même colonne (bloc vertical de pied de facture uniquement, pas colonne de table!)
                following_row_cells = rows_map.get(sorted_row_keys[idx_rk + 1], []) if idx_rk + 1 < len(sorted_row_keys) else []
                second_following_cells = rows_map.get(sorted_row_keys[idx_rk + 2], []) if idx_rk + 2 < len(sorted_row_keys) else []
                amt_prov, uncached_hit = self._resolve_amount_for_label_cell(
                    label_cell=cell,
                    label_text=cell_text,
                    row_cells=rcells[c_pos + 1 :],
                    next_row_cells=following_row_cells,
                    second_next_row_cells=second_following_cells,
                    default_currency=default_ccy,
                )

                if uncached_hit is not None:
                    row_summary_matched = True
                    in_line_items = False
                    uncached_dict = uncached_hit.to_dict()
                    uncached_dict["associated_label"] = cell_text
                    uncached_dict["associated_role"] = role
                    if not any(u["cell_ref"] == uncached_dict["cell_ref"] for u in uncached_formulas):
                        uncached_formulas.append(uncached_dict)
                    continue

                if amt_prov is None:
                    continue

                row_summary_matched = True
                in_line_items = False
                if amt_prov.currency in KNOWN_CURRENCIES and amt_prov.currency not in explicit_currencies:
                    explicit_currencies.append(amt_prov.currency)

                if role == "subtotal":
                    subtotal_candidates.append(amt_prov)
                elif role == "discount":
                    discount_candidates.append(amt_prov)
                elif role == "tax" and tax_code:
                    taxes.append(
                        TaxBreakdownItem(
                            tax_type=tax_code,
                            rate_percent=rate_dec,
                            amount=amt_prov.amount,
                            currency=amt_prov.currency or default_ccy,
                            sheet_name=amt_prov.sheet_name,
                            cell_ref=amt_prov.cell_ref,
                            raw_label=cell_text,
                        )
                    )
                elif role == "tax_total":
                    explicit_tax_total = amt_prov
                elif role == "grand_total":
                    grand_total_candidates.append(amt_prov)
                elif role == "prior_balance":
                    prior_balance_candidates.append(amt_prov)
                elif role == "amount_paid":
                    amount_paid_candidates.append(amt_prov)
                elif role == "balance_due":
                    balance_due_candidates.append(amt_prov)

            # Toute formule sans cache ailleurs dans la feuille est aussi tracée
            for cell in rcells:
                if cell.uncached_formula and not any(u["cell_ref"] == cell.cell_ref for u in uncached_formulas):
                    uncached_formulas.append(cell.to_dict())

            if row_summary_matched:
                continue

            # Si on est dans la zone des lignes d'articles d'un tableau structuré
            if in_line_items and col_roles:
                li = self._extract_structured_line_item(rcells, col_roles, default_ccy)
                if li is not None:
                    line_items.append(li)
                    if li.currency in KNOWN_CURRENCIES and li.currency not in explicit_currencies:
                        explicit_currencies.append(li.currency)
            elif table_header_row is None:
                # Facture texte/PDF/OCR sans grille de colonnes : détecter les lignes "Description ... Qté x Prix ... Total"
                li_txt = self._extract_text_line_item(rcells, default_ccy)
                if li_txt is not None:
                    line_items.append(li_txt)

        # Détecter conflit de devises (ex: lignes en USD et total en CAD sans conversion autorisée)
        known_detected = tuple(c for c in explicit_currencies if c in KNOWN_CURRENCIES)
        currency_conflict = len(known_detected) > 1
        resolved_currency: str | None = (
            "MIXED_CURRENCY_CONFLICT"
            if currency_conflict
            else (known_detected[0] if len(known_detected) == 1 else None)
        )

        # Propager la devise résolue aux ProvenancedAmount qui n'avaient que '$' ou None
        if resolved_currency and not currency_conflict:
            subtotal_candidates = [self._with_currency(a, resolved_currency) for a in subtotal_candidates]
            discount_candidates = [self._with_currency(a, resolved_currency) for a in discount_candidates]
            grand_total_candidates = [self._with_currency(a, resolved_currency) for a in grand_total_candidates]
            prior_balance_candidates = [self._with_currency(a, resolved_currency) for a in prior_balance_candidates]
            amount_paid_candidates = [self._with_currency(a, resolved_currency) for a in amount_paid_candidates]
            balance_due_candidates = [self._with_currency(a, resolved_currency) for a in balance_due_candidates]
            if explicit_tax_total is not None:
                explicit_tax_total = self._with_currency(explicit_tax_total, resolved_currency)

        subtotal = subtotal_candidates[-1] if subtotal_candidates else None
        discount = discount_candidates[-1] if discount_candidates else None
        prior_balance = prior_balance_candidates[-1] if prior_balance_candidates else None
        amount_paid = amount_paid_candidates[-1] if amount_paid_candidates else None
        balance_due = balance_due_candidates[-1] if balance_due_candidates else None

        tax_total = (
            sum((t.amount for t in taxes), Decimal("0.00"))
            if taxes
            else (explicit_tax_total.amount if explicit_tax_total is not None else Decimal("0.00"))
        )

        # Si aucun "TOTAL" explicite mais un "TOTAL DUE / SOLDE DÛ" sans acompte ni solde antérieur,
        # alors le montant total dû EST le montant total de la facture.
        if not grand_total_candidates and balance_due is not None and amount_paid is None and prior_balance is None:
            grand_total_candidates.append(balance_due)

        # Sélection et vérification mathématique du total
        (
            selected_total,
            ambiguous,
            math_ok,
            math_detail,
            verif_status,
            ground_status,
        ) = self._resolve_and_verify_totals(
            line_items=line_items,
            subtotal=subtotal,
            discount=discount,
            tax_total=tax_total,
            grand_total_candidates=grand_total_candidates,
            prior_balance=prior_balance,
            amount_paid=amount_paid,
            balance_due=balance_due,
            uncached_formulas=uncached_formulas,
            currency_conflict=currency_conflict,
            tax_included=tax_included,
            is_credit_note=is_credit_note,
        )

        # Si pas de `balance_due` explicite mais `selected_total` et `amount_paid` existent, calculer le solde vérifié
        if balance_due is None and selected_total is not None and amount_paid is not None:
            computed_bal = (
                selected_total.amount
                + (prior_balance.amount if prior_balance else Decimal("0.00"))
                - abs(amount_paid.amount)
            )
            balance_due = ProvenancedAmount(
                amount=computed_bal,
                currency=selected_total.currency,
                label="calculated_balance_due",
                file_name=file_name,
                sheet_name=selected_total.sheet_name,
                cell_ref=f"{selected_total.cell_ref}-{amount_paid.coordinate}",
                coordinate=selected_total.coordinate,
                raw_value=format(computed_bal, "f"),
                normalized_value=format(computed_bal.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), "f"),
                formula=None,
                uncached_formula=False,
                data_type="currency",
                extracted_at=selected_total.extracted_at,
                confidence=selected_total.confidence,
                verification_status="derived_decimal_subtraction",
            )

        if selected_total is not None and selected_total.amount < Decimal("0.00"):
            is_credit_note = True

        description_summary = "; ".join(li.description for li in line_items[:3] if li.description) or None
        if po_number and f"PO:{po_number}" not in doc_refs:
            doc_refs.append(f"PO:{po_number}")
        if invoice_number and f"INV:{invoice_number}" not in doc_refs:
            doc_refs.append(f"INV:{invoice_number}")

        direct_statement_fr = self._build_direct_statement_fr(
            total=selected_total,
            balance_due=balance_due,
            amount_paid=amount_paid,
            currency=resolved_currency,
            verification_status=verif_status,
        )

        return ExtractedInvoice(
            file_name=file_name,
            sheet_name=sheet_name,
            invoice_number=invoice_number,
            invoice_number_ref=invoice_number_ref,
            po_number=po_number,
            po_number_ref=po_number_ref,
            issue_date=issue_date,
            issue_date_ref=issue_date_ref,
            due_date=due_date,
            due_date_ref=due_date_ref,
            vendor=vendor,
            vendor_ref=vendor_ref,
            customer=customer,
            customer_ref=customer_ref,
            description=description_summary,
            is_credit_note=is_credit_note,
            tax_included=tax_included,
            line_items=tuple(line_items),
            subtotal=subtotal,
            discount=discount,
            taxes=tuple(taxes),
            tax_total=tax_total,
            total_amount=selected_total,
            prior_balance=prior_balance,
            amount_paid=amount_paid,
            balance_due=balance_due,
            currency=resolved_currency,
            detected_currencies=known_detected,
            currency_conflict=currency_conflict,
            payment_method=payment_method,
            document_refs=tuple(doc_refs),
            uncached_formulas=tuple(uncached_formulas),
            ambiguous_candidates=ambiguous,
            math_verified=math_ok,
            math_verification_detail=math_detail,
            rounding_tolerance=self._tolerance,
            verification_status=verif_status,
            grounding_status=ground_status,
            direct_statement_fr=direct_statement_fr,
        )

    @staticmethod
    def _with_currency(prov: ProvenancedAmount, currency: str) -> ProvenancedAmount:
        if prov.currency in KNOWN_CURRENCIES:
            return prov
        return ProvenancedAmount(
            amount=prov.amount,
            currency=currency,
            label=prov.label,
            file_name=prov.file_name,
            sheet_name=prov.sheet_name,
            cell_ref=prov.cell_ref,
            coordinate=prov.coordinate,
            raw_value=prov.raw_value,
            normalized_value=prov.normalized_value,
            formula=prov.formula,
            uncached_formula=prov.uncached_formula,
            data_type=prov.data_type,
            extracted_at=prov.extracted_at,
            confidence=prov.confidence,
            verification_status=prov.verification_status,
            is_hidden_sheet=prov.is_hidden_sheet,
        )

    def _extract_header_metadata(
        self,
        *,
        rows_map: dict[tuple[str | None, int], list[CellProvenance]],
        sorted_row_keys: list[tuple[str | None, int]],
        meta_out: dict[str, str | None],
    ) -> None:
        inv_re = re.compile(
            r"(?:facture\s*(?:no\.?|n°|#)?|invoice\s*(?:no\.?|number|#)?|n°\s*de\s*facture)\s*[:.]?\s*([A-Z0-9][A-Z0-9\-/]{2,30})",
            re.IGNORECASE,
        )
        po_re = re.compile(
            r"(?:\bpo\s*(?:nr\.?|no\.?|number|#)?|p\.o\.?\s*(?:no\.?|#)?|bon\s+de\s+commande\s*(?:no\.?|#)?|purchase\s+order\s*(?:no\.?|#)?)\s*[:.]?\s*([A-Z0-9][A-Z0-9\-/]{1,30})",
            re.IGNORECASE,
        )
        pay_re = re.compile(
            r"\b(virement\s+bancaire|virement\s+interac|interac|eft|ach|wire\s+transfer|cheque|chèque|carte\s+de\s+cr[ée]dit|credit\s+card)\b",
            re.IGNORECASE,
        )

        for idx_rk, rk in enumerate(sorted_row_keys):
            rcells = rows_map[rk]
            for c_pos, cell in enumerate(rcells):
                if cell.uncached_formula:
                    continue
                txt = str(cell.normalized_value or cell.raw_value or "").strip()
                if not txt:
                    continue
                folded = _fold_text(txt)
                next_val = (
                    str(rcells[c_pos + 1].normalized_value or rcells[c_pos + 1].raw_value or "").strip()
                    if c_pos + 1 < len(rcells) and not rcells[c_pos + 1].uncached_formula
                    else ""
                )
                next_ref = rcells[c_pos + 1].cell_ref if c_pos + 1 < len(rcells) else cell.cell_ref

                # Fournisseur en haut de facture (ex: "CIM Trans Inc.")
                if meta_out["vendor"] is None and idx_rk <= 4:
                    if re.search(r"\b(?:inc\.?|lt[ée]e\.?|ltd\.?|llc|corp\.?|s\.a\.?|enr\.?|senc)\b", txt, re.IGNORECASE) and not any(
                        k in folded for k in ("facture a", "facturer a", "bill to", "sold to", "client", "destinataire")
                    ):
                        meta_out["vendor"] = txt
                        meta_out["vendor_ref"] = cell.cell_ref
                    elif folded.startswith(("fournisseur", "emetteur", "vendor", "from")):
                        val = txt.split(":", 1)[1].strip() if ":" in txt and txt.split(":", 1)[1].strip() else next_val
                        if val:
                            meta_out["vendor"] = val
                            meta_out["vendor_ref"] = next_ref if val == next_val else cell.cell_ref

                # Client ("Facturé à : JAF 2000 Inc." ou cellule en dessous / à droite)
                if meta_out["customer"] is None:
                    if any(k in folded for k in ("facture a", "facturer a", "bill to", "sold to", "client :", "destinataire")):
                        after_colon = txt.split(":", 1)[1].strip() if ":" in txt else ""
                        if after_colon:
                            meta_out["customer"] = after_colon
                            meta_out["customer_ref"] = cell.cell_ref
                        elif next_val:
                            meta_out["customer"] = next_val
                            meta_out["customer_ref"] = next_ref
                        elif idx_rk + 1 < len(sorted_row_keys):
                            below_cells = rows_map[sorted_row_keys[idx_rk + 1]]
                            below_match = next((bc for bc in below_cells if bc.column >= cell.column and (bc.normalized_value or bc.raw_value)), None)
                            if below_match:
                                meta_out["customer"] = str(below_match.normalized_value or below_match.raw_value).strip()
                                meta_out["customer_ref"] = below_match.cell_ref

                # Numéro de facture
                if meta_out["invoice_number"] is None:
                    m_inv = inv_re.search(txt)
                    if m_inv and m_inv.group(1).lower() not in {"a", "du", "de", "date", "total"}:
                        meta_out["invoice_number"] = m_inv.group(1).strip()
                        meta_out["invoice_number_ref"] = cell.cell_ref
                    elif folded in {"facture", "facture #", "facture no", "no facture", "invoice", "invoice #", "invoice no"} and next_val:
                        if re.match(r"^[A-Z0-9][A-Z0-9\-/]{1,30}$", next_val, re.IGNORECASE):
                            meta_out["invoice_number"] = next_val
                            meta_out["invoice_number_ref"] = next_ref

                # PO Number (ex: "PO Nr. 17175")
                if meta_out["po_number"] is None:
                    m_po = po_re.search(txt)
                    if m_po and m_po.group(1).lower() not in {"nr", "no", "number"}:
                        meta_out["po_number"] = m_po.group(1).strip()
                        meta_out["po_number_ref"] = cell.cell_ref
                    elif re.match(r"^(?:po|po\s*nr\.?|po\s*no\.?|p\.o\.?|bon\s+de\s+commande)\s*:?$", folded) and next_val:
                        meta_out["po_number"] = next_val
                        meta_out["po_number_ref"] = next_ref

                # Dates d'émission et d'échéance
                if any(k in folded for k in ("echeance", "due date", "payable avant", "date limite")):
                    d_parsed = parse_textual_or_iso_date(txt) or (parse_textual_or_iso_date(next_val) if next_val else None)
                    if d_parsed and meta_out["due_date"] is None:
                        meta_out["due_date"] = d_parsed
                        meta_out["due_date_ref"] = next_ref if (parse_textual_or_iso_date(txt) is None) else cell.cell_ref
                elif "date" in folded or cell.data_type == "date":
                    d_parsed = parse_textual_or_iso_date(txt) or (parse_textual_or_iso_date(next_val) if next_val else None)
                    if d_parsed and meta_out["issue_date"] is None:
                        meta_out["issue_date"] = d_parsed
                        meta_out["issue_date_ref"] = next_ref if (parse_textual_or_iso_date(txt) is None) else cell.cell_ref

                if meta_out["payment_method"] is None:
                    m_pay = pay_re.search(txt)
                    if m_pay:
                        meta_out["payment_method"] = m_pay.group(1)

    def _resolve_amount_for_label_cell(
        self,
        *,
        label_cell: CellProvenance,
        label_text: str,
        row_cells: list[CellProvenance],
        next_row_cells: list[CellProvenance],
        second_next_row_cells: list[CellProvenance] = [],
        default_currency: str | None,
    ) -> tuple[ProvenancedAmount | None, CellProvenance | None]:
        # 1. Cellules situées à droite sur la même ligne
        explicit_ccy_on_row: str | None = None
        for right_cell in row_cells:
            r_txt = str(right_cell.normalized_value or right_cell.raw_value or "").strip().upper()
            if r_txt in KNOWN_CURRENCIES:
                explicit_ccy_on_row = r_txt

        for right_cell in row_cells:
            if right_cell.uncached_formula:
                return None, right_cell
            if right_cell.data_type == "date":
                continue
            raw_right_str = str(right_cell.raw_value or "").strip()
            norm_right_str = str(right_cell.normalized_value or "").strip()
            is_pct_cell = (
                bool(right_cell.number_format and "%" in right_cell.number_format)
                or raw_right_str.endswith("%")
                or norm_right_str.endswith("%")
            )
            if is_pct_cell:
                continue
            parsed = parse_decimal_amount(
                right_cell.cached_value if right_cell.cached_value is not None else right_cell.raw_value,
                currency_hint=explicit_ccy_on_row or right_cell.currency_hint or default_currency,
                allow_bare_integer=True,
            )
            if parsed is not None:
                return self._cell_to_provenanced_amount(right_cell, parsed, label_text, default_currency), None

        # 2. Montant directement inclus dans la même cellule que le libellé (ex: "TOTAL FACTURÉ : 1 437,77 $ CAD")
        inline_part = label_text
        if ":" in label_text:
            inline_part = label_text.split(":", 1)[1].strip()
        else:
            inline_no_pct = _PERCENT_CLEAN_PATTERN.sub("", _TAX_REG_CLEAN_PATTERN.sub("", label_text))
            m_tail = re.search(
                r"(?:total(?:\s+factur[eé]|\s+a\s+payer|\s+ttc|\s+d[uû])?|montant(?:\s+total|\s+pay[eé])?|amount(?:\s+due|\s+paid)?|sous-total|subtotal|solde(?:\s+d[uû]|\s+ant[eé]rieur)?|net\s+[aà]\s+payer|tps|tvq|gst|qst|hst|remise|discount)\s*(?:\([^)]*\))?\s+(.+)$",
                inline_no_pct,
                flags=re.IGNORECASE,
            )
            inline_part = m_tail.group(1).strip() if m_tail else ""

        if inline_part:
            parsed_inline = parse_decimal_amount(
                inline_part,
                currency_hint=label_cell.currency_hint or default_currency,
                allow_bare_integer=False,
            )
            if parsed_inline is not None:
                return self._cell_to_provenanced_amount(label_cell, parsed_inline, label_text, default_currency), None

        # 3. Cellule immédiatement sous le libellé dans la même colonne (bloc vertical de pied de facture)
        # Ne jamais confondre un en-tête de colonne multi-lignes (où r+1 ET r+2 ont des valeurs numériques) avec un bloc récapitulatif!
        for below_cell in next_row_cells:
            if label_cell.column <= below_cell.column <= label_cell.end_column:
                has_column_continuation = any(
                    label_cell.column <= c2.column <= label_cell.end_column
                    and parse_decimal_amount(c2.cached_value if c2.cached_value is not None else c2.raw_value) is not None
                    for c2 in second_next_row_cells
                )
                if has_column_continuation:
                    continue
                b_txt = str(below_cell.normalized_value or below_cell.raw_value or "").strip()
                b_role, _, _ = classify_financial_label(b_txt)
                if b_role is not None:
                    continue
                if below_cell.uncached_formula:
                    return None, below_cell
                if below_cell.data_type == "date":
                    continue
                parsed_below = parse_decimal_amount(
                    below_cell.cached_value if below_cell.cached_value is not None else below_cell.raw_value,
                    currency_hint=below_cell.currency_hint or default_currency,
                    allow_bare_integer=True,
                )
                if parsed_below is not None:
                    return self._cell_to_provenanced_amount(below_cell, parsed_below, label_text, default_currency), None

        return None, None

    @staticmethod
    def _cell_to_provenanced_amount(
        cell: CellProvenance,
        parsed: ParsedMonetaryValue,
        label: str,
        default_currency: str | None,
    ) -> ProvenancedAmount:
        resolved_ccy = parsed.currency or (cell.currency_hint if cell.currency_hint in KNOWN_CURRENCIES else default_currency)
        quantized = parsed.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return ProvenancedAmount(
            amount=quantized,
            currency=resolved_ccy,
            label=label.strip()[:120],
            file_name=cell.file_name,
            sheet_name=cell.sheet_name,
            cell_ref=cell.cell_ref,
            coordinate=cell.coordinate,
            raw_value=cell.raw_value,
            normalized_value=format(quantized, "f"),
            formula=cell.formula,
            uncached_formula=cell.uncached_formula,
            data_type="currency",
            extracted_at=cell.extracted_at,
            confidence=cell.confidence,
            verification_status=cell.verification_status,
            is_hidden_sheet=cell.is_hidden_sheet,
        )

    def _extract_structured_line_item(
        self,
        rcells: list[CellProvenance],
        col_roles: dict[int, str],
        default_currency: str | None,
    ) -> InvoiceLineItem | None:
        desc_parts: list[str] = []
        qty: Decimal | None = None
        qty_ref: str | None = None
        unit_price: Decimal | None = None
        unit_ref: str | None = None
        line_total: Decimal | None = None
        line_ref: str | None = None
        line_ccy: str | None = default_currency
        sheet_name: str | None = rcells[0].sheet_name if rcells else None

        for cell in rcells:
            if cell.uncached_formula or cell.data_type == "date":
                continue
            role = col_roles.get(cell.column)
            val_source = cell.cached_value if cell.cached_value is not None else cell.raw_value
            if role == "description":
                txt = str(cell.normalized_value or val_source or "").strip()
                if txt:
                    desc_parts.append(txt)
            elif role == "quantity":
                parsed_q = parse_decimal_amount(val_source, allow_bare_integer=True)
                if parsed_q is not None:
                    qty = parsed_q.amount
                    qty_ref = cell.cell_ref
            elif role == "unit_price":
                parsed_u = parse_decimal_amount(val_source, currency_hint=cell.currency_hint or default_currency, allow_bare_integer=True)
                if parsed_u is not None:
                    unit_price = parsed_u.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    unit_ref = cell.cell_ref
                    if parsed_u.currency:
                        line_ccy = parsed_u.currency
            elif role == "line_total":
                parsed_t = parse_decimal_amount(val_source, currency_hint=cell.currency_hint or default_currency, allow_bare_integer=True)
                if parsed_t is not None:
                    line_total = parsed_t.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    line_ref = cell.cell_ref
                    if parsed_t.currency:
                        line_ccy = parsed_t.currency
            elif not desc_parts and cell.data_type == "text":
                txt = str(cell.normalized_value or val_source or "").strip()
                if txt:
                    desc_parts.append(txt)

        if line_total is None or line_ref is None:
            return None
        description = " - ".join(desc_parts) if desc_parts else "Ligne de facturation"
        return InvoiceLineItem(
            description=description,
            quantity=qty,
            unit_price=unit_price,
            line_total=line_total,
            currency=line_ccy,
            sheet_name=sheet_name,
            cell_ref=line_ref,
            unit_price_ref=unit_ref,
            quantity_ref=qty_ref,
        )

    def _extract_text_line_item(
        self,
        rcells: list[CellProvenance],
        default_currency: str | None,
    ) -> InvoiceLineItem | None:
        if len(rcells) != 1:
            return None
        cell = rcells[0]
        txt = str(cell.normalized_value or cell.raw_value or "").strip()
        if not txt:
            return None
        # Motif ligne texte : "Transport Montréal-Québec | 2 x 625,25 $ | 1 250,50 $"
        m = re.match(
            r"^(.{3,80}?)\s+(\d+(?:[.,]\d+)?)\s*[xX×*]\s*([$€£]?\s*\d[\d\s\u00a0.,]*[$€£]?)\s*(?:=|\||:|\s+)\s*([$€£]?\s*-?\d[\d\s\u00a0.,]*[$€£]?(?:\s*(?:CAD|USD|EUR))?)$",
            txt,
        )
        if not m:
            return None
        desc = m.group(1).strip(" |-:")
        qty_dec = _normalize_numeric_token_to_decimal(m.group(2))
        up_parsed = parse_decimal_amount(m.group(3), currency_hint=default_currency)
        lt_parsed = parse_decimal_amount(m.group(4), currency_hint=default_currency)
        if qty_dec is None or up_parsed is None or lt_parsed is None:
            return None
        return InvoiceLineItem(
            description=desc,
            quantity=qty_dec,
            unit_price=up_parsed.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            line_total=lt_parsed.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            currency=lt_parsed.currency or up_parsed.currency or default_currency,
            sheet_name=cell.sheet_name,
            cell_ref=cell.cell_ref,
        )

    def _resolve_and_verify_totals(
        self,
        *,
        line_items: list[InvoiceLineItem],
        subtotal: ProvenancedAmount | None,
        discount: ProvenancedAmount | None,
        tax_total: Decimal,
        grand_total_candidates: list[ProvenancedAmount],
        prior_balance: ProvenancedAmount | None,
        amount_paid: ProvenancedAmount | None,
        balance_due: ProvenancedAmount | None,
        uncached_formulas: list[dict[str, Any]],
        currency_conflict: bool,
        tax_included: bool,
        is_credit_note: bool,
    ) -> tuple[ProvenancedAmount | None, tuple[ProvenancedAmount, ...], bool, str, str, str]:
        # Si une formule de champ financier n'a aucune valeur mise en cache
        total_uncached = [
            u
            for u in uncached_formulas
            if u.get("associated_role")
            in {
                "grand_total",
                "balance_due",
                "subtotal",
                "tax",
                "tax_aggregate",
                "discount",
                "amount_paid",
                "prior_balance",
                "line_total",
            }
            or bool(u.get("cell_ref"))
        ]
        if not grand_total_candidates:
            if total_uncached or uncached_formulas:
                return (
                    None,
                    (),
                    False,
                    "Formule Excel sans valeur mise en cache détectée sur un champ financier ; confirmation impossible sans recalcul Excel.",
                    "uncached_formula",
                    "uncertain_candidates",
                )
            return (
                None,
                (),
                False,
                "Aucun montant total facturé détecté après lecture intégrale du document.",
                "no_amount_found",
                "missing_after_full_read",
            )

        if currency_conflict:
            return (
                None,
                tuple(grand_total_candidates),
                False,
                "Devises multiples contradictoires détectées dans la même facture ; aucune conversion implicite n'est autorisée.",
                "ambiguous_candidates",
                "uncertain_candidates",
            )

        # Dédupliquer les candidats ayant exactement le même montant (ex: rappel du total en haut et en bas de facture)
        unique_by_amount: dict[Decimal, ProvenancedAmount] = {}
        for cand in grand_total_candidates:
            unique_by_amount[cand.amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)] = cand

        # Calculer les sommes attendues en Decimal
        line_sum: Decimal | None = (
            sum((li.line_total for li in line_items), Decimal("0.00")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if line_items
            else None
        )
        discount_abs = abs(discount.amount) if discount is not None else Decimal("0.00")

        expected_totals: list[tuple[Decimal, str]] = []
        if subtotal is not None:
            # Cas standard : subtotal - discount + tax_total (ou subtotal + tax_total si remise déjà déduite du sous-total)
            if is_credit_note and subtotal.amount < Decimal("0.00"):
                expected_totals.append(
                    (
                        (subtotal.amount + discount_abs + tax_total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                        "credit_note: subtotal + discount + taxes",
                    )
                )
            expected_totals.append(
                (
                    (subtotal.amount - discount_abs + tax_total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                    "subtotal - discount + tax_total",
                )
            )
            if discount is not None and line_sum is not None and abs((line_sum - discount_abs) - subtotal.amount) <= self._tolerance:
                expected_totals.append(
                    (
                        (subtotal.amount + tax_total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                        "discounted_subtotal + tax_total",
                    )
                )
        if line_sum is not None:
            expected_totals.append(
                (
                    (line_sum - discount_abs + tax_total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                    "sum(line_items) - discount + tax_total",
                )
            )
            if tax_included:
                expected_totals.append(
                    (
                        (line_sum - discount_abs).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                        "tax_included: sum(line_items) - discount",
                    )
                )

        # Vérifier quels candidats correspondent mathématiquement
        matching_candidates: list[tuple[ProvenancedAmount, str]] = []
        for cand in unique_by_amount.values():
            for exp_val, formula_desc in expected_totals:
                if abs(cand.amount - exp_val) <= self._tolerance:
                    # Si à la fois line_items et subtotal existent, vérifier aussi leur cohérence mutuelle!
                    if line_sum is not None and subtotal is not None:
                        sub_ok = (
                            abs(line_sum - subtotal.amount) <= self._tolerance
                            or abs((line_sum - discount_abs) - subtotal.amount) <= self._tolerance
                        )
                        if not sub_ok:
                            continue
                    matching_candidates.append((cand, formula_desc))
                    break

        def _check_balance_reconciliation(total_val: Decimal) -> tuple[bool, str | None]:
            if balance_due is None or (amount_paid is None and prior_balance is None):
                return True, None
            prior_val = prior_balance.amount if prior_balance is not None else Decimal("0.00")
            paid_val = abs(amount_paid.amount) if amount_paid is not None else Decimal("0.00")
            expected_bal = (total_val + prior_val - paid_val).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            diff_bal = abs(balance_due.amount - expected_bal)
            if diff_bal <= self._tolerance:
                return True, None
            return (
                False,
                f"Écart de solde détecté : total ({format(total_val, 'f')}) + solde antérieur ({format(prior_val, 'f')}) - payé ({format(paid_val, 'f')}) = {format(expected_bal, 'f')} vs solde dû indiqué {format(balance_due.amount, 'f')} (écart {format(diff_bal, 'f')}).",
            )

        if len(matching_candidates) == 1:
            winner, formula_desc = matching_candidates[0]
            # S'il existe une formule non cachée sur une remise, taxe ou sous-total alors qu'on prétendait vérifier, refuser!
            if total_uncached:
                return (
                    None,
                    tuple(unique_by_amount.values()),
                    False,
                    "Une formule de sous-total/remise/taxe/total n'a pas de valeur mise en cache.",
                    "uncached_formula",
                    "uncertain_candidates",
                )
            bal_ok, bal_err = _check_balance_reconciliation(winner.amount)
            if not bal_ok:
                return (
                    winner,
                    (winner,),
                    False,
                    bal_err or "Écart de réconciliation du solde restant dû.",
                    "math_mismatch",
                    "uncertain_candidates",
                )
            return (
                winner,
                (),
                True,
                f"Vérifié mathématiquement ({formula_desc} = {format(winner.amount, 'f')}, tolérance ±{format(self._tolerance, 'f')}).",
                "math_verified",
                "math_verified",
            )

        if len(unique_by_amount) > 1:
            # Plusieurs totaux plausibles distincts sans gagnant mathématique unique -> ne JAMAIS deviner!
            return (
                None,
                tuple(grand_total_candidates),
                False,
                f"{len(unique_by_amount)} montants totaux distincts détectés sans réconciliation mathématique unique ; confirmation requise.",
                "ambiguous_candidates",
                "uncertain_candidates",
            )

        # Un seul candidat total dans le document
        sole = next(iter(unique_by_amount.values()))
        if total_uncached:
            return (
                None,
                (sole,),
                False,
                "Une formule associée n'a pas de valeur mise en cache.",
                "uncached_formula",
                "uncertain_candidates",
            )

        if expected_totals:
            # Il y avait des lignes ou un sous-total+taxes, mais aucun n'égale `sole.amount` dans la tolérance!
            closest_exp, closest_desc = min(expected_totals, key=lambda item: abs(sole.amount - item[0]))
            diff = abs(sole.amount - closest_exp)
            return (
                sole,
                (sole,),
                False,
                f"Écart mathématique détecté : attendu {format(closest_exp, 'f')} ({closest_desc}) vs total indiqué {format(sole.amount, 'f')} (écart {format(diff, 'f')} > {format(self._tolerance, 'f')}).",
                "math_mismatch",
                "uncertain_candidates",
            )

        bal_ok, bal_err = _check_balance_reconciliation(sole.amount)
        if not bal_ok:
            return (
                sole,
                (sole,),
                False,
                bal_err or "Écart de réconciliation du solde restant dû.",
                "math_mismatch",
                "uncertain_candidates",
            )

        # Facture simple / reçu ne comportant qu'un total unique sans détail de lignes ni sous-total contradictoire
        return (
            sole,
            (),
            False,
            "Montant total unique extrait sans ambiguïté (aucune ventilation lignes/sous-total présente pour double contrôle arithmétique).",
            "extracted_unverified_math",
            "extracted_structured",
        )

    @staticmethod
    def _build_direct_statement_fr(
        *,
        total: ProvenancedAmount | None,
        balance_due: ProvenancedAmount | None,
        amount_paid: ProvenancedAmount | None,
        currency: str | None,
        verification_status: str,
    ) -> str | None:
        if total is None or verification_status not in {"math_verified", "extracted_unverified_math"}:
            return None
        resolved_ccy = (
            currency
            if currency and currency in KNOWN_CURRENCIES
            else (total.currency if total.currency and total.currency in KNOWN_CURRENCIES else None)
        )
        ccy_suffix = f" {resolved_ccy}" if resolved_ccy else " (devise non spécifiée)"
        formatted_total = format_decimal_fr(total.amount)
        if total.sheet_name and re.match(r"^[A-Z]+\d+$", total.coordinate):
            stmt = (
                f"Le montant total facturé est {formatted_total}{ccy_suffix}, "
                f"indiqué dans l'onglet {total.sheet_name}, cellule {total.coordinate}."
            )
        else:
            stmt = f"Le montant total facturé est {formatted_total}{ccy_suffix}, indiqué à la référence {total.cell_ref}."

        if (
            balance_due is not None
            and amount_paid is not None
            and abs(amount_paid.amount) > Decimal("0.00")
            and balance_due.amount != total.amount
        ):
            stmt += (
                f" Après déduction du montant payé ({format_decimal_fr(abs(amount_paid.amount))}{ccy_suffix}), "
                f"le solde restant dû est {format_decimal_fr(balance_due.amount)}{ccy_suffix}."
            )
        return stmt


__all__ = [
    "ExtractedInvoice",
    "InvoiceExtractionReport",
    "InvoiceExtractionService",
    "InvoiceLineItem",
    "ParsedMonetaryValue",
    "ProvenancedAmount",
    "ROUNDING_TOLERANCE",
    "TaxBreakdownItem",
    "classify_financial_label",
    "format_decimal_fr",
    "parse_decimal_amount",
    "parse_textual_or_iso_date",
]
