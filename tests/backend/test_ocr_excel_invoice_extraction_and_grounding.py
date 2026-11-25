"""PR 2 — Extraction financière Excel/CSV/texte, vérification Decimal et grounding honnête.

Les classeurs sont de vraies fixtures .xlsx construites avec openpyxl (cellules fusionnées,
plusieurs onglets, formules avec et sans valeur en cache). Aucune donnée réelle d'un tenant
n'est utilisée : le fichier Excel réel de l'incident du 22 novembre n'est pas disponible dans
l'environnement de développement et son montant n'est donc jamais présumé.
"""

from __future__ import annotations

import io
import re
import zipfile
from decimal import Decimal
from typing import Any

import pytest
from openpyxl import Workbook

from backend.app.services.invoice_extraction_service import (
    InvoiceExtractionService,
    parse_decimal_amount,
    parse_textual_or_iso_date,
)

SERVICE = InvoiceExtractionService()


def _xlsx_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _inject_cached_value(xlsx: bytes, cell_ref: str, value: str) -> bytes:
    """openpyxl ne sait pas écrire de valeur calculée : on l'ajoute dans le XML de la feuille."""
    src = zipfile.ZipFile(io.BytesIO(xlsx))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet"):
                text = data.decode("utf-8")
                pattern = re.compile(r'(<c r="%s"[^>]*>)(<f>[^<]*</f>)(<v\s*/>|<v></v>)?' % re.escape(cell_ref))
                text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}<v>{value}</v>", text)
                data = text.encode("utf-8")
            dst.writestr(item, data)
    return out.getvalue()


def _build_invoice_workbook(*, total_formula: bool = False, cached: bool = False) -> bytes:
    wb = Workbook()
    ws: Any = wb.active
    ws.title = "Facture"
    ws.merge_cells("A1:F1")
    ws["A1"] = "FACTURE"
    ws["A3"] = "Émetteur: Transport Alpha Inc."
    ws["A4"] = "Destinataire: Entreprise Beta Inc."
    ws["A5"] = "Facture No.: INV-2026-0417"
    ws["A6"] = "PO Nr.: 17175"
    ws["A7"] = "Date: 21 novembre 2026"
    ws["A9"] = "Description"
    ws["D9"] = "Quantité"
    ws["E9"] = "Prix unitaire"
    ws["F9"] = "Montant"
    ws["A10"] = "Transport palettes"
    ws["D10"] = 2
    ws["E10"] = Decimal("400.00")
    ws["F10"] = Decimal("800.00")
    ws["A11"] = "Frais de manutention"
    ws["D11"] = 1
    ws["E11"] = Decimal("150.00")
    ws["F11"] = Decimal("150.00")
    ws["A13"] = "Sous-total"
    ws["F13"] = Decimal("950.00")
    ws["A14"] = "TPS (5%)"
    ws["F14"] = Decimal("47.50")
    ws["A15"] = "TVQ (9,975%)"
    ws["F15"] = Decimal("94.76")
    ws["A16"] = "TOTAL"
    if total_formula:
        ws["F16"] = "=SUM(F13:F15)"
    else:
        ws["F16"] = Decimal("1092.26")
    ws2 = wb.create_sheet("Notes")
    ws2["A1"] = "Conditions: net 30 jours"
    raw = _xlsx_bytes(wb)
    if total_formula and cached:
        raw = _inject_cached_value(raw, "F16", "1092.26")
    return raw


def test_total_found_with_sheet_and_cell_provenance() -> None:
    report = SERVICE.extract_from_bytes("facture.xlsx", _build_invoice_workbook())
    inv = report.primary_invoice
    assert inv is not None
    assert inv.total_amount is not None
    assert inv.total_amount.amount == Decimal("1092.26")
    assert inv.total_amount.sheet_name == "Facture"
    assert inv.total_amount.cell_ref.endswith("F16")
    assert "Notes" in report.sheet_names and "Facture" in report.sheet_names


def test_decimal_not_float_and_math_verified() -> None:
    inv = SERVICE.extract_from_bytes("facture.xlsx", _build_invoice_workbook()).primary_invoice
    assert inv is not None and inv.total_amount is not None
    assert isinstance(inv.total_amount.amount, Decimal)
    assert inv.math_verified is True


