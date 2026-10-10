"""Dry-run by default. Keys come only from CONNECTOR_ENCRYPTION_KEYS."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-environment")
    args = parser.parse_args()
    try:
        # Configuration validation can include sensitive input in its exception text.
        from backend.app.config.settings import get_settings
        from backend.app.database import SessionLocal
        from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
        from backend.app.services.connector_secret_rotation import rotate_connector_secrets
        settings = get_settings()
        if args.apply and args.confirm_environment != settings.environment:
            print("Explicit environment confirmation required; no changes applied.", file=sys.stderr)
            return 2
        cipher = ConnectorSecretCipher(settings.connector_encryption_keys)
        with SessionLocal() as db, db.begin():
            report = rotate_connector_secrets(db, cipher, apply=args.apply)
    except Exception:
        print("Connector rotation failed; transaction rolled back. Secret details withheld.", file=sys.stderr)
        return 1
    print(json.dumps({"environment": settings.environment, "applied": args.apply, **report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
