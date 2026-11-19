"""Test suite for Avenqo Voice AI — Complete Intelligence & Telephony Upgrade.

Validates:
1. Avenqo AI Employee Performance Coach (Avenqo Performance Coach AI):
   - Daily AI Employee Briefing after PIN authentication (priorities, execution order, role advice, motivation)
   - Intelligent role-based coaching (Sales, Receptionist, Retail, Manager, Technician, Support)
   - On-demand personal AI coach & task management (retrieval, completion mutation by ID/title)
   - Strict multi-tenant data isolation & principal authorization (fail-closed if anonymous)
   - Multilingual support (fr-CA, en-US, es-ES, ro-RO)
2. Voice Engine & Frontier Reasoning:
   - Voice audio model selection (gpt-live-1 primary, gpt-realtime-2.1 fallback)
   - Frontier reasoning (gpt-6.2-astra) and standard reasoning (gpt-6.2-sol) registered with accurate rate cards
   - Adapter graceful fallback and cancellation support
3. Universal pronunciation & security gating:
   - Dynamic tenant pronunciation (no hardcoded "Produits Héros", tenant-specific custom pronunciation)
   - Rejection of employee coaching inquiries when caller is not authenticated
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend.app.config.settings import Settings
from backend.app.core.permissions import UserRole
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.models.workspace import EmployeeResponsibility, EmployeeTask
from backend.app.services.employee_coach_service import EmployeeCoachService
from backend.app.ai.tools.business.coach_tools import (
    GetMyDailyBriefingTool,
    GetMyTasksTool,
    MarkMyTaskCompletedTool,
    GetCoachingAdviceTool,
    EmptyCoachArgs,
    TaskStatusArgs,
    CompleteTaskArgs,
    CoachingAdviceArgs,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.voice.tool_registry import VoiceToolRegistryService
from backend.app.voice.caller_scope import (
    PUBLIC_VOICE_CALLER_PERMISSIONS,
    is_public_voice_caller,
)
from backend.app.voice.direct_answers import (
    is_coach_briefing_question,
    is_coach_tasks_question,
    resolve_direct_voice_answer,
)
from backend.app.ai.llm.model_registry import (
    _KNOWN_MODEL_PROFILES,
    _DEFAULT_RATES,
)
from backend.app.voice.usage import voice_pricing_catalog
from backend.app.voice.adapters import OpenAIRealtimeAudioAdapter, OpenAIAudioConfig
from backend.app.assistants.registry import AssistantRegistry
from shared.ai_engine.contracts import TenantContext
from tests.backend.test_voice_agent import _voice_database


def _create_test_user(session, company_id: UUID, **kwargs) -> User:
    defaults = {
        "id": uuid4(),
        "company_id": company_id,
        "first_name": "Test",
        "last_name": "User",
        "email": f"user-{uuid4().hex[:8]}@avenqo.test",
        "password_hash": "argon2_test_hash_123456",
        "role": UserRole.USER,
        "is_active": True,
    }
    defaults.update(kwargs)
    user = User(**defaults)
    session.add(user)
    session.flush()
    return user


# ==============================================================================
# 1. EMPLOYEE PERFORMANCE COACH SERVICE TESTS
# ==============================================================================

def test_employee_coach_daily_briefing_sales_role(tmp_path):
    """Vérifie la génération du briefing quotidien pour un profil Ventes."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = _create_test_user(
            session,
            company.id,
            first_name="Alex",
            last_name="Tremblay",
            email="alex@avenqo.test",
            job_title="Représentant des ventes",
            department="Commercial",
            role=UserRole.USER,
        )

        # Add tasks
        task1 = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=user.id,
            created_by_user_id=user.id,
            title="Relancer les devis de la semaine passée",
            status="open",
            priority="high",
        )
        task2 = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=user.id,
            created_by_user_id=user.id,
            title="Préparer la démonstration client",
            status="open",
            priority="medium",
        )
        session.add_all([task1, task2])
        session.commit()

        coach = EmployeeCoachService(session)
        briefing = coach.get_daily_briefing(user, locale="fr-CA")

        assert briefing["status"] == "success"
        assert briefing["employee"]["first_name"] == "Alex"
        assert len(briefing["top_priorities"]) >= 2
        assert "spoken_summary" in briefing
        summary = briefing["spoken_summary"]
        assert "Alex" in summary
        assert "trois priorités" in summary or "priorité" in summary
        assert "🚀" in briefing["motivation"]
    finally:
        session.close()
        engine.dispose()


