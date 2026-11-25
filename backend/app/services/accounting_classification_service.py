"""Service de classification comptable automatique sensible au rôle de l'entreprise (Phase E).

Règles fondamentales :
1. La classification (revenu/créance vs dépense/dette vs avoir vs remboursement vs transfert vs non-comptable)
   repose sur le RÔLE VÉRIFIÉ de l'entreprise locataire (`Company` + `CompanyLegalProfile` + alias)
   par rapport à l'émetteur (`issuer`/`vendor`) et au destinataire (`recipient`/`customer`).
2. Une note de crédit (`avoir`) ou un remboursement (`refund`) n'est JAMAIS confondu avec une nouvelle vente.
3. Aucun taux de taxe (TPS/TVQ/GST/QST/HST) n'est jamais inventé : seules les taxes extraites du document
   ou issues d'une règle fiscale explicitement configurée par le tenant sont retenues, avec validation `Decimal`.
4. Gouvernance stricte des propositions : toute classification documentaire / IA crée une proposition
   `to_verify` (`is_confirmed=False`, `accounting_status='proposed'`) jusqu'à validation humaine auditée.
5. Prévention déterministe des doublons (empreinte SHA-256 fichier + clés métier) : avertissement explicite
   sans suppression silencieuse, et confirmation obligatoire avant approbation d'un doublon potentiel.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.accounting import (
    AccountingClassificationRule,
    AccountingInvoice,
    AccountingTenantPolicy,
    AccountingTransaction,
)
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.company import Company
from backend.app.models.company_legal_profile import CompanyLegalProfile
from backend.app.models.dataset import Dataset
from backend.app.models.workspace import TenantDocument

TWOPLACES = Decimal("0.01")
MATH_TOLERANCE = Decimal("0.02")

VALID_CLASSIFICATIONS: frozenset[str] = frozenset({
    "supplier_invoice",
    "customer_invoice",
    "receipt",
    "payment",
    "refund",
    "credit_note",
    "transfer",
    "non_posting",
})

GENERIC_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com",
    "yahoo.com",
    "yahoo.ca",
    "yahoo.fr",
    "hotmail.com",
    "hotmail.ca",
    "outlook.com",
    "icloud.com",
    "live.com",
    "msn.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "videotron.ca",
    "bell.net",
    "sympatico.ca",
})

CORPORATE_SUFFIXES: tuple[str, ...] = (
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "ltd",
    "limited",
    "ltee",
    "ltée",
    "llc",
    "senc",
    "s.e.n.c",
    "sarl",
    "sas",
    "gmbh",
    "plc",
    "co",
    "company",
)


class AccountingClassificationError(ValueError):
    """Erreur métier lors de la classification ou révision comptable."""


class DuplicateConfirmationRequiredError(AccountingClassificationError):
    """Levée lorsqu'une facture signalée comme doublon est approuvée sans confirmation explicite."""


def _to_decimal(value: Any, *, default: Decimal | None = Decimal("0.00")) -> Decimal | None:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    raw = str(value).strip()
    if not raw:
        return default
    cleaned = re.sub(r"[^\d,.\-]", "", raw)
    if not cleaned or cleaned in {"-", ".", ","}:
        return default
    if cleaned.count(",") == 1 and cleaned.count(".") == 0:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(",") >= 1 and cleaned.count(".") >= 1:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return default


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_party_identifier(value: str | None) -> str:
    """Normalise un nom d'entreprise ou de contrepartie pour la comparaison déterministe."""
    if not value:
        return ""
    lowered = _strip_accents(value).casefold()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    tokens = [tok for tok in lowered.split() if tok and tok not in CORPORATE_SUFFIXES]
    return " ".join(tokens)


