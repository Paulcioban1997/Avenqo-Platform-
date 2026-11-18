"""Test progressive chunked streaming uploads, disk spooling, and concurrency protection."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.services.data_import_policy import (
    DataImportFileTooLargeError,
    DataImportPolicy,
    DataImportQuotaExceeded,
)
from backend.app.services.upload_streaming import (
    CHUNK_SIZE,
    TenantUploadConcurrencyTracker,
    spool_progressive_upload,
)
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _seed_company(session: Session, plan: str = "base") -> Company:
    co = Company(
        id=uuid4(),
        name="Chunk Test Co",
        slug=f"chunk-test-{uuid4().hex[:6]}",
        email=f"chunk_{uuid4().hex[:6]}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan=plan,
        currency_code="CAD",
        status="active",
    )
    session.add(co)
    session.commit()
    return co


class MockAsyncUploadFile:
    """Simulates an asynchronous streaming UploadFile delivering chunks."""

    def __init__(self, data: bytes, chunk_size: int = 1024 * 1024, filename: str = "test.csv") -> None:
        self.filename = filename
        self._bio = BytesIO(data)
        self._chunk_size = chunk_size

    async def read(self, size: int = -1) -> bytes:
        read_size = size if size > 0 else self._chunk_size
        return self._bio.read(read_size)


@pytest.mark.asyncio
async def test_streaming_spool_success_and_cleanup(db_session):
    """Verify progressive 1 MB chunk reading spools to disk and cleans up on exit."""
    company = _seed_company(db_session, "base")
    tenant = TenantContext(company_id=company.id)

    with TemporaryDirectory() as tmp_dir:
        policy = DataImportPolicy(db_session, artifact_root=Path(tmp_dir))
        tracker = TenantUploadConcurrencyTracker()

        # Create 2.5 MB of CSV data (3 chunks: 1MB, 1MB, 0.5MB)
        header = b"id,val\n"
        row = b"1,data\n" * 150000  # ~1 MB
        content = header + row * 2

        mock_file = MockAsyncUploadFile(content, chunk_size=CHUNK_SIZE)
        spool_captured_path: Path | None = None

        async with spool_progressive_upload(mock_file, tenant, policy, tracker=tracker) as (spool_path, size):
            spool_captured_path = spool_path
            assert spool_path.exists(), "Spool file must exist during context execution"
            assert size == len(content)
            assert spool_path.stat().st_size == len(content)

        # After exiting context, spool file must be cleanly deleted
        assert spool_captured_path is not None
        assert not spool_captured_path.exists(), "Spool file must be automatically deleted after context exit"


@pytest.mark.asyncio
async def test_streaming_spool_aborts_mid_stream_on_max_file_exceeded(db_session, monkeypatch):
    """Verify progressive streaming stops reading and cleans up disk if max file limit is hit."""
    company = _seed_company(db_session, "base")
    tenant = TenantContext(company_id=company.id)

    with TemporaryDirectory() as tmp_dir:
        policy = DataImportPolicy(db_session, artifact_root=Path(tmp_dir))
        # Force a small max upload limit of 1.5 MB
        monkeypatch.setattr(policy, "max_upload_bytes", lambda t, g=None: int(1.5 * 1024 * 1024))
        tracker = TenantUploadConcurrencyTracker()

        # 3 MB of data
        content = b"header\n" + b"x" * (3 * 1024 * 1024)
        mock_file = MockAsyncUploadFile(content, chunk_size=CHUNK_SIZE)

        with pytest.raises(DataImportFileTooLargeError) as exc_info:
            async with spool_progressive_upload(mock_file, tenant, policy, tracker=tracker):
                pass

        assert "supérieure à la limite autorisée" in str(exc_info.value)
        # Verify tracker released any reserved in-flight bytes
        assert tracker.get_in_flight_bytes(tenant.company_id) == 0


@pytest.mark.asyncio
async def test_streaming_spool_concurrency_protection(db_session):
    """Verify concurrent uploads per tenant are tracked and throttled at the limit."""
    company = _seed_company(db_session, "base")
    tenant = TenantContext(company_id=company.id)
    tracker = TenantUploadConcurrencyTracker()

    # Max concurrent uploads is 3
    async with tracker.reserve(tenant.company_id, max_concurrent=2) as r1:
        r1.update_bytes(100)
        assert tracker.get_in_flight_bytes(tenant.company_id) == 100

        async with tracker.reserve(tenant.company_id, max_concurrent=2) as r2:
            r2.update_bytes(200)
            assert tracker.get_in_flight_bytes(tenant.company_id) == 300

            # 3rd concurrent upload must be rejected with HTTP 429
            with pytest.raises(HTTPException) as exc_info:
                async with tracker.reserve(tenant.company_id, max_concurrent=2):
                    pass
            assert exc_info.value.status_code == 429
            assert "Trop de téléversements simultanés" in exc_info.value.detail

    # All reservations released
    assert tracker.get_in_flight_bytes(tenant.company_id) == 0


@pytest.mark.asyncio
async def test_streaming_spool_rejects_empty_file(db_session):
    """Verify empty uploads are cleanly rejected and temp files deleted."""
    company = _seed_company(db_session, "base")
    tenant = TenantContext(company_id=company.id)

    with TemporaryDirectory() as tmp_dir:
        policy = DataImportPolicy(db_session, artifact_root=Path(tmp_dir))
        mock_file = MockAsyncUploadFile(b"")

        with pytest.raises(ValueError) as exc_info:
            async with spool_progressive_upload(mock_file, tenant, policy):
                pass
        assert "vide" in str(exc_info.value)
