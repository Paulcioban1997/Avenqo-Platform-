"""Extraction réelle et sans perte de documents multi-formats pour Avenqo.

Sépare strictement :
1. L'extraction fidèle des cellules, feuilles, pages, tableaux et formules avec provenance complète
   (`file_name`, `sheet_name`, `cell_ref`, `raw_value`, `normalized_value`, `data_type`,
   `extracted_at`, `confidence`, `verification_status`).
2. L'interprétation financière structurée (déléguée à `invoice_extraction_service.py`).

Corrections critiques (Incident OCR / Excel multi-feuilles) :
- Remplacement de la troncature `pandas.read_excel() -> CSV` (qui ne lisait que le 1er onglet,
  écrasait les cellules fusionnées et perdait les coordonnées/devises/formules) par une lecture
  double passe `openpyxl` (`data_only=False` + `data_only=True`) sur tous les onglets pertinents
  (visibles + onglets masqués contenant des données financières).
- Détection explicite des formules Excel sans valeur mise en cache (`uncached_formula=True`) :
  ne traite JAMAIS `"=SUM(...)"` comme un montant confirmé.
- Extraction complète des paragraphes ET tableaux `.docx`, des pages `.pdf` numériques vs scannées,
  et des fichiers `.csv`/`.tsv`/`.xls`/images OCR.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import io
from pathlib import Path
import re
from typing import Any, Callable


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
EXCEL_OPENPYXL_SUFFIXES = {".xlsx", ".xlsm"}
EXCEL_SUFFIXES = {*EXCEL_OPENPYXL_SUFFIXES, ".xls"}

SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    *EXCEL_SUFFIXES,
    *IMAGE_SUFFIXES,
}

_FINANCIAL_SHEET_HINTS = (
    "total",
    "montant",
    "amount",
    "sous-total",
    "subtotal",
    "facture",
    "invoice",
    "tps",
    "tvq",
    "gst",
    "qst",
    "hst",
    "tax",
    "solde",
    "balance",
    "cad",
    "usd",
    "eur",
    "$",
    "€",
)

_CURRENCY_FORMAT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CAD", re.compile(r"\bCAD\b|\[\$CAD|\[\$-\d*C0C\]", re.IGNORECASE)),
    ("USD", re.compile(r"\bUSD\b|\[\$USD|US\$", re.IGNORECASE)),
    ("EUR", re.compile(r"\bEUR\b|€|\[\$€", re.IGNORECASE)),
    ("GBP", re.compile(r"\bGBP\b|£|\[\$£", re.IGNORECASE)),
)


class UnsupportedDocumentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CellProvenance:
    """Provenance unitaire certifiée d'une cellule, ligne de tableau ou segment de page."""

    file_name: str
    sheet_name: str | None
    cell_ref: str
    coordinate: str
    row: int
    column: int
    end_row: int
    end_column: int
    raw_value: Any
    cached_value: Any
    normalized_value: str | None
    number_format: str | None
    formula: str | None
    uncached_formula: bool
    merged_range: str | None
    is_hidden_sheet: bool
    data_type: str
    currency_hint: str | None
    extracted_at: str
    confidence: float
    verification_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "sheet_name": self.sheet_name,
            "cell_ref": self.cell_ref,
            "coordinate": self.coordinate,
            "row": self.row,
            "column": self.column,
            "end_row": self.end_row,
            "end_column": self.end_column,
            "raw_value": _json_safe_scalar(self.raw_value),
            "cached_value": _json_safe_scalar(self.cached_value),
            "normalized_value": self.normalized_value,
            "number_format": self.number_format,
            "formula": self.formula,
            "uncached_formula": self.uncached_formula,
            "merged_range": self.merged_range,
            "is_hidden_sheet": self.is_hidden_sheet,
            "data_type": self.data_type,
            "currency_hint": self.currency_hint,
            "extracted_at": self.extracted_at,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
        }


@dataclass(frozen=True, slots=True)
class ExtractedSheet:
    """Représentation structurée d'un onglet Excel, tableau DOCX ou page PDF."""

    sheet_name: str
    sheet_state: str
    is_hidden: bool
    has_financial_data: bool
    max_row: int
    max_column: int
    merged_ranges: tuple[str, ...]
    cells: tuple[CellProvenance, ...]
    uncached_formula_cells: tuple[str, ...]
    rendered_text: str

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "sheet_state": self.sheet_state,
            "is_hidden": self.is_hidden,
            "has_financial_data": self.has_financial_data,
            "max_row": self.max_row,
            "max_column": self.max_column,
            "cell_count": len(self.cells),
            "merged_ranges": list(self.merged_ranges),
            "uncached_formula_cells": list(self.uncached_formula_cells),
        }


@dataclass(frozen=True, slots=True)
class DocumentExtractionBundle:
    """Résultat complet sans perte d'une extraction documentaire multi-formats."""

    file_name: str
    file_format: str
    sha256: str
    extracted_at: str
    extraction_mode: str
    full_text: str
    page_count: int
    sheets: tuple[ExtractedSheet, ...]
    cells: tuple[CellProvenance, ...]
    has_uncached_formulas: bool
    uncached_formula_refs: tuple[str, ...]
    warnings: tuple[str, ...]
    is_incomplete_source: bool = False

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_format": self.file_format,
            "sha256": self.sha256,
            "extracted_at": self.extracted_at,
            "extraction_mode": self.extraction_mode,
            "is_incomplete_source": self.is_incomplete_source,
            "page_count": self.page_count,
            "sheet_count": len(self.sheets),
            "sheets": [s.to_summary_dict() for s in self.sheets],
            "total_cells_extracted": len(self.cells),
            "has_uncached_formulas": self.has_uncached_formulas,
            "uncached_formula_refs": list(self.uncached_formula_refs),
            "warnings": list(self.warnings),
        }


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return str(_decimal_from_float(value))
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if hasattr(value, "text"):
        return str(getattr(value, "text"))
    return str(value)


def _decimal_from_float(value: float) -> Decimal:
    """Convertit un float binaire Excel en Decimal propre sans artefact IEEE-754."""
    dec = Decimal(str(value))
    # Normalise les artefacts binaires type 1250.5000000000002 -> 1250.50 tout en gardant jusqu'à 6 décimales utiles
    quantized = dec.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).normalize()
    text = format(quantized, "f")
    if "." in text:
        int_part, frac_part = text.split(".", 1)
        if len(frac_part) == 1:
            text = f"{int_part}.{frac_part}0"
    return Decimal(text)


