"""Fail the build if a live credential is committed to a tracked file."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "fernet_connector_key": re.compile(
        r"(CONNECTOR_ENCRYPTION_KEYS?\s*[=:]\s*[`'\"]?|ConnectorSecretCipher\(\s*\[\s*[`'\"])[A-Za-z0-9_\-]{43}="
    ),
    "stripe_live_key": re.compile(r"\b(sk|rk)_live_[A-Za-z0-9]{16,}"),
    "stripe_webhook_secret": re.compile(r"\bwhsec_[A-Za-z0-9]{24,}"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai_key": re.compile(r"\bsk-(proj-)?[A-Za-z0-9]{32,}"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "telnyx_api_key": re.compile(r"\bKEY[0-9A-F]{32}_[A-Za-z0-9]{20,}"),
    "postgres_url_with_password": re.compile(
        r"postgres(?:ql)?(?:\+\w+)?://[^:/@\s]+:(?!test-only-password@|password@|postgres@|\$\{|<)[^@\s'\"]{8,}@[a-z0-9\-]+\.[a-z0-9.\-]+"
    ),
}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".zip", ".gz", ".xlsx", ".pkl", ".joblib", ".wasm", ".symbols", ".frag",
}


def _tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8", "replace")
    return [ROOT / name for name in output.split("\0") if name]


def test_no_live_credentials_in_tracked_files() -> None:
    findings: list[str] = []
    for path in _tracked_files():
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT).as_posix()}:{line_number} [{name}]")
    assert not findings, "Committed credentials detected (values not shown):\n" + "\n".join(findings)
