"""Add company_routing_nips table and secure resolver function for inbound DTMF telephony routing.

Revision ID: 0065_company_routing_nips
Revises: 0064_ai_enterprise_memory
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0065_company_routing_nips"
down_revision = "0064_ai_enterprise_memory"
branch_labels = None
depends_on = None


def _is_postgres(bind) -> bool:
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and getattr(dialect, "name", None) == "postgresql"


_RESOLVER_SQL = """
CREATE OR REPLACE FUNCTION public.resolve_company_routing_nip(
    p_routing_code_hash text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_company_id uuid;
BEGIN
    SELECT company_id INTO v_company_id
    FROM company_routing_nips
    WHERE routing_code_hash = p_routing_code_hash
      AND status = 'ACTIVE'
      AND (locked_until IS NULL OR locked_until < now())
    LIMIT 1;

    RETURN v_company_id;
END;
$$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "company_routing_nips" not in tables:
        op.create_table(
            "company_routing_nips",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("routing_code", sa.String(16), nullable=False),
            sa.Column("routing_code_hash", sa.String(64), nullable=False, index=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE", index=True),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

        if _is_postgres(bind):
            op.execute(
                "CREATE UNIQUE INDEX uq_active_company_routing_nip ON company_routing_nips (company_id) WHERE status = 'ACTIVE';"
            )
            op.execute(
                "CREATE UNIQUE INDEX uq_active_routing_code_hash ON company_routing_nips (routing_code_hash) WHERE status = 'ACTIVE';"
            )

            op.execute("ALTER TABLE company_routing_nips ENABLE ROW LEVEL SECURITY;")
            op.execute("ALTER TABLE company_routing_nips FORCE ROW LEVEL SECURITY;")
            op.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE tablename = 'company_routing_nips'
                        AND policyname = 'company_routing_nips_tenant_isolation'
                    ) THEN
                        CREATE POLICY company_routing_nips_tenant_isolation
                        ON company_routing_nips
                        USING (company_id = avenqo_tenant_id())
                        WITH CHECK (company_id = avenqo_tenant_id());
                    END IF;
                END $$;
                """
            )

            op.execute(_RESOLVER_SQL)
            op.execute("GRANT EXECUTE ON FUNCTION public.resolve_company_routing_nip(text) TO PUBLIC;")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "company_routing_nips" in tables:
        if _is_postgres(bind):
            op.execute("DROP FUNCTION IF EXISTS public.resolve_company_routing_nip(text);")
            op.execute("DROP POLICY IF EXISTS company_routing_nips_tenant_isolation ON company_routing_nips;")
        op.drop_table("company_routing_nips")