def _excel_col_letter(col_idx: int) -> str:
    result = []
    n = max(1, col_idx)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result.append(chr(65 + rem))
    return "".join(reversed(result))


def _currency_hint_from_format_and_text(number_format: str | None, text_value: str | None) -> str | None:
    fmt = number_format or ""
    for code, pattern in _CURRENCY_FORMAT_PATTERNS:
        if pattern.search(fmt):
            return code
    txt = text_value or ""
    for code, pattern in _CURRENCY_FORMAT_PATTERNS:
        if pattern.search(txt):
            return code
    if "$" in fmt or "$" in txt:
        return "$"
    return None


def _classify_scalar_value(
    value: Any,
    *,
    number_format: str | None = None,
    is_date_cell: bool = False,
) -> tuple[str, str | None, str | None]:
    """Retourne `(data_type, normalized_value, currency_hint)` sans jamais convertir une formule en nombre."""
    if value is None:
        return "empty", None, None
    if isinstance(value, bool):
        return "boolean", "true" if value else "false", None
    if is_date_cell or isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            iso = value.date().isoformat() if (value.hour == 0 and value.minute == 0 and value.second == 0) else value.isoformat()
        elif isinstance(value, date):
            iso = value.isoformat()
        else:
            iso = str(value)
        return "date", iso, None
    if isinstance(value, time):
        return "text", value.isoformat(), None
    if isinstance(value, int):
        dec = Decimal(value)
        ccy = _currency_hint_from_format_and_text(number_format, None)
        dtype = "currency" if ccy else "number"
        return dtype, format(dec, "f"), ccy
    if isinstance(value, Decimal):
        ccy = _currency_hint_from_format_and_text(number_format, None)
        dtype = "currency" if ccy else "number"
        return dtype, format(value, "f"), ccy
    if isinstance(value, float):
        if value != value:
            return "empty", None, None
        dec = _decimal_from_float(value)
        ccy = _currency_hint_from_format_and_text(number_format, None)
        dtype = "currency" if ccy else "number"
        return dtype, format(dec, "f"), ccy

    text = str(value).strip()
    if not text:
        return "empty", None, None
    ccy = _currency_hint_from_format_and_text(number_format, text)
    return "text", text, ccy


def _sheet_has_financial_signals(cells: list[CellProvenance], sheet_name: str) -> bool:
    lower_name = sheet_name.lower()
    if any(hint in lower_name for hint in _FINANCIAL_SHEET_HINTS):
        return True
    for cell in cells:
        if cell.data_type in {"currency", "formula_uncached"}:
            return True
        raw_str = f"{cell.raw_value or ''} {cell.normalized_value or ''}".lower()
        if any(hint in raw_str for hint in _FINANCIAL_SHEET_HINTS):
            return True
    return False