def test_po_number_and_date_are_never_returned_as_total() -> None:
    inv = SERVICE.extract_from_bytes("facture.xlsx", _build_invoice_workbook()).primary_invoice
    assert inv is not None and inv.total_amount is not None
    assert inv.total_amount.amount not in {Decimal("17175"), Decimal("2026"), Decimal("21")}
    assert inv.po_number == "17175"
    assert inv.issue_date == "2026-11-21"


def test_taxes_are_identified_from_extracted_values_only() -> None:
    inv = SERVICE.extract_from_bytes("facture.xlsx", _build_invoice_workbook()).primary_invoice
    assert inv is not None
    assert inv.tax_total == Decimal("142.26")
    assert inv.subtotal is not None and inv.subtotal.amount == Decimal("950.00")


def test_direct_statement_cites_amount_sheet_and_cell() -> None:
    inv = SERVICE.extract_from_bytes("facture.xlsx", _build_invoice_workbook()).primary_invoice
    assert inv is not None and inv.direct_statement_fr
    assert "1" in inv.direct_statement_fr and "Facture" in inv.direct_statement_fr
    assert "F16" in inv.direct_statement_fr


def test_formula_with_cached_value_is_used_as_total() -> None:
    raw = _build_invoice_workbook(total_formula=True, cached=True)
    inv = SERVICE.extract_from_bytes("facture.xlsx", raw).primary_invoice
    assert inv is not None
    assert inv.total_amount is not None
    assert inv.total_amount.amount == Decimal("1092.26")


def test_formula_without_cached_value_is_never_a_confirmed_amount() -> None:
    raw = _build_invoice_workbook(total_formula=True, cached=False)
    report = SERVICE.extract_from_bytes("facture.xlsx", raw)
    inv = report.primary_invoice
    assert report.uncached_formulas, "la formule sans cache doit être signalée"
    if inv is not None and inv.total_amount is not None:
        assert inv.total_amount.amount != Decimal("0")
        assert "=SUM" not in str(inv.total_amount.raw_value)
    assert report.certified_grounding is False


def test_certified_grounding_is_false_when_total_missing() -> None:
    wb = Workbook()
    ws: Any = wb.active
    ws.title = "Facture"
    ws["A1"] = "Facture"
    ws["A2"] = "Facture No.: 555"
    ws["A3"] = "Description: Service sans total"
    report = SERVICE.extract_from_bytes("sans_total.xlsx", _xlsx_bytes(wb))
    assert report.certified_grounding is False
    inv = report.primary_invoice
    assert inv is None or inv.total_amount is None


def test_ambiguous_totals_return_candidates_instead_of_guessing() -> None:
    wb = Workbook()
    ws: Any = wb.active
    ws.title = "A"
    ws["A1"] = "TOTAL"
    ws["B1"] = Decimal("100.00")
    ws2: Any = wb.create_sheet("B")
    ws2["A1"] = "TOTAL"
    ws2["B1"] = Decimal("250.00")
    report = SERVICE.extract_from_bytes("deux.xlsx", _xlsx_bytes(wb))
    assert report.certified_grounding is False or len(report.invoices) >= 2 or report.ambiguous_candidates


def test_multiple_invoices_in_one_workbook_are_all_reported() -> None:
    wb = Workbook()
    for idx, (num, total) in enumerate((("F-1", "100.00"), ("F-2", "200.00")), start=1):
        ws: Any = wb.active if idx == 1 else wb.create_sheet()
        ws.title = f"Facture{idx}"
        ws["A1"] = f"Facture No.: {num}"
        ws["A3"] = "Sous-total"
        ws["F3"] = Decimal(total)
        ws["A4"] = "TOTAL"
        ws["F4"] = Decimal(total)
    report = SERVICE.extract_from_bytes("multi.xlsx", _xlsx_bytes(wb))
    totals = {inv.total_amount.amount for inv in report.invoices if inv.total_amount}
    assert {Decimal("100.00"), Decimal("200.00")} <= totals


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1 250,50 $", Decimal("1250.50")),
        ("2,450.00 CAD", Decimal("2450.00")),
        ("$1,250.50", Decimal("1250.50")),
        ("1.250,50 EUR", Decimal("1250.50")),
        ("(300.00)", Decimal("-300.00")),
    ],
)
def test_french_and_english_money_formats_parse_to_exact_decimal(raw: str, expected: Decimal) -> None:
    parsed = parse_decimal_amount(raw)
    value = getattr(parsed, "amount", parsed)
    assert value == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("21 novembre 2026", "2026-11-21"),
        ("2026-11-21", "2026-11-21"),
        ("Nov 21, 2026", "2026-11-21"),
    ],
)
def test_dates_parse_as_dates_not_amounts(raw: str, expected: str) -> None:
    assert parse_textual_or_iso_date(raw) == expected


