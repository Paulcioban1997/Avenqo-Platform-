"""Extraction réelle de texte à partir des formats déjà supportés par Avenqo."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path


SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xlsx",
    ".xls",
}


class UnsupportedDocumentError(ValueError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocumentError(
            f"Format non pris en charge : {suffix or 'sans extension'}. "
            f"Formats acceptés : {', '.join(sorted(SUPPORTED_SUFFIXES))}."
        )
    if not content:
        return ""
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if suffix == ".docx":
        from docx import Document

        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs).strip()
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd

        frame = pd.read_excel(io.BytesIO(content))
        return frame.to_csv(index=False)
    return content.decode("utf-8", errors="replace").strip()


def classify_document(text: str, filename: str) -> str:
    haystack = f"{filename}\n{text}".lower()
    rules = (
        ("invoice", ("invoice", "facture", "tax", "tps", "tvq", "gst")),
        ("contract", ("agreement", "contrat", "whereas", "clause", "party")),
        ("receipt", ("receipt", "reçu", "merci de votre achat")),
        ("identity", ("passport", "permis", "driver licence", "date of birth")),
        ("statement", ("statement", "relevé", "balance")),
    )
    for label, needles in rules:
        if any(needle in haystack for needle in needles):
            return label
    return "unclassified"
