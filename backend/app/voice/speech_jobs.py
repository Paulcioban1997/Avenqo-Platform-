"""Bounded, durable speech compute receipts. No audio, text, tools or secrets.

This is a worker-local SQLite journal, NOT the active Avenqo database. Receipts
measure wall-clock inference (including work completed after HTTP cancellation),
not GPU utilization or supplier invoices. Tenant attribution stays in Avenqo.
"""
import math
import sqlite3
import threading
import time
from decimal import Decimal
from uuid import UUID


class SpeechJobConflict(ValueError):
    pass


class SpeechJobJournal:
    def __init__(self, path=":memory:", *, capacity=1000):
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS speech_jobs (
            id TEXT PRIMARY KEY, role TEXT NOT NULL, model TEXT NOT NULL,
            revision TEXT NOT NULL, status TEXT NOT NULL, started REAL NOT NULL,
            inference_seconds REAL)""")
        # A process restart cannot prove whether its unfinished kernel completed.
        # Preserve the uncertainty; never settle an interrupted worker as free.
        self.db.execute("UPDATE speech_jobs SET status='unknown' WHERE status='running'")
        self.db.commit()
        self.capacity = capacity
        self.durable = str(path) != ":memory:"

    def start(self, job_id, artifact, role):
        if str(UUID(job_id)) != job_id:
            raise ValueError("Canonical opaque UUID required")
        with self._lock:
            if self.db.execute("SELECT 1 FROM speech_jobs WHERE id=?", (job_id,)).fetchone():
                raise SpeechJobConflict("Job already accepted; reconcile receipt, do not replay")
            if self.db.execute("SELECT count(*) FROM speech_jobs").fetchone()[0] >= self.capacity:
                raise SpeechJobConflict("Usage journal full; reconciliation required")
            self.db.execute("INSERT INTO speech_jobs(id,role,model,revision,status,started) VALUES(?,?,?,?,?,?)",
                            (job_id, role, artifact.model_id, artifact.revision, "running", time.time()))
            self.db.commit()

    def finish(self, job_id, seconds, status):
        if status not in {"completed", "failed"} or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid measured inference receipt")
        with self._lock:
            self.db.execute("UPDATE speech_jobs SET status=?, inference_seconds=? WHERE id=? AND status='running'",
                            (status, seconds, job_id))
            self.db.commit()

    def receipt(self, job_id):
        with self._lock:
            row = self.db.execute("SELECT * FROM speech_jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def has_unknown(self):
        with self._lock:
            return self.db.execute("SELECT 1 FROM speech_jobs WHERE status='unknown' LIMIT 1").fetchone() is not None


class PilotUsageLedger:
    """Server-side attribution and idempotent reconciliation for the unpaid lab.

    No customer billing or credit debit. A live invoice/credit-ledger integration
    is deliberately not implied. Rates are explicit allocation estimates.
    """
    def __init__(self, *, company_id, call_id, rate_usd_per_compute_second=None, source=None):
        self.company_id, self.call_id = company_id, call_id
        self.rate = Decimal(str(rate_usd_per_compute_second)) if rate_usd_per_compute_second is not None else None
        if self.rate is not None and (not self.rate.is_finite() or self.rate < 0):
            raise ValueError("Invalid allocation rate")
        if self.rate == 0 and source != "existing-local-unpaid-lab":
            raise ValueError("Zero rate only describes explicitly unpaid local experiments")
        self.source, self.jobs, self.settlements = source, set(), {}

    def register(self, job_id):
        if self.rate is None or not self.source:
            raise ValueError("Unknown compute cost: pilot admission denied")
        self.jobs.add(job_id)

    def reconcile(self, receipt):
        job_id = receipt["id"]
        if job_id not in self.jobs:
            raise PermissionError("Receipt not owned by this server-bound call")
        if receipt["status"] not in {"completed", "failed"} or receipt["inference_seconds"] is None:
            raise ValueError("Unfinished/unknown computation must remain unsettled")
        seconds = Decimal(str(receipt["inference_seconds"]))
        if not seconds.is_finite() or seconds < 0:
            raise ValueError("Invalid compute duration")
        cost = seconds * self.rate
        if job_id in self.settlements and self.settlements[job_id] != cost:
            raise ValueError("Conflicting receipt")
        self.settlements[job_id] = cost
        return {"company_id": str(self.company_id), "call_id": str(self.call_id),
                "job_id": job_id, "estimated_compute_cost_usd": str(cost),
                "source": self.source, "supplier_invoice": False}
