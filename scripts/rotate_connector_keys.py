"""CLI opérations : rotation de CONNECTOR_ENCRYPTION_KEYS sans perte de données.

Usage :
    python scripts/rotate_connector_keys.py generate
    python scripts/rotate_connector_keys.py status
    python scripts/rotate_connector_keys.py rotate            # simulation (aucune écriture)
    python scripts/rotate_connector_keys.py rotate --apply    # rechiffrement par lots
    python scripts/rotate_connector_keys.py verify            # code retour 0 seulement si l'ancienne clé peut être retirée

Lit DATABASE_URL et CONNECTOR_ENCRYPTION_KEYS depuis l'environnement. N'affiche
jamais une clé existante : seules des empreintes SHA-256 tronquées sont imprimées.
Procédure complète : docs/security/connector-key-rotation.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.connector_key_rotation import (
    ConnectorKeyRotationService,
    generate_connector_key,
    key_fingerprint,
)


def _keys_from_env() -> list[str]:
    raw = os.getenv("CONNECTOR_ENCRYPTION_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise SystemExit("CONNECTOR_ENCRYPTION_KEYS est requis (nouvelle clé en premier, ancienne ensuite).")
    return keys


def _session():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL est requis.")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return sessionmaker(bind=create_engine(url, pool_pre_ping=True), expire_on_commit=False)()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="Génère une nouvelle clé Fernet (à copier directement dans Railway)")
    sub.add_parser("status", help="Compte les identifiants par clé (lecture seule)")
    rotate = sub.add_parser("rotate", help="Rechiffre avec la clé primaire")
    rotate.add_argument("--apply", action="store_true", help="Écrit réellement (sinon simulation)")
    rotate.add_argument("--batch-size", type=int, default=100)
    sub.add_parser("verify", help="Vérifie que tout est déchiffrable avec la seule clé primaire")
    args = parser.parse_args(argv)

    if args.command == "generate":
        key = generate_connector_key()
        print(f"fingerprint={key_fingerprint(key)}", file=sys.stderr)
        print("Ne collez cette clé ni dans Git, ni dans un ticket, ni dans un chat.", file=sys.stderr)
        print(key)
        return 0

    keys = _keys_from_env()
    print(f"keys_configured={len(keys)} " + " ".join(
        f"{'primary' if i == 0 else 'previous'}={key_fingerprint(k)}" for i, k in enumerate(keys)
    ))
    session = _session()
    try:
        service = ConnectorKeyRotationService(session, keys)
        if args.command == "status":
            report = service.status()
        elif args.command == "rotate":
            report = service.rotate(batch_size=args.batch_size, dry_run=not args.apply)
        else:
            report = service.status()
    finally:
        session.close()

    print(json.dumps(report.to_dict(), indent=2))
    if args.command == "verify":
        return 0 if report.safe_to_retire_previous_keys and report.undecryptable == 0 else 2
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
