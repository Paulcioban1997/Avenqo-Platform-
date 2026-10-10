"""Credential URL guard. Outputs locations only; never source or secret values."""
import argparse
from pathlib import Path
import re
import subprocess

PATTERN = re.compile(r'''(?i)(?:postgres(?:ql)?(?:\+[a-z0-9]+)?|mysql|redis)://[^\s"'<>:@]+:([^\s"'<>@]+)@''')


def violations(body: str) -> list[int]:
    return [body[:match.start()].count("\n") + 1 for match in PATTERN.finditer(body)
            if match.group(1) != "test-only-password" and not match.group(1).startswith("${")]


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
            print(f"Credential-shaped database URL blocked: {name}:{line}")
    return int(found)


if __name__ == "__main__":
    raise SystemExit(main())
