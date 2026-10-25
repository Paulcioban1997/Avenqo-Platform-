import os
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from scripts.database_runtime import require_database_url
db_url = require_database_url()

# For alembic, ensure postgresql:// or postgresql+psycopg2://
os.environ["DATABASE_URL"] = db_url

from alembic.config import Config
from alembic import command

alembic_cfg = Config(str(root_dir / "alembic.ini"))
alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

print("Running alembic upgrade head...")
command.upgrade(alembic_cfg, "head")
print("Migrations applied successfully!")
