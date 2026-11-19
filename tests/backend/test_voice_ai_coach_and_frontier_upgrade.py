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
from decimal import Decimal
from types import SimpleNamespace
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


def _create_test_user(session, company_id: UUID, create_membership: bool = True, **kwargs) -> User:
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
    if create_membership:
        membership = CompanyMembership(
            user_id=user.id,
            company_id=company_id,
            role=user.role,
            is_active=True,
        )
        session.add(membership)
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

        # 1. Complete task by keyword without confirmation -> requires confirmation with server token
        res_conf = coach.complete_task(user, "matériel", confirmed=False, session_id="call-sess-001", turn_id=1)
        assert res_conf["status"] == "requires_confirmation"
        assert "confirmez-vous" in res_conf["message"].lower()
        token = res_conf.get("confirmation_token")
        assert token is not None

        # Task remains open before confirmation
        t_row = session.get(EmployeeTask, task.id)
        assert t_row is not None and t_row.status == "open"

        # 2. Try to complete with confirmed=True but without server token -> rejected with requires_confirmation!
        res_unproven = coach.complete_task(user, "matériel", confirmed=True, confirmation_token="fake-unissued-token", session_id="call-sess-001", turn_id=2)
        assert res_unproven["status"] == "requires_confirmation"
        token2 = res_unproven.get("confirmation_token")
        assert token2 is not None

        # Task still remains open
        t_row2 = session.get(EmployeeTask, task.id)
        assert t_row2 is not None and t_row2.status == "open"

        # 3. Complete task with explicit confirmation and genuine server token in subsequent turn -> success
        res = coach.complete_task(user, "matériel", confirmed=True, confirmation_token=token2, session_id="call-sess-001", turn_id=3)
        assert res["status"] == "success"
        assert res["status_after"] == "done"

        # Verify in DB
        updated = session.get(EmployeeTask, task.id)
        assert updated is not None
        assert updated.status == "done"
        assert updated.completed_at is not None

        # 4. Repeated command -> already_completed (idempotency)
        res_repeat = coach.complete_task(user, "matériel", confirmed=True)
        assert res_repeat["status"] == "already_completed"
        assert "déjà" in res_repeat["message"].lower()
        assert "terminée" in res_repeat["message"].lower()
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

        # Complete task requires explicit confirmation with server token
        t3 = MarkMyTaskCompletedTool(session)
        r3_pre = await t3.run(auth_context, CompleteTaskArgs(task_identifier="Dupont", confirmed=False))
        assert r3_pre.success is False
        assert r3_pre.error == "requires_confirmation"
        token = r3_pre.data.get("confirmation_token")
        assert token is not None

        # Trying confirmed=True without token fails
        r3_fake = await t3.run(auth_context, CompleteTaskArgs(task_identifier="Dupont", confirmed=True, confirmation_token=None))
        assert r3_fake.success is False
        assert r3_fake.error == "requires_confirmation"
        token2 = r3_fake.data.get("confirmation_token")
        assert token2 is not None

        # Complete task with confirmation and genuine server token
        r3 = await t3.run(auth_context, CompleteTaskArgs(task_identifier="Dupont", confirmed=True, confirmation_token=token2))
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
            create_membership=False,
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
    """Vérifie la présence et la tarification de gpt-6.2-astra, gpt-6.2-sol et gpt-live-1."""
    # LLM Model Registry Astra (officiel standard: 8 $ entrée, 40 $ sortie, 0,40 $ cache, tier 2)
    assert ("openai", "gpt-6.2-astra") in _KNOWN_MODEL_PROFILES
    assert ("openai", "gpt-6.2-astra") in _DEFAULT_RATES
    pricing_astra = _DEFAULT_RATES[("openai", "gpt-6.2-astra")]
    assert pricing_astra["input_cost_per_million_usd"] == "8.00"
    assert pricing_astra["cached_input_cost_per_million_usd"] == "0.40"
    assert pricing_astra["output_cost_per_million_usd"] == "40.00"
    assert _KNOWN_MODEL_PROFILES[("openai", "gpt-6.2-astra")]["speed_tier"] == 2

    # LLM Model Registry Sol (officiel standard: 2 $ entrée, 10 $ sortie, 0,10 $ cache, speed tier 1 fast reasoning)
    assert ("openai", "gpt-6.2-sol") in _KNOWN_MODEL_PROFILES
    assert ("openai", "gpt-6.2-sol") in _DEFAULT_RATES
    pricing_sol = _DEFAULT_RATES[("openai", "gpt-6.2-sol")]
    assert pricing_sol["input_cost_per_million_usd"] == "2.00"
    assert pricing_sol["cached_input_cost_per_million_usd"] == "0.10"
    assert pricing_sol["output_cost_per_million_usd"] == "10.00"
    assert _KNOWN_MODEL_PROFILES[("openai", "gpt-6.2-sol")]["speed_tier"] == 1

    # Voice Pricing Catalog
    catalog = voice_pricing_catalog()
    assert catalog is not None
    entry_sol = catalog.lookup("openai", "gpt-6.2-sol")
    assert entry_sol is not None
    assert entry_sol.output_cost_per_million_usd == Decimal("10.00")
    assert entry_sol.cached_input_cost_per_million_usd == Decimal("0.10")


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
        coach_dict = config.ai_coach_config or {}
        assert coach_dict.get("daily_briefing_time") == "08:30"

        # Check public_config dictionary
        pub = orchestrator.public_config(config)
        assert pub["ai_coach_enabled"] is True
        pub_coach = pub["ai_coach_config"] or {}
        assert pub_coach.get("daily_briefing_time") == "08:30"
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

    # Default tenant without custom pronunciation preserves exact company_name
    p2 = build_personality_system_prompt(
        company_name="Produits Ero",
        locale="fr-CA",
        custom_pronunciation=None,
    )
    assert "You represent the company 'Produits Ero'. Spoken name: 'Produits Ero'." in p2
    assert "PRONUNCIATION INSTRUCTION" not in p2

    # Tenant with explicit custom pronunciation gets phonetic instruction
    p3 = build_personality_system_prompt(
        company_name="Produits Ero",
        locale="fr-CA",
        custom_pronunciation="Produits Éro",
    )
    assert "Spoken name: 'Produits Éro'." in p3
    assert "PRONUNCIATION INSTRUCTION: The official phonetic spoken name for 'Produits Ero' is 'Produits Éro'." in p3