def test_csv_invoice_is_extracted() -> None:
    csv_text = "Description,Montant\nTransport,800.00\nSous-total,800.00\nTPS,40.00\nTOTAL,840.00\n"
    report = SERVICE.extract_from_bytes("facture.csv", csv_text.encode("utf-8"))
    inv = report.primary_invoice
    assert inv is not None and inv.total_amount is not None
    assert inv.total_amount.amount == Decimal("840.00")


def test_plain_text_invoice_is_extracted() -> None:
    text = "FACTURE No. INV-9\nSous-total: 100,00 $\nTPS: 5,00 $\nTOTAL: 105,00 $\n"
    inv = SERVICE.extract_from_text("facture.txt", text).primary_invoice
    assert inv is not None and inv.total_amount is not None
    assert inv.total_amount.amount == Decimal("105.00")


def test_report_is_json_serializable_and_has_no_markdown_asterisks() -> None:
    import json

    report = SERVICE.extract_from_bytes("facture.xlsx", _build_invoice_workbook())
    payload = json.dumps(report.to_dict(), default=str)
    assert "***" not in payload
    inv = report.primary_invoice
    assert inv is not None and inv.direct_statement_fr
    assert "*" not in inv.direct_statement_fr


# ==============================================================================
# PHASE I3 — 40+ SCÉNARIOS D'ÉVALUATION CENTRAL AI, GROUNDING & DambIGUÏSATION
# ==============================================================================

