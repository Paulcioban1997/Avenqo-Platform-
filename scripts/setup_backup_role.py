"""Provision the dedicated, read-only avenqo_backup PostgreSQL role.

This script configures a dedicated backup role with BYPASSRLS and read-only
SELECT privileges, sets BACKUP_DATABASE_URL on the Railway API service,
and activates BACKUP_SCHEDULED_ENABLED without leaking credentials in logs.
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
from urllib.parse import quote_plus, urlsplit, urlunsplit

from sqlalchemy import create_engine, text

RAILWAY_BIN = shutil.which("railway") or "railway"


def get_railway_variables(service: str, environment: str) -> dict[str, str]:
    """Retrieve service variables as a dict using railway CLI JSON output."""
    cmd = [
        RAILWAY_BIN,
        "variable",
        "list",
        "--service",
        service,
        "--environment",
        environment,
        "--json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=sys.platform == "win32")
    return json.loads(res.stdout)


def set_railway_variable(
    service: str, environment: str, key: str, value: str, skip_deploys: bool = True
) -> None:
    """Set an environment variable via railway variable set."""
    cmd = [
        RAILWAY_BIN,
        "variable",
        "set",
        f"{key}={value}",
        "--service",
        service,
        "--environment",
        environment,
    ]
    if skip_deploys:
        cmd.append("--skip-deploys")
    subprocess.run(cmd, capture_output=True, text=True, check=True, shell=sys.platform == "win32")


def delete_railway_variable(service: str, environment: str, key: str) -> None:
    """Delete an environment variable if it exists."""
    cmd = [
        RAILWAY_BIN,
        "variable",
        "delete",
        key,
        "--service",
        service,
        "--environment",
        environment,
        "--yes",
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=False, shell=sys.platform == "win32")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure avenqo_backup role on Railway")
    parser.add_argument(
        "--environment",
        choices=["production", "sandbox"],
        required=True,
        help="Target Railway environment",
    )
    args = parser.parse_args()

    env_name = args.environment
    print(f"[*] Starting backup role provisioning for environment: {env_name}")

    # 1. Fetch Postgres service connection details
    pg_vars = get_railway_variables("Postgres", env_name)
    admin_public_url = pg_vars.get("DATABASE_PUBLIC_URL")
    if not admin_public_url:
        print("[!] DATABASE_PUBLIC_URL missing from Postgres service.", file=sys.stderr)
        sys.exit(1)

    # 2. Generate secure password for avenqo_backup
    backup_password = secrets.token_urlsafe(32)

    # 3. Connect as admin and configure role
    engine = create_engine(admin_public_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        print("[*] Creating / updating avenqo_backup role with BYPASSRLS...")
        conn.execute(
            text(
                """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'avenqo_backup') THEN
                    CREATE ROLE avenqo_backup WITH LOGIN PASSWORD :pwd NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
                ELSE
                    ALTER ROLE avenqo_backup WITH LOGIN PASSWORD :pwd NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
                END IF;
            END $$;
            """
            ),
            {"pwd": backup_password},
        )

        print("[*] Granting read-only schema and table privileges...")
        conn.execute(text("GRANT CONNECT ON DATABASE railway TO avenqo_backup;"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO avenqo_backup;"))
        conn.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO avenqo_backup;"))
        conn.execute(text("GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO avenqo_backup;"))
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO avenqo_backup;"
            )
        )
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO avenqo_backup;"
            )
        )

        # Verify role attributes
        row = conn.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'avenqo_backup'"
            )
        ).fetchone()
        print(f"[*] avenqo_backup verified: name={row[0]}, superuser={row[1]}, bypassrls={row[2]}, canlogin={row[3]}")

    # 4. Construct internal DATABASE_URL for Avenqo-Platform-
    # Internal host is postgres.railway.internal:5432 / railway
    quoted_pwd = quote_plus(backup_password)
    netloc = f"avenqo_backup:{quoted_pwd}@postgres.railway.internal:5432"
    internal_backup_url = urlunsplit(("postgresql", netloc, "/railway", "", ""))

    # 5. Set BACKUP_DATABASE_URL and BACKUP_SCHEDULED_ENABLED on Avenqo-Platform-
    print("[*] Configuring BACKUP_DATABASE_URL on Avenqo-Platform-...")
    set_railway_variable("Avenqo-Platform-", env_name, "BACKUP_DATABASE_URL", internal_backup_url)

    print("[*] Enabling in-process scheduled backup worker (BACKUP_SCHEDULED_ENABLED=true)...")
    set_railway_variable("Avenqo-Platform-", env_name, "BACKUP_SCHEDULED_ENABLED", "true")

    # In sandbox, clean up corrupted variable name with leading space if present
    if env_name == "sandbox":
        api_vars = get_railway_variables("Avenqo-Platform-", env_name)
        for k, v in api_vars.items():
            if k.strip() == "BACKUP_S3_ACCESS_KEY" and k != "BACKUP_S3_ACCESS_KEY":
                print("[*] Fixing malformed variable with leading space in sandbox...")
                delete_railway_variable("Avenqo-Platform-", env_name, k)
                set_railway_variable("Avenqo-Platform-", env_name, "BACKUP_S3_ACCESS_KEY", v)

    print(f"[+] Backup role and environment variables configured successfully for {env_name}.")


if __name__ == "__main__":
    main()