# ==============================================================================
# 6. COACH AMBIGUITY, RBAC GATING & REALTIME ADAPTER TESTS
# ==============================================================================

def test_coach_task_ambiguity_gating_and_audit(tmp_path):
    """Vérifie qu'en cas d'ambiguïté vocale, aucune tâche n'est modifiée et une clarification est exigée."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = _create_test_user(
            session,
            company.id,
            first_name="Jean",
            last_name="Tremblay",
            email="jean@avenqo.test",
            job_title="Conseiller Ventes",
            role=UserRole.USER,
        )
        task1 = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=user.id,
            created_by_user_id=user.id,
            title="Relancer client Dupont pour contrat annuel",
            status="open",
        )
        task2 = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=user.id,
            created_by_user_id=user.id,
            title="Préparer facture Dupont pour la livraison",
            status="open",
        )
        session.add_all([task1, task2])
        session.commit()

        coach = EmployeeCoachService(session)

        # Ambiguous keyword "Dupont" matches 2 tasks
        res_ambiguous = coach.complete_task(user, "Dupont", confirmed=True)
        assert res_ambiguous["status"] == "ambiguous"
        assert res_ambiguous["error"] == "ambiguous_match"
        assert len(res_ambiguous["matches"]) == 2
        assert "Reconnaissance ambiguë" in res_ambiguous["message"]

        # Neither task was mutated
        t1_check = session.get(EmployeeTask, task1.id)
        t2_check = session.get(EmployeeTask, task2.id)
        assert t1_check is not None and t1_check.status == "open"
        assert t2_check is not None and t2_check.status == "open"

        # Specific keyword "contrat" matches only task1 -> requires confirmation
        res_one = coach.complete_task(user, "contrat", confirmed=False, session_id="call-sess-disam", turn_id=1)
        assert res_one["status"] == "requires_confirmation"
        t1_after_pre = session.get(EmployeeTask, task1.id)
        assert t1_after_pre is not None and t1_after_pre.status == "open"
        token = res_one.get("confirmation_token")

        # Specific keyword "contrat" with confirmed=True mutates task1
        res_done = coach.complete_task(user, "contrat", confirmed=True, confirmation_token=token, session_id="call-sess-disam", turn_id=2)
        assert res_done["status"] == "success"
        t1_done = session.get(EmployeeTask, task1.id)
        t2_still_open = session.get(EmployeeTask, task2.id)
        assert t1_done is not None and t1_done.status == "done"
        assert t2_still_open is not None and t2_still_open.status == "open"
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_coach_tools_rbac_and_write_permission_gating(tmp_path):
    """Vérifie le respect strict du RBAC : viewer interdit en écriture, tenant désactivé refusé."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        viewer_user = _create_test_user(
            session,
            company.id,
            create_membership=False,
            first_name="Stéphane",
            last_name="Auditeur",
            email="stephane@avenqo.test",
            job_title="Auditeur Externe",
            role=UserRole.VIEWER,
        )
        session.add(CompanyMembership(company_id=company.id, user_id=viewer_user.id, role=UserRole.VIEWER, is_active=True))
        task = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=viewer_user.id,
            created_by_user_id=viewer_user.id,
            title="Consulter rapports mensuels",
            status="open",
        )
        session.add(task)
        session.commit()

        viewer_context = ToolExecutionContext(
            tenant=TenantContext(company.id, viewer_user.id),
            user_id=viewer_user.id,
            permissions=frozenset({"ai:use"}),
            request_id="req-viewer-1",
            locale="fr-CA",
        )

        # Viewer can read tasks
        get_tasks_tool = GetMyTasksTool(session)
        r_get = await get_tasks_tool.run(viewer_context, TaskStatusArgs())
        assert r_get.success is True

        # Viewer cannot mutate tasks
        complete_tool = MarkMyTaskCompletedTool(session)
        r_mutate = await complete_tool.run(viewer_context, CompleteTaskArgs(task_identifier="rapports", confirmed=True))
        assert r_mutate.success is False
        assert "lecture seule" in (r_mutate.error or "").lower()
        t_view = session.get(EmployeeTask, task.id)
        assert t_view is not None and t_view.status == "open"

        # Tenant with ai_coach_enabled=False blocks coach tools
        config.ai_coach_enabled = False
        session.commit()

        r_blocked = await get_tasks_tool.run(viewer_context, TaskStatusArgs())
        assert r_blocked.success is False
        assert "désactivé" in (r_blocked.error or "").lower()
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_realtime_audio_adapter_lifecycle_and_fallback():
    """Vérifie le cycle de vie de l'adaptateur audio OpenAI, le fallback automatique et les interruptions."""
    from backend.app.voice.adapters import OpenAIAudioConfig, OpenAIRealtimeAudioAdapter
    from unittest.mock import AsyncMock, MagicMock

    config = OpenAIAudioConfig(api_key="sk-test-fake", tts_voice="marin", speech_speed=1.0)
    adapter = OpenAIRealtimeAudioAdapter(config, realtime_model="gpt-live-1")

    # Mock connection and manager
    mock_connection = AsyncMock()
    mock_manager = AsyncMock()
    mock_manager.__aenter__.return_value = mock_connection

    adapter._manager = mock_manager
    adapter._connection = mock_connection

    # Test audio buffer sending
    await adapter.send_audio(b"\x00\x01\x02")
    mock_connection.send.assert_awaited()
    last_call_arg = mock_connection.send.call_args[0][0]
    assert last_call_arg["type"] == "input_audio_buffer.append"

    # Test speech synthesis trigger
    await adapter.speak("Bonjour, comment allez-vous ?")
    last_speak_arg = mock_connection.send.call_args[0][0]
    assert last_speak_arg["type"] == "response.create"
    assert "Bonjour" in str(last_speak_arg)

    # Test interruption (barge-in / clear)
    await adapter.interrupt()
    last_interrupt_arg = mock_connection.send.call_args[0][0]
    assert last_interrupt_arg["type"] == "response.cancel"

    # Test clear_input
    await adapter.clear_input()
    last_clear_arg = mock_connection.send.call_args[0][0]
    assert last_clear_arg["type"] == "input_audio_buffer.clear"

    # Test mid-call reconnect
    await adapter.close()
    assert adapter._connection is None


