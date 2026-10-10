"""Credential URL guard. Outputs locations only; never source or secret values."""
import argparse
from pathlib import Path
import re
import subprocess

PATTERN = re.compile(r'''(?i)(?:postgres(?:ql)?(?:\+[a-z0-9]+)?|mysql|redis)://[^\s"'<>:@]+:([^\s"'<>@]+)@''')
CONNECTOR_PATTERN = re.compile(
    r'''(?i)(?:CONNECTOR_ENCRYPTION_KEYS?\s*[=:][\s\["'`]*|ConnectorSecretCipher\s*\(\s*\[[\s"']*)([A-Za-z0-9_-]{43}=)'''
)
WEBHOOK_PATTERN = re.compile(
    r'''(?i)(?:\.get\(\s*["']webhook_secret["']\s*,\s*["']|(?:webhook_secret|wh_secret)["']?\s*[:=]\s*["'])([A-Za-z0-9_-]{32,})'''
)


def violations(body: str) -> list[int]:
    database_lines = [body[:match.start()].count("\n") + 1 for match in PATTERN.finditer(body)
                      if match.group(1) != "test-only-password" and not match.group(1).startswith("${")]
    connector_lines = [body[:match.start()].count("\n") + 1 for match in CONNECTOR_PATTERN.finditer(body)]
    webhook_lines = [body[:match.start()].count("\n") + 1 for match in WEBHOOK_PATTERN.finditer(body)]
    return sorted(set(database_lines + connector_lines + webhook_lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"] if args.staged else ["git", "ls-files", "-z"]
    names = subprocess.check_output(command).decode().split("\0")
    found = False
    for name in filter(None, names):
        try:
            content = subprocess.check_output(["git", "show", ":" + name], stderr=subprocess.DEVNULL) if args.staged else Path(name).read_bytes()
            if b"\0" in content:
                continue
            body = content.decode("utf-8-sig")
        except (UnicodeError, OSError, subprocess.CalledProcessError):
            continue
        for line in violations(body):
            found = True
            print(f"Literal credential blocked: {name}:{line}")
    return int(found)


if __name__ == "__main__":
    raise SystemExit(main())
