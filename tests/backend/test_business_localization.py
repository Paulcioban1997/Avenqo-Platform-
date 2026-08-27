"""Tests ciblés de la localisation métier mondiale (42 locales).

Règles prouvées ici :
- devise déduite du PAYS à la création (jamais de la langue) ;
- changer la langue ne change JAMAIS la devise de l'entreprise ;
- le contexte IA reçoit company_currency=CAD pour un tenant Canada ;
- les outils monétaires renvoient valeur numérique + currency_code (pas de "€284").
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.locale_catalog import (
    LOCALES,
    currency_for_country,
    distinct_currencies,
    defaults_for_country,
)
from backend.app.models import Base, Company, Dataset, DatasetStatus, User, UserRole
from backend.app.ai.chat.chat_service import _localized_system_instruction, SYSTEM_INSTRUCTION
from backend.app.ai.tools.business.sales_tools import GetBusinessOverviewTool, BusinessOverviewArgs
from backend.app.ai.tools.contracts import ToolExecutionContext
from shared.ai_engine.contracts import TenantContext

from tests.backend.test_phase30_tool_calling import FakeIngestionService, _prepared_dataset

import pytest

pytestmark = pytest.mark.asyncio


def _session():
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory()


def _company(session, *, country, language, currency=None):
    company = Company(
        name=f"Co {country}-{language}-{uuid4().hex[:6]}",
        slug=f"co-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.com",
        country=country,
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="demo",
        preferred_language=language,
        currency_code=currency or currency_for_country(country),
    )
    session.add(company)
    session.commit()
    return company


# --- 9. Tests catalogue pays -> devise -------------------------------------


def test_canada_fr_defaults_to_cad() -> None:
    assert currency_for_country("Canada") == "CAD"
    assert defaults_for_country("Canada").default_timezone == "America/Toronto"


def test_canada_en_defaults_to_cad() -> None:
    assert currency_for_country("Canada") == "CAD"


def test_france_fr_now_in_catalog_defaults_to_eur() -> None:
    # La France est maintenant dans le catalogue via fr-FR.
    assert currency_for_country("France") == "EUR"


def test_spain_and_germany_default_to_eur() -> None:
    assert currency_for_country("Spain") == "EUR"
    assert currency_for_country("Germany") == "EUR"


def test_romania_ro_defaults_to_ron() -> None:
    assert currency_for_country("Romania") == "RON"


def test_japan_ja_defaults_to_jpy() -> None:
    assert currency_for_country("Japan") == "JPY"


def test_india_hi_and_ta_default_to_inr() -> None:
    assert currency_for_country("India") == "INR"
    assert defaults_for_country("India").currency_code == "INR"


def test_unknown_country_falls_back_to_usd() -> None:
    assert currency_for_country("Atlantis") == "USD"


def test_catalog_supports_44_locales_and_distinct_currencies() -> None:
    assert len(LOCALES) == 44
    assert "CAD" in distinct_currencies() and "EUR" in distinct_currencies() and "JPY" in distinct_currencies()


# --- 9. Changer la langue ne change jamais la devise ------------------------


def test_changing_language_never_changes_company_currency() -> None:
    session = _session()
    company = _company(session, country="Canada", language="fr")
    assert company.currency_code == "CAD"

    # L'utilisateur passe l'interface en anglais : preferred_language change,
    # currency_code reste CAD (jamais écrasé par la langue).
    company.preferred_language = "en"
    session.commit()

    session.expire_all()
    reloaded = session.get(Company, company.id)
    assert reloaded.preferred_language == "en"
    assert reloaded.currency_code == "CAD"


def test_explicit_currency_is_never_overwritten_by_country_default() -> None:
    session = _session()
    company = _company(session, country="France", language="fr", currency="CHF")
    assert company.currency_code == "CHF"  # explicit choice preserved


# --- 9. Contexte IA : company_currency transmis au LLM ----------------------


def test_ai_system_instruction_carries_cad_context_for_canada() -> None:
    instruction = _localized_system_instruction(
        SYSTEM_INSTRUCTION,
        user_language="fr",
        company_country="Canada",
        company_currency="CAD",
        company_timezone="America/Toronto",
    )
    assert "User language: French" in instruction
    assert "Company country: Canada" in instruction
    assert "Company currency: CAD" in instruction
    assert "Company timezone: America/Toronto" in instruction
    assert "Never infer currency from language" in instruction


# --- Outils : valeur numérique + currency_code, jamais de symbole -----------


async def test_business_overview_tool_returns_numeric_value_with_currency_code() -> None:
    session = _session()
    company = _company(session, country="Canada", language="fr")
    dataset = Dataset(
        company_id=company.id, name="Sales", type="csv", source="s.csv",
        rows_count=6, columns_count=6, status=DatasetStatus.READY,
    )
    session.add(dataset)
    session.commit()

    prepared = _prepared_dataset(company_id=company.id, dataset_id=dataset.id)
    ingestion = FakeIngestionService(prepared)
    tool = GetBusinessOverviewTool(session=session, ingestion=ingestion)
    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company.id),
        user_id=uuid4(), permissions=frozenset({"ai:use"}), request_id="r",
    )

    result = await tool.run(context, BusinessOverviewArgs())

    assert result.success is True
    assert isinstance(result.data["revenue"], float)
    assert result.data["currency_code"] == "CAD"
    # Aucun symbole monétaire concaténé dans les valeurs.
    assert not any(isinstance(v, str) and ("€" in v or "$" in v) for v in result.data.values())
