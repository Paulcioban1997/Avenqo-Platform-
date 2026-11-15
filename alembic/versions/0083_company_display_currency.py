"""Optional company display currency. Settlement currency stays currency_code.

Revision ID: 0083_company_display_currency
Revises: 0082_trading_watch_items
"""

from alembic import op
import sqlalchemy as sa

revision = "0083_company_display_currency"
down_revision = "0082_trading_watch_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("companies")}
    if "display_currency" not in columns:
        op.add_column("companies", sa.Column("display_currency", sa.String(length=3), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("companies")}
    if "display_currency" in columns:
        op.drop_column("companies", "display_currency")