def _extract_xlsx_bundle(filename: str, content: bytes, extracted_at: str, digest: str) -> DocumentExtractionBundle:
    import openpyxl

    try:
        wb_formulas = openpyxl.load_workbook(io.BytesIO(content), data_only=False, read_only=False)
        wb_values = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=False)
    except Exception as exc:
        raise UnsupportedDocumentError(f"Classeur Excel illisible ou corrompu ({filename}) : {exc}") from exc

    sheets_out: list[ExtractedSheet] = []
    all_cells: list[CellProvenance] = []
    all_uncached_refs: list[str] = []
    warnings: list[str] = []
    is_incomplete_workbook = False
    max_cells_per_sheet = 50_000
    max_cells_per_workbook = 150_000
    max_expanded_merged_cells = 10_000

    try:
        for sheet_name in wb_formulas.sheetnames:
            ws_f = wb_formulas[sheet_name]
            ws_v = wb_values[sheet_name]
            sheet_state = str(getattr(ws_f, "sheet_state", "visible") or "visible")
            is_hidden = sheet_state != "visible"

            # Cartographier toutes les plages fusionnées sans matérialiser des millions de tuples sur une plage géante
            merged_anchors: dict[tuple[int, int], tuple[str, int, int]] = {}
            merged_slaves: set[tuple[int, int]] = set()
            large_merged_bboxes: list[tuple[int, int, int, int, tuple[int, int]]] = []
            merged_range_strs: list[str] = []

            for m_range in ws_f.merged_cells.ranges:
                range_str = str(m_range.coord)
                merged_range_strs.append(range_str)
                anchor = (m_range.min_row, m_range.min_col)
                merged_anchors[anchor] = (range_str, m_range.max_row, m_range.max_col)
                span_cells = (m_range.max_row - m_range.min_row + 1) * (m_range.max_col - m_range.min_col + 1)
                if span_cells <= max_expanded_merged_cells:
                    for r_idx in range(m_range.min_row, m_range.max_row + 1):
                        for c_idx in range(m_range.min_col, m_range.max_col + 1):
                            if (r_idx, c_idx) != anchor:
                                merged_slaves.add((r_idx, c_idx))
                else:
                    large_merged_bboxes.append(
                        (m_range.min_row, m_range.min_col, m_range.max_row, m_range.max_col, anchor)
                    )

            def _is_merged_slave(coord_rc: tuple[int, int]) -> bool:
                if coord_rc in merged_slaves:
                    return True
                r_c, c_c = coord_rc
                for min_r, min_c, max_r, max_c, anch in large_merged_bboxes:
                    if min_r <= r_c <= max_r and min_c <= c_c <= max_c and coord_rc != anch:
                        return True
                return False

            # Itération creuse (sparse) uniquement sur les cellules réellement présentes en mémoire openpyxl (`_cells`),
            # pour qu'une feuille contenant une cellule formatée lointaine (ex: XFD1048576) n'épuise jamais le worker.
            cells_dict_f = getattr(ws_f, "_cells", None)
            cells_dict_v = getattr(ws_v, "_cells", None)
            if isinstance(cells_dict_f, dict) or isinstance(cells_dict_v, dict):
                populated_coords_set: set[tuple[int, int]] = set()
                if isinstance(cells_dict_f, dict):
                    populated_coords_set.update(cells_dict_f.keys())
                if isinstance(cells_dict_v, dict):
                    populated_coords_set.update(cells_dict_v.keys())
                populated_coords_set.update(merged_anchors.keys())
                sorted_coords = sorted(populated_coords_set)
            else:
                max_r_bound = min(max(int(ws_f.max_row or 0), int(ws_v.max_row or 0)), 2000)
                max_c_bound = min(max(int(ws_f.max_column or 0), int(ws_v.max_column or 0)), 200)
                sorted_coords = [
                    (r_i, c_i)
                    for r_i in range(1, max_r_bound + 1)
                    for c_i in range(1, max_c_bound + 1)
                ]

            rows_to_cols: dict[int, list[int]] = {}
            coord_count = 0
            for r_idx, c_idx in sorted_coords:
                if _is_merged_slave((r_idx, c_idx)):
                    continue
                if coord_count >= max_cells_per_sheet or (len(all_cells) + coord_count) >= max_cells_per_workbook:
                    is_incomplete_workbook = True
                    warnings.append(
                        f"Limite de sécurité de cellules atteinte sur '{sheet_name}' ({max_cells_per_sheet} cellules) : extraction bornée."
                    )
                    break
                rows_to_cols.setdefault(r_idx, []).append(c_idx)
                coord_count += 1

            max_row = max(rows_to_cols.keys(), default=0)
            max_col = max((max(cols) for cols in rows_to_cols.values() if cols), default=0)

            sheet_cells: list[CellProvenance] = []
            sheet_uncached: list[str] = []
            rendered_lines: list[str] = []

            for r_idx in sorted(rows_to_cols.keys()):
                row_tokens: list[str] = []
                for c_idx in rows_to_cols[r_idx]:
                    cell_f = cells_dict_f.get((r_idx, c_idx)) if isinstance(cells_dict_f, dict) else ws_f.cell(row=r_idx, column=c_idx)
                    cell_v = cells_dict_v.get((r_idx, c_idx)) if isinstance(cells_dict_v, dict) else ws_v.cell(row=r_idx, column=c_idx)

                    raw_f = getattr(cell_f, "value", None) if cell_f is not None else None
                    val_v = getattr(cell_v, "value", None) if cell_v is not None else None

                    if raw_f is None and val_v is None:
                        continue

                    coord = f"{_excel_col_letter(c_idx)}{r_idx}"
                    merged_info = merged_anchors.get((r_idx, c_idx))
                    merged_str = merged_info[0] if merged_info else None
                    end_row = merged_info[1] if merged_info else r_idx
                    end_col = merged_info[2] if merged_info else c_idx
                    cell_ref = f"{sheet_name}!{coord}"
                    raw_num_fmt = getattr(cell_f, "number_format", None) if cell_f is not None else (getattr(cell_v, "number_format", None) if cell_v is not None else None)
                    number_format = str(raw_num_fmt) if raw_num_fmt else None

                    is_formula = (
                        getattr(cell_f, "data_type", None) == "f"
                        or (isinstance(raw_f, str) and raw_f.strip().startswith("="))
                        or hasattr(raw_f, "text")
                    )

                    if is_formula:
                        formula_text = str(getattr(raw_f, "text", raw_f)).strip()
                        has_cached = val_v is not None and not (
                            isinstance(val_v, str) and val_v.strip().startswith("=")
                        )
                        if has_cached:
                            dtype, norm_val, ccy_hint = _classify_scalar_value(
                                val_v,
                                number_format=number_format,
                                is_date_cell=bool(getattr(cell_v, "is_date", False)),
                            )
                            prov = CellProvenance(
                                file_name=filename,
                                sheet_name=sheet_name,
                                cell_ref=cell_ref,
                                coordinate=coord,
                                row=r_idx,
                                column=c_idx,
                                end_row=end_row,
                                end_column=end_col,
                                raw_value=formula_text,
                                cached_value=val_v,
                                normalized_value=norm_val,
                                number_format=number_format,
                                formula=formula_text,
                                uncached_formula=False,
                                merged_range=merged_str,
                                is_hidden_sheet=is_hidden,
                                data_type=dtype,
                                currency_hint=ccy_hint,
                                extracted_at=extracted_at,
                                confidence=1.0,
                                verification_status="cached_formula",
                            )
                            display_ccy = f" {ccy_hint}" if ccy_hint and ccy_hint not in (norm_val or "") and ccy_hint != "$" else (
                                " $" if ccy_hint == "$" and "$" not in (norm_val or "") else ""
                            )
                            row_tokens.append(f"[{coord}] {norm_val}{display_ccy}")
                        else:
                            sheet_uncached.append(cell_ref)
                            all_uncached_refs.append(cell_ref)
                            prov = CellProvenance(
                                file_name=filename,
                                sheet_name=sheet_name,
                                cell_ref=cell_ref,
                                coordinate=coord,
                                row=r_idx,
                                column=c_idx,
                                end_row=end_row,
                                end_column=end_col,
                                raw_value=formula_text,
                                cached_value=None,
                                normalized_value=None,
                                number_format=number_format,
                                formula=formula_text,
                                uncached_formula=True,
                                merged_range=merged_str,
                                is_hidden_sheet=is_hidden,
                                data_type="formula_uncached",
                                currency_hint=_currency_hint_from_format_and_text(number_format, None),
                                extracted_at=extracted_at,
                                confidence=0.0,
                                verification_status="uncached_formula",
                            )
                            row_tokens.append(f"[{coord} FORMULA_UNCACHED: {formula_text}]")
                    else:
                        effective_val = val_v if val_v is not None else raw_f
                        dtype, norm_val, ccy_hint = _classify_scalar_value(
                            effective_val,
                            number_format=number_format,
                            is_date_cell=bool(getattr(cell_f, "is_date", False)),
                        )
                        if dtype == "empty":
                            continue
                        prov = CellProvenance(
                            file_name=filename,
                            sheet_name=sheet_name,
                            cell_ref=cell_ref,
                            coordinate=coord,
                            row=r_idx,
                            column=c_idx,
                            end_row=end_row,
                            end_column=end_col,
                            raw_value=raw_f,
                            cached_value=val_v,
                            normalized_value=norm_val,
                            number_format=number_format,
                            formula=None,
                            uncached_formula=False,
                            merged_range=merged_str,
                            is_hidden_sheet=is_hidden,
                            data_type=dtype,
                            currency_hint=ccy_hint,
                            extracted_at=extracted_at,
                            confidence=1.0,
                            verification_status="verified_cell",
                        )
                        display_ccy = f" {ccy_hint}" if ccy_hint and ccy_hint not in (norm_val or "") and ccy_hint != "$" and dtype == "currency" else (
                            " $" if ccy_hint == "$" and "$" not in (norm_val or "") and dtype == "currency" else ""
                        )
                        row_tokens.append(f"[{coord}] {norm_val}{display_ccy}")

                    sheet_cells.append(prov)

                if row_tokens:
                    rendered_lines.append(f"L{r_idx}: " + " | ".join(row_tokens))

            has_financial = _sheet_has_financial_signals(sheet_cells, sheet_name)
            # Conserver toutes les feuilles visibles non vides + les feuilles masquées contenant des données financières
            if not sheet_cells and is_hidden:
                continue
            if is_hidden and not has_financial:
                continue

            if is_hidden and has_financial:
                warnings.append(
                    f"L'onglet masqué '{sheet_name}' ({sheet_state}) contient des données financières et a été inclus."
                )
            if sheet_uncached:
                warnings.append(
                    f"Formule(s) Excel sans valeur mise en cache détectée(s) dans '{sheet_name}' : {', '.join(sheet_uncached)}."
                )

            header_tag = f"=== ONGLET: {sheet_name}" + (" (MASQUÉ)" if is_hidden else "") + " ==="
            sheet_text = f"{header_tag}\n" + "\n".join(rendered_lines) if rendered_lines else header_tag

            sheets_out.append(
                ExtractedSheet(
                    sheet_name=sheet_name,
                    sheet_state=sheet_state,
                    is_hidden=is_hidden,
                    has_financial_data=has_financial,
                    max_row=max_row,
                    max_column=max_col,
                    merged_ranges=tuple(merged_range_strs),
                    cells=tuple(sheet_cells),
                    uncached_formula_cells=tuple(sheet_uncached),
                    rendered_text=sheet_text,
                )
            )
            all_cells.extend(sheet_cells)
    finally:
        wb_formulas.close()
        wb_values.close()

    full_text = "\n\n".join(s.rendered_text for s in sheets_out if s.cells).strip()
    return DocumentExtractionBundle(
        file_name=filename,
        file_format=Path(filename).suffix.lower().lstrip("."),
        sha256=digest,
        extracted_at=extracted_at,
        extraction_mode="openpyxl_dual_pass",
        full_text=full_text,
        page_count=len(sheets_out),
        sheets=tuple(sheets_out),
        cells=tuple(all_cells),
        has_uncached_formulas=bool(all_uncached_refs),
        uncached_formula_refs=tuple(all_uncached_refs),
        warnings=tuple(warnings),
        is_incomplete_source=is_incomplete_workbook,
    )


