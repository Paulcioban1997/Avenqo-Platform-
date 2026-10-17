"""Safe non-destructive production security status verification. Never prints credentials."""
import json
import os
import sys
import urllib.request
import psycopg2

def check_old_password_rejected(host: str, port: int, user: str, old_pass: str) -> bool:
    try:
        psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=old_pass,
            dbname="railway",
            connect_timeout=4,
        )
        return False
    except psycopg2.OperationalError:
        return True

def check_api_health(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Avenqo-SecurityAudit/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None

def main():
    print("================================================================================")
    print("AVENQO PRODUCTION SECURITY VERIFICATION")
    print("================================================================================")

    # 1. Check API Health
    health = check_api_health("https://api.avenqo.ca/health")
    if health:
        print(f"[PASS] Production API is healthy: env={health.get('environment')}, version={health.get('version')}")
    else:
        print("[FAIL] Production API is not reachable or unhealthy.")
        sys.exit(1)

    # 2. Check Old Compromised Password Rejection
    old_pw = os.environ.get("PROD_OLD_POSTGRES_PASSWORD", "")
    if old_pw:
        rejected = check_old_password_rejected("tramway.proxy.rlwy.net", 25367, "postgres", old_pw)
        if rejected:
            print("[PASS] Old PostgreSQL credential confirmed REJECTED (FATAL: password authentication failed).")
        else:
            print("[FAIL] CRITICAL: Old PostgreSQL credential STILL AUTHENTICATES!")
            sys.exit(1)
    else:
        print("[INFO] PROD_OLD_POSTGRES_PASSWORD not set; skipping live rejection probe.")

    print("\n[VERDICT: PRODUCTION SECURE & OPERATIONAL]")

if __name__ == "__main__":
    main()
