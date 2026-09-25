from io import BytesIO

import pytest
from reportlab.pdfgen.canvas import Canvas

from shared.ai_engine.dataset_ingestion.exceptions import DatasetParseError, UnsupportedDatasetFormat
from shared.ai_engine.dataset_ingestion.loader import CompanyDatasetLoader, SUPPORTED_EXTENSIONS


@pytest.fixture
def loader() -> CompanyDatasetLoader:
    return CompanyDatasetLoader(max_upload_bytes=1024 * 1024)


def test_supported_upload_formats_are_explicit(loader: CompanyDatasetLoader) -> None:
    assert SUPPORTED_EXTENSIONS == (".csv", ".xls", ".xlsx", ".pdf", ".json", ".txt", ".parquet")


def test_txt_table_and_plain_text_are_importable(loader: CompanyDatasetLoader) -> None:
    table = loader.load("records.txt", b"id|name\n1|Paul\n2|Ava\n")
    assert table.rows[0]["id"] == 1
    assert table.rows[1]["name"] == "Ava"

    prose = loader.load("notes.txt", b"First note\nSecond note\n")
    assert prose.rows == ({"text": "First note"}, {"text": "Second note"})


def test_pdf_text_is_importable(loader: CompanyDatasetLoader) -> None:
    buffer = BytesIO()
    document = Canvas(buffer)
    document.drawString(72, 720, "id,name")
    document.drawString(72, 700, "1,Paul")
    document.save()

    result = loader.load("records.pdf", buffer.getvalue())
    assert any("1,Paul" in row["text"] for row in result.rows)


def test_xls_is_routed_to_excel_parser(loader: CompanyDatasetLoader) -> None:
    with pytest.raises(DatasetParseError, match="XLS invalide"):
        loader.load("records.xls", b"not-an-excel-file")


def test_unlisted_format_is_rejected(loader: CompanyDatasetLoader) -> None:
    with pytest.raises(UnsupportedDatasetFormat):
        loader.load("records.docx", b"data")