def _extract_xls_fallback_bundle(filename: str, content: bytes, extracted_at: str, digest: str) -> DocumentExtractionBundle:
    """Extraction multi-feuilles pour les anciens classeurs `.xls` (sans troncature au 1er onglet)."""
    import pandas as pd

    try:
        frames_by_sheet = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
    except Exception as exc:
        raise UnsupportedDocumentError(f"Classeur XLS illisible ({filename}) : {exc}") from exc

    sheets_out: list[ExtractedSheet] = []
    all_cells: list[CellProvenance] = []

    for sheet_name, frame in frames_by_sheet.items():
        sheet_cells: list[CellProvenance] = []
        rendered_lines: list[str] = []
        nrows, ncols = frame.shape
        for r_zero in range(nrows):
            row_tokens: list[str] = []
            r_idx = r_zero + 1
            for c_zero in range(ncols):
                c_idx = c_zero + 1
                raw_val = frame.iat[r_zero, c_zero]
                if raw_val is None or (isinstance(raw_val, float) and raw_val != raw_val):
                    continue
                dtype, norm_val, ccy_hint = _classify_scalar_value(raw_val)
                if dtype == "empty" or norm_val is None:
                    continue
                coord = f"{_excel_col_letter(c_idx)}{r_idx}"
                cell_ref = f"{sheet_name}!{coord}"
                prov = CellProvenance(
                    file_name=filename,
                    sheet_name=str(sheet_name),
                    cell_ref=cell_ref,
                    coordinate=coord,
                    row=r_idx,
                    column=c_idx,
                    end_row=r_idx,
                    end_column=c_idx,
                    raw_value=raw_val,
                    cached_value=raw_val,
                    normalized_value=norm_val,
                    number_format=None,
                    formula=None,
                    uncached_formula=False,
                    merged_range=None,
                    is_hidden_sheet=False,
                    data_type=dtype,
                    currency_hint=ccy_hint,
                    extracted_at=extracted_at,
                    confidence=0.95,
                    verification_status="verified_cell",
                )
                sheet_cells.append(prov)
                row_tokens.append(f"[{coord}] {norm_val}")
            if row_tokens:
                rendered_lines.append(f"L{r_idx}: " + " | ".join(row_tokens))

        if not sheet_cells:
            continue
        sheet_text = f"=== ONGLET: {sheet_name} ===\n" + "\n".join(rendered_lines)
        sheets_out.append(
            ExtractedSheet(
                sheet_name=str(sheet_name),
                sheet_state="visible",
                is_hidden=False,
                has_financial_data=_sheet_has_financial_signals(sheet_cells, str(sheet_name)),
                max_row=nrows,
                max_column=ncols,
                merged_ranges=(),
                cells=tuple(sheet_cells),
                uncached_formula_cells=(),
                rendered_text=sheet_text,
            )
        )
        all_cells.extend(sheet_cells)

    full_text = "\n\n".join(s.rendered_text for s in sheets_out).strip()
    return DocumentExtractionBundle(
        file_name=filename,
        file_format="xls",
        sha256=digest,
        extracted_at=extracted_at,
        extraction_mode="pandas_multisheet_xls",
        full_text=full_text,
        page_count=len(sheets_out),
        sheets=tuple(sheets_out),
        cells=tuple(all_cells),
        has_uncached_formulas=False,
        uncached_formula_refs=(),
        warnings=(),
    )


