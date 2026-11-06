"""Keep production startup separate from database migrations."""

import json
import re
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_railway_start_commands_run_the_app_without_migrating() -> None:
    configured = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))["deploy"]["startCommand"]
    iac = (ROOT / ".railway" / "railway.ts").read_text(encoding="utf-8")
    match = re.search(r'startCommand:\s*"([^"]+)"', iac)

    assert match is not None
    assert configured == match.group(1)
    assert shlex.split(configured)[:2] == ["uvicorn", "backend.main:app"]
    assert "alembic" not in configured

