"""Chargement universel de fichiers de données d'entreprise (Phase 26).

Supporte CSV, XLSX, JSON et Parquet via une seule abstraction
`CompanyDatasetLoader`, avec validation stricte avant tout parsing coûteux.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from shared.ai_engine.dataset_ingestion.exceptions import (
    DatasetParseError,
    DatasetTooLarge,
    EmptyDataset,
    InvalidDatasetFile,
    UnsupportedDatasetFormat,
)

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".csv", ".xlsx", ".json", ".parquet")


@dataclass(frozen=True, slots=True)
class LoadedDataset:
    """Représentation intermédiaire, indépendante du format source."""

    rows: tuple[dict[str, Any], ...]
    columns: tuple[str, ...]
    source_format: str


class CompanyDatasetLoader:
    """Charge un fichier client dans une représentation ligne/colonne générique."""

    def __init__(self, max_upload_bytes: int) -> None:
        self._max_upload_bytes = max_upload_bytes

    def load(self, filename: str, content: bytes) -> LoadedDataset:
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise UnsupportedDatasetFormat(
                f"Format '{extension or 'inconnu'}' non supporté. "
                f"Formats acceptés : {', '.join(SUPPORTED_EXTENSIONS)}."
            )
        if not content:
            raise EmptyDataset("Le fichier envoyé est vide.")
        if len(content) > self._max_upload_bytes:
            raise DatasetTooLarge(
                f"Le fichier dépasse la taille maximale autorisée "
                f"({self._max_upload_bytes} octets)."
            )

        if extension == ".csv":
            rows = self._load_csv(content)
        elif extension == ".xlsx":
            rows = self._load_excel(content)
        elif extension == ".json":
            rows = self._load_json(content)
        else:
            rows = self._load_parquet(content)

        if not rows:
            raise EmptyDataset("Le fichier ne contient aucune ligne exploitable.")

        columns = tuple(dict.fromkeys(key for row in rows for key in row))
        if not columns:
            raise InvalidDatasetFile("Aucune colonne détectée dans le fichier.")

        normalized = tuple({key: self._coerce(value) for key, value in row.items()} for row in rows)
        return LoadedDataset(rows=normalized, columns=columns, source_format=extension.lstrip("."))

    def _load_csv(self, content: bytes) -> list[dict[str, Any]]:
        try:
            text = content.decode("utf-8-sig")
            rows = list(csv.DictReader(StringIO(text)))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise InvalidDatasetFile("CSV invalide ou encodage non supporté.") from exc
        if not rows or rows[0] is None:
            raise EmptyDataset("Le CSV doit contenir un en-tête et au moins une ligne.")
        return rows

    def _load_excel(self, content: bytes) -> list[dict[str, Any]]:
        try:
            import pandas as pd

            frame = pd.read_excel(BytesIO(content), engine="openpyxl")
        except EmptyDataset:
            raise
        except Exception as exc:  # pragma: no cover - dépend de la lib externe
            raise DatasetParseError(f"XLSX invalide ou illisible : {exc}") from exc
        return self._frame_to_rows(frame)

    def _load_json(self, content: bytes) -> list[dict[str, Any]]:
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidDatasetFile("JSON invalide ou encodage non supporté.") from exc
        if isinstance(payload, dict) and "data" in payload:
            payload = payload["data"]
        if not isinstance(payload, list):
            raise InvalidDatasetFile("Le JSON doit être une liste d'objets (ou {'data': [...]}).")
        rows: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise InvalidDatasetFile("Chaque élément JSON doit être un objet clé/valeur.")
            rows.append(item)
        return rows

    def _load_parquet(self, content: bytes) -> list[dict[str, Any]]:
        try:
            import pandas as pd

            frame = pd.read_parquet(BytesIO(content))
        except Exception as exc:  # pragma: no cover - dépend de la lib externe
            raise DatasetParseError(f"Parquet invalide ou illisible : {exc}") from exc
        return self._frame_to_rows(frame)

    @staticmethod
    def _frame_to_rows(frame: Any) -> list[dict[str, Any]]:
        records = frame.to_dict(orient="records")
        return [dict(record) for record in records]

    @staticmethod
    def _coerce(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            lowered = stripped.lower()
            if lowered in {"true", "false"}:
                return lowered == "true"
            try:
                return int(stripped)
            except ValueError:
                pass
            try:
                return float(stripped)
            except ValueError:
                pass
            try:
                return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                pass
            return stripped
        if hasattr(value, "isoformat") and isinstance(value, (datetime, date)):
            return value
        if hasattr(value, "item"):
            try:
                native = value.item()
            except Exception:
                return value
            if isinstance(native, float) and math.isnan(native):
                return None
            return native
        return value