def _extract_docx_bundle(filename: str, content: bytes, extracted_at: str, digest: str) -> DocumentExtractionBundle:
    """Extrait à la fois les paragraphes ET tous les tableaux Word (`.docx`) sans dupliquer les cellules fusionnées."""
    from docx import Document

    doc = Document(io.BytesIO(content))
    all_cells: list[CellProvenance] = []
    sheets_out: list[ExtractedSheet] = []
    text_sections: list[str] = []

    para_cells: list[CellProvenance] = []
    para_lines: list[str] = []
    for idx, paragraph in enumerate(doc.paragraphs, start=1):
        txt = (paragraph.text or "").strip()
        if not txt:
            continue
        para_lines.append(txt)
        _, norm_val, ccy_hint = _classify_scalar_value(txt)
        para_cells.append(
            CellProvenance(
                file_name=filename,
                sheet_name="Paragraphes",
                cell_ref=f"Paragraphes!P{idx}",
                coordinate=f"P{idx}",
                row=idx,
                column=1,
                end_row=idx,
                end_column=1,
                raw_value=txt,
                cached_value=txt,
                normalized_value=norm_val,
                number_format=None,
                formula=None,
                uncached_formula=False,
                merged_range=None,
                is_hidden_sheet=False,
                data_type="text",
                currency_hint=ccy_hint,
                extracted_at=extracted_at,
                confidence=1.0,
                verification_status="digital_text",
            )
        )
    if para_lines:
        para_text = "\n".join(para_lines)
        text_sections.append(para_text)
        sheets_out.append(
            ExtractedSheet(
                sheet_name="Paragraphes",
                sheet_state="visible",
                is_hidden=False,
                has_financial_data=_sheet_has_financial_signals(para_cells, "Paragraphes"),
                max_row=len(para_lines),
                max_column=1,
                merged_ranges=(),
                cells=tuple(para_cells),
                uncached_formula_cells=(),
                rendered_text=para_text,
            )
        )
        all_cells.extend(para_cells)

    for t_idx, table in enumerate(doc.tables, start=1):
        t_name = f"Table {t_idx}"
        t_cells: list[CellProvenance] = []
        t_lines: list[str] = []
        max_cols = 0
        seen_tc_ids: set[int] = set()
        for r_idx, row in enumerate(table.rows, start=1):
            row_tokens: list[str] = []
            max_cols = max(max_cols, len(row.cells))
            for c_idx, cell in enumerate(row.cells, start=1):
                tc_id = id(cell._tc)
                if tc_id in seen_tc_ids:
                    continue
                seen_tc_ids.add(tc_id)
                cell_txt = " ".join((cell.text or "").split()).strip()
                if not cell_txt:
                    continue
                coord = f"{_excel_col_letter(c_idx)}{r_idx}"
                _, norm_val, ccy_hint = _classify_scalar_value(cell_txt)
                prov = CellProvenance(
                    file_name=filename,
                    sheet_name=t_name,
                    cell_ref=f"{t_name}!{coord}",
                    coordinate=coord,
                    row=r_idx,
                    column=c_idx,
                    end_row=r_idx,
                    end_column=c_idx,
                    raw_value=cell_txt,
                    cached_value=cell_txt,
                    normalized_value=norm_val,
                    number_format=None,
                    formula=None,
                    uncached_formula=False,
                    merged_range=None,
                    is_hidden_sheet=False,
                    data_type="text",
                    currency_hint=ccy_hint,
                    extracted_at=extracted_at,
                    confidence=1.0,
                    verification_status="digital_text",
                )
                t_cells.append(prov)
                row_tokens.append(f"[{coord}] {cell_txt}")
            if row_tokens:
                t_lines.append(f"L{r_idx}: " + " | ".join(row_tokens))

        if t_cells:
            t_rendered = f"=== {t_name} ===\n" + "\n".join(t_lines)
            text_sections.append(t_rendered)
            sheets_out.append(
                ExtractedSheet(
                    sheet_name=t_name,
                    sheet_state="visible",
                    is_hidden=False,
                    has_financial_data=_sheet_has_financial_signals(t_cells, t_name),
                    max_row=len(table.rows),
                    max_column=max_cols,
                    merged_ranges=(),
                    cells=tuple(t_cells),
                    uncached_formula_cells=(),
                    rendered_text=t_rendered,
                )
            )
            all_cells.extend(t_cells)

    return DocumentExtractionBundle(
        file_name=filename,
        file_format="docx",
        sha256=digest,
        extracted_at=extracted_at,
        extraction_mode="docx_paragraphs_and_tables",
        full_text="\n\n".join(text_sections).strip(),
        page_count=max(1, len(sheets_out)),
        sheets=tuple(sheets_out),
        cells=tuple(all_cells),
        has_uncached_formulas=False,
        uncached_formula_refs=(),
        warnings=(),
    )


