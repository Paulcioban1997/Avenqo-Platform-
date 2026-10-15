"""Local-only deploy + rollback rehearsal on a disposable PostgreSQL (synthetic data).

Refuses any host other than localhost/127.0.0.1 and any database not named
``rollback_sim*``. Never reads Railway, Sandbox or Production settings.

Usage:
  python scripts/local_rollback_rehearsal.py seed      # ORM seed (3 synthetic tenants)
  python scripts/local_rollback_rehearsal.py counts    # print per-table row counts
"""

from __future__ import annotations

import json
import os
import sys
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.models import Company, CompanyMembership, CRMClient, User, UserRole
from tests.subscription_helpers import add_active_subscription


def _engine():
    raw = os.environ.get("ALEMBIC_DATABASE_URL", "")
    url = make_url(raw)
    if url.host not in {"localhost", "127.0.0.1"}:
        sys.exit("refused: host must be localhost")
    if not str(url.database or "").startswith("rollback_sim"):
        sys.exit("refused: database must start with rollback_sim")
    return create_engine(url)


def seed() -> None:
    engine = _engine()
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        for slug in ("sim-a", "sim-b", "sim-c"):
            company = Company(
                name=f"Co {slug}", slug=slug, email=f"{slug}@example.com", country="CA",
                timezone="America/Toronto", industry="Retail", subscription_plan="professional",
            )
            session.add(company)
            session.flush()
            add_active_subscription(session, company)
            user = User(
                company_id=company.id, first_name="Syn", last_name=slug,
                email=f"user-{uuid4()}@example.com", password_hash="hash", role=UserRole.OWNER,
            )
            session.add(user)
            session.flush()
            session.add(CompanyMembership(user_id=user.id, company_id=company.id, role=UserRole.OWNER, is_active=True))
            for i in range(5):
                session.add(CRMClient(company_id=company.id, first_name="C", last_name=f"{slug}-{i}", email=f"{slug}-{i}@example.com"))
        session.commit()


def counts() -> None:
    engine = _engine()
    with engine.connect() as conn:
        out = {}
        for table in ("companies", "users", "company_memberships", "crm_clients"):
            out[table] = conn.execute(text(f"select count(*) from {table}")).scalar()
        per_tenant = conn.execute(
            text("select company_id::text, count(*) from crm_clients group by 1 order by 1")
        ).all()
        out["crm_per_tenant"] = sorted(int(c) for _, c in per_tenant)
        print(json.dumps(out))


if __name__ == "__main__":
    {"seed": seed, "counts": counts}[sys.argv[1]]()
