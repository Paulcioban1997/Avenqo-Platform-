"""Add Company.currency_code (ISO-4217) with country-derived backfill.

Revision ID: 0005_company_currency_code
Revises: 0004_company_signup_profile

Pour les entreprises existantes : la devise est déduite du PAYS (jamais de la
langue) via le catalogue central quand le pays est connu, sinon USD comme
fallback technique. Une devise déjà renseignée n'est jamais écrasée.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_company_currency_code"
down_revision = "0004_company_signup_profile"
branch_labels = None
depends_on = None

# country (lowercase) -> ISO-4217 (mêmes defaults que le catalogue central).
_COUNTRY_TO_CURRENCY = {
    "canada": "CAD", "ca": "CAD",
    "united states": "USD", "us": "USD", "usa": "USD",
    "spain": "EUR", "es": "EUR", "portugal": "EUR", "pt": "EUR",
    "germany": "EUR", "de": "EUR", "italy": "EUR", "it": "EUR",
    "netherlands": "EUR", "nl": "EUR", "greece": "EUR", "gr": "EUR",
    "france": "EUR", "fr": "EUR",
    "romania": "RON", "ro": "RON",
    "poland": "PLN", "pl": "PLN",
    "russia": "RUB", "ru": "RUB",
    "ukraine": "UAH", "ua": "UAH",
    "sweden": "SEK", "se": "SEK",
    "turkey": "TRY", "tr": "TRY",
    "czechia": "CZK", "cz": "CZK",
    "georgia": "GEL", "ge": "GEL",
    "armenia": "AMD", "am": "AMD",
    "saudi arabia": "SAR", "sa": "SAR",
    "egypt": "EGP", "eg": "EGP",
    "israel": "ILS", "il": "ILS",
    "iran": "IRR", "ir": "IRR",
    "kenya": "KES", "ke": "KES",
    "ethiopia": "ETB", "et": "ETB",
    "south africa": "ZAR", "za": "ZAR",
    "nigeria": "NGN", "ng": "NGN",
    "china": "CNY", "cn": "CNY",
    "japan": "JPY", "jp": "JPY",
    "south korea": "KRW", "kr": "KRW",
    "india": "INR", "in": "INR",
    "bangladesh": "BDT", "bd": "BDT",
    "pakistan": "PKR", "pk": "PKR",
    "nepal": "NPR", "np": "NPR",
    "vietnam": "VND", "vn": "VND",
    "thailand": "THB", "th": "THB",
    "indonesia": "IDR", "id": "IDR",
    "malaysia": "MYR", "my": "MYR",
    "philippines": "PHP", "ph": "PHP",
    "myanmar": "MMK", "mm": "MMK",
    "cambodia": "KHR", "kh": "KHR",
    "mongolia": "MNT", "mn": "MNT",
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    company_columns = {column["name"] for column in inspector.get_columns("companies")}
    if "currency_code" not in company_columns:
        op.add_column(
            "companies",
            sa.Column("currency_code", sa.String(length=3), nullable=True),
        )

    # Backfill par pays (jamais par langue), sans écraser une valeur existante.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, country FROM companies WHERE currency_code IS NULL")).fetchall()
    for company_id, country in rows:
        currency = _COUNTRY_TO_CURRENCY.get((country or "").strip().lower(), "USD")
        bind.execute(
            sa.text("UPDATE companies SET currency_code = :currency WHERE id = :id"),
            {"currency": currency, "id": company_id},
        )


def downgrade() -> None:
    op.drop_column("companies", "currency_code")
