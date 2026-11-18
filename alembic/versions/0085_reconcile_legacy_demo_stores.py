"""Reconcile legacy synthetic demo stores and demo products missed by 0084.

Revision ID: 0085_reconcile_legacy_demo_stores
Revises: 0084_commerce_demo_isolation
"""

from __future__ import annotations

import logging
from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

revision = "0085_reconcile_legacy_demo_stores"
down_revision = "0084_commerce_demo_isolation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    is_demo_val = "true" if is_pg else "1"

    # Step 1: Read-only inventory of matching legacy demo connections without exposing credentials
    inventory_sql = sa.text(
        "SELECT id, company_id, provider, external_account_id, display_name, status, last_successful_sync "
        "FROM commerce_connections "
        "WHERE ("
        "  external_account_id LIKE '%.avenqo.test%' "
        "  OR external_account_id LIKE '%-store.avenqo.test' "
        "  OR display_name LIKE 'Boutique % Sandbox' "
        "  OR display_name LIKE '%(Boutique de démonstration%' "
        "  OR id IN ("
        "    SELECT DISTINCT connection_id FROM normalized_commerce_records "
        "    WHERE source_record_id LIKE '%-prod-101' "
        "       OR source_record_id LIKE '%-prod-102' "
        "       OR source_record_id LIKE '%-prod-103' "
        "       OR source_record_id LIKE '%-prod-104'"
        "  )"
        ") "
        "AND ("
        "  external_account_id LIKE '%.avenqo.test%' "
        "  OR display_name LIKE 'Boutique % Sandbox' "
        "  OR display_name LIKE '%(Boutique de démonstration%' "
        "  OR provider IN ('sandbox_demo', 'demo')"
        ")"
    )

    rows = bind.execute(inventory_sql).fetchall()
    tenant_breakdown: dict[str, int] = {}
    for row in rows:
        tenant_id = str(row[1])
        tenant_breakdown[tenant_id] = tenant_breakdown.get(tenant_id, 0) + 1

    logger.info(
        "0085_reconcile_legacy_demo_stores: Discovered %d legacy synthetic demo connections across %d tenants.",
        len(rows),
        len(tenant_breakdown),
    )

    # Step 2: Mutate legacy demo connections: mark is_demo=True and clear fake sync timestamps
    update_connections_sql = sa.text(
        f"UPDATE commerce_connections "
        f"SET is_demo = {is_demo_val}, last_successful_sync = NULL, sync_completed_at = NULL "
        f"WHERE ("
        f"  external_account_id LIKE '%.avenqo.test%' "
        f"  OR external_account_id LIKE '%-store.avenqo.test' "
        f"  OR display_name LIKE 'Boutique % Sandbox' "
        f"  OR display_name LIKE '%(Boutique de démonstration%' "
        f"  OR id IN ("
        f"    SELECT DISTINCT connection_id FROM normalized_commerce_records "
        f"    WHERE source_record_id LIKE '%-prod-101' "
        f"       OR source_record_id LIKE '%-prod-102' "
        f"       OR source_record_id LIKE '%-prod-103' "
        f"       OR source_record_id LIKE '%-prod-104'"
        f"  )"
        f") "
        f"AND ("
        f"  external_account_id LIKE '%.avenqo.test%' "
        f"  OR display_name LIKE 'Boutique % Sandbox' "
        f"  OR display_name LIKE '%(Boutique de démonstration%' "
        f"  OR provider IN ('sandbox_demo', 'demo')"
        f")"
    )
    bind.execute(update_connections_sql)

    # Step 3: Mutate associated synthetic products and any orphaned demo items
    is_demo_cond = f"is_demo = {is_demo_val}"
    update_records_sql = sa.text(
        f"UPDATE normalized_commerce_records "
        f"SET is_demo = {is_demo_val} "
        f"WHERE connection_id IN (SELECT id FROM commerce_connections WHERE {is_demo_cond}) "
        f"OR source_record_id LIKE '%-prod-101' "
        f"OR source_record_id LIKE '%-prod-102' "
        f"OR source_record_id LIKE '%-prod-103' "
        f"OR source_record_id LIKE '%-prod-104' "
        f"OR source_record_id LIKE 'demo_%' "
        f"OR provider IN ('sandbox_demo', 'demo')"
    )
    bind.execute(update_records_sql)


def downgrade() -> None:
    # Downgrade preserves schema structure (columns added in 0084 remain untouched)
    pass
