"""Report whether Enterprise quote env vars exist, without printing secrets."""

from __future__ import annotations

from pathlib import Path
import os

NAMES = (
    "RESEND_API_KEY",
    "EMAIL_API_KEY",
    "BACKEND_API_URL",
    "BACKEND_URL",
    "AVENQO_ENTERPRISE_QUOTE_RECIPIENTS",
    "EMAIL_FROM_EMAIL",
    "EMAIL_FROM_NAME",
    "EMAIL_PROVIDER",
)


def _status(value: str | None) -> str:
    return "set" if (value or "").strip() else "missing"


def main() -> None:
    print("process")
    for name in NAMES:
        print(f"  {name} {_status(os.environ.get(name))}")
    root = Path(__file__).resolve().parents[1]
    for rel in ("backend/.env", "web/.env", "web/.env.local", ".env"):
        path = root / rel
        if not path.exists():
            print(f"{rel} absent")
            continue
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, raw = line.split("=", 1)
            values[key.strip()] = raw.strip().strip("\"'")
        print(rel)
        for name in NAMES:
            print(f"  {name} {_status(values.get(name))}")
    recipients = (
        os.environ.get("AVENQO_ENTERPRISE_QUOTE_RECIPIENTS")
        or "info@avenqo.ca,paulmircea15@gmail.com"
    )
    normalized = [item.strip().lower() for item in recipients.split(",") if item.strip()]
    print("recipients_include_info", "info@avenqo.ca" in normalized)
    print("recipients_include_owner_gmail", "paulmircea15@gmail.com" in normalized)


if __name__ == "__main__":
    main()