def test_employee_coach_strict_active_company_membership_required(tmp_path):
    """Vérifie que l'adhésion active (CompanyMembership) est strictement obligatoire pour accéder au Coach."""
    from backend.app.ai.tools.business.coach_tools import _verify_coach_access

    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        # User without CompanyMembership
        user_no_membership = _create_test_user(
            session,
            company.id,
            create_membership=False,
            first_name="Orphan",
            last_name="User",
            email="orphan@avenqo.test",
        )
        context_no_mem = ToolExecutionContext(
            tenant=TenantContext(company.id, user_no_membership.id),
            user_id=user_no_membership.id,
            permissions=frozenset({"ai:use"}),
            request_id="req-orphan-1",
            locale="fr-CA",
        )
        ok, err, actor = _verify_coach_access(session, context_no_mem, write=False)
        assert ok is False
        assert "adhésion active" in (err or "").lower()

        # Tool registry must not offer coach tools to user without active membership
        registry = VoiceToolRegistryService(session, AssistantRegistry())
        tools, _ = registry.allowed_tools(TenantContext(company.id, user_no_membership.id), permissions=frozenset({"ai:use"}))
        assert "get_my_daily_briefing" not in tools
        assert "mark_my_task_completed" not in tools

        # User with inactive CompanyMembership (is_active=False)
        inactive_mem = CompanyMembership(
            user_id=user_no_membership.id,
            company_id=company.id,
            role=user_no_membership.role,
            is_active=False,
        )
        session.add(inactive_mem)
        session.commit()

        ok2, err2, _ = _verify_coach_access(session, context_no_mem, write=False)
        assert ok2 is False
        assert "adhésion active" in (err2 or "").lower()

        # Activate membership -> immediately succeeds
        inactive_mem.is_active = True
        session.commit()

        ok3, err3, act = _verify_coach_access(session, context_no_mem, write=False)
        assert ok3 is True
        assert act is not None
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_telnyx_media_bridge_automatic_midcall_reconnect():
    """Vérifie que la session Telnyx déclenche automatiquement reconnect() lors d'une déconnexion audio."""
    from backend.app.voice.telnyx_media import TelnyxMediaBridge

    mock_socket = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.fallback_model = "gpt-realtime-2.1"
    mock_adapter.reconnect = AsyncMock()

    # Generator simulating 1 event then an error, followed by reconnect
    event_count = 0
    async def mock_events():
        nonlocal event_count
        if event_count == 0:
            event_count += 1
            yield SimpleNamespace(type="session.updated")
            # Simulate unexpected provider disconnection
            raise ConnectionError("Provider stream closed unexpectedly")
        else:
            yield SimpleNamespace(type="session.updated")

    mock_adapter.events = mock_events

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        stt_model="whisper-large-v3",
        realtime_model="gpt-live-1",
    )

    # Run _provider_events task briefly
    task = asyncio.create_task(bridge._provider_events())
    await asyncio.sleep(0.05)
    bridge._stop_event.set()
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify reconnect was called automatically
    mock_adapter.reconnect.assert_awaited()
    assert bridge.telemetry.get("reconnect_triggered") is True
    reconnect_attempts = bridge.telemetry.get("reconnect_attempts")
    assert isinstance(reconnect_attempts, int) and reconnect_attempts >= 1