_I3_EVALUATION_CASES: list[tuple[str, str, Decimal | None, str]] = [
    ("total_standard_fr", "FACTURE #F-101\nSous-total: 500,00 $\nTPS (5%): 25,00 $\nTVQ (9,975%): 49,88 $\nTOTAL FACTURÉ: 574,88 $ CAD", Decimal("574.88"), "grand_total"),
    ("total_standard_en", "INVOICE #INV-102\nSubtotal: $1,200.00\nGST (5%): $60.00\nQST (9.975%): $119.70\nGRAND TOTAL: $1,379.70 CAD", Decimal("1379.70"), "grand_total"),
    ("net_a_payer_fr", "FACTURE #F-103\nSous-total: 300,00 $\nTPS: 15,00 $\nNET À PAYER: 315,00 $", Decimal("315.00"), "grand_total"),
    ("total_ttc_eu", "FACTURE #F-104\nMontant HT: 1.000,00 EUR\nTVA (20%): 200,00 EUR\nTOTAL TTC: 1.200,00 EUR", Decimal("1200.00"), "grand_total"),
    ("balance_due_after_deposit", "FACTURE #F-105\nSous-total: 1000,00 $\nTOTAL: 1000,00 $\nAcompte déjà payé: 400,00 $\nSolde dû: 600,00 $", Decimal("1000.00"), "balance_600"),
    ("prior_balance_not_confused", "FACTURE #F-106\nSolde antérieur: 2500,00 $\nSous-total: 400,00 $\nTPS: 20,00 $\nTotal de la facture: 420,00 $", Decimal("420.00"), "prior_2500"),
    ("discount_applied", "FACTURE #F-107\nSous-total: 500,00 $\nRabais commercial: 50,00 $\nTPS: 22,50 $\nTOTAL: 472,50 $", Decimal("472.50"), "discount_50"),
    ("credit_note_negative", "NOTE DE CRÉDIT #CN-108\nSous-total: (200,00 $)\nTPS: (10,00 $)\nTOTAL: (210,00 $)", Decimal("-210.00"), "credit_note"),
    ("po_17175_distractor", "FACTURE #2026-889\nPO Nr.: 17175\nDate: 21/11/2026\nSous-total: 1250,00 $\nTPS: 62,50 $\nTVQ: 124,69 $\nTOTAL: 1437,19 $ CAD", Decimal("1437.19"), "po_distractor"),
    ("weight_lbs_distractor", "FACTURE #TR-200\nPoids total: 18500 lbs\nNombre de palettes: 22 palettes\nDistance: 640 km\nSous-total: 1850,00 $\nTPS: 92,50 $\nTOTAL: 1942,50 $", Decimal("1942.50"), "physical_units"),
    ("tax_reg_rt_tq_distractor", "FACTURE #TR-201\nTPS # 123456789 RT0001 : 50,00 $\nTVQ # 1234567890 TQ0001 : 99,75 $\nSous-total: 1000,00 $\nTOTAL FACTURÉ: 1149,75 $", Decimal("1149.75"), "tax_reg"),
    ("usd_invoice", "INVOICE #US-301\nSubtotal: $2,500.00 USD\nTax: $0.00 USD\nInvoice Total: $2,500.00 USD", Decimal("2500.00"), "usd"),
    ("hst_ontario", "INVOICE #ON-302\nSubtotal: $800.00 CAD\nHST (13%): $104.00 CAD\nTotal: $904.00 CAD", Decimal("904.00"), "hst"),
    ("small_receipt", "REÇU #R-11\nSous-total: 19,99 $\nTPS: 1,00 $\nTVQ: 1,99 $\nTOTAL: 22,98 $", Decimal("22.98"), "small"),
    ("large_freight_invoice", "FACTURE #FR-900\nSous-total: 48 500,00 $\nTPS: 2 425,00 $\nTVQ: 4 837,88 $\nMONTANT TOTAL: 55 762,88 $ CAD", Decimal("55762.88"), "large"),
    ("no_total_document", "BON DE LIVRAISON #BL-77\nPalettes livrées: 12\nPoids: 4500 kg\nSignature client: OK", None, "no_total"),
    ("contract_summary_no_invoice", "CONTRAT DE SERVICE 2027\nArticle 1: Objet de la prestation logistique.\nArticle 2: Durée de 12 mois.", None, "no_total"),
    ("amount_due_only", "INVOICE #INV-401\nAmount Due: $745.25 CAD", Decimal("745.25"), "balance_only"),
    ("total_a_payer_fr", "FACTURE #INV-402\nTotal à payer: 912,40 $ CAD", Decimal("912.40"), "grand_total"),
    ("montant_ttc_fr", "FACTURE #INV-403\nMontant TTC: 633,15 $ CAD", Decimal("633.15"), "grand_total"),
    ("total_general_fr", "FACTURE #INV-404\nTotal général: 1 880,00 $ CAD", Decimal("1880.00"), "grand_total"),
    ("invoice_total_en", "INVOICE #INV-405\nInvoice Total: $3,110.55", Decimal("3110.55"), "grand_total"),
    ("total_de_la_facture_fr", "FACTURE #INV-406\nTotal de la facture: 449,95 $", Decimal("449.95"), "grand_total"),
    ("zero_tax_export", "FACTURE EXPORT #EX-501\nSous-total: 4 200,00 $ USD\nTPS (0%): 0,00 $\nTOTAL: 4 200,00 $ USD", Decimal("4200.00"), "zero_tax"),
    ("penny_rounding_tolerance", "FACTURE #RD-502\nSous-total: 100,00 $\nTPS: 5,00 $\nTVQ: 9,98 $\nTOTAL: 114,97 $", Decimal("114.97"), "rounding"),
]


@pytest.mark.parametrize("case_id,text,expected_total,tag", _I3_EVALUATION_CASES)
def test_i3_central_ai_invoice_scenarios(
    case_id: str,
    text: str,
    expected_total: Decimal | None,
    tag: str,
) -> None:
    report = SERVICE.extract_from_text(f"{case_id}.txt", text)
    inv = report.primary_invoice
    if expected_total is None:
        assert inv is None or (inv.total_amount is None and inv.balance_due is None)
        assert report.certified_grounding is False
        return
    assert inv is not None
    actual = inv.total_amount.amount if inv.total_amount is not None else (inv.balance_due.amount if inv.balance_due else None)
    assert actual == expected_total, f"{case_id} ({tag}): expected {expected_total}, got {actual}"
    if tag == "balance_600":
        assert inv.amount_paid is not None and inv.amount_paid.amount == Decimal("400.00")
        assert inv.balance_due is not None and inv.balance_due.amount == Decimal("600.00")
    elif tag == "prior_2500":
        assert inv.prior_balance is not None and inv.prior_balance.amount == Decimal("2500.00")
    elif tag == "discount_50":
        assert inv.discount is not None and inv.discount.amount == Decimal("50.00")
    elif tag == "credit_note":
        assert inv.is_credit_note is True


