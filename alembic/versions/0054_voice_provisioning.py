"""Add durable commercial Voice provisioning; no active-DB execution here."""
from alembic import op
import sqlalchemy as sa
revision = "0054_voice_provisioning"
down_revision = "0053_voice_module_permissions"
branch_labels = depends_on = None

def uid(name, target=None, **kw):
    args = [sa.ForeignKey(target)] if target else []
    return sa.Column(name, sa.Uuid(), *args, **kw)

def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]

def upgrade():
    existing = sa.inspect(op.get_bind())
    if not existing.has_table("voice_number_tariffs"):
        op.create_table("voice_number_tariffs", uid("id", primary_key=True),
            sa.Column("country", sa.String(2), nullable=False), sa.Column("number_type", sa.String(32), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False), sa.Column("monthly_amount", sa.Integer(), nullable=False),
            sa.Column("stripe_price_id", sa.String(255)), sa.Column("provider_cost_limits", sa.JSON(), nullable=False),
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()), *timestamps(),
            sa.UniqueConstraint("country", "number_type", "currency", name="uq_voice_tariff_market"),
            sa.CheckConstraint("monthly_amount > 0", name="ck_voice_tariff_amount"))
    if not existing.has_table("voice_provisioning_orders"):
        op.create_table("voice_provisioning_orders", uid("id", primary_key=True),
            uid("company_id", "companies.id", nullable=False, index=True), uid("actor_id", "users.id", nullable=False),
            sa.Column("phone_number", sa.String(32), nullable=False, index=True), sa.Column("status", sa.String(40), nullable=False, index=True),
            sa.Column("snapshot", sa.JSON(), nullable=False), sa.Column("consent_at", sa.DateTime(timezone=True)),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("stripe_customer_id", sa.String(255), nullable=False),
            sa.Column("stripe_subscription_id", sa.String(255), nullable=False, index=True),
            sa.Column("stripe_invoice_id", sa.String(255), unique=True), sa.Column("stripe_item_id", sa.String(255)),
            sa.Column("invoice_url", sa.String(2048)), sa.Column("paid_at", sa.DateTime(timezone=True)),
            sa.Column("provider_order_id", sa.String(255), unique=True), sa.Column("provider_number_id", sa.String(255), unique=True),
            uid("number_id", "voice_phone_numbers.id"), uid("config_id", "voice_business_configs.id"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("available_at", sa.DateTime(timezone=True), nullable=False), sa.Column("lease_until", sa.DateTime(timezone=True)),
            sa.Column("error_code", sa.String(64)), sa.Column("suspended_by_owner", sa.Boolean(), nullable=False, server_default=sa.false()), *timestamps())
    if not existing.has_table("voice_provisioning_claims"):
        op.create_table("voice_provisioning_claims", sa.Column("phone_number", sa.String(32), primary_key=True),
                        uid("order_id", "voice_provisioning_orders.id", unique=True, nullable=False),
                        uid("company_id", "companies.id", unique=True, nullable=False))
    if not existing.has_table("voice_telecom_costs"):
        op.create_table("voice_telecom_costs",uid("call_id","voice_calls.id",primary_key=True),
            uid("company_id","companies.id",nullable=False,index=True),sa.Column("event_id",sa.String(255),nullable=False,unique=True),
            sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False),sa.Column("status",sa.String(32),nullable=False),
            sa.Column("costs_by_currency",sa.JSON(),nullable=False),sa.Column("billed_seconds",sa.Integer(),nullable=False,server_default="0"))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE voice_provisioning_claims ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE voice_provisioning_claims FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS voice_provisioning_claims_tenant ON voice_provisioning_claims")
        op.execute("""CREATE POLICY voice_provisioning_claims_tenant ON voice_provisioning_claims
            USING (current_setting('app.bypass_rls',true)='on' OR company_id=avenqo_tenant_id())
            WITH CHECK (current_setting('app.bypass_rls',true)='on' OR company_id=avenqo_tenant_id())""")
        op.execute("ALTER TABLE voice_provisioning_orders ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE voice_provisioning_orders FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS voice_provisioning_orders_tenant ON voice_provisioning_orders")
        op.execute("""CREATE POLICY voice_provisioning_orders_tenant ON voice_provisioning_orders
            USING (current_setting('app.bypass_rls',true)='on' OR company_id=avenqo_tenant_id())
            WITH CHECK (current_setting('app.bypass_rls',true)='on' OR company_id=avenqo_tenant_id())""")
        op.execute("ALTER TABLE voice_telecom_costs ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE voice_telecom_costs FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS voice_telecom_costs_tenant ON voice_telecom_costs")
        op.execute("""CREATE POLICY voice_telecom_costs_tenant ON voice_telecom_costs
            USING (current_setting('app.bypass_rls',true)='on' OR company_id=avenqo_tenant_id())
            WITH CHECK (current_setting('app.bypass_rls',true)='on' OR company_id=avenqo_tenant_id())""")

def downgrade():
    raise RuntimeError("Preserve consent and billing history; use an approved forward repair instead of dropping these tables")
