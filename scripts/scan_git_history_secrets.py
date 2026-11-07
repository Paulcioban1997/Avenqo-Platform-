"""CLI sécurité : recherche de secrets dans tout l'historique Git (toutes les références).

Usage :
    python scripts/scan_git_history_secrets.py

N'affiche jamais une valeur : uniquement commit, fichier et type de secret, afin de
préparer le nettoyage d'historique (git filter-repo) et la liste des rotations.
"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.security.test_no_committed_secrets import SECRET_PATTERNS


def main() -> int:
    process = subprocess.Popen(
        ["git", "log", "--all", "-p", "--no-color", "--format=commit %h %ad", "--date=short", "--unified=0"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
    )
    assert process.stdout is not None
    commit = path = ""
    first_seen: dict[tuple[str, str], str] = {}
    commits: dict[tuple[str, str], set[str]] = defaultdict(set)
    for raw in process.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if line.startswith("commit "):
            commit = line[7:]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    key = (name, path)
                    commits[key].add(commit.split()[0])
                    first_seen[key] = commit
    process.wait()
    if not commits:
        print("Aucun secret détecté dans l'historique.")
        return 0
    for (name, file_path), shas in sorted(commits.items()):
        print(f"[{name}] {file_path} commits={len(shas)} earliest={first_seen[(name, file_path)]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
