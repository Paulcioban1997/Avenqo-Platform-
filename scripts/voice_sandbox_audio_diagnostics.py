"""Run offline Voice audio checks. Refuses production and never places a call."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    environment = os.environ.get("ENVIRONMENT", "development").strip().lower()
    if environment in {"production", "prod"}:
        print(json.dumps({"ok": False, "reason": "production_refused", "calls_placed": False}))
        return 2
    from backend.app.voice.audio_diagnostics import run_offline_audio_diagnostics

    report = run_offline_audio_diagnostics()
    report["environment"] = environment
    report["ok"] = bool(report["test_a_direct_audio"]["valid"] and report["test_b_tts_encoding"]["valid"])
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
