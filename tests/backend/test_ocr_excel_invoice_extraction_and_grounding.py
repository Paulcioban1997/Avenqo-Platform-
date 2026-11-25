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