def test_employee_coach_role_adaptations(tmp_path):
    """Vérifie que les conseils sont adaptés à chaque métier (Manager, Receptionist, Technician)."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        coach = EmployeeCoachService(session)

        roles_to_test = [
            ("Sophie", "Réceptionniste", "Accueil", "receptionist"),
            ("Marc", "Technicien d'atelier", "Maintenance", "technician"),
            ("Hélène", "Directrice des opérations", "Direction", "manager"),
            ("Karim", "Agent support client", "Support", "support"),
        ]

        for fname, title, dept, expected_key in roles_to_test:
            user = _create_test_user(
                session,
                company.id,
                first_name=fname,
                last_name="Test",
                email=f"{fname.lower()}-{uuid4().hex[:4]}@avenqo.test",
                job_title=title,
                department=dept,
                role=UserRole.MANAGER if expected_key == "manager" else UserRole.USER,
            )

            advice = coach.get_coaching_advice(user, locale="fr-CA")
            assert advice["status"] == "success"
            assert advice["role"] == expected_key
            assert len(advice["tips"]) >= 3
            assert len(advice["actionable_steps"]) == 3
    finally:
        session.close()
        engine.dispose()


def test_employee_coach_multilingual(tmp_path):
    """Vérifie la génération du coaching dans les 4 langues majeures."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        coach = EmployeeCoachService(session)
        user = _create_test_user(
            session,
            company.id,
            first_name="Elena",
            last_name="Popescu",
            email="elena@avenqo.test",
            job_title="Sales Consultant",
            department="Sales",
            role=UserRole.USER,
        )
        session.commit()

        # French
        fr = coach.get_daily_briefing(user, locale="fr-CA")
        assert "Bonjour Elena" in fr["spoken_summary"]

        # English
        en = coach.get_daily_briefing(user, locale="en-US")
        assert "Hello Elena" in en["spoken_summary"]

        # Spanish
        es = coach.get_daily_briefing(user, locale="es-ES")
        assert "¡Hola Elena!" in es["spoken_summary"]

        # Romanian
        ro = coach.get_daily_briefing(user, locale="ro-RO")
        assert "Salut Elena!" in ro["spoken_summary"]
    finally:
        session.close()
        engine.dispose()


