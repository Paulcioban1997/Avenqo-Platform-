"""Resumable re-encryption of stored connector credentials after a key rotation.

Ordering contract for ``CONNECTOR_ENCRYPTION_KEYS`` (comma separated):
the first key encrypts, every listed key may decrypt. A rotation is therefore
``new,old`` -> ``rotate`` -> ``verify`` -> ``new``. Putting ``old`` back in first
position and running ``rotate`` again is the rollback path, which is why the
previous key must stay configured until ``verify`` reports no dependency on it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.commerce_connection import CommerceConnection
from backend.app.models.crm import CRMCalendarConnection
from backend.app.services.connector_secret_cipher import ConnectorSecretError

ENCRYPTED_CREDENTIAL_MODELS: tuple[type, ...] = (CommerceConnection, CRMCalendarConnection)
UNDECRYPTABLE = "undecryptable"


def generate_connector_key() -> str:
    return Fernet.generate_key().decode("ascii")


def key_fingerprint(key: str) -> str:
    """Stable, non-reversible identifier safe for logs and reports."""
    return hashlib.sha256(key.strip().encode("ascii")).hexdigest()[:12]


@dataclass(slots=True)
class TableReport:
    table: str
    total: int = 0
    by_key: dict[str, int] = field(default_factory=dict)
    rotated: int = 0
    failed_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "total": self.total,
            "by_key": dict(self.by_key),
            "rotated": self.rotated,
            "failed_ids": list(self.failed_ids),
        }


@dataclass(slots=True)
class RotationReport:
    primary_fingerprint: str
    dry_run: bool
    tables: list[TableReport]

    @property
    def undecryptable(self) -> int:
        return sum(t.by_key.get(UNDECRYPTABLE, 0) for t in self.tables)

    @property
    def not_on_primary(self) -> int:
        return sum(
            count
            for t in self.tables
            for fp, count in t.by_key.items()
            if fp != self.primary_fingerprint
        )

    @property
    def failed(self) -> int:
        return sum(len(t.failed_ids) for t in self.tables)

    @property
    def safe_to_retire_previous_keys(self) -> bool:
        return self.not_on_primary == 0 and self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_fingerprint": self.primary_fingerprint,
            "dry_run": self.dry_run,
            "undecryptable": self.undecryptable,
            "not_on_primary": self.not_on_primary,
            "failed": self.failed,
            "safe_to_retire_previous_keys": self.safe_to_retire_previous_keys,
            "tables": [t.to_dict() for t in self.tables],
        }


class ConnectorKeyRotationService:
    def __init__(self, session: Session, keys: Sequence[str]) -> None:
        cleaned = [k.strip() for k in keys if k and k.strip()]
        if not cleaned:
            raise ConnectorSecretError("Connector encryption is not configured")
        if len(set(cleaned)) != len(cleaned):
            raise ConnectorSecretError("Connector encryption keys contain duplicates")
        try:
            self._fernets = [(key_fingerprint(k), Fernet(k.encode("ascii"))) for k in cleaned]
        except (ValueError, UnicodeEncodeError) as exc:
            raise ConnectorSecretError("Connector encryption key is invalid") from exc
        self._session = session
        self._primary_fp, self._primary = self._fernets[0]
        self._multi = MultiFernet([f for _, f in self._fernets])

    @property
    def primary_fingerprint(self) -> str:
        return self._primary_fp

    def _identify(self, token: str) -> str:
        raw = token.encode("ascii")
        for fp, fernet in self._fernets:
            try:
                fernet.decrypt(raw)
                return fp
            except InvalidToken:
                continue
        return UNDECRYPTABLE

    def _rows(self, model: type, *, lock: bool, batch_size: int) -> Iterator[list[Any]]:
        last_id = None
        while True:
            stmt = select(model).where(model.encrypted_credentials.is_not(None)).order_by(model.id)
            if last_id is not None:
                stmt = stmt.where(model.id > last_id)
            stmt = stmt.limit(batch_size)
            if lock:
                stmt = stmt.with_for_update(skip_locked=False)
            batch = list(self._session.scalars(stmt))
            if not batch:
                return
            yield batch
            last_id = batch[-1].id

    def status(self, *, batch_size: int = 200) -> RotationReport:
        tables = []
        for model in ENCRYPTED_CREDENTIAL_MODELS:
            report = TableReport(table=model.__tablename__)
            for batch in self._rows(model, lock=False, batch_size=batch_size):
                for row in batch:
                    report.total += 1
                    fp = self._identify(row.encrypted_credentials)
                    report.by_key[fp] = report.by_key.get(fp, 0) + 1
            tables.append(report)
        self._session.rollback()
        return RotationReport(self._primary_fp, dry_run=True, tables=tables)

    def rotate(self, *, batch_size: int = 100, dry_run: bool = True) -> RotationReport:
        """Re-encrypt every row not already on the primary key, one committed batch at a time."""
        tables = []
        for model in ENCRYPTED_CREDENTIAL_MODELS:
            report = TableReport(table=model.__tablename__)
            for batch in self._rows(model, lock=not dry_run, batch_size=batch_size):
                for row in batch:
                    report.total += 1
                    token = row.encrypted_credentials
                    fp = self._identify(token)
                    report.by_key[fp] = report.by_key.get(fp, 0) + 1
                    if fp in (self._primary_fp, UNDECRYPTABLE):
                        if fp == UNDECRYPTABLE:
                            report.failed_ids.append(str(row.id))
                        continue
                    rotated = self._multi.rotate(token.encode("ascii"))
                    if not self._same_plaintext(token, rotated):
                        report.failed_ids.append(str(row.id))
                        continue
                    if not dry_run:
                        row.encrypted_credentials = rotated.decode("ascii")
                    report.rotated += 1
                if dry_run:
                    self._session.rollback()
                else:
                    self._session.commit()
            tables.append(report)
        return RotationReport(self._primary_fp, dry_run=dry_run, tables=tables)

    def _same_plaintext(self, original: str, rotated: bytes) -> bool:
        try:
            before = json.loads(self._multi.decrypt(original.encode("ascii")))
            after = json.loads(self._primary.decrypt(rotated))
        except (InvalidToken, ValueError):
            return False
        return isinstance(after, dict) and before == after
