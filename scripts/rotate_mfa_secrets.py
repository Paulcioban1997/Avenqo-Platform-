"""Dry-run by default; preserve MFA enrollment and recovery data atomically."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-environment')
    args = parser.parse_args()
    try:
        from backend.app.config.settings import get_settings
        from backend.app.database import SessionLocal
        from backend.app.services.mfa_secret_rotation import rotate_mfa_secrets
        settings = get_settings()
        if args.apply and args.confirm_environment != settings.environment:
            print('Explicit environment confirmation required; no changes applied.', file=sys.stderr)
            return 2
        with SessionLocal() as db, db.begin():
            report = rotate_mfa_secrets(db, settings.mfa_encryption_keys, apply=args.apply)
        print(json.dumps({'environment': settings.environment, 'applied': args.apply, **report}))
        return 0
    except Exception:
        print('MFA rotation failed; transaction rolled back. Sensitive details withheld.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
