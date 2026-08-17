from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.experiments import InMemoryExperimentRepository
from tests.ai_engine.test_experiment_contracts import build_run


def test_depot_sauvegarde_et_retrouve_un_run_de_son_tenant() -> None:
    repository = InMemoryExperimentRepository()
    run = build_run("00000000-0000-0000-0000-000000000001")

    repository.save(run)

    assert repository.get(run.tenant, run.id) == run


def test_depot_masque_un_run_aux_autres_tenants() -> None:
    repository = InMemoryExperimentRepository()
    run = build_run("00000000-0000-0000-0000-000000000001")
    other_tenant = TenantContext(
        UUID("00000000-0000-0000-0000-000000000002")
    )
    repository.save(run)

    assert repository.get(other_tenant, run.id) is None


def test_depot_filtre_historique_par_tenant_module_et_tache() -> None:
    repository = InMemoryExperimentRepository()
    demand = build_run("00000000-0000-0000-0000-000000000001")
    classification = replace(
        build_run("00000000-0000-0000-0000-000000000001"),
        task_code="classification",
    )
    other_company = build_run("00000000-0000-0000-0000-000000000002")
    for run in (demand, classification, other_company):
        repository.save(run)

    history = repository.list_for_task(demand.tenant, "retail", "demand")

    assert history == (demand,)


def test_depot_classe_historique_du_plus_recent_au_plus_ancien() -> None:
    repository = InMemoryExperimentRepository()
    old_run = replace(
        build_run("00000000-0000-0000-0000-000000000001"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    recent_run = replace(
        build_run("00000000-0000-0000-0000-000000000001"),
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    repository.save(old_run)
    repository.save(recent_run)

    history = repository.list_for_task(old_run.tenant, "retail", "demand")

    assert history == (recent_run, old_run)


def test_depot_refuse_de_transferer_un_run_a_un_autre_tenant() -> None:
    repository = InMemoryExperimentRepository()
    run = build_run("00000000-0000-0000-0000-000000000001")
    repository.save(run)
    transferred = replace(
        run,
        tenant=TenantContext(
            UUID("00000000-0000-0000-0000-000000000002")
        ),
    )

    with pytest.raises(ValueError, match="changer d'entreprise"):
        repository.save(transferred)