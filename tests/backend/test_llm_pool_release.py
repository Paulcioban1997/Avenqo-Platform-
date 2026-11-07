"""A slow LLM await must not keep the only pooled SQLAlchemy connection checked out."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import TimeoutError as SQLTimeoutError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.retrieval_service import RetrievalService
from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.schemas import LLMGeneration
from backend.app.ai.usage.policy import AIQuotaPolicy, MONTHLY_AI_REQUESTS
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings
from backend.app.models import Base, Company, User, UserRole
from backend.app.services.tenant_rls import release_tenant_connection


def _pool_engine(tmp_path: Path):
    return create_engine(
        f"sqlite:///{tmp_path / 'pool-release.db'}",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        connect_args={"check_same_thread": False},
    )


class SlowStubProvider(LLMProvider):
    name = "slow-stub"
    supports_tool_calling = False

    def __init__(self, engine) -> None:
        self.engine = engine
        self.checked_out_during_await: int | None = None
        self.second_checkout_ok = False

    async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
        self.checked_out_during_await = self.engine.pool.checkedout()
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            self.second_checkout_ok = True
        await asyncio.sleep(0.05)
        return LLMGeneration(
            content="Slow answer",
            provider=self.name,
            model="slow-stub",
            token_usage={"input_tokens": 4, "output_tokens": 2},
        )

    async def stream(self, *, system_instruction: str, prompt: str):
        yield "Slow answer"


def test_held_session_occupies_the_only_pool_connection(tmp_path: Path) -> None:
    engine = _pool_engine(tmp_path)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        session.execute(text("SELECT 1"))
        assert engine.pool.checkedout() == 1
        with pytest.raises(SQLTimeoutError):
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        release_tenant_connection(session)
        assert engine.pool.checkedout() == 0
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        session.close()
        engine.dispose()


def test_release_tenant_connection_keeps_rls_info_for_rebind() -> None:
    class _Session:
        def __init__(self) -> None:
            self.info = {"avenqo_rls": {"flag": "off", "cid": "abc"}}
            self.committed = False
            self.closed = False

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    session = _Session()
    release_tenant_connection(session)
    assert session.committed is True
    assert session.closed is True
    assert session.info["avenqo_rls"]["cid"] == "abc"


@pytest.mark.asyncio
async def test_slow_chat_llm_does_not_occupy_the_only_pool_connection(tmp_path: Path) -> None:
    engine = _pool_engine(tmp_path)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    company = Company(
        name="Pool Co",
        slug=f"pool-{uuid4().hex[:8]}",
        email=f"pool-{uuid4().hex[:8]}@example.ca",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    user = User(
        company_id=company.id,
        first_name="Pool",
        last_name="Owner",
        email=f"pool-user-{uuid4().hex[:8]}@example.ca",
        password_hash="hash",
        role=UserRole.OWNER,
    )
    session.add(user)
    session.commit()
    try:
        provider = SlowStubProvider(engine)
        usage = AIUsageService(
            session,
            AIQuotaPolicy(
                Settings(
                    AUTH_JWT_SECRET="a" * 32,
                    AI_QUOTA_LIMITS={"professional": {MONTHLY_AI_REQUESTS: 100}},
                )
            ),
        )
        conversations = ConversationService(session)
        conversation = conversations.create(company.id, user.id, "Pool")
        chat = ChatService(conversations, RetrievalService(session), provider, usage_service=usage)
        message, _sources = await chat.send(
            company.id,
            user.id,
            conversation.id,
            "Bonjour",
            permissions=frozenset({"ai:use"}),
            plan_code="professional",
            request_id="pool-release-1",
        )
        assert message.content == "Slow answer"
        assert provider.second_checkout_ok is True
        assert provider.checked_out_during_await == 0
    finally:
        session.close()
        engine.dispose()
