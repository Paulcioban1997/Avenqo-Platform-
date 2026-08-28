"""Gestion transactionnelle des crédits IA Avenqo par tenant."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AICreditBalance, AICreditTransaction
from payments import get_credit_pack, get_plan


class InsufficientAICreditsError(ValueError):
    pass


class AICreditService:
    """Gère le quota mensuel et les crédits achetés qui n'expirent pas."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def current_period() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def get_balance(self, company_id: UUID, plan_code: str) -> AICreditBalance:
        balance = self._session.scalar(
            select(AICreditBalance).where(AICreditBalance.company_id == company_id)
        )
        allowance = get_plan(plan_code).included_ai_credits
        # Enterprise reste contractuel : None signifie que la limite est gérée
        # par contrat/override et n'est pas bloquée par le wallet standard.
        standard_allowance = int(allowance or 0)
        period = self.current_period()

        if balance is None:
            balance = AICreditBalance(
                company_id=company_id,
                billing_period=period,
                monthly_allowance=standard_allowance,
                monthly_remaining=standard_allowance,
                purchased_remaining=0,
            )
            self._session.add(balance)
            self._session.flush()
            return balance

        if balance.billing_period != period:
            balance.billing_period = period
            balance.monthly_allowance = standard_allowance
            balance.monthly_remaining = standard_allowance
            self._session.add(AICreditTransaction(
                company_id=company_id,
                transaction_type="monthly_reset",
                amount=standard_allowance,
                description=f"Monthly AI credits for {period}",
            ))
            self._session.flush()
        elif balance.monthly_allowance != standard_allowance:
            consumed = max(balance.monthly_allowance - balance.monthly_remaining, 0)
            balance.monthly_allowance = standard_allowance
            balance.monthly_remaining = max(standard_allowance - consumed, 0)
            self._session.flush()

        return balance

    def ensure_available(self, company_id: UUID, plan_code: str, amount: int = 1) -> None:
        if amount <= 0:
            return
        if get_plan(plan_code).included_ai_credits is None:
            return
        balance = self.get_balance(company_id, plan_code)
        if balance.total_remaining < amount:
            raise InsufficientAICreditsError("Your Avenqo AI credit balance has been exhausted.")

    def consume(self, company_id: UUID, plan_code: str, amount: int = 1) -> AICreditBalance:
        if amount <= 0:
            return self.get_balance(company_id, plan_code)
        if get_plan(plan_code).included_ai_credits is None:
            return self.get_balance(company_id, plan_code)

        balance = self.get_balance(company_id, plan_code)
        if balance.total_remaining < amount:
            raise InsufficientAICreditsError("Your Avenqo AI credit balance has been exhausted.")

        from_monthly = min(balance.monthly_remaining, amount)
        balance.monthly_remaining -= from_monthly
        remaining = amount - from_monthly
        if remaining:
            balance.purchased_remaining -= remaining

        self._session.add(AICreditTransaction(
            company_id=company_id,
            transaction_type="usage",
            amount=-amount,
            description="AI request usage",
        ))
        self._session.flush()
        return balance

    def grant_pack(self, company_id: UUID, pack_code: str, reference_id: str) -> AICreditBalance:
        existing = self._session.scalar(
            select(AICreditTransaction).where(AICreditTransaction.reference_id == reference_id)
        )
        balance = self.get_balance(company_id, self._plan_code_for_balance(company_id))
        if existing is not None:
            return balance

        pack = get_credit_pack(pack_code)
        balance.purchased_remaining += pack.credits
        self._session.add(AICreditTransaction(
            company_id=company_id,
            transaction_type="purchase",
            amount=pack.credits,
            reference_id=reference_id,
            description=pack.code,
        ))
        self._session.flush()
        return balance

    def _plan_code_for_balance(self, company_id: UUID) -> str:
        from backend.app.models import BillingAccount

        account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company_id)
        )
        return account.plan_code if account is not None else "demo"