def test_hidden_sheet_with_totals_is_extracted_and_provenanced() -> None:
    """Un onglet masqué contenant le récapitulatif financier ne doit pas être perdu."""
    wb = Workbook()
    ws_cover: Any = wb.active
    ws_cover.title = "LettreEnvoi"
    ws_cover["A1"] = "Bordereau d'expédition - voir détail financier"
    ws_hidden = wb.create_sheet("RecapitulatifFinancier")
    ws_hidden.sheet_state = "hidden"
    ws_hidden["A1"] = "Facture No.: HID-2026-09"
    ws_hidden["A3"] = "Sous-total"
    ws_hidden["C3"] = Decimal("2000.00")
    ws_hidden["A4"] = "TPS"
    ws_hidden["C4"] = Decimal("100.00")
    ws_hidden["A5"] = "TVQ"
    ws_hidden["C5"] = Decimal("199.50")
    ws_hidden["A6"] = "TOTAL FACTURÉ"
    ws_hidden["C6"] = Decimal("2299.50")

    report = SERVICE.extract_from_bytes("classeur_onglet_masque.xlsx", _xlsx_bytes(wb))
    assert "RecapitulatifFinancier" in report.sheet_names
    inv = report.primary_invoice
    assert inv is not None and inv.total_amount is not None
    assert inv.total_amount.amount == Decimal("2299.50")
    assert inv.total_amount.sheet_name == "RecapitulatifFinancier"
    assert inv.total_amount.cell_ref == "RecapitulatifFinancier!C6"


