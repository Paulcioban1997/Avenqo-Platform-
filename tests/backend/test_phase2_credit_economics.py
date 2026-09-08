from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Lock, Thread
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.llm.schemas import LLMProviderAttempt, LLMUsage
from backend.app.ai.usage.exceptions import AIQuotaExceededError, INSUFFICIENT_AI_CREDITS
from backend.app.ai.usage.policy import AIQuotaPolicy, MONTHLY_AI_REQUESTS
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings
from backend.app.models import (
    Base,
    Company,
    TenantAICreditBalance,
    TenantAICreditLedgerEntry,
    TenantAICreditReservation,
    TenantAIProviderAttempt,
    TenantAIUsage,
)


def _settings(limit: int) -> Settings:
    return Settings(
        AUTH_JWT_SECRET="a" * 32,
        AI_QUOTA_LIMITS={"professional": {MONTHLY_AI_REQUESTS: limit}},
    )


def _company(session: Session, slug: str) -> Company:
    company = Company(
        name=slug,
        slug=slug,
        email=f"{slug}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.commit()
    return company


def _attempt(
    request_id: str,
    cost: str,
    *,
    number: int = 1,
    provider: str = "openai",
    success: bool = True,
) -> LLMProviderAttempt:
    usage = LLMUsage(
        provider=provider,
        model="metered-model",
        input_tokens=1_000,
        output_tokens=100,
        avenqo_request_id=request_id,
        provider_request_id=f"provider-{request_id}-{number}",
    )
    return LLMProviderAttempt(
        provider=provider,
        model=usage.model,
        operation="generate",
        attempt_number=number,
        success=success,
        failure_category=None if success else "timeout",
        latency_ms=10,
        usage=usage,
        provider_cost_usd=Decimal(cost),
    )


@pytest.fixture
def credit_db(tmp_path: Path):
    database_path = tmp_path / "phase2-credit.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_reserve_settle_releases_unused_and_records_fallback_cost(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "reserve-settle")
        service = AIUsageService(session, AIQuotaPolicy(_settings(3)))
        service.add_purchased_credits(company.id, 2)
        session.commit()

        reservation = service.reserve_credits(company.id, "professional", "request-a", 4)
        balance = service.get_credit_balance(company.id, "professional")
        assert reservation.reserved_included == 3
        assert reservation.reserved_purchased == 1
        assert balance["monthly_used"] == 0
        assert balance["monthly_remaining"] == 3
        assert balance["purchased_remaining"] == 2

        attempts = (
            _attempt("request-a", "0.00031", success=False),
            _attempt("request-a", "0.00020", number=2, provider="gemini"),
        )
        settled = service.settle_reservation(
            company.id,
            "professional",
            "request-a",
            tokens=2_200,
            attempts=attempts,
        )

        assert settled.status == "settled"
        assert settled.actual_credits == 2
        assert settled.settled_included == 2
        assert settled.settled_purchased == 0
        assert settled.unfunded_credits == 0
        balance = service.get_credit_balance(company.id, "professional")
        assert balance["monthly_used"] == 2
        assert balance["monthly_remaining"] == 1
        assert balance["purchased_remaining"] == 2
        provider_attempts = session.query(TenantAIProviderAttempt).order_by(
            TenantAIProviderAttempt.attempt_number
        ).all()
        assert len(provider_attempts) == 2
        assert sum(attempt.provider_cost_usd for attempt in provider_attempts) == Decimal("0.00051")
        assert [attempt.avenqo_credits for attempt in provider_attempts] == [0, 2]
        assert session.query(TenantAICreditLedgerEntry).filter_by(
            transaction_type="ai_settlement"
        ).count() == 1

        service.settle_reservation(
            company.id,
            "professional",
            "request-a",
            attempts=attempts,
        )
        assert service.get_credit_balance(company.id, "professional") == balance
        assert session.query(TenantAIProviderAttempt).count() == 2


def test_plan_allocation_is_metered_without_quota_environment_override(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "catalog-allocation")
        company.subscription_plan = "demo"
        service = AIUsageService(session, AIQuotaPolicy(_settings(0)))

        reservation = service.reserve_credits(company.id, "demo", "first-request", 1)
        settled = service.settle_reservation(
            company.id,
            "demo",
            "first-request",
            attempts=(_attempt("first-request", "0.00030"),),
        )
        balance = service.get_credit_balance(company.id, "demo")

        assert reservation.reserved_included == 1
        assert settled.settled_included == 1
        assert balance["monthly_included"] == 6_500
        assert balance["monthly_used"] == 1
        assert balance["monthly_remaining"] == 6_499


def test_multiple_settlements_reconcile_to_monthly_usage_and_cap(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "multiple-settlements")
        service = AIUsageService(session, AIQuotaPolicy(_settings(3)))

        service.reserve_credits(company.id, "professional", "request-one", 1)
        service.settle_reservation(
            company.id,
            "professional",
            "request-one",
            attempts=(_attempt("request-one", "0.00030"),),
        )
        service.reserve_credits(company.id, "professional", "request-two", 2)
        service.settle_reservation(
            company.id,
            "professional",
            "request-two",
            attempts=(_attempt("request-two", "0.00060"),),
        )

        balance = service.get_credit_balance(company.id, "professional")
        settlements = session.query(TenantAICreditLedgerEntry).filter_by(
            company_id=company.id,
            transaction_type="ai_settlement",
        ).order_by(TenantAICreditLedgerEntry.created_at).all()
        assert balance["monthly_used"] == 3
        assert balance["monthly_remaining"] == 0
        assert len(settlements) == 2
        assert -sum(entry.included_delta for entry in settlements) == 3
        assert settlements[-1].monthly_used_after == 3
        with pytest.raises(AIQuotaExceededError, match=f"^{INSUFFICIENT_AI_CREDITS}$"):
            service.reserve_credits(company.id, "professional", "over-cap", 1)


def test_zero_cost_failure_releases_without_recording_usage(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "zero-cost-failure")
        service = AIUsageService(session, AIQuotaPolicy(_settings(1)))
        service.reserve_credits(company.id, "professional", "failed-request", 1)

        released = service.settle_reservation(
            company.id,
            "professional",
            "failed-request",
            attempts=(_attempt("failed-request", "0", success=False),),
            count_request=False,
        )

        balance = service.get_credit_balance(company.id, "professional")
        settlement = session.query(TenantAICreditLedgerEntry).filter_by(
            company_id=company.id,
            transaction_type="ai_settlement",
        ).one()
        attempt = session.query(TenantAIProviderAttempt).filter_by(
            company_id=company.id,
        ).one()
        assert released.status == "released"
        assert released.actual_credits == 0
        assert balance["monthly_used"] == 0
        assert balance["monthly_remaining"] == 1
        assert settlement.included_delta == settlement.purchased_delta == 0
        assert settlement.included_reserved_after == 0
        assert attempt.provider_cost_usd == Decimal("0")
        assert attempt.avenqo_credits == 0
        assert session.query(TenantAIUsage).filter_by(company_id=company.id).count() == 0


def test_included_exhaustion_debits_purchased_credits_for_only_one_tenant(credit_db) -> None:
    with credit_db() as session:
        company_a = _company(session, "settlement-tenant-a")
        company_b = _company(session, "settlement-tenant-b")
        service = AIUsageService(session, AIQuotaPolicy(_settings(1)))
        service.add_purchased_credits(company_a.id, 2)

        for request_id in ("included-request", "purchased-request"):
            service.reserve_credits(company_a.id, "professional", request_id, 1)
            service.settle_reservation(
                company_a.id,
                "professional",
                request_id,
                attempts=(_attempt(request_id, "0.00030"),),
            )

        balance_a = service.get_credit_balance(company_a.id, "professional")
        balance_b = service.get_credit_balance(company_b.id, "professional")
        ledger_a = session.query(TenantAICreditLedgerEntry).filter_by(
            company_id=company_a.id,
        ).all()
        assert balance_a["monthly_used"] == 1
        assert balance_a["monthly_remaining"] == 0
        assert balance_a["purchased_remaining"] == 1
        assert balance_a["total_remaining"] == 1
        assert sum(entry.purchased_delta for entry in ledger_a) == 1
        assert -sum(entry.included_delta for entry in ledger_a) == 1
        assert balance_b["monthly_used"] == 0
        assert balance_b["monthly_remaining"] == 1
        assert balance_b["purchased_remaining"] == 0
        assert session.query(TenantAIProviderAttempt).filter_by(
            company_id=company_b.id,
        ).count() == 0


def test_release_and_actual_over_estimate_never_make_balances_negative(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "over-estimate")
        service = AIUsageService(session, AIQuotaPolicy(_settings(2)))
        service.add_purchased_credits(company.id, 1)
        session.commit()

        service.reserve_credits(company.id, "professional", "released", 2)
        service.release_reservation(company.id, "released", reason="cancelled")
        assert service.get_credit_balance(company.id, "professional")["total_remaining"] == 3

        service.reserve_credits(company.id, "professional", "expensive", 1)
        settled = service.settle_reservation(
            company.id,
            "professional",
            "expensive",
            attempts=(_attempt("expensive", "0.00120"),),
        )
        balance = session.get(TenantAICreditBalance, company.id)
        assert settled.actual_credits == 4
        assert settled.status == "underfunded"
        assert settled.unfunded_credits == 1
        assert balance is not None
        assert balance.monthly_used == 2
        assert balance.purchased_balance == 0
        assert balance.included_reserved == 0
        assert balance.purchased_reserved == 0


def test_stale_reservation_releases_purchased_credits_and_records_expiry(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "stale-reservation")
        service = AIUsageService(
            session,
            AIQuotaPolicy(_settings(0)),
            reservation_ttl_minutes=30,
        )
        service.add_purchased_credits(company.id, 1)
        session.commit()
        reservation = service.reserve_credits(
            company.id,
            "professional",
            "stale-request",
            1,
        )
        reservation.created_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        session.commit()

        assert service.release_stale_reservations(company.id) == 1

        session.refresh(reservation)
        assert reservation.status == "expired"
        balance = service.get_credit_balance(company.id, "professional")
        assert balance["purchased_remaining"] == 1
        assert session.query(TenantAICreditLedgerEntry).filter_by(
            transaction_type="ai_reservation_expiry"
        ).count() == 1


def test_renewal_with_inflight_reservation_is_replay_safe(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "renewal-inflight")
        service = AIUsageService(session, AIQuotaPolicy(_settings(2)))
        service.record_usage(company.id, "professional")
        service.reserve_credits(
            company.id,
            "professional",
            "cross-period-request",
            1,
        )

        service.reset_credits_for_renewal(company.id, "2099-01")
        balance = session.get(TenantAICreditBalance, company.id)
        assert balance is not None
        assert balance.monthly_used == 0
        assert balance.included_reserved == 1

        service.settle_reservation(
            company.id,
            "professional",
            "cross-period-request",
        )
        assert balance.monthly_used == 1
        assert balance.included_reserved == 0

        service.reset_credits_for_renewal(company.id, "2099-01")
        assert balance.monthly_used == 1
        assert session.query(TenantAICreditLedgerEntry).filter_by(
            transaction_type="included_renewal"
        ).count() == 1


def test_reservations_are_idempotent_and_tenant_scoped(credit_db) -> None:
    with credit_db() as session:
        company_a = _company(session, "reservation-a")
        company_b = _company(session, "reservation-b")
        service = AIUsageService(session, AIQuotaPolicy(_settings(1)))

        first = service.reserve_credits(company_a.id, "professional", "same-request", 1)
        duplicate = service.reserve_credits(company_a.id, "professional", "same-request", 1)
        other_tenant = service.reserve_credits(company_b.id, "professional", "same-request", 1)

        assert first.id == duplicate.id
        assert first.id != other_tenant.id
        assert session.query(TenantAICreditReservation).count() == 2
        assert service.get_credit_balance(company_a.id, "professional")["total_remaining"] == 1
        assert service.get_credit_balance(company_b.id, "professional")["total_remaining"] == 1


def test_reservation_claim_has_one_execution_owner_and_exact_insufficient_code(credit_db) -> None:
    with credit_db() as session:
        company = _company(session, "reservation-owner")
        service = AIUsageService(session, AIQuotaPolicy(_settings(1)))

        first = service.claim_credit_reservation(
            company.id,
            "professional",
            "owned-request",
            1,
        )
        duplicate = service.claim_credit_reservation(
            company.id,
            "professional",
            "owned-request",
            1,
        )

        assert first.acquired is True
        assert duplicate.acquired is False
        assert duplicate.reservation.id == first.reservation.id

        with pytest.raises(AIQuotaExceededError, match=f"^{INSUFFICIENT_AI_CREDITS}$"):
            service.reserve_credits(
                company.id,
                "professional",
                "unfunded-request",
                1,
            )


def test_concurrent_reservations_cannot_double_spend(credit_db) -> None:
    with credit_db() as setup_session:
        company = _company(setup_session, "concurrent-reservations")
        company_id = company.id
        service = AIUsageService(setup_session, AIQuotaPolicy(_settings(1)))
        service.get_credit_balance(company_id, "professional")
        setup_session.commit()

    barrier = Barrier(2)
    result_lock = Lock()
    results: list[str] = []

    def reserve(request_id: str) -> None:
        with credit_db() as session:
            service = AIUsageService(session, AIQuotaPolicy(_settings(1)))
            barrier.wait()
            try:
                service.reserve_credits(company_id, "professional", request_id, 1)
            except AIQuotaExceededError:
                result = "rejected"
            else:
                result = "reserved"
            with result_lock:
                results.append(result)

    threads = [
        Thread(target=reserve, args=(f"request-{uuid4()}",)),
        Thread(target=reserve, args=(f"request-{uuid4()}",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert sorted(results) == ["rejected", "reserved"]
    with credit_db() as session:
        balance = session.get(TenantAICreditBalance, company_id)
        assert balance is not None
        assert balance.monthly_used == 0
        assert balance.included_reserved == 1
        assert balance.purchased_balance == 0
        assert balance.purchased_reserved == 0
        assert session.query(TenantAICreditReservation).filter_by(status="reserved").count() == 1