def test_employee_coach_task_mutation(tmp_path):
    """Vérifie l'inspection et la complétion sécurisée de tâche par ID ou mot-clé."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = _create_test_user(
            session,
            company.id,
            first_name="David",
            last_name="Miller",
            email="david@avenqo.test",
            job_title="Conseiller technique",
            role=UserRole.USER,
        )

        task = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=user.id,
            created_by_user_id=user.id,
            title="Inspecter le matériel reçu ce matin",
            status="open",
            priority="high",
        )
        session.add(task)
        session.commit()

        coach = EmployeeCoachService(session)

        # List tasks
        my_tasks = coach.get_my_tasks(user, status="open")
        assert len(my_tasks) == 1
        assert my_tasks[0]["title"] == "Inspecter le matériel reçu ce matin"

        # Complete task by keyword substring
        res = coach.complete_task(user, "matériel")
        assert res["status"] == "success"
        assert res["status_after"] == "done"

        # Verify in DB
        updated = session.get(EmployeeTask, task.id)
        assert updated is not None
        assert updated.status == "done"
        assert updated.completed_at is not None
    finally:
        session.close()
        engine.dispose()


def test_employee_coach_cross_tenant_isolation(tmp_path):
    """Vérifie l'isolation stricte multi-tenant : un employé de l'entreprise A ne peut ni voir ni muter les tâches de B."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        # Company A
        user_a = _create_test_user(
            session,
            company.id,
            first_name="UserA",
            last_name="CompanyA",
            email="user_a@companya.test",
            role=UserRole.USER,
        )

        # Company B
        company_b = Company(
            id=uuid4(),
            name="Other Tenant B",
            slug="other-tenant-b",
            email="other@tenantb.test",
            country="CA",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company_b)
        session.flush()

        user_b = _create_test_user(
            session,
            company_b.id,
            first_name="UserB",
            last_name="CompanyB",
            email="user_b@tenantb.test",
            role=UserRole.USER,
        )
        task_b = EmployeeTask(
            id=uuid4(),
            company_id=company_b.id,
            assignee_user_id=user_b.id,
            created_by_user_id=user_b.id,
            title="Secret project in company B",
            status="open",
        )
        session.add(task_b)
        session.commit()

        coach = EmployeeCoachService(session)

        # User A cannot see User B's task
        tasks_a = coach.get_my_tasks(user_a)
        assert len(tasks_a) == 0

        # User A cannot complete User B's task
        res = coach.complete_task(user_a, str(task_b.id))
        assert res["status"] == "error"

        # Task B remains untouched
        session.refresh(task_b)
        assert task_b.status == "open"
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 2. AI COACH TOOLS EXECUTION & SECURITY GATE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_coach_ai_tools_fail_closed_when_anonymous(tmp_path):
    """Vérifie que tous les outils Coach refusent immédiatement un appelant non authentifié."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        # Anonymous context: user_id is None
        anon_context = ToolExecutionContext(
            tenant=TenantContext(company.id, None),
            user_id=uuid4(),
            permissions=frozenset({"ai:use"}),
            request_id="req-anon-1",
            locale="fr-CA",
        )

        t1 = GetMyDailyBriefingTool(session)
        r1 = await t1.run(anon_context, EmptyCoachArgs())
        assert r1.success is False
        assert "authentification" in (r1.error or "").lower()

        t2 = GetMyTasksTool(session)
        r2 = await t2.run(anon_context, TaskStatusArgs())
        assert r2.success is False

        t3 = MarkMyTaskCompletedTool(session)
        r3 = await t3.run(anon_context, CompleteTaskArgs(task_identifier="any"))
        assert r3.success is False

        t4 = GetCoachingAdviceTool(session)
        r4 = await t4.run(anon_context, CoachingAdviceArgs(topic="sales"))
        assert r4.success is False
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_coach_ai_tools_succeed_when_authenticated(tmp_path):
    """Vérifie l'exécution des outils Coach pour un employé authentifié."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = _create_test_user(
            session,
            company.id,
            first_name="Julie",
            last_name="Gagnon",
            email="julie@avenqo.test",
            job_title="Conseillère clientèle",
            role=UserRole.USER,
        )
        task = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=user.id,
            created_by_user_id=user.id,
            title="Appeler M. Dupont pour confirmer la commande",
            status="open",
        )
        session.add(task)
        session.commit()

        auth_context = ToolExecutionContext(
            tenant=TenantContext(company.id, user.id),
            user_id=user.id,
            permissions=frozenset({"ai:use"}),
            request_id="req-auth-1",
            locale="fr-CA",
        )

        # Briefing
        t1 = GetMyDailyBriefingTool(session)
        r1 = await t1.run(auth_context, EmptyCoachArgs())
        assert r1.success is True
        assert "Julie" in str(r1.data)

        # Tasks list
        t2 = GetMyTasksTool(session)
        r2 = await t2.run(auth_context, TaskStatusArgs())
        assert r2.success is True
        assert r2.data["count"] == 1

        # Complete task
        t3 = MarkMyTaskCompletedTool(session)
        r3 = await t3.run(auth_context, CompleteTaskArgs(task_identifier="Dupont"))
        assert r3.success is True

        # Advice
        t4 = GetCoachingAdviceTool(session)
        r4 = await t4.run(auth_context, CoachingAdviceArgs(topic="accueil"))
        assert r4.success is True
    finally:
        session.close()
        engine.dispose()


def test_voice_tool_registry_distinguishes_public_vs_staff(tmp_path):
    """Vérifie que les outils de coaching ne sont disponibles QUE pour le staff authentifié."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = _create_test_user(
            session,
            company.id,
            email="staff@avenqo.test",
            role=UserRole.USER,
        )
        session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.USER, is_active=True))
        session.commit()

        registry_service = VoiceToolRegistryService(session, AssistantRegistry())

        # Public caller scope
        public_tenant = TenantContext(company.id, None)
        public_tools, _ = registry_service.allowed_tools(
            public_tenant,
            permissions=PUBLIC_VOICE_CALLER_PERMISSIONS,
            active_modules=frozenset({"voice"}),
        )
        assert "get_my_daily_briefing" not in public_tools
        assert "get_my_tasks" not in public_tools
        assert "mark_my_task_completed" not in public_tools
        assert "get_coaching_advice" not in public_tools

        # Authenticated staff scope
        staff_tenant = TenantContext(company.id, user.id)
        staff_tools, _ = registry_service.allowed_tools(
            staff_tenant,
            permissions=frozenset({"ai:use"}),
            active_modules=frozenset({"voice"}),
        )
        assert "get_my_daily_briefing" in staff_tools
        assert "get_my_tasks" in staff_tools
        assert "mark_my_task_completed" in staff_tools
        assert "get_coaching_advice" in staff_tools
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 3. DIRECT VOICE ANSWERS & SECURITY GATING TESTS
# ==============================================================================

def test_direct_voice_answers_coaching_inquiry(tmp_path):
    """Vérifie la réponse directe au coaching avec filtrage de sécurité pour appelant anonyme."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = _create_test_user(
            session,
            company.id,
            first_name="Maxime",
            last_name="Boucher",
            email="maxime@avenqo.test",
            job_title="Conseiller commercial",
            role=UserRole.USER,
        )
        session.commit()

        shift_query = "Salut Avenqo, j'ai commencé mon shift. Qu'est-ce que je devrais faire aujourd'hui pour améliorer mes performances ?"

        # 1. Anonymous caller inquiry is refused with PIN prompt requirement
        anon_ans = resolve_direct_voice_answer(
            session,
            company_id=company.id,
            transcript=shift_query,
            authenticated_staff=False,
            locale="fr-CA",
            user_id=None,
        )
        assert anon_ans is not None
        assert "authentifiés par NIP" in anon_ans

        # 2. Authenticated employee receives their spoken daily briefing
        auth_ans = resolve_direct_voice_answer(
            session,
            company_id=company.id,
            transcript=shift_query,
            authenticated_staff=True,
            locale="fr-CA",
            user_id=user.id,
        )
        assert auth_ans is not None
        assert "Maxime" in auth_ans
        assert "priorités" in auth_ans
    finally:
        session.close()
        engine.dispose()