def normalize_tax_identifier(value: str | None) -> str:
    """Normalise un identifiant fiscal (TPS/TVQ/BN/NEQ) en majuscules alphanumériques."""
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _extract_domain(email_or_url: str | None) -> str | None:
    if not email_or_url:
        return None
    raw = email_or_url.strip().lower()
    if "@" in raw and "://" not in raw:
        domain = raw.rsplit("@", 1)[-1].strip(" >)")
    else:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        domain = (parsed.hostname or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain or "." not in domain or domain in GENERIC_EMAIL_DOMAINS:
        return None
    return domain


def _parse_datetime(value: Any, *, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return fallback or datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class CompanyIdentityProfile:
    company_id: UUID
    canonical_name: str
    normalized_names: frozenset[str]
    tax_identifiers: frozenset[str]
    corporate_domains: frozenset[str]
    default_currency: str


@dataclass(slots=True)
class ClassificationOutcome:
    classification: str  # supplier_invoice, customer_invoice, receipt, payment, refund, credit_note, transfer, non_posting
    invoice_type: str  # payable, receivable, credit_note, refund, payment, transfer, other
    direction: str  # expense, revenue, expense_reversal, revenue_reversal, neutral
    company_role: str  # customer_buyer, issuer_supplier, internal_transfer, ambiguous, unknown
    category: str
    party_name: str
    issuer_name: str | None
    recipient_name: str | None
    invoice_number: str
    issue_date: datetime
    due_date: datetime
    currency: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    tax_breakdown: dict[str, str]
    line_items: list[dict[str, Any]]
    confidence_score: float
    verification_status: str
    accounting_status: str
    is_confirmed: bool
    rationale: str
    math_validation: dict[str, Any] = field(default_factory=dict)


class AccountingClassificationService:
    """Moteur de classification comptable vérifiant l'identité de l'entreprise, les taxes et les doublons."""

    def __init__(
        self,
        session: Session,
        *,
        llm_classifier: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._session = session
        self._llm_classifier = llm_classifier

    def get_or_create_policy(self, company_id: UUID) -> AccountingTenantPolicy:
        policy = self._session.scalar(
            select(AccountingTenantPolicy).where(AccountingTenantPolicy.company_id == company_id)
        )
        if policy is None:
            policy = AccountingTenantPolicy(
                company_id=company_id,
                auto_confirm_verified_connector_settlements=False,
                confidence_threshold=0.85,
                configured_tax_rules={},
                company_aliases=[],
                extra_config={},
            )
            self._session.add(policy)
            self._session.flush()
        return policy

    def update_policy(
        self,
        company_id: UUID,
        *,
        actor_user_id: UUID | None = None,
        auto_confirm_verified_connector_settlements: bool | None = None,
        confidence_threshold: float | None = None,
        configured_tax_rules: dict[str, Any] | None = None,
        company_aliases: list[str] | None = None,
    ) -> AccountingTenantPolicy:
        policy = self.get_or_create_policy(company_id)
        if auto_confirm_verified_connector_settlements is not None:
            policy.auto_confirm_verified_connector_settlements = bool(auto_confirm_verified_connector_settlements)
        if confidence_threshold is not None:
            policy.confidence_threshold = max(0.5, min(float(confidence_threshold), 0.99))
        if configured_tax_rules is not None:
            policy.configured_tax_rules = dict(configured_tax_rules)
        if company_aliases is not None:
            policy.company_aliases = [str(a).strip() for a in company_aliases if str(a).strip()]

        self._session.add(
            AuditLogEntry(
                actor_user_id=actor_user_id,
                company_id=company_id,
                action="accounting.policy.updated",
                target_type="AccountingTenantPolicy",
                target_id=str(policy.id),
                safe_metadata={
                    "auto_confirm_verified_connector_settlements": policy.auto_confirm_verified_connector_settlements,
                    "confidence_threshold": policy.confidence_threshold,
                    "aliases_count": len(policy.company_aliases or []),
                    "has_tax_rules": bool(policy.configured_tax_rules),
                },
            )
        )
        self._session.commit()
        self._session.refresh(policy)
        return policy

    def add_classification_rule(
        self,
        company_id: UUID,
        *,
        counterparty_pattern: str,
        forced_classification: str,
        default_category: str = "other",
        match_field: str = "counterparty",
        notes: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> AccountingClassificationRule:
        if forced_classification not in VALID_CLASSIFICATIONS:
            raise AccountingClassificationError(f"Classification invalide: {forced_classification}")
        clean_pattern = counterparty_pattern.strip()
        if not clean_pattern:
            raise AccountingClassificationError("Le motif de contrepartie est obligatoire.")
        rule = AccountingClassificationRule(
            company_id=company_id,
            counterparty_pattern=clean_pattern,
            match_field=match_field,
            forced_classification=forced_classification,
            default_category=default_category.strip() or "other",
            is_active=True,
            notes=notes,
        )
        self._session.add(rule)
        self._session.flush()
        self._session.add(
            AuditLogEntry(
                actor_user_id=actor_user_id,
                company_id=company_id,
                action="accounting.classification_rule.created",
                target_type="AccountingClassificationRule",
                target_id=str(rule.id),
                safe_metadata={
                    "forced_classification": forced_classification,
                    "default_category": rule.default_category,
                    "match_field": match_field,
                },
            )
        )
        self._session.commit()
        self._session.refresh(rule)
        return rule

    def resolve_company_identity(self, company_id: UUID) -> CompanyIdentityProfile:
        company = self._session.get(Company, company_id)
        if company is None:
            raise LookupError("Entreprise introuvable")

        legal = self._session.scalar(
            select(CompanyLegalProfile).where(CompanyLegalProfile.company_id == company_id)
        )
        policy = self._session.scalar(
            select(AccountingTenantPolicy).where(AccountingTenantPolicy.company_id == company_id)
        )

        names: set[str] = set()
        for raw_name in (
            company.name,
            company.slug.replace("-", " "),
            legal.legal_name if legal else None,
            legal.trade_name if legal else None,
            *(policy.company_aliases if policy and policy.company_aliases else []),
        ):
            norm = normalize_party_identifier(raw_name)
            if norm:
                names.add(norm)

        tax_ids: set[str] = set()
        if legal is not None:
            for raw_tax in (
                legal.registration_number,
                legal.business_number,
                legal.tax_id_gst,
                legal.tax_id_qst,
                legal.tax_id_other,
            ):
                norm_tax = normalize_tax_identifier(raw_tax)
                if len(norm_tax) >= 5:
                    tax_ids.add(norm_tax)

        domains: set[str] = set()
        for raw_contact in (
            company.email,
            company.billing_email,
            company.website,
            legal.website if legal else None,
            legal.general_email if legal else None,
            legal.billing_email if legal else None,
        ):
            dom = _extract_domain(raw_contact)
            if dom:
                domains.add(dom)

        default_currency = (company.currency_code or "CAD").upper()
        return CompanyIdentityProfile(
            company_id=company_id,
            canonical_name=(legal.legal_name if legal and legal.legal_name else company.name),
            normalized_names=frozenset(names),
            tax_identifiers=frozenset(tax_ids),
            corporate_domains=frozenset(domains),
            default_currency=default_currency,
        )

    @staticmethod
    def _match_party_to_company(
        profile: CompanyIdentityProfile,
        *,
        party_name: str | None,
        party_tax_id: str | None = None,
        party_email_or_domain: str | None = None,
    ) -> tuple[bool, float, str]:
        norm_tax = normalize_tax_identifier(party_tax_id)
        if norm_tax and norm_tax in profile.tax_identifiers:
            return True, 0.98, f"Identifiant fiscal exact vérifié ({norm_tax})"

        norm_party = normalize_party_identifier(party_name)
        if norm_party:
            if norm_party in profile.normalized_names:
                return True, 0.94, f"Nom d'entreprise vérifié correspondant ('{party_name}')"
            for known_name in profile.normalized_names:
                if len(known_name) >= 4 and len(norm_party) >= 4:
                    if known_name in norm_party or norm_party in known_name:
                        return True, 0.87, f"Correspondance de raison sociale/marque ('{party_name}')"

        dom = _extract_domain(party_email_or_domain)
        if dom and dom in profile.corporate_domains:
            return True, 0.88, f"Domaine corporatif vérifié ({dom})"

        return False, 0.0, ""

    @staticmethod
    def _extract_parties_from_text(extracted_text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        if not extracted_text:
            return result
        issuer_patterns = (
            r"(?:de|from|fournisseur|vendor|supplier|émetteur|emetteur|émis par|sold by)\s*[:\-]\s*([^\n\r]{2,120})",
        )
        recipient_patterns = (
            r"(?:facturé à|facture a|bill to|billed to|client|customer|destinataire|vendu à|sold to)\s*[:\-]\s*([^\n\r]{2,120})",
        )
        for pat in issuer_patterns:
            m = re.search(pat, extracted_text, flags=re.IGNORECASE)
            if m:
                result["issuer"] = m.group(1).strip()
                break
        for pat in recipient_patterns:
            m = re.search(pat, extracted_text, flags=re.IGNORECASE)
            if m:
                result["recipient"] = m.group(1).strip()
                break
        return result

    @staticmethod
    def _detect_document_nature_signal(payload: Mapping[str, Any], extracted_text: str) -> str | None:
        raw_hint = str(
            payload.get("document_type")
            or payload.get("document_nature")
            or payload.get("kind_hint")
            or ""
        ).strip().lower()
        combined = f"{raw_hint} {(extracted_text or '')[:1500].lower()}"

        if raw_hint in VALID_CLASSIFICATIONS:
            return raw_hint
        if raw_hint in {"avoir", "credit_memo", "note_de_credit"} or any(
            kw in combined for kw in ("note de crédit", "note de credit", "avoir ", "credit note", "credit memo")
        ):
            return "credit_note"
        if raw_hint in {"remboursement", "return_refund"} or any(
            kw in combined for kw in ("remboursement", "refund receipt", "avis de remboursement", "refunded")
        ):
            return "refund"
        if raw_hint in {"virement", "internal_transfer"} or any(
            kw in combined for kw in ("virement interne", "transfert entre comptes", "internal transfer")
        ):
            return "transfer"
        if raw_hint in {"quote", "devis", "soumission", "proforma", "statement", "purchase_order"} or any(
            kw in combined
            for kw in ("devis ", "soumission ", "facture proforma", "proforma invoice", "bon de commande")
        ):
            return "non_posting"
        if raw_hint in {"payment_advice", "remittance"} or any(
            kw in combined for kw in ("avis de paiement", "remittance advice", "confirmation de paiement")
        ):
            return "payment"
        if raw_hint in {"receipt", "recu", "reçu"} or any(
            kw in combined for kw in ("reçu de caisse", "recu de caisse", "sales receipt", "reçu #")
        ):
            return "receipt"
        return None

    @staticmethod
    def _infer_expense_category(party_name: str, text_and_lines: str) -> str:
        blob = f"{party_name} {text_and_lines}".lower()
        if any(k in blob for k in ("hydro", "électricité", "electricite", "gaz", "telecom", "bell", "videotron", "internet")):
            return "utilities"
        if any(k in blob for k in ("saas", "cloud", "aws", "google", "microsoft", "openai", "software", "logiciel", "abonnement")):
            return "software"
        if any(k in blob for k in ("facebook ads", "google ads", "meta", "publicité", "publicite", "marketing", "campagne")):
            return "marketing"
        if any(k in blob for k in ("inventaire", "marchandise", "wholesale", "matière première", "cogs", "stock")):
            return "cogs"
        if any(k in blob for k in ("loyer", "rent", "bail")):
            return "rent"
        return "other"

    def _validate_amounts_and_taxes(
        self,
        payload: Mapping[str, Any],
        policy: AccountingTenantPolicy,
    ) -> tuple[Decimal, Decimal, Decimal, dict[str, str], list[dict[str, Any]], dict[str, Any]]:
        raw_lines = payload.get("line_items")
        normalized_lines: list[dict[str, Any]] = []
        lines_sum = Decimal("0.00")

        if isinstance(raw_lines, list):
            for idx, item in enumerate(raw_lines):
                if not isinstance(item, Mapping):
                    continue
                qty = _to_decimal(item.get("quantity", 1), default=Decimal("1.00")) or Decimal("1.00")
                unit_price = _to_decimal(item.get("unit_price"), default=None)
                line_total = _to_decimal(item.get("total") if item.get("total") is not None else item.get("amount"), default=None)
                if line_total is None and unit_price is not None:
                    line_total = (qty * unit_price).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
                if line_total is None:
                    line_total = Decimal("0.00")
                lines_sum += line_total
                normalized_lines.append({
                    "line_index": idx + 1,
                    "description": str(item.get("description") or item.get("title") or f"Ligne {idx + 1}"),
                    "quantity": str(qty),
                    "unit_price": str(unit_price) if unit_price is not None else None,
                    "total": str(line_total),
                    "sku": item.get("sku"),
                    "tax_code": item.get("tax_code"),
                    "source_ref": item.get("source_ref"),
                })

        subtotal = _to_decimal(payload.get("subtotal_amount") if payload.get("subtotal_amount") is not None else payload.get("subtotal"), default=None)
        total = _to_decimal(payload.get("total_amount") if payload.get("total_amount") is not None else payload.get("total"), default=None)

        # Extraction stricte des taxes documentées (jamais inventées)
        tax_breakdown: dict[str, str] = {}
        raw_breakdown = payload.get("tax_breakdown")
        if isinstance(raw_breakdown, Mapping):
            for k, v in raw_breakdown.items():
                dec_v = _to_decimal(v, default=None)
                if dec_v is not None and dec_v != Decimal("0.00"):
                    tax_breakdown[str(k)] = str(dec_v)

        for key_alias, canonical_tax_key in (
            ("gst_amount", "gst_tps"),
            ("tps_amount", "gst_tps"),
            ("qst_amount", "qst_tvq"),
            ("tvq_amount", "qst_tvq"),
            ("hst_amount", "hst_tvh"),
            ("tvh_amount", "hst_tvh"),
        ):
            if payload.get(key_alias) is not None and canonical_tax_key not in tax_breakdown:
                dec_v = _to_decimal(payload.get(key_alias), default=None)
                if dec_v is not None and dec_v != Decimal("0.00"):
                    tax_breakdown[canonical_tax_key] = str(dec_v)

        explicit_tax = _to_decimal(payload.get("tax_amount"), default=None)
        breakdown_sum = sum((Decimal(v) for v in tax_breakdown.values()), Decimal("0.00"))

        tax_source = "extracted"
        if explicit_tax is not None:
            tax_amount = explicit_tax
        elif tax_breakdown:
            tax_amount = breakdown_sum
        elif bool(payload.get("apply_configured_tax_rules")) and policy.configured_tax_rules and subtotal is not None:
            # Règle fiscale explicitement configurée par le tenant et demandée — jamais devinée
            tax_source = "configured_tenant_rule"
            computed_tax = Decimal("0.00")
            for tax_name, rate_raw in policy.configured_tax_rules.items():
                rate = _to_decimal(rate_raw, default=None)
                if rate is not None and rate > Decimal("0.00"):
                    leg = (subtotal * rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
                    tax_breakdown[str(tax_name)] = str(leg)
                    computed_tax += leg
            tax_amount = computed_tax
        else:
            tax_amount = Decimal("0.00")
            tax_source = "none_documented"

        if total is None and subtotal is not None:
            total = (subtotal + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        elif total is None and normalized_lines:
            subtotal = lines_sum
            total = (subtotal + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        if total is None or total <= Decimal("0.00"):
            # Pour documents non-comptables sans montant, autoriser 0.00 uniquement si non_posting explicite
            if str(payload.get("document_type") or "").lower() in {"non_posting", "quote", "devis"}:
                total = Decimal("0.00")
                subtotal = Decimal("0.00")
            else:
                raise AccountingClassificationError(
                    "Montant total absent ou invalide : aucun montant comptable n'a été inventé."
                )

        if subtotal is None:
            subtotal = (total - tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        expected_total = (subtotal + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        header_delta = abs(total - expected_total)
        lines_delta = abs(subtotal - lines_sum) if normalized_lines else Decimal("0.00")
        breakdown_delta = abs(tax_amount - breakdown_sum) if tax_breakdown else Decimal("0.00")

        math_valid = (
            header_delta <= MATH_TOLERANCE
            and lines_delta <= MATH_TOLERANCE
            and breakdown_delta <= MATH_TOLERANCE
        )
        math_validation = {
            "math_valid": math_valid,
            "subtotal_amount": str(subtotal),
            "tax_amount": str(tax_amount),
            "total_amount": str(total),
            "lines_sum": str(lines_sum) if normalized_lines else None,
            "header_discrepancy": str(header_delta),
            "lines_discrepancy": str(lines_delta) if normalized_lines else "0.00",
            "tax_breakdown_discrepancy": str(breakdown_delta) if tax_breakdown else "0.00",
            "tax_source": tax_source,
        }
        return subtotal, tax_amount, total, tax_breakdown, normalized_lines, math_validation

    def classify_document_payload(
        self,
        company_id: UUID,
        payload: Mapping[str, Any],
    ) -> ClassificationOutcome:
        """Classe un document financier en fonction du rôle vérifié de l'entreprise."""
        profile = self.resolve_company_identity(company_id)
        policy = self.get_or_create_policy(company_id)
        extracted_text = str(payload.get("extracted_text") or "")

        text_parties = self._extract_parties_from_text(extracted_text)
        issuer_name = (
            str(
                payload.get("issuer")
                or payload.get("issuer_name")
                or payload.get("vendor")
                or payload.get("supplier")
                or payload.get("seller")
                or text_parties.get("issuer")
                or ""
            ).strip()
            or None
        )
        recipient_name = (
            str(
                payload.get("recipient")
                or payload.get("recipient_name")
                or payload.get("customer")
                or payload.get("buyer")
                or payload.get("client")
                or payload.get("bill_to")
                or text_parties.get("recipient")
                or ""
            ).strip()
            or None
        )

        issuer_is_company, issuer_conf, issuer_reason = self._match_party_to_company(
            profile,
            party_name=issuer_name,
            party_tax_id=payload.get("issuer_tax_id"),
            party_email_or_domain=payload.get("issuer_email") or payload.get("issuer_domain"),
        )
        recipient_is_company, recipient_conf, recipient_reason = self._match_party_to_company(
            profile,
            party_name=recipient_name,
            party_tax_id=payload.get("recipient_tax_id"),
            party_email_or_domain=payload.get("recipient_email") or payload.get("recipient_domain"),
        )

        nature_signal = self._detect_document_nature_signal(payload, extracted_text)
        subtotal, tax_amount, total, tax_breakdown, normalized_lines, math_validation = (
            self._validate_amounts_and_taxes(payload, policy)
        )

        reasons: list[str] = []
        classification: str
        invoice_type: str
        direction: str
        company_role: str
        confidence: float
        counterparty: str
        category: str

        # 1. Comparaison du rôle de l'entreprise (émetteur vs client/acheteur)
        if issuer_is_company and recipient_is_company:
            company_role = "internal_transfer"
            classification = "transfer"
            invoice_type = "transfer"
            direction = "neutral"
            counterparty = profile.canonical_name
            category = "transfer"
            confidence = min(issuer_conf, recipient_conf)
            reasons.append("L'émetteur et le destinataire correspondent tous deux à l'entreprise vérifiée (transfert interne).")
        elif recipient_is_company and not issuer_is_company:
            company_role = "customer_buyer"
            counterparty = issuer_name or "Fournisseur à confirmer"
            reasons.append(f"L'entreprise est identifiée comme acheteur/destinataire ({recipient_reason}).")
            if issuer_name:
                reasons.append(f"Émetteur externe détecté : '{issuer_name}'.")

            if nature_signal == "credit_note":
                classification = "credit_note"
                invoice_type = "credit_note"
                direction = "expense_reversal"
                category = "expense_credits"
                confidence = round(recipient_conf * 0.96, 2) if issuer_name else 0.72
                reasons.append("Document identifié comme note de crédit (avoir fournisseur) réduisant les charges/dettes — jamais une vente.")
            elif nature_signal == "refund":
                classification = "refund"
                invoice_type = "refund"
                direction = "expense_reversal"
                category = "expense_refunds"
                confidence = round(recipient_conf * 0.95, 2) if issuer_name else 0.70
                reasons.append("Remboursement fournisseur reçu — jamais comptabilisé comme nouvelle vente.")
            elif nature_signal == "non_posting":
                classification = "non_posting"
                invoice_type = "other"
                direction = "neutral"
                category = "non_posting"
                confidence = 0.90
                reasons.append("Document informatif/pré-contractuel (devis/bon de commande) non comptabilisable au grand livre.")
            elif nature_signal == "payment":
                classification = "payment"
                invoice_type = "payment"
                direction = "neutral"
                category = "settlement"
                confidence = 0.86
                reasons.append("Avis de décaissement/règlement fournisseur sans création d'une nouvelle charge distincte.")
            elif nature_signal == "receipt":
                classification = "receipt"
                invoice_type = "payable"
                direction = "expense"
                category = self._infer_expense_category(counterparty, extracted_text)
                confidence = round(recipient_conf * 0.95, 2) if issuer_name else 0.75
                reasons.append("Reçu d'achat fournisseur classé en dépense d'entreprise.")
            else:
                classification = "supplier_invoice"
                invoice_type = "payable"
                direction = "expense"
                category = str(payload.get("category") or self._infer_expense_category(counterparty, extracted_text))
                confidence = round(recipient_conf * 0.97, 2) if issuer_name else 0.74
                reasons.append("Facture fournisseur classée en dépense / compte fournisseur (payable).")
        elif issuer_is_company and not recipient_is_company:
            company_role = "issuer_supplier"
            counterparty = recipient_name or "Client à confirmer"
            reasons.append(f"L'entreprise est identifiée comme émetteur/vendeur ({issuer_reason}).")
            if recipient_name:
                reasons.append(f"Client destinataire détecté : '{recipient_name}'.")

            if nature_signal == "credit_note":
                classification = "credit_note"
                invoice_type = "credit_note"
                direction = "revenue_reversal"
                category = "sales_returns"
                confidence = round(issuer_conf * 0.96, 2) if recipient_name else 0.72
                reasons.append("Note de crédit (avoir client) émise par l'entreprise : diminue les revenus/créances, jamais confondue avec une vente.")
            elif nature_signal == "refund":
                classification = "refund"
                invoice_type = "refund"
                direction = "revenue_reversal"
                category = "sales_returns"
                confidence = round(issuer_conf * 0.95, 2) if recipient_name else 0.70
                reasons.append("Remboursement client émis par l'entreprise : contre-passation de vente, jamais une nouvelle vente.")
            elif nature_signal == "non_posting":
                classification = "non_posting"
                invoice_type = "other"
                direction = "neutral"
                category = "non_posting"
                confidence = 0.90
                reasons.append("Devis / soumission client non comptabilisable tant qu'aucune facture n'est émise.")
            elif nature_signal == "payment":
                classification = "payment"
                invoice_type = "payment"
                direction = "revenue"
                category = "settlement"
                confidence = 0.86
                reasons.append("Confirmation d'encaissement client.")
            else:
                classification = "customer_invoice"
                invoice_type = "receivable"
                direction = "revenue"
                category = str(payload.get("category") or "sales")
                confidence = round(issuer_conf * 0.97, 2) if recipient_name else 0.74
                reasons.append("Facture émise par l'entreprise à un client tiers : classée en revenu / créance client (receivable).")
        else:
            # Rôle ambigu : vérifier d'abord les règles déterministes du tenant, puis le fallback LLM structuré éventuel
            company_role = "ambiguous"
            counterparty = issuer_name or recipient_name or str(payload.get("party_name") or "Contrepartie à vérifier")
            matched_rule = self._match_tenant_rule(company_id, counterparty, extracted_text)

            if nature_signal == "credit_note":
                classification = "credit_note"
                invoice_type = "credit_note"
                direction = "revenue_reversal" if payload.get("direction_hint") == "revenue" else "expense_reversal"
                category = "sales_returns" if direction == "revenue_reversal" else "expense_credits"
                confidence = 0.55
                reasons.append("Note de crédit détectée mais le rôle exact de l'entreprise (émetteur vs client) est ambigu — vérification requise.")
            elif nature_signal == "refund":
                classification = "refund"
                invoice_type = "refund"
                direction = "revenue_reversal"
                category = "sales_returns"
                confidence = 0.55
                reasons.append("Remboursement détecté avec parties ambiguës — vérification requise.")
            elif nature_signal == "transfer":
                classification = "transfer"
                invoice_type = "transfer"
                direction = "neutral"
                category = "transfer"
                confidence = 0.60
                reasons.append("Transfert détecté — vérification humaine requise.")
            elif nature_signal == "non_posting":
                classification = "non_posting"
                invoice_type = "other"
                direction = "neutral"
                category = "non_posting"
                confidence = 0.75
                reasons.append("Document non comptable détecté.")
            elif matched_rule is not None:
                classification = matched_rule.forced_classification
                invoice_type, direction = self._map_classification_to_type_and_direction(classification)
                category = matched_rule.default_category
                confidence = 0.80
                reasons.append(
                    f"Règle comptable configurée appliquée (motif='{matched_rule.counterparty_pattern}' -> {classification})."
                )
            else:
                llm_guess = self._try_llm_fallback(payload, profile)
                if llm_guess and llm_guess.get("classification") in VALID_CLASSIFICATIONS:
                    classification = str(llm_guess["classification"])
                    invoice_type, direction = self._map_classification_to_type_and_direction(classification)
                    category = str(llm_guess.get("category") or "other")
                    confidence = min(float(llm_guess.get("confidence", 0.55)), 0.65)
                    reasons.append(
                        f"Identité d'entreprise non résolue dans les parties ; hypothèse IA '{classification}' soumise à validation obligatoire."
                    )
                else:
                    classification = "supplier_invoice"
                    invoice_type = "payable"
                    direction = "expense"
                    category = self._infer_expense_category(counterparty, extracted_text)
                    confidence = 0.45
                    reasons.append(
                        "Impossible de confirmer le rôle de l'entreprise parmi l'émetteur et le destinataire ; classé en proposition à vérifier."
                    )

        if not math_validation["math_valid"]:
            confidence = min(confidence, 0.50)
            reasons.append(
                f"Écart arithmétique détecté (sous-total {subtotal} + taxes {tax_amount} vs total {total}) : revue humaine requise."
            )

        now = datetime.now(timezone.utc)
        issue_date = _parse_datetime(payload.get("issue_date") or payload.get("date"), fallback=now)
        due_date = _parse_datetime(
            payload.get("due_date"),
            fallback=issue_date + timedelta(days=30),
        )
        currency = str(payload.get("currency") or profile.default_currency or "CAD").upper()[:10]
        raw_inv_no = str(payload.get("invoice_number") or "").strip()
        invoice_number = raw_inv_no[:100] if raw_inv_no else f"DOC-{uuid4().hex[:8].upper()}"

        # Gouvernance des propositions : TOUTE classification documentaire/IA démarre en `to_verify` (`is_confirmed=False`)
        return ClassificationOutcome(
            classification=classification,
            invoice_type=invoice_type,
            direction=direction,
            company_role=company_role,
            category=category,
            party_name=counterparty[:255],
            issuer_name=issuer_name[:255] if issuer_name else None,
            recipient_name=recipient_name[:255] if recipient_name else None,
            invoice_number=invoice_number,
            issue_date=issue_date,
            due_date=due_date,
            currency=currency,
            subtotal_amount=subtotal,
            tax_amount=tax_amount,
            total_amount=total,
            tax_breakdown=tax_breakdown,
            line_items=normalized_lines,
            confidence_score=round(confidence, 2),
            verification_status="to_verify",
            accounting_status="proposed",
            is_confirmed=False,
            rationale=" ".join(reasons),
            math_validation=math_validation,
        )

    @staticmethod
    def _map_classification_to_type_and_direction(classification: str) -> tuple[str, str]:
        mapping = {
            "supplier_invoice": ("payable", "expense"),
            "receipt": ("payable", "expense"),
            "customer_invoice": ("receivable", "revenue"),
            "credit_note": ("credit_note", "revenue_reversal"),
            "refund": ("refund", "revenue_reversal"),
            "payment": ("payment", "neutral"),
            "transfer": ("transfer", "neutral"),
            "non_posting": ("other", "neutral"),
        }
        return mapping.get(classification, ("payable", "expense"))

    def _match_tenant_rule(
        self,
        company_id: UUID,
        counterparty: str,
        extracted_text: str,
    ) -> AccountingClassificationRule | None:
        rules = list(
            self._session.scalars(
                select(AccountingClassificationRule).where(
                    AccountingClassificationRule.company_id == company_id,
                    AccountingClassificationRule.is_active.is_(True),
                )
            ).all()
        )
        norm_cp = normalize_party_identifier(counterparty)
        lowered_text = extracted_text.lower()
        for rule in rules:
            pat = normalize_party_identifier(rule.counterparty_pattern)
            if not pat:
                continue
            if rule.match_field == "description" and pat in lowered_text:
                return rule
            if pat in norm_cp or (rule.counterparty_pattern.lower() in counterparty.lower()):
                return rule
        return None

    def _try_llm_fallback(
        self,
        payload: Mapping[str, Any],
        profile: CompanyIdentityProfile,
    ) -> dict[str, Any] | None:
        if self._llm_classifier is None:
            return None
        try:
            return self._llm_classifier({
                "company_canonical_name": profile.canonical_name,
                "issuer": payload.get("issuer") or payload.get("vendor"),
                "recipient": payload.get("recipient") or payload.get("customer"),
                "invoice_number": payload.get("invoice_number"),
                "extracted_text_excerpt": str(payload.get("extracted_text") or "")[:1500],
            })
        except Exception:
            return None

    @staticmethod
    def compute_duplicate_fingerprint(
        *,
        company_id: UUID,
        party_name: str,
        invoice_number: str,
        issue_date: datetime,
        total_amount: Decimal,
        currency: str,
    ) -> str:
        norm_party = normalize_party_identifier(party_name)
        norm_inv = re.sub(r"[^a-z0-9]", "", (invoice_number or "").lower())
        date_str = issue_date.strftime("%Y-%m-%d")
        amt_str = str(total_amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP))
        curr = (currency or "CAD").upper().strip()
        canonical = f"{company_id}|{norm_party}|{norm_inv}|{date_str}|{amt_str}|{curr}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def find_duplicate_candidates(
        self,
        company_id: UUID,
        *,
        file_sha256: str | None,
        duplicate_fingerprint: str,
        invoice_number: str,
        party_name: str,
        issue_date: datetime,
        total_amount: Decimal,
        currency: str,
        external_id: str | None = None,
        exclude_invoice_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Recherche déterministe de doublons au sein du même tenant sans suppression automatique."""
        existing_invoices = list(
            self._session.scalars(
                select(AccountingInvoice).where(
                    AccountingInvoice.company_id == company_id,
                    AccountingInvoice.status != "rejected",
                )
            ).all()
        )
        norm_party = normalize_party_identifier(party_name)
        norm_inv = re.sub(r"[^a-z0-9]", "", (invoice_number or "").lower())
        target_day = issue_date.strftime("%Y-%m-%d")
        target_amt = float(total_amount)
        target_curr = currency.upper()

        candidates: list[dict[str, Any]] = []
        for inv in existing_invoices:
            if exclude_invoice_id is not None and inv.id == exclude_invoice_id:
                continue
            match_reasons: list[str] = []
            if file_sha256 and inv.file_sha256 and inv.file_sha256 == file_sha256:
                match_reasons.append("exact_file_sha256")
            if inv.duplicate_fingerprint and inv.duplicate_fingerprint == duplicate_fingerprint:
                match_reasons.append("exact_business_fingerprint")
            if external_id and inv.external_id and inv.external_id == external_id:
                match_reasons.append("same_external_id")

            inv_norm_no = re.sub(r"[^a-z0-9]", "", (inv.invoice_number or "").lower())
            inv_norm_party = normalize_party_identifier(inv.party_name)
            same_amount = abs(float(inv.total_amount) - target_amt) < 0.01 and (inv.currency or "").upper() == target_curr
            same_day = inv.issue_date.strftime("%Y-%m-%d") == target_day if inv.issue_date else False

            if norm_inv and inv_norm_no == norm_inv and norm_party and inv_norm_party == norm_party:
                if "same_invoice_number_and_counterparty" not in match_reasons:
                    match_reasons.append("same_invoice_number_and_counterparty")
            if norm_party and inv_norm_party == norm_party and same_day and same_amount:
                if "same_counterparty_date_and_amount" not in match_reasons:
                    match_reasons.append("same_counterparty_date_and_amount")

            if match_reasons:
                candidates.append({
                    "invoice_id": str(inv.id),
                    "invoice_number": inv.invoice_number,
                    "party_name": inv.party_name,
                    "total_amount": round(inv.total_amount, 2),
                    "currency": inv.currency,
                    "issue_date": inv.issue_date.strftime("%Y-%m-%d") if inv.issue_date else None,
                    "verification_status": inv.verification_status,
                    "is_confirmed": inv.is_confirmed,
                    "match_reasons": match_reasons,
                })
        return candidates

    def import_document_proposal(
        self,
        company_id: UUID,
        payload: Mapping[str, Any],
        *,
        actor_user_id: UUID | None = None,
        document_id: UUID | None = None,
        dataset_id: UUID | None = None,
    ) -> tuple[AccountingInvoice, dict[str, Any]]:
        """Importe et classe un document financier en proposition `to_verify` avec traçabilité complète."""
        merged: dict[str, Any] = dict(payload)
        doc_row: TenantDocument | None = None

        resolved_doc_id = document_id
        if resolved_doc_id is None and merged.get("document_id"):
            resolved_doc_id = UUID(str(merged["document_id"]))

        if resolved_doc_id is not None:
            doc_row = self._session.scalar(
                select(TenantDocument).where(
                    TenantDocument.id == resolved_doc_id,
                    TenantDocument.company_id == company_id,
                )
            )
            if doc_row is None:
                raise LookupError("Document source introuvable pour cette entreprise.")
            if not merged.get("extracted_text") and doc_row.extracted_text:
                merged["extracted_text"] = doc_row.extracted_text
            if not merged.get("file_sha256") and doc_row.sha256:
                merged["file_sha256"] = doc_row.sha256
            if doc_row.analysis_json:
                try:
                    parsed_analysis = json.loads(doc_row.analysis_json)
                    fields = parsed_analysis.get("fields") or {}
                    for k_src, k_dst in (
                        ("invoice_number", "invoice_number"),
                        ("total", "total_amount"),
                        ("date", "issue_date"),
                    ):
                        if fields.get(k_src) and not merged.get(k_dst):
                            merged[k_dst] = fields[k_src]
                except json.JSONDecodeError:
                    pass

        resolved_ds_id = dataset_id
        if resolved_ds_id is None and merged.get("dataset_id"):
            resolved_ds_id = UUID(str(merged["dataset_id"]))
        if resolved_ds_id is not None:
            ds_row = self._session.scalar(
                select(Dataset).where(
                    Dataset.id == resolved_ds_id,
                    Dataset.company_id == company_id,
                )
            )
            if ds_row is None:
                raise LookupError("Jeu de données source introuvable pour cette entreprise.")

        file_sha256 = str(merged.get("file_sha256") or "").strip().lower() or None
        if file_sha256 is None and isinstance(merged.get("raw_content_bytes"), (bytes, bytearray)):
            file_sha256 = hashlib.sha256(bytes(merged["raw_content_bytes"])).hexdigest()

        outcome = self.classify_document_payload(company_id, merged)
        fingerprint = self.compute_duplicate_fingerprint(
            company_id=company_id,
            party_name=outcome.party_name,
            invoice_number=outcome.invoice_number,
            issue_date=outcome.issue_date,
            total_amount=outcome.total_amount,
            currency=outcome.currency,
        )
        external_id = str(merged.get("external_id") or "").strip() or None
        candidates = self.find_duplicate_candidates(
            company_id,
            file_sha256=file_sha256,
            duplicate_fingerprint=fingerprint,
            invoice_number=outcome.invoice_number,
            party_name=outcome.party_name,
            issue_date=outcome.issue_date,
            total_amount=outcome.total_amount,
            currency=outcome.currency,
            external_id=external_id,
        )

        provenance = {
            "source_module": str(merged.get("source_module") or ("ocr" if resolved_doc_id else "dataset" if resolved_ds_id else "manual_upload")),
            "document_id": str(resolved_doc_id) if resolved_doc_id else None,
            "dataset_id": str(resolved_ds_id) if resolved_ds_id else None,
            "filename": doc_row.filename if doc_row else merged.get("filename"),
            "file_sha256": file_sha256,
            "page_refs": merged.get("page_refs") or [],
            "cell_refs": merged.get("cell_refs") or [],
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }

        rationale = outcome.rationale
        if candidates:
            rationale = (
                f"{rationale} Avertissement doublon : {len(candidates)} facture(s) existante(s) correspondent "
                f"aux clés métier ou à l'empreinte du fichier."
            )

        invoice = AccountingInvoice(
            company_id=company_id,
            invoice_number=outcome.invoice_number,
            invoice_type=outcome.invoice_type,
            document_nature=outcome.classification,
            direction=outcome.direction,
            company_role=outcome.company_role,
            party_name=outcome.party_name,
            issuer_name=outcome.issuer_name,
            recipient_name=outcome.recipient_name,
            issue_date=outcome.issue_date,
            due_date=outcome.due_date,
            subtotal_amount=float(outcome.subtotal_amount),
            tax_amount=float(outcome.tax_amount),
            tax_breakdown=outcome.tax_breakdown,
            total_amount=float(outcome.total_amount),
            paid_amount=float(_to_decimal(merged.get("paid_amount"), default=Decimal("0.00")) or Decimal("0.00")),
            currency=outcome.currency,
            status="to_verify",
            is_confirmed=False,
            notes=str(merged.get("notes") or "") or None,
            line_items=outcome.line_items,
            source_module=provenance["source_module"],
            external_id=external_id,
            idempotency_key=str(merged.get("idempotency_key") or "").strip() or None,
            document_id=resolved_doc_id,
            dataset_id=resolved_ds_id,
            file_sha256=file_sha256,
            duplicate_fingerprint=fingerprint,
            duplicate_warning=bool(candidates),
            duplicate_candidates=candidates,
            verification_status="to_verify",
            accounting_status="proposed",
            confidence_score=outcome.confidence_score,
            classification_rationale=rationale,
            revision_history=[
                {
                    "revision_id": str(uuid4()),
                    "action": "classified_proposal_created",
                    "revised_by": str(actor_user_id) if actor_user_id else "system_ai",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": rationale,
                    "previous_values": {},
                    "new_values": {
                        "document_nature": outcome.classification,
                        "invoice_type": outcome.invoice_type,
                        "direction": outcome.direction,
                        "company_role": outcome.company_role,
                        "category": outcome.category,
                        "total_amount": float(outcome.total_amount),
                        "verification_status": "to_verify",
                    },
                }
            ],
            extra_data={
                "category": outcome.category,
                "provenance": provenance,
                "math_validation": outcome.math_validation,
            },
        )
        self._session.add(invoice)
        self._session.flush()

        self._session.add(
            AuditLogEntry(
                actor_user_id=actor_user_id,
                company_id=company_id,
                action="accounting.document.classified_proposal",
                target_type="AccountingInvoice",
                target_id=str(invoice.id),
                safe_metadata={
                    "document_nature": invoice.document_nature,
                    "invoice_type": invoice.invoice_type,
                    "company_role": invoice.company_role,
                    "verification_status": invoice.verification_status,
                    "confidence_score": invoice.confidence_score,
                    "duplicate_warning": invoice.duplicate_warning,
                    "duplicate_candidates_count": len(candidates),
                },
            )
        )
        self._session.commit()
        self._session.refresh(invoice)

        summary = {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "classification": invoice.document_nature,
            "invoice_type": invoice.invoice_type,
            "direction": invoice.direction,
            "company_role": invoice.company_role,
            "party_name": invoice.party_name,
            "issuer_name": invoice.issuer_name,
            "recipient_name": invoice.recipient_name,
            "subtotal_amount": invoice.subtotal_amount,
            "tax_amount": invoice.tax_amount,
            "tax_breakdown": invoice.tax_breakdown,
            "total_amount": invoice.total_amount,
            "currency": invoice.currency,
            "verification_status": invoice.verification_status,
            "accounting_status": invoice.accounting_status,
            "is_confirmed": invoice.is_confirmed,
            "confidence_score": invoice.confidence_score,
            "classification_rationale": invoice.classification_rationale,
            "duplicate_warning": invoice.duplicate_warning,
            "duplicate_candidates": invoice.duplicate_candidates,
            "provenance": provenance,
            "math_validation": outcome.math_validation,
        }
        return invoice, summary

    def review_invoice_proposal(
        self,
        company_id: UUID,
        invoice_id: UUID,
        *,
        actor_user_id: UUID,
        action: str,
        reason: str | None = None,
        overrides: Mapping[str, Any] | None = None,
        confirm_duplicate: bool = False,
    ) -> dict[str, Any]:
        """Corrige manuellement, approuve ou rejette une proposition avec piste d'audit complète."""
        valid_actions = {"approve", "correct_and_approve", "correct", "reject"}
        if action not in valid_actions:
            raise AccountingClassificationError(f"Action de révision invalide: '{action}'.")

        invoice = self._session.scalar(
            select(AccountingInvoice).where(
                AccountingInvoice.id == invoice_id,
                AccountingInvoice.company_id == company_id,
            )
        )
        if invoice is None:
            raise LookupError("Facture introuvable pour cette entreprise.")

        if action in {"approve", "correct_and_approve"} and invoice.duplicate_warning and not confirm_duplicate:
            raise DuplicateConfirmationRequiredError(
                "Cette facture présente un avertissement de doublon potentiel. "
                "Veuillez confirmer explicitement (confirm_duplicate=True) après vérification."
            )

        overrides_dict = dict(overrides or {})
        tracked_fields = (
            "document_nature",
            "invoice_type",
            "direction",
            "party_name",
            "subtotal_amount",
            "tax_amount",
            "total_amount",
            "currency",
            "verification_status",
            "accounting_status",
            "is_confirmed",
            "status",
        )
        previous_values: dict[str, Any] = {f: getattr(invoice, f) for f in tracked_fields}
        extra = dict(invoice.extra_data or {})
        previous_values["category"] = extra.get("category")

        if "classification" in overrides_dict and "document_nature" not in overrides_dict:
            overrides_dict["document_nature"] = overrides_dict["classification"]

        if "document_nature" in overrides_dict and overrides_dict["document_nature"] is not None:
            new_nature = str(overrides_dict["document_nature"])
            if new_nature not in VALID_CLASSIFICATIONS:
                raise AccountingClassificationError(f"Classification invalide: {new_nature}")
            invoice.document_nature = new_nature
            default_inv_type, default_dir = self._map_classification_to_type_and_direction(new_nature)
            if "invoice_type" not in overrides_dict:
                invoice.invoice_type = default_inv_type
            if "direction" not in overrides_dict:
                invoice.direction = default_dir

        if "invoice_type" in overrides_dict and overrides_dict["invoice_type"] is not None:
            invoice.invoice_type = str(overrides_dict["invoice_type"])
        if "direction" in overrides_dict and overrides_dict["direction"] is not None:
            invoice.direction = str(overrides_dict["direction"])
        if "party_name" in overrides_dict and overrides_dict["party_name"] is not None:
            invoice.party_name = str(overrides_dict["party_name"]).strip()[:255]
        if "subtotal_amount" in overrides_dict and overrides_dict["subtotal_amount"] is not None:
            dec_sub = _to_decimal(overrides_dict["subtotal_amount"], default=None)
            if dec_sub is not None:
                invoice.subtotal_amount = float(dec_sub)
        if "tax_amount" in overrides_dict and overrides_dict["tax_amount"] is not None:
            dec_tax = _to_decimal(overrides_dict["tax_amount"], default=None)
            if dec_tax is not None:
                invoice.tax_amount = float(dec_tax)
        if "total_amount" in overrides_dict and overrides_dict["total_amount"] is not None:
            dec_tot = _to_decimal(overrides_dict["total_amount"], default=None)
            if dec_tot is None or dec_tot < Decimal("0.00"):
                raise AccountingClassificationError("Montant total corrigé invalide.")
            invoice.total_amount = float(dec_tot)
        if "currency" in overrides_dict and overrides_dict["currency"] is not None:
            invoice.currency = str(overrides_dict["currency"]).upper()[:10]
        if "notes" in overrides_dict and overrides_dict["notes"] is not None:
            invoice.notes = str(overrides_dict["notes"])
        if "category" in overrides_dict and overrides_dict["category"] is not None:
            extra["category"] = str(overrides_dict["category"])

        linked_tx: AccountingTransaction | None = None
        if action in {"approve", "correct_and_approve"}:
            invoice.verification_status = "approved"
            if invoice.document_nature == "non_posting":
                invoice.accounting_status = "non_posting"
                invoice.is_confirmed = False
                invoice.status = "void"
            else:
                invoice.accounting_status = "posted"
                invoice.is_confirmed = True
                if invoice.invoice_type in {"receivable", "payable"}:
                    if invoice.paid_amount >= invoice.total_amount and invoice.total_amount > 0:
                        invoice.status = "paid"
                    elif invoice.paid_amount > 0:
                        invoice.status = "partial"
                    else:
                        invoice.status = "unpaid"
                else:
                    invoice.status = "posted"
                linked_tx = self._upsert_ledger_transaction_for_approved_invoice(
                    invoice,
                    category=str(extra.get("category") or ("sales" if invoice.direction == "revenue" else "other")),
                    actor_user_id=actor_user_id,
                )
        elif action == "reject":
            invoice.verification_status = "rejected"
            invoice.accounting_status = "rejected"
            invoice.is_confirmed = False
            invoice.status = "rejected"
            existing_tx = self._session.scalar(
                select(AccountingTransaction).where(
                    AccountingTransaction.company_id == company_id,
                    AccountingTransaction.invoice_id == invoice.id,
                )
            )
            if existing_tx is not None:
                existing_tx.is_confirmed = False
                existing_tx.verification_status = "rejected"
                existing_tx.accounting_status = "rejected"
                existing_tx.status = "rejected"
        elif action == "correct":
            invoice.verification_status = "to_verify"
            invoice.accounting_status = "proposed"
            invoice.is_confirmed = False
            invoice.status = "to_verify"

        invoice.extra_data = extra
        new_values: dict[str, Any] = {f: getattr(invoice, f) for f in tracked_fields}
        new_values["category"] = extra.get("category")

        revision_entry = {
            "revision_id": str(uuid4()),
            "action": action,
            "revised_by": str(actor_user_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason or f"Action manuelle: {action}",
            "confirm_duplicate": confirm_duplicate,
            "previous_values": previous_values,
            "new_values": new_values,
        }
        history = list(invoice.revision_history or [])
        history.append(revision_entry)
        invoice.revision_history = history

        audit_entry = AuditLogEntry(
            actor_user_id=actor_user_id,
            company_id=company_id,
            action=f"accounting.invoice.{action}",
            target_type="AccountingInvoice",
            target_id=str(invoice.id),
            safe_metadata={
                "action": action,
                "reason": reason or "",
                "confirm_duplicate": confirm_duplicate,
                "previous_classification": previous_values.get("document_nature"),
                "new_classification": new_values.get("document_nature"),
                "previous_invoice_type": previous_values.get("invoice_type"),
                "new_invoice_type": new_values.get("invoice_type"),
                "verification_status": invoice.verification_status,
                "accounting_status": invoice.accounting_status,
                "linked_transaction_id": str(linked_tx.id) if linked_tx else None,
            },
        )
        self._session.add(audit_entry)
        self._session.commit()
        self._session.refresh(invoice)

        return {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "classification": invoice.document_nature,
            "invoice_type": invoice.invoice_type,
            "direction": invoice.direction,
            "category": extra.get("category"),
            "party_name": invoice.party_name,
            "subtotal_amount": invoice.subtotal_amount,
            "tax_amount": invoice.tax_amount,
            "total_amount": invoice.total_amount,
            "currency": invoice.currency,
            "status": invoice.status,
            "verification_status": invoice.verification_status,
            "accounting_status": invoice.accounting_status,
            "is_confirmed": invoice.is_confirmed,
            "linked_transaction_id": str(linked_tx.id) if linked_tx else None,
            "latest_revision": revision_entry,
            "revision_count": len(invoice.revision_history or []),
        }

    def _upsert_ledger_transaction_for_approved_invoice(
        self,
        invoice: AccountingInvoice,
        *,
        category: str,
        actor_user_id: UUID,
    ) -> AccountingTransaction:
        idem_key = f"invoice:{invoice.company_id}:{invoice.id}:ledger"
        tx = self._session.scalar(
            select(AccountingTransaction).where(
                AccountingTransaction.company_id == invoice.company_id,
                or_(
                    AccountingTransaction.idempotency_key == idem_key,
                    AccountingTransaction.invoice_id == invoice.id,
                ),
            )
        )

        nature = invoice.document_nature
        if nature in {"supplier_invoice", "receipt"}:
            tx_type = "expense"
            entry_kind = "journal_entry"
            tx_cat = category if category != "sales" else "other"
        elif nature == "customer_invoice":
            tx_type = "revenue"
            entry_kind = "journal_entry"
            tx_cat = category or "sales"
        elif nature == "credit_note":
            tx_type = "credit_note"
            entry_kind = "credit_note"
            tx_cat = "sales_returns" if invoice.direction == "revenue_reversal" else "expense_credits"
        elif nature == "refund":
            tx_type = "refund"
            entry_kind = "refund"
            tx_cat = "sales_returns" if invoice.direction != "expense_reversal" else "expense_refunds"
        elif nature == "transfer":
            tx_type = "transfer"
            entry_kind = "transfer"
            tx_cat = "transfer"
        else:
            tx_type = "payment"
            entry_kind = "payment_collected" if invoice.direction == "revenue" else "payment_disbursed"
            tx_cat = "settlement"

        net_amount = (
            invoice.subtotal_amount
            if invoice.subtotal_amount is not None and invoice.subtotal_amount > 0
            else max(0.0, round(invoice.total_amount - invoice.tax_amount, 2))
        )
        if tx_type == "payment":
            posting_amount = round(invoice.total_amount, 2)
        else:
            posting_amount = round(net_amount, 2) if net_amount > 0 else round(invoice.total_amount, 2)

        desc = f"{nature.replace('_', ' ').title()} {invoice.invoice_number} — {invoice.party_name}"[:255]
        if tx is None:
            tx = AccountingTransaction(
                company_id=invoice.company_id,
                transaction_date=invoice.issue_date,
                transaction_type=tx_type,
                entry_kind=entry_kind,
                category=tx_cat,
                description=desc,
                amount=posting_amount,
                subtotal_amount=invoice.subtotal_amount,
                currency=invoice.currency,
                status="confirmed",
                is_confirmed=True,
                tax_amount=invoice.tax_amount,
                reference_id=invoice.invoice_number,
                source_module=invoice.source_module,
                external_id=invoice.external_id,
                idempotency_key=idem_key,
                document_id=invoice.document_id,
                dataset_id=invoice.dataset_id,
                invoice_id=invoice.id,
                verification_status="approved",
                accounting_status="posted",
                confidence_score=1.0,
                classification_rationale=f"Posté suite à l'approbation humaine par {actor_user_id}",
                duplicate_fingerprint=invoice.duplicate_fingerprint,
                extra_data={
                    "gross_total_amount": invoice.total_amount,
                    "direction": invoice.direction,
                    "tax_breakdown": invoice.tax_breakdown,
                },
            )
            self._session.add(tx)
        else:
            tx.transaction_date = invoice.issue_date
            tx.transaction_type = tx_type
            tx.entry_kind = entry_kind
            tx.category = tx_cat
            tx.description = desc
            tx.amount = posting_amount
            tx.subtotal_amount = invoice.subtotal_amount
            tx.currency = invoice.currency
            tx.tax_amount = invoice.tax_amount
            tx.status = "confirmed"
            tx.is_confirmed = True
            tx.verification_status = "approved"
            tx.accounting_status = "posted"
            tx.extra_data = {
                **(tx.extra_data or {}),
                "gross_total_amount": invoice.total_amount,
                "direction": invoice.direction,
                "tax_breakdown": invoice.tax_breakdown,
            }
        self._session.flush()
        return tx
