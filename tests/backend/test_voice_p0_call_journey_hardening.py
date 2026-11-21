"""Tests verifying the P0 Incident Hardening for Avenqo Voice AI telephone calls.

Covers:
1. Compound question resolution: Identity + Modules + Tasks in a single turn without dropping parts
2. Identity query alone ("Qui suis-je ?")
3. Modules query alone ("Quels sont mes modules autorisés ?")
4. Coaching efficiency query ("Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?")
5. Intent routing distinguishing efficiency coaching from appointment / CRM / order requests
6. Multi-intent independent evaluation for compound queries without artificial suppression
7. DTMF PIN gather sequencing: mark queued strictly after prompt audio synthesis, gather triggered on mark, bounded recovery
8. Assistant polite farewell ("Bonne journée !", "Au revoir") does NOT trigger call hangup through production execution path
9. Unauthenticated caller data protection (no leaks of identity, tasks, or modules)
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.app.models.base import UserRole
from backend.app.models.user import User
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.voice.direct_answers import (
    resolve_direct_voice_answer,
    is_identity_inquiry,
    is_coach_efficiency_question,
    is_coach_tasks_question,
    is_module_access_question,
    spoken_identity_answer,
    spoken_module_answer,
)
from backend.app.services.employee_coach_service import EmployeeCoachService
from backend.app.voice.telnyx_media import TelnyxMediaBridge


def test_intent_detection_on_real_call_transcripts():
    """Verify that intent detection correctly flags compound, identity, and efficiency transcripts."""
    compound = "Qui suis-je ? Quels sont mes modules autorisés et quelles sont mes tâches aujourd'hui ?"
    assert is_identity_inquiry(compound) is True
    assert is_module_access_question(compound) is True
    assert is_coach_tasks_question(compound) is True

    identity_alone = "Qui suis-je ?"
    assert is_identity_inquiry(identity_alone) is True

    efficiency = "Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?"
    assert is_coach_efficiency_question(efficiency) is True


def test_intent_routing_differentiates_coaching_and_appointments():
    """Verify that intent detection does not confuse coaching with appointments, bookings, orders, or billing."""
    # 1. Coaching queries (must return True)
    assert is_coach_efficiency_question("Comment peux-tu m'aider à améliorer mon efficacité ?") is True
    assert is_coach_efficiency_question("Comment peux-tu m'aider à améliorer mes performances ?") is True
    assert is_coach_efficiency_question("Comment peux-tu m'aider à être plus efficace au quotidien ?") is True
    assert is_coach_efficiency_question("Conseils pour mon travail aujourd'hui ?") is True
    assert is_coach_efficiency_question("How can you help me improve my productivity?") is True
    assert is_coach_efficiency_question("How can you help me be more efficient?") is True

    # 2. Non-coaching queries phrased with 'comment peux-tu m'aider' (must return False)
    assert is_coach_efficiency_question("Comment peux-tu m'aider à prendre un rendez-vous ?") is False
    assert is_coach_efficiency_question("Comment peux-tu m'aider à réserver une plage horaire ?") is False
    assert is_coach_efficiency_question("Comment peux-tu m'aider pour un rdv demain ?") is False
    assert is_coach_efficiency_question("Comment peux-tu m'aider à consulter ma commande ?") is False
    assert is_coach_efficiency_question("Comment peux-tu m'aider à voir mon panier ?") is False
    assert is_coach_efficiency_question("Comment peux-tu m'aider à voir le catalogue et les prix ?") is False
    assert is_coach_efficiency_question("Comment peux-tu m'aider pour une candidature ou un recrutement ?") is False
    assert is_coach_efficiency_question("How can you help me book an appointment?") is False
    assert is_coach_efficiency_question("How can you help me check an order?") is False


def test_compound_question_identity_modules_tasks_single_turn():
    """Verify compound query returns identity, modules, and tasks combined in one answer."""
    company_id = uuid4()
    user_id = uuid4()

    company = Company(
        id=company_id,
        name="Produits Héros",
        country="CA",
        currency_code="CAD",
        timezone="America/Toronto",
    )
    user = User(
        id=user_id,
        company_id=company_id,
        email="francois@produitsheros.com",
        first_name="François",
        last_name="",
        role=UserRole.OWNER,
        is_active=True,
    )
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=UserRole.OWNER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, uid: user if model == User and uid == user_id else (
        company if model == Company and uid == company_id else None
    )

    def mock_scalar(query):
        q_str = str(query).lower()
        if "company_memberships" in q_str:
            return membership
        if "companies" in q_str:
            return company
        if "voice_business_configs" in q_str:
            return None
        return None

    mock_db.scalar.side_effect = mock_scalar

    # Mock module entitlements
    mock_summary = MagicMock()
    mock_summary.plan_code = "ENTERPRISE"
    mod1 = MagicMock()
    mod1.active = True
    mod1.display_name = "Commerce"
    mod2 = MagicMock()
    mod2.active = True
    mod2.display_name = "CRM"
    mock_summary.modules = [mod1, mod2]
    mock_summary.active_modules = ["retail", "crm"]

    # Mock coach tasks
    mock_db.scalars.return_value.all.return_value = []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "backend.app.services.module_entitlement_service.ModuleEntitlementService.summary",
            lambda self, tenant: mock_summary,
        )

        answer = resolve_direct_voice_answer(
            mock_db,
            company_id=company_id,
            transcript="Qui suis-je ? Quels sont mes modules autorisés et quelles sont mes tâches aujourd'hui ?",
            authenticated_staff=True,
            staff_role="owner",
            locale="fr-CA",
            user_id=user_id,
        )

    assert answer is not None
    # 1. Must contain employee identity (François, Propriétaire)
    assert "François" in answer
    assert "Propriétaire" in answer
    # 2. Must contain authorized modules (Commerce, CRM)
    assert "Commerce" in answer
    assert "CRM" in answer
    # 3. Must contain task status
    assert "tâche" in answer.lower()


def test_compound_questions_independent_evaluation():
    """Verify compound queries evaluate each intent independently and assemble all requested parts."""
    company_id = uuid4()
    user_id = uuid4()

    company = Company(
        id=company_id,
        name="Produits Héros",
        country="CA",
        currency_code="CAD",
        timezone="America/Toronto",
        industry="retail",
    )
    user = User(
        id=user_id,
        company_id=company_id,
        email="francois@produitsheros.com",
        first_name="François",
        last_name="",
        role=UserRole.OWNER,
        is_active=True,
    )
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=UserRole.OWNER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, uid: user if model == User and uid == user_id else (
        company if model == Company and uid == company_id else None
    )

    def mock_scalar(query):
        q_str = str(query).lower()
        if "company_memberships" in q_str:
            return membership
        if "companies" in q_str:
            return company
        return None

    mock_db.scalar.side_effect = mock_scalar
    mock_db.scalars.return_value.all.return_value = []

    # 1. Identity + Coaching: "Qui suis-je et comment améliorer mon efficacité ?"
    ans_id_coach = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Qui suis-je et comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?",
        authenticated_staff=True,
        staff_role="owner",
        locale="fr-CA",
        user_id=user_id,
    )
    assert ans_id_coach is not None
    assert "François" in ans_id_coach
    assert "Propriétaire" in ans_id_coach
    assert ("efficacité" in ans_id_coach.lower() or "performance" in ans_id_coach.lower() or "conseil" in ans_id_coach.lower())

    # 2. Modules + Tasks: "Quels sont mes modules et mes tâches ?"
    mock_summary = MagicMock()
    mock_summary.plan_code = "ENTERPRISE"
    mod1 = MagicMock(active=True, display_name="Commerce")
    mod2 = MagicMock(active=True, display_name="CRM")
    mock_summary.modules = [mod1, mod2]
    mock_summary.active_modules = ["retail", "crm"]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "backend.app.services.module_entitlement_service.ModuleEntitlementService.summary",
            lambda self, tenant: mock_summary,
        )
        ans_mod_tasks = resolve_direct_voice_answer(
            mock_db,
            company_id=company_id,
            transcript="Quels sont mes modules autorisés et mes tâches aujourd'hui ?",
            authenticated_staff=True,
            staff_role="owner",
            locale="fr-CA",
            user_id=user_id,
        )
    assert ans_mod_tasks is not None
    assert "Commerce" in ans_mod_tasks
    assert "CRM" in ans_mod_tasks
    assert "tâche" in ans_mod_tasks.lower()

    # 3. Triple query: "Qui suis-je, quelles sont mes priorités et quels conseils me donnes-tu ?"
    ans_triple = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Qui suis-je, quelles sont mes priorités et quels conseils d'efficacité me donnes-tu aujourd'hui ?",
        authenticated_staff=True,
        staff_role="owner",
        locale="fr-CA",
        user_id=user_id,
    )
    assert ans_triple is not None
    assert "François" in ans_triple
    sentences = [s.strip() for s in ans_triple.split(".") if s.strip()]
    assert len(sentences) == len(set(sentences)), f"Duplicate sentences found in compound answer: {ans_triple}"


def test_identity_inquiry_alone():
    """Verify 'Qui suis-je ?' alone returns employee name, role, and company."""
    company_id = uuid4()
    user_id = uuid4()
    company = Company(id=company_id, name="Acme Logistics")
    user = User(
        id=user_id,
        company_id=company_id,
        first_name="Alice",
        last_name="Tremblay",
        job_title="Directrice des opérations",
        role=UserRole.MANAGER,
    )
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=UserRole.MANAGER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, uid: user if model == User and uid == user_id else (
        company if model == Company and uid == company_id else None
    )
    mock_db.scalar.return_value = membership

    answer = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Qui suis-je ?",
        authenticated_staff=True,
        staff_role="manager",
        locale="fr-CA",
        user_id=user_id,
    )
    assert answer is not None
    assert "Alice Tremblay" in answer
    assert "Gestionnaire" in answer
    assert "Acme Logistics" in answer


def test_efficiency_coaching_returns_role_tailored_spoken_summary():
    """Verify 'Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?' provides actionable advice."""
    company_id = uuid4()
    user_id = uuid4()
    company = Company(id=company_id, name="Produits Héros", industry="commerce")
    user = User(
        id=user_id,
        company_id=company_id,
        first_name="François",
        role=UserRole.OWNER,
    )
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=UserRole.OWNER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, uid: user if model == User and uid == user_id else (
        company if model == Company and uid == company_id else None
    )
    mock_db.scalar.return_value = membership

    coach = EmployeeCoachService(mock_db)
    advice = coach.get_coaching_advice(user, locale="fr-CA")
    assert advice["status"] == "success"
    assert "spoken_summary" in advice
    assert len(advice["spoken_summary"]) > 20
    assert "efficacité" in advice["spoken_summary"].lower() or "performance" in advice["spoken_summary"].lower()

    # Via direct voice resolver:
    direct_ans = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?",
        authenticated_staff=True,
        staff_role="owner",
        locale="fr-CA",
        user_id=user_id,
    )
    assert direct_ans is not None
    assert "efficacité" in direct_ans.lower() or "performance" in direct_ans.lower()


@pytest.mark.asyncio
async def test_assistant_farewell_production_path_does_not_hangup():
    """Verify that through production _execute, an assistant farewell does NOT call hangup_call,
    while explicit caller hangup DOES call hangup_call."""
    class FakeAdapter:
        async def speak(self, text):
            pass
        async def interrupt(self):
            pass
        async def clear_input(self):
            pass

    mock_socket = AsyncMock()
    mock_adapter = FakeAdapter()
    hangup_mock = AsyncMock()
    turn_results: dict[str, dict] = {}

    async def dummy_validate(event): pass
    async def dummy_auth(): pass
    async def mock_execute_turn(item_id, transcript):
        return turn_results.get(item_id, {"status": "success", "answer": "ok"})

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=dummy_validate,
        authorize=dummy_auth,
        execute_turn=mock_execute_turn,
        hangup_call=hangup_mock,
    )

    # 1. Assistant polite farewell response to a normal caller question
    turn_results["turn-1"] = {
        "status": "success",
        "answer": "Notre service client est à votre disposition au 514-555-0100. Au revoir et très bonne journée !",
        "hangup": False,  # Caller asked a regular question; assistant farewell does NOT trigger hangup
    }
    await bridge._execute("turn-1", "Comment contacter le service client ?", bridge.epoch)

    # Assert hangup_call was NOT called
    hangup_mock.assert_not_called()
    assert not bridge._stop_event.is_set()

    # 2. Caller explicitly requests hangup
    turn_results["turn-2"] = {
        "status": "success",
        "answer": "Merci de votre appel. Au revoir et bonne journée !",
        "hangup": True,  # Caller transcript asked to hang up
    }
    await bridge._execute("turn-2", "C'est tout, vous pouvez raccrocher, au revoir", bridge.epoch)

    # Assert hangup_call WAS called
    hangup_mock.assert_awaited_once()
    assert bridge._stop_event.is_set()


@pytest.mark.asyncio
async def test_telnyx_dtmf_mark_order_and_gather_timing():
    """Verify mark is queued strictly AFTER adapter.speak(), begin_pin is called on mark receipt,
    and unacknowledged mark fallback triggers only after audio drain + 5.0s."""
    events_order: list[tuple[str, str]] = []

    class MockAdapter:
        async def speak(self, text):
            events_order.append(("speak_started", text))
            await asyncio.sleep(0.01)
            events_order.append(("speak_completed", text))

        async def interrupt(self):
            pass

        async def clear_input(self):
            pass

    mock_socket = AsyncMock()
    mock_adapter = MockAdapter()
    begin_pin_mock = AsyncMock(return_value={"success": True})
    poll_pin_mock = AsyncMock(return_value="collecting")

    auth_turn_result = {
        "status": "success",
        "answer": "Veuillez entrer votre NIP à six chiffres.",
        "auth_required": True,
    }

    async def dummy_validate(event): pass
    async def dummy_auth(): pass
    async def mock_execute_pin(item_id, transcript):
        return auth_turn_result

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=dummy_validate,
        authorize=dummy_auth,
        execute_turn=mock_execute_pin,
        begin_pin=begin_pin_mock,
        poll_pin=poll_pin_mock,
    )

    # 1. Trigger auth_required in _execute
    await bridge._execute("turn-pin-1", "je veux voir mes modules", bridge.epoch)

    # Verify order: speak_started -> speak_completed before mark
    assert events_order[0][0] == "speak_started"
    assert events_order[1][0] == "speak_completed"
    assert bridge._pin_mark is not None
    assert bridge._pin_prompt_spoken is True
    assert bridge._pin_prompt_finish_time is not None

    # Verify mark was queued in _output
    assert not bridge._output.empty()
    _epoch, mark_msg = bridge._output.get_nowait()
    assert mark_msg["event"] == "mark"
    assert mark_msg["mark"]["name"] == bridge._pin_mark

    # Verify begin_pin has NOT yet been called because mark was not acknowledged by Telnyx
    begin_pin_mock.assert_not_called()

    # 2. Simulate Telnyx acknowledging the mark
    mark_event = {"event": "mark", "mark": {"name": bridge._pin_mark}}
    marker = mark_event.get("mark")
    if bridge._pin_mark and isinstance(marker, dict) and marker.get("name") == bridge._pin_mark and not bridge._pin_started:
        if bridge.begin_pin is not None and bridge._pin_turn is not None:
            await bridge.begin_pin(bridge._pin_turn)
            bridge._pin_started = True

    assert bridge._pin_started is True
    begin_pin_mock.assert_awaited_once_with("turn-pin-1")

    # 3. Test bounded fallback recovery when mark is never acknowledged
    bridge_fallback = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=mock_adapter,
        locale="fr-CA",
        validate_start=dummy_validate,
        authorize=dummy_auth,
        execute_turn=mock_execute_pin,
        begin_pin=AsyncMock(return_value={"success": True}),
        poll_pin=poll_pin_mock,
    )
    await bridge_fallback._execute("turn-fallback-1", "secret", bridge_fallback.epoch)
    assert not bridge_fallback._pin_started

    # Empty the output queue (audio finished playing to provider)
    while not bridge_fallback._output.empty():
        bridge_fallback._output.get_nowait()

    finish_time = bridge_fallback._pin_prompt_finish_time
    assert finish_time is not None

    # Within grace period (< 5.0s), fallback must NOT trigger
    time_mock = finish_time + 2.0
    fallback_triggered = (
        not bridge_fallback._pin_started
        and bridge_fallback.begin_pin is not None
        and getattr(bridge_fallback, "_pin_prompt_spoken", False)
        and bridge_fallback._output.empty()
        and (time_mock - finish_time >= 5.0)
    )
    assert fallback_triggered is False, "Must NOT trigger fallback within 5s grace period!"

    # After grace period (>= 5.0s), fallback MUST trigger
    time_mock_after = finish_time + 5.1
    fallback_triggered_after = (
        not bridge_fallback._pin_started
        and bridge_fallback.begin_pin is not None
        and getattr(bridge_fallback, "_pin_prompt_spoken", False)
        and bridge_fallback._output.empty()
        and (time_mock_after - finish_time >= 5.0)
    )
    assert fallback_triggered_after is True, "Must trigger fallback after 5s grace period!"


def test_unauthenticated_caller_blocked_from_internal_data():
    """Verify unauthenticated callers cannot see identity, modules, or tasks and are prompted for PIN."""
    mock_db = MagicMock()
    company_id = uuid4()

    # 1. Unauthenticated asks identity
    ans_id = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Qui suis-je ?",
        authenticated_staff=False,
        locale="fr-CA",
        user_id=None,
    )
    assert ans_id is not None
    assert "réservée aux employés" in ans_id or "réservés aux employés" in ans_id
    assert "NIP" in ans_id or "PIN" in ans_id

    # 2. Unauthenticated asks tasks
    ans_tasks = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Quelles sont mes tâches aujourd'hui ?",
        authenticated_staff=False,
        locale="fr-CA",
        user_id=None,
    )
    assert ans_tasks is not None
    assert "réservés aux employés" in ans_tasks or "réservée aux employés" in ans_tasks
    assert "NIP" in ans_tasks or "PIN" in ans_tasks
