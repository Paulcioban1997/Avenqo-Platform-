"""Service d'usage IA Avenqo : compteurs par tenant, indépendants du fournisseur LLM.

Toute logique de comptage passe par ce service — jamais directement par
`ChatService` ou par un fournisseur LLM — afin que l'agrégation reste unique
et indépendante d'OpenAI/Anthropic/Gemini (Exigence Phase 31 : suivi d'usage
"provider-independent").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from threading import Lock
from uuid import UUID
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ai.usage.exceptions import AIQuotaExceededError, INSUFFICIENT_AI_CREDITS
from backend.app.ai.llm.schemas import LLMProviderAttempt
from backend.app.ai.usage.policy import (
    MONTHLY_AI_REQUESTS,
    MONTHLY_LLM_TOKENS,
    MONTHLY_PREDICTIVE_REQUESTS,
    MONTHLY_TOOL_CALLS,
    AIQuotaPolicy,
)
from backend.app.models.ai_usage import (
    TenantAICreditBalance,
    TenantAICreditLedgerEntry,
    TenantAICreditReservation,
    TenantAIProviderAttempt,
    TenantAIUsage,
)
from backend.app.models.billing import AICreditPurchase
from backend.app.models.enterprise_override import EnterpriseOverride
from payments.plans import get_plan

_DEFAULT_PLAN = "demo"
_DEFAULT_PROVIDER_COST_PER_CREDIT_USD = Decimal("0.00030")
_TENANT_LOCKS_GUARD = Lock()
_TENANT_LOCKS: dict[UUID, Lock] = {}


def _tenant_credit_lock(company_id: UUID) -> Lock:
    with _TENANT_LOCKS_GUARD:
        return _TENANT_LOCKS.setdefault(company_id, Lock())


def credits_from_provider_cost(
    provider_cost_usd: Decimal,
    provider_cost_per_credit_usd: Decimal,
) -> int:
    if provider_cost_per_credit_usd <= 0:
        raise ValueError("Provider cost per credit must be positive")
    if provider_cost_usd <= 0:
        return 0
    return int((provider_cost_usd / provider_cost_per_credit_usd).to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True, slots=True)
class CreditReservationClaim:
    reservation: TenantAICreditReservation
    acquired: bool


class AIUsageService:
    """Vérifie et incrémente l'usage IA d'un tenant pour la période courante."""

    def __init__(
        self,
        db: Session,
        policy: AIQuotaPolicy,
        provider_cost_per_credit_usd: Decimal = _DEFAULT_PROVIDER_COST_PER_CREDIT_USD,
        reservation_ttl_minutes: int = 1440,
    ) -> None:
        self._db = db
        self._policy = policy
        if provider_cost_per_credit_usd <= 0:
            raise ValueError("Provider cost per credit must be positive")
        if reservation_ttl_minutes <= 0:
            raise ValueError("Reservation TTL must be positive")
        self._provider_cost_per_credit_usd = provider_cost_per_credit_usd
        self._reservation_ttl = timedelta(minutes=reservation_ttl_minutes)

    def current_billing_period(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _get_or_create(self, company_id: UUID, plan_code: str | None) -> TenantAIUsage:
        period = self.current_billing_period()
        usage = (
            self._db.query(TenantAIUsage)
            .filter(TenantAIUsage.company_id == company_id, TenantAIUsage.billing_period == period)
            .one_or_none()
        )
        if usage is None:
            usage = TenantAIUsage(
                company_id=company_id,
                billing_period=period,
                subscription_plan=plan_code or _DEFAULT_PLAN,
            )
            self._db.add(usage)
            self._db.flush()
        elif plan_code is not None and usage.subscription_plan != plan_code:
            usage.subscription_plan = plan_code
        return usage

    def get_usage(self, company_id: UUID, plan_code: str | None) -> TenantAIUsage:
        """Lecture seule de l'usage courant (sans incrément)."""

        return self._get_or_create(company_id, plan_code)

    def ensure_quota_available(self, company_id: UUID, plan_code: str | None) -> None:
        """Vérifie le quota `monthly_ai_requests` AVANT tout appel LLM/outil.

        Ne lève jamais l'erreur brute d'un fournisseur : uniquement
        `AIQuotaExceededError`, un message sûr et générique.
        """

        limit = self.limit_for(company_id, plan_code, MONTHLY_AI_REQUESTS)
        if limit is None:
            return
        credits = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(company_id, credits)
        included_available = max(
            limit - credits.monthly_used - credits.included_reserved,
            0,
        )
        purchased_available = max(
            credits.purchased_balance - credits.purchased_reserved,
            0,
        )
        if included_available + purchased_available <= 0:
            raise AIQuotaExceededError(INSUFFICIENT_AI_CREDITS)

    def get_credit_balance(self, company_id: UUID, plan_code: str | None) -> dict[str, int | str | None]:
        credits = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(company_id, credits)
        included = self.limit_for(company_id, plan_code, MONTHLY_AI_REQUESTS)
        monthly_remaining = (
            None
            if included is None
            else max(included - credits.monthly_used, 0)
        )
        purchased_remaining = credits.purchased_balance
        total = None if monthly_remaining is None else monthly_remaining + purchased_remaining
        return {
            "billing_period": credits.monthly_period,
            "monthly_included": included,
            "monthly_used": credits.monthly_used,
            "monthly_remaining": monthly_remaining,
            "purchased_remaining": purchased_remaining,
            "total_remaining": total,
        }

    def _record_credit_transaction(
        self,
        company_id: UUID,
        balance: TenantAICreditBalance,
        *,
        idempotency_key: str,
        transaction_type: str,
        included_delta: int = 0,
        purchased_delta: int = 0,
        included_reserved_delta: int = 0,
        purchased_reserved_delta: int = 0,
        reference_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._db.add(TenantAICreditLedgerEntry(
            company_id=company_id,
            idempotency_key=idempotency_key,
            transaction_type=transaction_type,
            reference_id=reference_id,
            billing_period=balance.monthly_period,
            included_delta=included_delta,
            purchased_delta=purchased_delta,
            included_reserved_delta=included_reserved_delta,
            purchased_reserved_delta=purchased_reserved_delta,
            monthly_used_after=balance.monthly_used,
            purchased_balance_after=balance.purchased_balance,
            included_reserved_after=balance.included_reserved,
            purchased_reserved_after=balance.purchased_reserved,
            details=details or {},
        ))

    def add_purchased_credits(
        self,
        company_id: UUID,
        credits: int,
        *,
        idempotency_key: str | None = None,
        reference_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> TenantAICreditBalance:
        if credits <= 0:
            raise ValueError("Credit amount must be positive")
        ledger_key = idempotency_key or f"credit-grant:{company_id}:{uuid4()}"
        balance = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(company_id, balance)
        existing = self._db.scalar(
            select(TenantAICreditLedgerEntry.id).where(
                TenantAICreditLedgerEntry.idempotency_key == ledger_key
            )
        )
        if existing is not None:
            return balance
        balance.purchased_balance += credits
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=ledger_key,
            transaction_type="purchase_grant",
            purchased_delta=credits,
            reference_id=reference_id,
            details=details,
        )
        self._db.flush()
        return balance

    def reverse_purchased_credits(
        self,
        company_id: UUID,
        credits: int,
        *,
        idempotency_key: str,
        reference_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> int:
        if credits <= 0:
            return 0
        balance = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(company_id, balance)
        existing = self._db.scalar(
            select(TenantAICreditLedgerEntry.id).where(
                TenantAICreditLedgerEntry.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return 0
        reversed_credits = min(
            credits,
            max(balance.purchased_balance - balance.purchased_reserved, 0),
        )
        balance.purchased_balance -= reversed_credits
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=idempotency_key,
            transaction_type="purchase_refund",
            purchased_delta=-reversed_credits,
            reference_id=reference_id,
            details=details,
        )
        self._db.flush()
        return reversed_credits

    def estimate_credits(self, provider_cost_usd: Decimal | None) -> int:
        if provider_cost_usd is None:
            return 1
        return max(
            credits_from_provider_cost(
                provider_cost_usd,
                self._provider_cost_per_credit_usd,
            ),
            1,
        )

    def _reserve_purchase_lots(
        self,
        company_id: UUID,
        credits: int,
    ) -> list[dict[str, object]]:
        remaining = credits
        allocations: list[dict[str, object]] = []
        purchases = self._db.scalars(
            select(AICreditPurchase)
            .where(
                AICreditPurchase.company_id == company_id,
                AICreditPurchase.credits_remaining > AICreditPurchase.credits_reserved,
            )
            .order_by(AICreditPurchase.created_at, AICreditPurchase.id)
            .with_for_update()
        ).all()
        for purchase in purchases:
            available = purchase.credits_remaining - purchase.credits_reserved
            allocated = min(remaining, available)
            if allocated <= 0:
                continue
            purchase.credits_reserved += allocated
            allocations.append({"purchase_id": str(purchase.id), "credits": allocated})
            remaining -= allocated
            if remaining == 0:
                break
        if remaining:
            allocations.append({"purchase_id": None, "credits": remaining})
        return allocations

    def _settle_purchase_allocations(
        self,
        allocations: list[dict],
        purchased_credits: int,
    ) -> None:
        remaining_to_consume = purchased_credits
        for allocation in allocations:
            allocated = int(allocation.get("credits") or 0)
            purchase_id = allocation.get("purchase_id")
            consumed = min(remaining_to_consume, allocated)
            if purchase_id:
                purchase = self._db.scalar(
                    select(AICreditPurchase)
                    .where(AICreditPurchase.id == UUID(str(purchase_id)))
                    .with_for_update()
                )
                if purchase is not None:
                    purchase.credits_reserved = max(purchase.credits_reserved - allocated, 0)
                    purchase.credits_remaining = max(purchase.credits_remaining - consumed, 0)
            remaining_to_consume -= consumed

    def _consume_purchase_lots(self, company_id: UUID, credits: int) -> None:
        remaining = credits
        purchases = self._db.scalars(
            select(AICreditPurchase)
            .where(
                AICreditPurchase.company_id == company_id,
                AICreditPurchase.credits_remaining > AICreditPurchase.credits_reserved,
            )
            .order_by(AICreditPurchase.created_at, AICreditPurchase.id)
            .with_for_update()
        ).all()
        for purchase in purchases:
            available = purchase.credits_remaining - purchase.credits_reserved
            consumed = min(remaining, available)
            if consumed <= 0:
                continue
            purchase.credits_remaining -= consumed
            remaining -= consumed
            if remaining == 0:
                break

    def reserve_credits(
        self,
        company_id: UUID,
        plan_code: str | None,
        avenqo_request_id: str,
        estimated_credits: int,
    ) -> TenantAICreditReservation:
        return self.claim_credit_reservation(
            company_id,
            plan_code,
            avenqo_request_id,
            estimated_credits,
        ).reservation

    def claim_credit_reservation(
        self,
        company_id: UUID,
        plan_code: str | None,
        avenqo_request_id: str,
        estimated_credits: int,
    ) -> CreditReservationClaim:
        with _tenant_credit_lock(company_id):
            return self._claim_credit_reservation_locked(
                company_id,
                plan_code,
                avenqo_request_id,
                estimated_credits,
            )

    def _claim_credit_reservation_locked(
        self,
        company_id: UUID,
        plan_code: str | None,
        avenqo_request_id: str,
        estimated_credits: int,
    ) -> CreditReservationClaim:
        if estimated_credits <= 0:
            raise ValueError("Estimated credits must be positive")
        self._lock_credit_account(company_id)
        balance = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(company_id, balance)
        existing = self._db.scalar(
            select(TenantAICreditReservation).where(
                TenantAICreditReservation.company_id == company_id,
                TenantAICreditReservation.avenqo_request_id == avenqo_request_id,
            )
        )
        if existing is not None:
            return CreditReservationClaim(existing, acquired=False)

        limit = self.limit_for(company_id, plan_code, MONTHLY_AI_REQUESTS)
        if limit is None:
            included_reservation = 0
            purchased_reservation = 0
            allocations: list[dict[str, object]] = []
        else:
            included_available = max(
                limit - balance.monthly_used - balance.included_reserved,
                0,
            )
            purchased_available = max(
                balance.purchased_balance - balance.purchased_reserved,
                0,
            )
            if estimated_credits > included_available + purchased_available:
                raise AIQuotaExceededError(INSUFFICIENT_AI_CREDITS)
            included_reservation = min(estimated_credits, included_available)
            purchased_reservation = estimated_credits - included_reservation
            balance.included_reserved += included_reservation
            balance.purchased_reserved += purchased_reservation
            allocations = self._reserve_purchase_lots(company_id, purchased_reservation)

        reservation = TenantAICreditReservation(
            company_id=company_id,
            avenqo_request_id=avenqo_request_id,
            billing_period=balance.monthly_period,
            estimated_credits=estimated_credits,
            reserved_included=included_reservation,
            reserved_purchased=purchased_reservation,
            purchase_allocations=allocations,
        )
        self._db.add(reservation)
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=f"ai-reservation:{company_id}:{avenqo_request_id}",
            transaction_type="ai_reservation",
            included_reserved_delta=included_reservation,
            purchased_reserved_delta=purchased_reservation,
            reference_id=avenqo_request_id,
            details={"estimated_credits": estimated_credits},
        )
        self._db.commit()
        self._db.refresh(reservation)
        return CreditReservationClaim(reservation, acquired=True)

    def release_reservation(
        self,
        company_id: UUID,
        avenqo_request_id: str,
        *,
        reason: str,
    ) -> TenantAICreditReservation | None:
        self._lock_credit_account(company_id)
        reservation = self._db.scalar(
            select(TenantAICreditReservation)
            .where(
                TenantAICreditReservation.company_id == company_id,
                TenantAICreditReservation.avenqo_request_id == avenqo_request_id,
            )
            .with_for_update()
        )
        if reservation is None or reservation.status != "reserved":
            return reservation
        balance = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(
            company_id,
            balance,
            exclude_request_id=avenqo_request_id,
        )
        balance.included_reserved -= reservation.reserved_included
        balance.purchased_reserved -= reservation.reserved_purchased
        self._settle_purchase_allocations(reservation.purchase_allocations, 0)
        reservation.status = "released"
        reservation.settled_at = datetime.now(timezone.utc)
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=f"ai-release:{company_id}:{avenqo_request_id}",
            transaction_type="ai_release",
            included_reserved_delta=-reservation.reserved_included,
            purchased_reserved_delta=-reservation.reserved_purchased,
            reference_id=avenqo_request_id,
            details={"reason": reason},
        )
        self._db.commit()
        return reservation

    def settle_reservation(
        self,
        company_id: UUID,
        plan_code: str | None,
        avenqo_request_id: str,
        *,
        tokens: int = 0,
        tool_calls: int = 0,
        attempts: tuple[LLMProviderAttempt, ...] = (),
        count_request: bool = True,
    ) -> TenantAICreditReservation:
        self._lock_credit_account(company_id)
        reservation = self._db.scalar(
            select(TenantAICreditReservation)
            .where(
                TenantAICreditReservation.company_id == company_id,
                TenantAICreditReservation.avenqo_request_id == avenqo_request_id,
            )
            .with_for_update()
        )
        if reservation is None:
            raise ValueError("Credit reservation not found")
        if reservation.status != "reserved":
            return reservation

        provider_cost = sum(
            (attempt.provider_cost_usd for attempt in attempts),
            start=Decimal("0"),
        )
        actual_credits = (
            credits_from_provider_cost(
                provider_cost,
                self._provider_cost_per_credit_usd,
            )
            if attempts
            else (1 if count_request else 0)
        )
        balance = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(
            company_id,
            balance,
            exclude_request_id=avenqo_request_id,
        )
        limit = self.limit_for(company_id, plan_code, MONTHLY_AI_REQUESTS)

        balance.included_reserved -= reservation.reserved_included
        balance.purchased_reserved -= reservation.reserved_purchased
        if limit is None:
            included_debit = 0
            purchased_debit = 0
            unfunded = 0
            self._settle_purchase_allocations(reservation.purchase_allocations, 0)
        else:
            included_debit = min(actual_credits, reservation.reserved_included)
            purchased_debit = min(
                max(actual_credits - included_debit, 0),
                reservation.reserved_purchased,
            )
            self._settle_purchase_allocations(
                reservation.purchase_allocations,
                purchased_debit,
            )
            extra = max(
                actual_credits - included_debit - purchased_debit,
                0,
            )
            included_available = max(
                limit
                - balance.monthly_used
                - balance.included_reserved
                - included_debit,
                0,
            )
            extra_included = min(extra, included_available)
            included_debit += extra_included
            extra -= extra_included
            purchased_available = max(
                balance.purchased_balance - balance.purchased_reserved - purchased_debit,
                0,
            )
            extra_purchased = min(extra, purchased_available)
            purchased_debit += extra_purchased
            self._consume_purchase_lots(company_id, extra_purchased)
            unfunded = extra - extra_purchased
            balance.monthly_used += included_debit
            balance.purchased_balance -= purchased_debit

        reservation.actual_credits = actual_credits
        reservation.settled_included = included_debit
        reservation.settled_purchased = purchased_debit
        reservation.unfunded_credits = unfunded
        reservation.status = "underfunded" if unfunded else ("settled" if actual_credits else "released")
        reservation.settled_at = datetime.now(timezone.utc)
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=f"ai-settlement:{company_id}:{avenqo_request_id}",
            transaction_type="ai_settlement",
            included_delta=-included_debit,
            purchased_delta=-purchased_debit,
            included_reserved_delta=-reservation.reserved_included,
            purchased_reserved_delta=-reservation.reserved_purchased,
            reference_id=avenqo_request_id,
            details={
                "estimated_credits": reservation.estimated_credits,
                "actual_credits": actual_credits,
                "unfunded_credits": unfunded,
            },
        )
        if attempts:
            self._record_provider_attempts(company_id, attempts, actual_credits)
        if count_request or tokens or tool_calls:
            usage = self._get_or_create(company_id, plan_code)
            if count_request:
                usage.ai_requests_count += 1
            usage.llm_tokens_count += max(tokens, 0)
            usage.tool_calls_count += max(tool_calls, 0)
        self._db.commit()
        return reservation

    def record_credit_event(
        self,
        company_id: UUID,
        *,
        idempotency_key: str,
        transaction_type: str,
        reference_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        balance = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(company_id, balance)
        existing = self._db.scalar(
            select(TenantAICreditLedgerEntry.id).where(
                TenantAICreditLedgerEntry.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=idempotency_key,
            transaction_type=transaction_type,
            reference_id=reference_id,
            details=details,
        )
        self._db.flush()

    def reset_credits_for_renewal(
        self,
        company_id: UUID,
        billing_period: str,
    ) -> TenantAICreditBalance:
        """Réinitialise l'allocation incluse au renouvellement.

        Les crédits achetés sont un solde prépayé séparé : ils persistent
        jusqu'à consommation, sauf future politique d'expiration explicite.
        """
        balance = self._get_or_create_credits(company_id)
        self._release_stale_reservations_locked(company_id, balance)
        ledger_key = f"credit-renewal:{company_id}:{billing_period}"
        existing = self._db.scalar(
            select(TenantAICreditLedgerEntry.id).where(
                TenantAICreditLedgerEntry.idempotency_key == ledger_key
            )
        )
        if existing is not None:
            return balance
        previous_monthly_used = balance.monthly_used
        balance.monthly_period = billing_period
        balance.monthly_used = 0
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=ledger_key,
            transaction_type="included_renewal",
            included_delta=previous_monthly_used,
        )
        self._db.flush()
        return balance

    def release_stale_reservations(self, company_id: UUID) -> int:
        with _tenant_credit_lock(company_id):
            balance = self._get_or_create_credits(company_id)
            released = self._release_stale_reservations_locked(company_id, balance)
            if released:
                self._db.commit()
            return released

    def _release_stale_reservations_locked(
        self,
        company_id: UUID,
        balance: TenantAICreditBalance,
        *,
        exclude_request_id: str | None = None,
    ) -> int:
        stale_before = datetime.now(timezone.utc) - self._reservation_ttl
        query = select(TenantAICreditReservation).where(
            TenantAICreditReservation.company_id == company_id,
            TenantAICreditReservation.status == "reserved",
            TenantAICreditReservation.created_at <= stale_before,
        )
        if exclude_request_id is not None:
            query = query.where(
                TenantAICreditReservation.avenqo_request_id != exclude_request_id
            )
        reservations = self._db.scalars(query.with_for_update()).all()
        for reservation in reservations:
            balance.included_reserved = max(
                balance.included_reserved - reservation.reserved_included,
                0,
            )
            balance.purchased_reserved = max(
                balance.purchased_reserved - reservation.reserved_purchased,
                0,
            )
            self._settle_purchase_allocations(reservation.purchase_allocations, 0)
            reservation.status = "expired"
            reservation.settled_at = datetime.now(timezone.utc)
            self._record_credit_transaction(
                company_id,
                balance,
                idempotency_key=(
                    f"ai-reservation-expiry:{company_id}:{reservation.avenqo_request_id}"
                ),
                transaction_type="ai_reservation_expiry",
                included_reserved_delta=-reservation.reserved_included,
                purchased_reserved_delta=-reservation.reserved_purchased,
                reference_id=reservation.avenqo_request_id,
                details={"reason": "reservation_ttl_elapsed"},
            )
        if reservations:
            self._db.flush()
        return len(reservations)

    def _get_or_create_credits(self, company_id: UUID) -> TenantAICreditBalance:
        period = self.current_billing_period()
        self._lock_credit_account(company_id)
        balance = self._db.scalar(
            select(TenantAICreditBalance)
            .where(TenantAICreditBalance.company_id == company_id)
            .with_for_update()
        )
        if balance is None:
            balance = TenantAICreditBalance(company_id=company_id, monthly_period=period)
            self._db.add(balance)
            self._db.flush()
        return balance

    def _lock_credit_account(self, company_id: UUID) -> None:
        bind = self._db.get_bind()
        if bind.dialect.name != "postgresql":
            return
        lock_key = company_id.int & ((1 << 63) - 1)
        self._db.execute(select(func.pg_advisory_xact_lock(lock_key)))

    def _consume_credits(
        self,
        company_id: UUID,
        plan_code: str | None,
        amount: int,
        *,
        idempotency_key: str,
        reference_id: str | None,
    ) -> None:
        if amount <= 0:
            return
        included = self.limit_for(company_id, plan_code, MONTHLY_AI_REQUESTS)
        if included is None:
            return
        balance = self._get_or_create_credits(company_id)
        included_remaining = max(
            included - balance.monthly_used - balance.included_reserved,
            0,
        )
        purchased_remaining = max(
            balance.purchased_balance - balance.purchased_reserved,
            0,
        )
        if amount > included_remaining + purchased_remaining:
            raise AIQuotaExceededError(INSUFFICIENT_AI_CREDITS)
        included_debit = min(amount, included_remaining)
        balance.monthly_used += included_debit
        purchased_debit = min(amount - included_debit, purchased_remaining)
        balance.purchased_balance -= purchased_debit
        self._consume_purchase_lots(company_id, purchased_debit)
        self._record_credit_transaction(
            company_id,
            balance,
            idempotency_key=idempotency_key,
            transaction_type="ai_usage",
            included_delta=-included_debit,
            purchased_delta=-purchased_debit,
            reference_id=reference_id,
            details={"credits": amount},
        )

    def _record_provider_attempts(
        self,
        company_id: UUID,
        attempts: tuple[LLMProviderAttempt, ...],
        credits_used: int,
    ) -> None:
        request_id = next(
            (attempt.usage.avenqo_request_id for attempt in attempts if attempt.usage.avenqo_request_id),
            str(uuid4()),
        )
        for index, attempt in enumerate(attempts):
            usage = attempt.usage
            self._db.add(TenantAIProviderAttempt(
                company_id=company_id,
                avenqo_request_id=request_id,
                provider_request_id=usage.provider_request_id,
                operation=attempt.operation,
                attempt_number=attempt.attempt_number,
                provider=attempt.provider,
                model=attempt.model,
                success=attempt.success,
                failure_category=attempt.failure_category,
                latency_ms=max(attempt.latency_ms, 0),
                input_tokens=max(usage.input_tokens, 0),
                cached_input_tokens=max(usage.cached_input_tokens, 0),
                output_tokens=max(usage.output_tokens, 0),
                reasoning_tokens=max(usage.reasoning_tokens, 0),
                tool_calls=max(usage.tool_calls, 0),
                provider_cost_usd=attempt.provider_cost_usd,
                input_cost_per_million_usd=attempt.input_cost_per_million_usd,
                cached_input_cost_per_million_usd=attempt.cached_input_cost_per_million_usd,
                output_cost_per_million_usd=attempt.output_cost_per_million_usd,
                tool_call_cost_usd=attempt.tool_call_cost_usd,
                avenqo_credits=credits_used if index == len(attempts) - 1 else 0,
            ))

    def limit_for(self, company_id: UUID, plan_code: str | None, metric: str) -> int | None:
        """Résout la limite effective : dérogation Enterprise (Phase 33) en priorité,
        sinon la configuration, puis l'allocation du catalogue de plans."""

        override = self._db.scalar(
            select(EnterpriseOverride).where(EnterpriseOverride.company_id == company_id)
        )
        if override is not None and metric in (override.quota_overrides or {}):
            value = override.quota_overrides[metric]
            return None if value is None else int(value)
        configured = self._policy.limit_for(plan_code, metric)
        if configured is not None or metric != MONTHLY_AI_REQUESTS or plan_code is None:
            return configured
        try:
            return get_plan(plan_code).monthly_ai_credits
        except ValueError:
            return None

    def record_usage(
        self,
        company_id: UUID,
        plan_code: str | None,
        *,
        tokens: int = 0,
        tool_calls: int = 0,
        predictive_requests: int = 0,
        attempts: tuple[LLMProviderAttempt, ...] | None = None,
    ) -> TenantAIUsage:
        """Incrémente les compteurs APRÈS un appel IA réussi."""

        if attempts:
            request_id = next(
                (attempt.usage.avenqo_request_id for attempt in attempts if attempt.usage.avenqo_request_id),
                None,
            )
            if request_id is not None:
                existing = self._db.scalar(
                    select(TenantAIProviderAttempt.id).where(
                        TenantAIProviderAttempt.company_id == company_id,
                        TenantAIProviderAttempt.avenqo_request_id == request_id,
                    )
                )
                if existing is not None:
                    return self._get_or_create(company_id, plan_code)
            provider_cost = sum(
                (attempt.provider_cost_usd for attempt in attempts),
                start=Decimal("0"),
            )
            credits_used = credits_from_provider_cost(
                provider_cost,
                self._provider_cost_per_credit_usd,
            )
        else:
            credits_used = 1

        reference_id = request_id if attempts else None
        self._consume_credits(
            company_id,
            plan_code,
            credits_used,
            idempotency_key=(
                f"ai-usage:{company_id}:{request_id}"
                if attempts
                else f"ai-usage:{company_id}:{uuid4()}"
            ),
            reference_id=reference_id,
        )
        usage = self._get_or_create(company_id, plan_code)
        usage.ai_requests_count += 1
        usage.llm_tokens_count += max(tokens, 0)
        usage.tool_calls_count += max(tool_calls, 0)
        usage.predictive_requests_count += max(predictive_requests, 0)
        if attempts:
            self._record_provider_attempts(company_id, attempts, credits_used)
        self._db.flush()
        return usage


def tokens_from_usage(token_usage: dict[str, object]) -> int:
    """Additionne les tokens input/output d'un `token_usage` de provider, sans hypothèse de format."""

    total = 0
    for key in ("input_tokens", "output_tokens"):
        value = token_usage.get(key)
        if isinstance(value, int):
            total += value
    return total


__all__ = [
    "AIUsageService",
    "CreditReservationClaim",
    "AIQuotaExceededError",
    "AIQuotaPolicy",
    "MONTHLY_AI_REQUESTS",
    "MONTHLY_LLM_TOKENS",
    "MONTHLY_TOOL_CALLS",
    "MONTHLY_PREDICTIVE_REQUESTS",
    "tokens_from_usage",
    "credits_from_provider_cost",
]
