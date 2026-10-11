"""Identify and optionally restore included AI credits for one admin tenant.

Usage:
    python scripts/restore_admin_voice_credits.py --email paulmircea15@gmail.com
    python scripts/restore_admin_voice_credits.py --email paulmircea15@gmail.com --apply --company-id <uuid>

Safety:
  - Dry-run by default. Never writes unless --apply and --company-id match.
  - Touches only the named company's included monthly_used.
  - Does not change Stripe subscriptions, purchased packs, or other tenants.
  - Does not print secrets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import get_settings
from backend.app.database import SessionLocal
from backend.app.models import Company, TenantAICreditBalance, TenantAICreditLedgerEntry, User
from backend.app.services.audit_log_service import AuditLogService


def identify_admin_tenant(session, email: str) -> tuple[User, Company]:
    normalized = email.strip().lower()
    user = session.scalar(select(User).where(User.email == normalized, User.is_active.is_(True)))
    if user is None:
        raise ValueError(f"No active user for {normalized}")
    company = session.get(Company, user.company_id)
    if company is None:
        raise ValueError("The user has no company")
    if not user.is_platform_admin and user.role.value not in {"OWNER", "ADMIN"}:
        raise ValueError("The user is not a platform admin or tenant owner/admin")
    return user, company


def snapshot_other_balances(session, company_id: UUID) -> dict[UUID, tuple[int, int]]:
    rows = session.scalars(
        select(TenantAICreditBalance).where(TenantAICreditBalance.company_id != company_id)
    ).all()
    return {row.company_id: (row.monthly_used, row.purchased_balance) for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Admin account email")
    parser.add_argument("--apply", action="store_true", help="Write the ledger adjustment")
    parser.add_argument("--company-id", help="Required with --apply to confirm the tenant")
    parser.add_argument("--reason", default="Owner-requested Voice included-credit restore to 100%")
    args = parser.parse_args()

    settings = get_settings()
    with SessionLocal() as session:
        user, company = identify_admin_tenant(session, args.email)
        usage = AIUsageService(session, AIQuotaPolicy(settings), settings.avenqo_provider_cost_per_credit_usd)
        before = usage.get_credit_balance(company.id, company.subscription_plan)
        others_before = snapshot_other_balances(session, company.id)
        other_count = session.scalar(select(func.count()).select_from(TenantAICreditBalance).where(
            TenantAICreditBalance.company_id != company.id
        ))
        print("identified_email", user.email)
        print("platform_admin", user.is_platform_admin)
        print("company_id", company.id)
        print("company_name", company.name)
        print("company_slug", company.slug)
        print("subscription_plan", company.subscription_plan)
        print("billing_period", before["billing_period"])
        print("monthly_included", before["monthly_included"])
        print("monthly_used", before["monthly_used"])
        print("monthly_remaining", before["monthly_remaining"])
        print("purchased_remaining", before["purchased_remaining"])
        print("total_remaining", before["total_remaining"])
        print("other_credit_accounts", other_count)
        if not args.apply:
            print("mode", "dry-run")
            print("no_write", True)
            return 0
        if str(company.id) != str(args.company_id or ""):
            print("ÉCHEC : --company-id must match the identified tenant", file=sys.stderr)
            return 1
        period = str(before["billing_period"])
        result = usage.restore_included_monthly_credits(
            company.id,
            company.subscription_plan,
            idempotency_key=f"manual-included-restore:{company.id}:{period}:voice",
            reason=args.reason,
            actor_user_id=user.id,
        )
        AuditLogService(session).record(
            actor_user_id=user.id,
            action="voice_included_credits_restored",
            target_type="company",
            target_id=str(company.id),
            company_id=company.id,
            metadata={
                "billing_period": period,
                "before": result["before"],
                "after": result["after"],
                "applied": result["applied"],
            },
        )
        session.commit()
        others_after = snapshot_other_balances(session, company.id)
        if others_before != others_after:
            print("ÉCHEC : other tenant credit balances changed", file=sys.stderr)
            return 1
        ledger = session.scalar(
            select(TenantAICreditLedgerEntry).where(
                TenantAICreditLedgerEntry.company_id == company.id,
                TenantAICreditLedgerEntry.transaction_type == "manual_included_restore",
            )
        )
        print("mode", "apply")
        print("applied", result["applied"])
        print("after_monthly_used", result["after"]["monthly_used"])
        print("after_monthly_remaining", result["after"]["monthly_remaining"])
        print("after_total_remaining", result["after"]["total_remaining"])
        print("ledger_recorded", ledger is not None)
        print("other_accounts_unchanged", True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