def _extract_pdf_bundle(
    filename: str,
    content: bytes,
    extracted_at: str,
    digest: str,
    *,
    image_ocr: Callable[[str, bytes], str] | None = None,
) -> DocumentExtractionBundle:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    sheets_out: list[ExtractedSheet] = []
    all_cells: list[CellProvenance] = []
    page_texts: list[str] = []
    warnings: list[str] = []
    total_pages = len(reader.pages)
    digital_pages = 0
    ocr_pages = 0
    unreadable_pages: list[int] = []

    for page_idx, page in enumerate(reader.pages, start=1):
        page_name = f"Page {page_idx}"
        raw_page_text = (page.extract_text() or "").strip()
        is_page_ocr = False
        if not raw_page_text and image_ocr is not None:
            ocr_page_label = f"{filename}#page={page_idx}" if total_pages > 1 else filename
            raw_page_text = str(image_ocr(ocr_page_label, content) or "").strip()
            if not raw_page_text and total_pages == 1:
                raw_page_text = str(image_ocr(filename, content) or "").strip()
            if raw_page_text:
                is_page_ocr = True
                page_name = f"Page {page_idx} (OCR)"

        if not raw_page_text:
            unreadable_pages.append(page_idx)
            warnings.append(
                f"Page {page_idx}/{total_pages} sans texte numérique exploitable et non résolue par OCR."
            )
            continue

        if is_page_ocr:
            ocr_pages += 1
        else:
            digital_pages += 1

        page_cells: list[CellProvenance] = []
        lines = [ln.strip() for ln in raw_page_text.splitlines() if ln.strip()]
        for line_idx, line in enumerate(lines, start=1):
            coord = f"L{line_idx}"
            _, norm_val, ccy_hint = _classify_scalar_value(line)
            page_cells.append(
                CellProvenance(
                    file_name=filename,
                    sheet_name=page_name,
                    cell_ref=f"{page_name}!{coord}",
                    coordinate=coord,
                    row=line_idx,
                    column=1,
                    end_row=line_idx,
                    end_column=1,
                    raw_value=line,
                    cached_value=line,
                    normalized_value=norm_val,
                    number_format=None,
                    formula=None,
                    uncached_formula=False,
                    merged_range=None,
                    is_hidden_sheet=False,
                    data_type="text",
                    currency_hint=ccy_hint,
                    extracted_at=extracted_at,
                    confidence=0.85 if is_page_ocr else 1.0,
                    verification_status="ocr_text" if is_page_ocr else "digital_text",
                )
            )
        rendered = f"=== {page_name} ===\n{raw_page_text}" if total_pages > 1 else raw_page_text
        page_texts.append(rendered)
        sheets_out.append(
            ExtractedSheet(
                sheet_name=page_name,
                sheet_state="visible",
                is_hidden=False,
                has_financial_data=_sheet_has_financial_signals(page_cells, page_name),
                max_row=len(lines),
                max_column=1,
                merged_ranges=(),
                cells=tuple(page_cells),
                uncached_formula_cells=(),
                rendered_text=rendered,
            )
        )
        all_cells.extend(page_cells)

    full_text = "\n\n".join(page_texts).strip()
    is_incomplete = bool(unreadable_pages) or (total_pages > 0 and not full_text)
    if not full_text:
        mode = "pdf_scanned_unreadable"
        if not warnings:
            warnings.append(
                "PDF scanné sans couche de texte numérique exploitable et sans moteur OCR visuel configuré."
            )
    elif unreadable_pages:
        mode = "pdf_mixed_partial_ocr"
    elif ocr_pages > 0 and digital_pages > 0:
        mode = "pdf_mixed_digital_and_ocr"
    elif ocr_pages > 0:
        mode = "pdf_ocr_fallback"
    else:
        mode = "pdf_digital"

    return DocumentExtractionBundle(
        file_name=filename,
        file_format="pdf",
        sha256=digest,
        extracted_at=extracted_at,
        extraction_mode=mode,
        full_text=full_text,
        page_count=total_pages,
        sheets=tuple(sheets_out),
        cells=tuple(all_cells),
        has_uncached_formulas=False,
        uncached_formula_refs=(),
        warnings=tuple(warnings),
        is_incomplete_source=is_incomplete,
    )


def _extract_delimited_or_text_bundle(
    filename: str,
    text: str,
    suffix: str,
    extracted_at: str,
    digest: str,
    *,
    verification_status: str = "digital_text",
    confidence: float = 1.0,
) -> DocumentExtractionBundle:
    fmt = suffix.lstrip(".") or "txt"
    cells: list[CellProvenance] = []
    sheet_name = "CSV" if suffix in {".csv", ".tsv"} else ("OCR" if verification_status == "ocr_text" else "Texte")
    max_col = 1

    if suffix in {".csv", ".tsv"} and text.strip():
        delim = "\t" if suffix == ".tsv" else ","
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        row_count = 0
        for r_idx, row in enumerate(reader, start=1):
            row_count = r_idx
            max_col = max(max_col, len(row))
            for c_idx, val in enumerate(row, start=1):
                cleaned = val.strip()
                if not cleaned:
                    continue
                coord = f"{_excel_col_letter(c_idx)}{r_idx}"
                is_formula = cleaned.startswith("=")
                if is_formula:
                    cells.append(
                        CellProvenance(
                            file_name=filename,
                            sheet_name=sheet_name,
                            cell_ref=f"{sheet_name}!{coord}",
                            coordinate=coord,
                            row=r_idx,
                            column=c_idx,
                            end_row=r_idx,
                            end_column=c_idx,
                            raw_value=cleaned,
                            cached_value=None,
                            normalized_value=None,
                            number_format=None,
                            formula=cleaned,
                            uncached_formula=True,
                            merged_range=None,
                            is_hidden_sheet=False,
                            data_type="formula_uncached",
                            currency_hint=None,
                            extracted_at=extracted_at,
                            confidence=0.0,
                            verification_status="uncached_formula",
                        )
                    )
                else:
                    _, norm_val, ccy_hint = _classify_scalar_value(cleaned)
                    cells.append(
                        CellProvenance(
                            file_name=filename,
                            sheet_name=sheet_name,
                            cell_ref=f"{sheet_name}!{coord}",
                            coordinate=coord,
                            row=r_idx,
                            column=c_idx,
                            end_row=r_idx,
                            end_column=c_idx,
                            raw_value=cleaned,
                            cached_value=cleaned,
                            normalized_value=norm_val,
                            number_format=None,
                            formula=None,
                            uncached_formula=False,
                            merged_range=None,
                            is_hidden_sheet=False,
                            data_type="text",
                            currency_hint=ccy_hint,
                            extracted_at=extracted_at,
                            confidence=confidence,
                            verification_status=verification_status,
                        )
                    )
        uncached = tuple(c.cell_ref for c in cells if c.uncached_formula)
        sheet = ExtractedSheet(
            sheet_name=sheet_name,
            sheet_state="visible",
            is_hidden=False,
            has_financial_data=_sheet_has_financial_signals(cells, sheet_name),
            max_row=row_count,
            max_column=max_col,
            merged_ranges=(),
            cells=tuple(cells),
            uncached_formula_cells=uncached,
            rendered_text=text.strip(),
        )
        return DocumentExtractionBundle(
            file_name=filename,
            file_format=fmt,
            sha256=digest,
            extracted_at=extracted_at,
            extraction_mode="tabular_text",
            full_text=text.strip(),
            page_count=1,
            sheets=(sheet,),
            cells=tuple(cells),
            has_uncached_formulas=bool(uncached),
            uncached_formula_refs=uncached,
            warnings=(),
        )

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for idx, line in enumerate(lines, start=1):
        coord = f"L{idx}"
        _, norm_val, ccy_hint = _classify_scalar_value(line)
        cells.append(
            CellProvenance(
                file_name=filename,
                sheet_name=sheet_name,
                cell_ref=f"{sheet_name}!{coord}",
                coordinate=coord,
                row=idx,
                column=1,
                end_row=idx,
                end_column=1,
                raw_value=line,
                cached_value=line,
                normalized_value=norm_val,
                number_format=None,
                formula=None,
                uncached_formula=False,
                merged_range=None,
                is_hidden_sheet=False,
                data_type="text",
                currency_hint=ccy_hint,
                extracted_at=extracted_at,
                confidence=confidence,
                verification_status=verification_status,
            )
        )

    sheet = ExtractedSheet(
        sheet_name=sheet_name,
        sheet_state="visible",
        is_hidden=False,
        has_financial_data=_sheet_has_financial_signals(cells, sheet_name),
        max_row=len(lines),
        max_column=1,
        merged_ranges=(),
        cells=tuple(cells),
        uncached_formula_cells=(),
        rendered_text=text.strip(),
    )
    return DocumentExtractionBundle(
        file_name=filename,
        file_format=fmt if verification_status != "ocr_text" else "image",
        sha256=digest,
        extracted_at=extracted_at,
        extraction_mode="image_ocr" if verification_status == "ocr_text" else "digital_text",
        full_text=text.strip(),
        page_count=1,
        sheets=(sheet,) if lines else (),
        cells=tuple(cells),
        has_uncached_formulas=False,
        uncached_formula_refs=(),
        warnings=(),
    )