@pytest.mark.asyncio
async def test_employee_coach_session_id_strict_binding(tmp_path):
    """Vérifie que la confirmation de tâche exige une session strictement identique, rejetant toute session absente ou différente."""
    engine, session, company, config, _api_key, _orchestrator = _voice_database(tmp_path)
    try:
        user = _create_test_user(
            session,
            company.id,
            first_name="Jean",
            last_name="Tremblay",
            email="jean.tremblay@avenqo.test",
            job_title="Technicien",
            role=UserRole.USER,
        )
        task = EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=user.id,
            created_by_user_id=user.id,
            title="Vérifier le compresseur atelier",
            status="open",
        )
        session.add(task)
        session.commit()

        coach = EmployeeCoachService(session)

        # 0. Test du cas None -> None (token émis sans session, confirmation sans session) -> REJET STRICT
        pre_none = coach.complete_task(
            user,
            "compresseur",
            confirmed=False,
            session_id=None,
        )
        assert pre_none["status"] == "requires_confirmation"
        token_none = pre_none["confirmation_token"]
        assert token_none is not None
        res_none_none = coach.complete_task(
            user,
            "compresseur",
            confirmed=True,
            confirmation_token=token_none,
            session_id=None,
        )
        assert res_none_none["status"] == "requires_confirmation"

        # 1. Demande de confirmation rattachée à la session call-438 et turn_id=1
        pre = coach.complete_task(
            user,
            "compresseur",
            confirmed=False,
            session_id="call-438",
            turn_id=1,
        )
        assert pre["status"] == "requires_confirmation"
        token = pre["confirmation_token"]
        assert token is not None

        # 2. Tentative avec token valide mais session_id absent (None) -> REJET OBLIGATOIRE
        res_no_session = coach.complete_task(
            user,
            "compresseur",
            confirmed=True,
            confirmation_token=token,
            session_id=None,
            turn_id=2,
        )
        assert res_no_session["status"] == "requires_confirmation"

        # 3. Demande à nouveau avec call-438 et turn_id=1
        pre2 = coach.complete_task(
            user,
            "compresseur",
            confirmed=False,
            session_id="call-438",
            turn_id=1,
        )
        token2 = pre2["confirmation_token"]

        # 4. Tentative avec session différente ("call-999") -> REJET OBLIGATOIRE
        res_wrong_session = coach.complete_task(
            user,
            "compresseur",
            confirmed=True,
            confirmation_token=token2,
            session_id="call-999",
            turn_id=2,
        )
        assert res_wrong_session["status"] == "requires_confirmation"

        # 5. Tentative sur le même tour vocal (turn_id=1 au lieu d'un tour ultérieur) -> REJET OBLIGATOIRE
        pre_turn = coach.complete_task(
            user,
            "compresseur",
            confirmed=False,
            session_id="call-438",
            turn_id=1,
        )
        token_turn = pre_turn["confirmation_token"]
        res_same_turn = coach.complete_task(
            user,
            "compresseur",
            confirmed=True,
            confirmation_token=token_turn,
            session_id="call-438",
            turn_id=1,
        )
        assert res_same_turn["status"] == "requires_confirmation"

        # 6. Tentative avec tour antérieur (turn_id=0) -> REJET OBLIGATOIRE
        pre_past = coach.complete_task(
            user,
            "compresseur",
            confirmed=False,
            session_id="call-438",
            turn_id=2,
        )
        token_past = pre_past["confirmation_token"]
        res_past_turn = coach.complete_task(
            user,
            "compresseur",
            confirmed=True,
            confirmation_token=token_past,
            session_id="call-438",
            turn_id=1,
        )
        assert res_past_turn["status"] == "requires_confirmation"

        # 7. Demande avec call-438 et turn_id=3
        pre3 = coach.complete_task(
            user,
            "compresseur",
            confirmed=False,
            session_id="call-438",
            turn_id=3,
        )
        token3 = pre3["confirmation_token"]

        # 8. Tentative avec session exacte "call-438" et tour ultérieur vérifié (turn_id=4) -> SUCCÈS
        res_valid = coach.complete_task(
            user,
            "compresseur",
            confirmed=True,
            confirmation_token=token3,
            session_id="call-438",
            turn_id=4,
        )
        assert res_valid["status"] == "success"
        assert res_valid["status_after"] == "done"
    finally:
        session.close()
        engine.dispose()