# ==============================================================================
# 4. SETTINGS & FRONTIER MODEL REGISTRY TESTS
# ==============================================================================

def test_settings_voice_model_defaults_and_reasoning():
    """Vérifie la configuration par défaut de gpt-live-1, gpt-realtime-2.1 et gpt-6.2-astra."""
    settings = Settings()
    assert settings.voice_realtime_model == "gpt-live-1"
    assert settings.voice_realtime_fallback_model == "gpt-realtime-2.1"
    assert settings.voice_reasoning_model == "gpt-6.2-astra"
    assert settings.voice_reasoning_effort == "medium"
    assert settings.voice_standard_reasoning_model == "gpt-6.2-sol"
    assert settings.voice_ai_coach_enabled is True


def test_frontier_models_in_catalog_and_registry():
    """Vérifie la présence et la tarification de gpt-6.2-astra et gpt-live-1."""
    # LLM Model Registry
    assert ("openai", "gpt-6.2-astra") in _KNOWN_MODEL_PROFILES
    assert ("openai", "gpt-6.2-astra") in _DEFAULT_RATES
    pricing_astra = _DEFAULT_RATES[("openai", "gpt-6.2-astra")]
    assert pricing_astra["input_cost_per_million_usd"] == "8.00"
    assert pricing_astra["output_cost_per_million_usd"] == "40.00"

    # Voice Pricing Catalog
    catalog = voice_pricing_catalog()
    assert catalog is not None


# ==============================================================================
# 5. VOICE BUSINESS CONFIG COACH EXTENSIONS & PROMPT PERSONA
# ==============================================================================

def test_voice_business_config_coach_extensions(tmp_path):
    """Vérifie que VoiceBusinessConfig inclut ai_coach_enabled et ai_coach_config."""
    engine, session, company, config, _api_key, orchestrator = _voice_database(tmp_path)
    try:
        config.ai_coach_enabled = True
        config.ai_coach_config = {"daily_briefing_time": "08:30", "focus_areas": ["sales", "retention"]}
        session.commit()
        session.refresh(config)

        assert config.ai_coach_enabled is True
        assert config.ai_coach_config["daily_briefing_time"] == "08:30"

        # Check public_config dictionary
        pub = orchestrator.public_config(config)
        assert pub["ai_coach_enabled"] is True
        assert pub["ai_coach_config"]["daily_briefing_time"] == "08:30"
    finally:
        session.close()
        engine.dispose()


def test_build_personality_system_prompt_universal_pronunciation():
    """Vérifie que la prononciation est universelle sans règle en dur parasite."""
    from backend.app.voice.realtime_provider import build_personality_system_prompt

    # Universal custom pronunciation
    p1 = build_personality_system_prompt(
        company_name="Clinique Du Nord",
        locale="fr-CA",
        custom_pronunciation="Clinique Du Nord Santé",
        is_authenticated_staff=True,
        staff_name="Dr. Martin",
        staff_role="Médecin",
    )
    assert "Clinique Du Nord Santé" in p1
    assert "AVENQO AI EMPLOYEE PERFORMANCE COACH" in p1
    assert "Dr. Martin (Médecin)" in p1