def extract_document_bundle(
    filename: str,
    content: bytes,
    *,
    image_ocr: Callable[[str, bytes], str] | None = None,
) -> DocumentExtractionBundle:
    """Point d'entrée principal d'extraction sans perte avec provenance cellule/page complète."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocumentError(
            f"Format non pris en charge : {suffix or 'sans extension'}. "
            f"Formats acceptés : {', '.join(sorted(SUPPORTED_SUFFIXES))}."
        )

    extracted_at = _utc_now_iso()
    digest = sha256_bytes(content)

    if not content:
        return DocumentExtractionBundle(
            file_name=filename,
            file_format=suffix.lstrip("."),
            sha256=digest,
            extracted_at=extracted_at,
            extraction_mode="empty",
            full_text="",
            page_count=0,
            sheets=(),
            cells=(),
            has_uncached_formulas=False,
            uncached_formula_refs=(),
            warnings=("Fichier vide.",),
        )

    if suffix in IMAGE_SUFFIXES:
        if image_ocr is None:
            raise UnsupportedDocumentError(
                "L'OCR des images JPEG/PNG scannées nécessite un extracteur de vision configuré. "
                "Aucun texte n'a été inventé."
            )
        text = image_ocr(filename, content)
        if not str(text or "").strip():
            raise UnsupportedDocumentError("Aucun texte n'a pu être lu sur cette image.")
        return _extract_delimited_or_text_bundle(
            filename,
            str(text).strip(),
            suffix,
            extracted_at,
            digest,
            verification_status="ocr_text",
            confidence=0.85,
        )

    if suffix == ".pdf":
        return _extract_pdf_bundle(filename, content, extracted_at, digest, image_ocr=image_ocr)

    if suffix == ".docx":
        return _extract_docx_bundle(filename, content, extracted_at, digest)

    if suffix in EXCEL_OPENPYXL_SUFFIXES:
        return _extract_xlsx_bundle(filename, content, extracted_at, digest)

    if suffix == ".xls":
        return _extract_xls_fallback_bundle(filename, content, extracted_at, digest)

    decoded = content.decode("utf-8-sig", errors="replace").strip()
    return _extract_delimited_or_text_bundle(filename, decoded, suffix, extracted_at, digest)


def bundle_from_extracted_text(
    filename: str,
    extracted_text: str,
    *,
    is_confirmed_complete: bool | None = None,
) -> DocumentExtractionBundle:
    """Reconstruit un `DocumentExtractionBundle` à partir d'un texte déjà persisté en base
    (y compris les rendus multi-onglets `=== ONGLET: ... === [Coord] ...`)."""
    extracted_at = _utc_now_iso()
    digest = sha256_bytes((extracted_text or "").encode("utf-8"))
    suffix = Path(filename).suffix.lower()
    text = (extracted_text or "").strip()

    if "=== ONGLET:" in text:
        sheet_blocks = re.split(r"(?==== ONGLET:\s*)", text)
        sheets_out: list[ExtractedSheet] = []
        all_cells: list[CellProvenance] = []
        all_uncached: list[str] = []

        header_re = re.compile(r"^=== ONGLET:\s*(.+?)\s*(\(MASQUÉ\))?\s*===$")
        cell_token_re = re.compile(r"\[([A-Z]+\d+)(?:\s+FORMULA_UNCACHED:\s*([^\]]+))?\]\s*([^|]*)")

        for block in sheet_blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.splitlines()
            m_hdr = header_re.match(lines[0].strip())
            if not m_hdr:
                continue
            sheet_name = m_hdr.group(1).strip()
            is_hidden = bool(m_hdr.group(2))
            s_cells: list[CellProvenance] = []
            s_uncached: list[str] = []
            max_r = 0
            max_c = 0

            for line in lines[1:]:
                for m_tok in cell_token_re.finditer(line):
                    coord = m_tok.group(1)
                    uncached_expr = m_tok.group(2)
                    val_str = (m_tok.group(3) or "").strip()
                    col_letters = "".join(ch for ch in coord if ch.isalpha())
                    row_digits = "".join(ch for ch in coord if ch.isdigit())
                    r_idx = int(row_digits) if row_digits else 1
                    c_idx = 0
                    for ch in col_letters:
                        c_idx = c_idx * 26 + (ord(ch) - 64)
                    c_idx = max(1, c_idx)
                    max_r = max(max_r, r_idx)
                    max_c = max(max_c, c_idx)
                    cell_ref = f"{sheet_name}!{coord}"

                    if uncached_expr is not None:
                        formula_str = uncached_expr.strip()
                        s_uncached.append(cell_ref)
                        all_uncached.append(cell_ref)
                        s_cells.append(
                            CellProvenance(
                                file_name=filename,
                                sheet_name=sheet_name,
                                cell_ref=cell_ref,
                                coordinate=coord,
                                row=r_idx,
                                column=c_idx,
                                end_row=r_idx,
                                end_column=c_idx,
                                raw_value=formula_str,
                                cached_value=None,
                                normalized_value=None,
                                number_format=None,
                                formula=formula_str,
                                uncached_formula=True,
                                merged_range=None,
                                is_hidden_sheet=is_hidden,
                                data_type="formula_uncached",
                                currency_hint=None,
                                extracted_at=extracted_at,
                                confidence=0.0,
                                verification_status="uncached_formula",
                            )
                        )
                    else:
                        _, norm_val, ccy_hint = _classify_scalar_value(val_str)
                        s_cells.append(
                            CellProvenance(
                                file_name=filename,
                                sheet_name=sheet_name,
                                cell_ref=cell_ref,
                                coordinate=coord,
                                row=r_idx,
                                column=c_idx,
                                end_row=r_idx,
                                end_column=c_idx,
                                raw_value=val_str,
                                cached_value=val_str,
                                normalized_value=norm_val,
                                number_format=None,
                                formula=None,
                                uncached_formula=False,
                                merged_range=None,
                                is_hidden_sheet=is_hidden,
                                data_type="text",
                                currency_hint=ccy_hint,
                                extracted_at=extracted_at,
                                confidence=0.95,
                                verification_status="verified_cell",
                            )
                        )
            sheets_out.append(
                ExtractedSheet(
                    sheet_name=sheet_name,
                    sheet_state="hidden" if is_hidden else "visible",
                    is_hidden=is_hidden,
                    has_financial_data=_sheet_has_financial_signals(s_cells, sheet_name),
                    max_row=max_r,
                    max_column=max_c,
                    merged_ranges=(),
                    cells=tuple(s_cells),
                    uncached_formula_cells=tuple(s_uncached),
                    rendered_text=block,
                )
            )
            all_cells.extend(s_cells)

        if sheets_out:
            return DocumentExtractionBundle(
                file_name=filename,
                file_format=suffix.lstrip(".") or "xlsx",
                sha256=digest,
                extracted_at=extracted_at,
                extraction_mode="rehydrated_multisheet_text",
                full_text=text,
                page_count=len(sheets_out),
                sheets=tuple(sheets_out),
                cells=tuple(all_cells),
                has_uncached_formulas=bool(all_uncached),
                uncached_formula_refs=tuple(all_uncached),
                warnings=(),
                is_incomplete_source=False if is_confirmed_complete is None else not is_confirmed_complete,
            )

    # Si un classeur Excel/multi-feuilles (ou PDF multi-pages) n'a pas le marqueur complet "=== ONGLET:"
    # et n'a pas été explicitement confirmé complet par ses métadonnées d'extraction, il peut s'agir
    # d'un ancien texte partiel (ex: 1re feuille CSV `pandas.read_excel`). Ne jamais certifier sur cette base.
    is_legacy_incomplete = (
        (not is_confirmed_complete)
        and (suffix in EXCEL_SUFFIXES or (is_confirmed_complete is False))
    )
    fallback_bundle = _extract_delimited_or_text_bundle(filename, text, suffix or ".txt", extracted_at, digest)
    if is_legacy_incomplete:
        return DocumentExtractionBundle(
            file_name=fallback_bundle.file_name,
            file_format=fallback_bundle.file_format,
            sha256=fallback_bundle.sha256,
            extracted_at=fallback_bundle.extracted_at,
            extraction_mode="legacy_partial_text",
            full_text=fallback_bundle.full_text,
            page_count=fallback_bundle.page_count,
            sheets=fallback_bundle.sheets,
            cells=fallback_bundle.cells,
            has_uncached_formulas=fallback_bundle.has_uncached_formulas,
            uncached_formula_refs=fallback_bundle.uncached_formula_refs,
            warnings=(
                *fallback_bundle.warnings,
                "Source textuelle héritée potentiellement partielle (binaire original absent ou non retraité) : certification bloquée.",
            ),
            is_incomplete_source=True,
        )
    return fallback_bundle


def extract_text(filename: str, content: bytes, *, image_ocr=None) -> str:
    """Extrait le texte intégral sans perte (toutes les feuilles Excel, tableaux DOCX et pages PDF)."""
    bundle = extract_document_bundle(filename, content, image_ocr=image_ocr)
    return bundle.full_text


def classify_document(text: str, filename: str) -> str:
    haystack = f"{filename}\n{text}".lower()
    rules = (
        (
            "purchase_order",
            (
                "purchase order",
                "bon de commande",
                "commande fournisseur",
                "orden de compra",
                "po number",
                "n° de commande",
            ),
        ),
        (
            "invoice",
            (
                "invoice",
                "facture",
                "factura",
                "rechnung",
                "fattura",
                "tax",
                "tps",
                "tvq",
                "gst",
                "qst",
                "hst",
                "tva",
                "vat",
                "mwst",
                "sous-total",
                "subtotal",
                "net à payer",
                "net a payer",
                "amount due",
                "montant dû",
                "po nr",
            ),
        ),
        ("contract", ("agreement", "contrat", "whereas", "clause", "party", "signataire", "bail", "nda")),
        ("receipt", ("receipt", "reçu", "recu", "merci de votre achat", "ticket de caisse", "pos receipt")),
        ("statement", ("bank statement", "relevé bancaire", "releve de compte", "statement", "relevé", "opening balance", "closing balance", "solde d'ouverture", "solde de clôture")),
        ("inventory", ("inventory", "inventaire", "stock count", "sku", "quantité en stock", "warehouse stock", "entrepôt")),
        ("hr_document", ("payroll", "fiche de paie", "bulletin de salaire", "timesheet", "feuille de temps", "contrat de travail", "salaire brut", "heures travaillées")),
        ("financial_report", ("income statement", "état des résultats", "bilan comptable", "balance sheet", "profit and loss", "p&l", "ebitda", "cash flow statement")),
        ("identity", ("passport", "permis", "driver licence", "date of birth")),
    )
    for label, needles in rules:
        if any(needle in haystack for needle in needles):
            return label
    return "unclassified"