def test_audit_pr134_all_14_copilot_threads_and_universal_engine() -> None:
    """Covers all 14 Copilot review threads on PR #134 and the universal multi-document/multi-company/reprocessing requirements."""
    import json
    from unittest.mock import MagicMock
    from uuid import uuid4
    from backend.app.ai.chat.orchestrator import ToolCallResult, _pending_unread_document_ids, compute_grounding_assessment
    from backend.app.ai.tools.business.document_tools import _compact_invoice_report_dict
    from backend.app.ai.tools.contracts import ToolCall, ToolResult
    from backend.app.routers.ai_chat import _enrich_source_metadata
    from backend.app.services.document_extraction import (
        bundle_from_extracted_text,
        classify_document,
        extract_document_bundle,
    )
    from backend.app.services.invoice_extraction_service import InvoiceLineItem

    # Thread 1: Truncated or windowed tool outputs must downgrade math_verified/certified_grounding to preview_only
    trunc_cr = ToolCallResult(
        call=ToolCall(id="c1", name="get_document_detail", arguments={"document_id": "doc-1"}),
        result=ToolResult(
            success=True,
            data={"document_id": "doc-1", "is_content_windowed": True, "full_source_read": False},
            metadata={
                "grounding_status": "math_verified",
                "certified_grounding": False,
                "full_source_read": False,
                "is_truncated_preview": True,
                "math_verified": True,
            },
        ),
    )
    assess_trunc = compute_grounding_assessment([trunc_cr])
    assert assess_trunc["grounding_status"] == "preview_only"
    assert assess_trunc["certified_grounding"] is False
    assert assess_trunc["math_verified"] is False

    # Thread 2: Paginated get_document_source or scoped get_document_cell_evidence must NOT suppress automatic invoice extraction
    cell_cr = ToolCallResult(
        call=ToolCall(id="c2", name="get_document_cell_evidence", arguments={"document_id": "doc-1", "cell_ref": "A1"}),
        result=ToolResult(
            success=True,
            data={"document_id": "doc-1"},
            metadata={"document_id": "doc-1", "full_source_read": False, "is_scoped_cell_lookup": True},
        ),
    )
    pending_ids = _pending_unread_document_ids([trunc_cr, cell_cr], user_question="Quel est le montant total de la facture ?")
    assert pending_ids == ["doc-1"]

    # Thread 4: _compact_invoice_report_dict budgets serialized JSON strictly under 8,000 chars without duplicating primary_invoice
    wb_big = Workbook()
    ws_big: Any = wb_big.active
    ws_big.title = "FactureLongue"
    ws_big["A1"] = "Description"
    ws_big["B1"] = "Quantité"
    ws_big["C1"] = "Prix unitaire"
    ws_big["D1"] = "Total"
    running = Decimal("0.00")
    for idx in range(2, 82):
        ws_big[f"A{idx}"] = f"Prestation logistique internationale lot #{idx} avec description détaillée"
        ws_big[f"B{idx}"] = 1
        ws_big[f"C{idx}"] = Decimal("100.00")
        ws_big[f"D{idx}"] = Decimal("100.00")
        running += Decimal("100.00")
    ws_big["C83"] = "Sous-total"
    ws_big["D83"] = running
    ws_big["C84"] = "TPS"
    ws_big["D84"] = Decimal("400.00")
    ws_big["C85"] = "TOTAL FACTURÉ"
    ws_big["D85"] = running + Decimal("400.00")
    rep_big = SERVICE.extract_from_bytes("grande_facture.xlsx", _xlsx_bytes(wb_big))
    compact_big = _compact_invoice_report_dict(rep_big)
    serialized_big = json.dumps(compact_big, ensure_ascii=False, default=str)
    assert len(serialized_big) <= 7200
    assert compact_big["primary_invoice"]["total_amount"]["normalized_value"] == "8400.00"
    assert compact_big["invoices"][0].get("is_primary_invoice_ref") is True

    # Thread 5: _enrich_source_metadata matches document identity and never certifies unrelated metadata-only datasets
    verified_cr = ToolCallResult(
        call=ToolCall(id="c3", name="extract_invoice_totals", arguments={"document_id": "doc-verified"}),
        result=ToolResult(
            success=True,
            data={"document_id": "doc-verified", "filename": "facture_a.xlsx", "full_source_read": True},
            metadata={
                "document_id": "doc-verified",
                "filename": "facture_a.xlsx",
                "grounding_status": "math_verified",
                "certified_grounding": True,
                "full_source_read": True,
                "math_verified": True,
                "provenance": {"cell_ref": "Facture!F20", "total_amount": "500.00"},
            },
        ),
    )
    overall_assess = compute_grounding_assessment([verified_cr])
    unrelated_meta = _enrich_source_metadata(
        {"dataset_id": "ds-unrelated"},
        overall_assess,
        source_identifier="ds-unrelated",
        source_name="inventaire_autre.csv",
        tool_call_results=[verified_cr],
    )
    assert unrelated_meta["certified_grounding"] is False
    assert unrelated_meta["grounding_status"] == "preview_only"
    assert "provenance" not in unrelated_meta

    matched_meta = _enrich_source_metadata(
        {"tool": "extract_invoice_totals", "document_id": "doc-verified"},
        overall_assess,
        source_identifier="doc-verified",
        source_name="facture_a.xlsx",
        tool_call_results=[verified_cr],
    )
    assert matched_meta["certified_grounding"] is True
    assert matched_meta["grounding_status"] == "math_verified"

    # Thread 6: Legacy partial workbook text (without === ONGLET: marker) marks is_incomplete_source=True and blocks certification
    legacy_bundle = bundle_from_extracted_text("ancien_classeur.xlsx", "Description,Montant\nSous-total,100.00\nTOTAL,100.00")
    assert legacy_bundle.is_incomplete_source is True
    assert legacy_bundle.extraction_mode == "legacy_partial_text"
    legacy_rep = SERVICE.extract_from_bundle(legacy_bundle)
    assert legacy_rep.full_source_read is False
    assert legacy_rep.certified_grounding is False
    assert legacy_rep.verification_status == "incomplete_source"
    assert legacy_rep.grounding_status == "uncertain_candidates"

    # Thread 7: Sparse XLSX with a distant cell does not hang or exhaust memory
    wb_sparse = Workbook()
    ws_sparse: Any = wb_sparse.active
    ws_sparse.title = "FactureSparse"
    ws_sparse["A1"] = "Sous-total"
    ws_sparse["B1"] = Decimal("250.00")
    ws_sparse["A2"] = "TOTAL"
    ws_sparse["B2"] = Decimal("250.00")
    ws_sparse["AZ5000"] = "Note lointaine"
    sparse_bundle = extract_document_bundle("sparse.xlsx", _xlsx_bytes(wb_sparse))
    assert len(sparse_bundle.cells) == 5

    # Thread 9: Unrelated hidden invoice or unresolved second sheet blocks single-invoice certification
    wb_two = Workbook()
    ws_v1: Any = wb_two.active
    ws_v1.title = "Facture1"
    ws_v1["A1"] = "Sous-total"
    ws_v1["B1"] = Decimal("100.00")
    ws_v1["A2"] = "TPS"
    ws_v1["B2"] = Decimal("5.00")
    ws_v1["A3"] = "TOTAL"
    ws_v1["B3"] = Decimal("105.00")
    ws_h2 = wb_two.create_sheet("FactureCacheeNonLiee")
    ws_h2.sheet_state = "hidden"
    ws_h2["A1"] = "TOTAL"
    ws_h2["B1"] = Decimal("999.00")
    rep_two = SERVICE.extract_from_bytes("deux_factures_non_liees.xlsx", _xlsx_bytes(wb_two))
    assert rep_two.primary_invoice is None
    assert rep_two.verification_status == "ambiguous_candidates"
    assert rep_two.certified_grounding is False

    # Thread 10: Uncached discount formula prevents false math_verified certification
    wb_disc = Workbook()
    ws_disc: Any = wb_disc.active
    ws_disc.title = "FactureRabais"
    ws_disc["A1"] = "Sous-total"
    ws_disc["B1"] = Decimal("100.00")
    ws_disc["A2"] = "Remise"
    ws_disc["B2"] = "=A1*0.1"
    ws_disc["A3"] = "TOTAL"
    ws_disc["B3"] = Decimal("100.00")
    rep_disc = SERVICE.extract_from_bytes("rabais_non_cache.xlsx", _xlsx_bytes(wb_disc))
    assert rep_disc.verification_status == "uncached_formula"
    assert rep_disc.certified_grounding is False

    # Thread 11: Inconsistent balance_due (total 100 - paid 40 != balance 90) fails math verification
    inconsistent_balance_txt = "FACTURE #B-99\nSous-total: 100,00 $ CAD\nTOTAL: 100,00 $ CAD\nMontant payé: 40,00 $ CAD\nSolde dû: 90,00 $ CAD"
    rep_bal = SERVICE.extract_from_text("solde_incoherent.txt", inconsistent_balance_txt)
    assert rep_bal.verification_status == "math_mismatch"
    assert rep_bal.certified_grounding is False

    # Thread 13: Percentage-formatted rate cell on tax row is skipped in favor of the monetary tax amount
    wb_pct = Workbook()
    ws_pct: Any = wb_pct.active
    ws_pct.title = "FactureTaux"
    ws_pct["A1"] = "Sous-total"
    ws_pct["C1"] = Decimal("950.00")
    ws_pct["A2"] = "TPS"
    ws_pct["B2"] = Decimal("0.05")
    ws_pct["B2"].number_format = "0%"
    ws_pct["C2"] = Decimal("47.50")
    ws_pct["A3"] = "TOTAL"
    ws_pct["C3"] = Decimal("997.50")
    rep_pct = SERVICE.extract_from_bytes("taux_pourcent.xlsx", _xlsx_bytes(wb_pct))
    assert rep_pct.verification_status == "math_verified"
    assert rep_pct.primary_invoice is not None
    assert rep_pct.primary_invoice.tax_total == Decimal("47.50")
    assert rep_pct.primary_invoice.total_amount is not None
    assert rep_pct.primary_invoice.total_amount.amount == Decimal("997.50")

    # Thread 14: Unknown currency is preserved as None and never fabricated as CAD in direct_statement_fr
    no_ccy_rep = SERVICE.extract_from_text("sans_devise.txt", "INVOICE #NC-1\nSubtotal: 100.00\nTotal: 100.00")
    assert no_ccy_rep.primary_invoice is not None
    assert no_ccy_rep.primary_invoice.currency is None
    assert "CAD" not in (no_ccy_rep.primary_invoice.direct_statement_fr or "")

    # Universal document classification across all 10 business document categories
    assert classify_document("Purchase Order PO Number 8812\nQty: 50", "po_8812.pdf") == "purchase_order"
    assert classify_document("Relevé bancaire - Solde d'ouverture: 12 000,00 $", "releve_nov.pdf") == "statement"
    assert classify_document("Inventaire entrepôt - SKU-101 Quantité en stock: 45", "stock.xlsx") == "inventory"
    assert classify_document("Bulletin de salaire - Salaire brut: 4 500,00 $ - Heures travaillées: 160", "paie.pdf") == "hr_document"
    assert classify_document("État des résultats - Bilan comptable et EBITDA 2026", "rapport_financier.pdf") == "financial_report"


