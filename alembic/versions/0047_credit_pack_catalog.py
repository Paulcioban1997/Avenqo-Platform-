"""Versioned voluntary CAD packs and immutable purchase terms."""
from alembic import op
import sqlalchemy as sa

revision = "0047_credit_pack_catalog"
down_revision = "0046_voice_personalization_customization"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "offer_snapshot" not in {column["name"] for column in inspector.get_columns("ai_credit_purchases")}:
        op.add_column("ai_credit_purchases", sa.Column("offer_snapshot", sa.JSON(), nullable=False, server_default="{}"))
    if inspector.has_table("ai_credit_pack_offers"):
        table = sa.Table("ai_credit_pack_offers", sa.MetaData(), autoload_with=bind)
    else:
        table = op.create_table("ai_credit_pack_offers",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("profitability_review", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("credits > 0", name="ck_credit_offer_credits_positive"),
        sa.CheckConstraint("price_cents > 0", name="ck_credit_offer_price_positive"))
    existing = set(bind.execute(sa.select(table.c.code)).scalars())
    seeds = [
        {"code":"starter_1000_v1", "name":"Starter", "credits":1000, "price_cents":1000, "enabled":False, "profitability_review":{}},
        {"code":"growth_4000_v1", "name":"Growth", "credits":4000, "price_cents":3500, "enabled":False, "profitability_review":{}},
        {"code":"power_10000_v1", "name":"Power", "credits":10000, "price_cents":8000, "enabled":False, "profitability_review":{}},
    ]
    missing = [seed for seed in seeds if seed["code"] not in existing]
    if missing:
        op.bulk_insert(table, missing)

def downgrade():
    op.drop_table("ai_credit_pack_offers")
    op.drop_column("ai_credit_purchases", "offer_snapshot")
