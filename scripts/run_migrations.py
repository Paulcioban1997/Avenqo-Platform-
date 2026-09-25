import os
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

db_url = os.environ.get(
    "DATABASE_PUBLIC_URL",
    "postgresql://postgres:aVxFamcMziEnMoleBZCYdkLpOELxLatB@tramway.proxy.rlwy.net:25367/railway"
)

# For alembic, ensure postgresql:// or postgresql+psycopg2://
os.environ["DATABASE_URL"] = db_url

from alembic.config import Config
from alembic import command

alembic_cfg = Config(str(root_dir / "alembic.ini"))
alembic_cfg.set_main_option("sqlalchemy.url", db_url)

print("Running alembic upgrade head...")
command.upgrade(alembic_cfg, "head")
print("Migrations applied successfully!")
