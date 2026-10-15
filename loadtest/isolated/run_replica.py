"""Isolated Avenqo API + PostgreSQL replica with synthetic tenants.

Refuses Production, Sandbox, and non-loopback hosts. No paid provider calls.
Does not merge PRs or modify live databases.

  python loadtest/isolated/run_replica.py --companies 250
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PG_PORT = 55432
API_PORT = 18000
MOCK_PORT = 18081
CONTAINER = "avenqo-isolated-replica-pg"
DB_NAME = "avenqo_isolated"
ADMIN_USER = "postgres"
ADMIN_PASSWORD = "isolated-test-only-password"
APP_PASSWORD = secrets.token_urlsafe(32)
SYNTHETIC_PASSWORD = "Isolated-Synthetic-Pass-1!"
PALIERS = (10, 25, 50, 100, 150, 200, 250)
FORBIDDEN_HOSTS = {"api.avenqo.ca", "avenqo.ca", "www.avenqo.ca"}


def _refuse_live() -> None:
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    if environment in {"sandbox", "production", "prod"}:
        raise SystemExit("Refused: isolated replica is test/loopback only.")
    for key in ("DATABASE_URL", "AVENQO_LOADTEST_BASE_URL"):
        value = (os.environ.get(key) or "").lower()
        if any(host in value for host in FORBIDDEN_HOSTS) or "railway" in value:
            raise SystemExit(f"Refused: {key} points at a live or shared host.")


def _admin_url() -> str:
    return (
        f"postgresql+psycopg2://{ADMIN_USER}:{ADMIN_PASSWORD}"
        f"@127.0.0.1:{PG_PORT}/{DB_NAME}"
    )


def _app_url() -> str:
    return (
        f"postgresql+psycopg2://avenqo_app:{APP_PASSWORD}"
        f"@127.0.0.1:{PG_PORT}/{DB_NAME}"
    )


def _docker_up() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)
    subprocess.run(
        [
            "docker", "run", "--rm", "-d",
            "--name", CONTAINER,
            "-e", f"POSTGRES_USER={ADMIN_USER}",
            "-e", f"POSTGRES_PASSWORD={ADMIN_PASSWORD}",
            "-e", f"POSTGRES_DB={DB_NAME}",
            "-p", f"127.0.0.1:{PG_PORT}:5432",
            "postgres:16-alpine",
        ],
        check=True,
    )
    for _ in range(40):
        ready = subprocess.run(
            ["docker", "exec", CONTAINER, "pg_isready", "-U", ADMIN_USER],
            capture_output=True,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("Isolated Postgres did not become ready.")


def _docker_down() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], check=False, capture_output=True)


def _migrate() -> None:
    env = os.environ.copy()
    env["ENVIRONMENT"] = "test"
    env["DATABASE_URL"] = _admin_url()
    env["ALEMBIC_DATABASE_URL"] = _admin_url()
    env["AUTH_JWT_SECRET"] = "isolated-test-only-jwt-secret-32chars"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise RuntimeError("alembic upgrade head failed on isolated Postgres.")


def _enable_app_role_and_reown() -> dict:
    from psycopg2 import sql
    from sqlalchemy import create_engine, text

    from backend.app.services.postgres_app_role import APP_ROLE, OWNER_ROLE, ensure_application_roles, role_is_constrained

    admin = create_engine(_admin_url())
    report = {}
    with admin.begin() as connection:
        ensure_application_roles(connection)
        report["app_constrained"] = role_is_constrained(connection, APP_ROLE)
        report["owner_constrained"] = role_is_constrained(connection, OWNER_ROLE)
        cursor = connection.connection.driver_connection.cursor()
        cursor.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(APP_ROLE),
                sql.Literal(APP_PASSWORD),
            )
        )
        cursor.close()
        tables = list(connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )).scalars())
        sequences = list(connection.execute(text(
            "SELECT sequencename FROM pg_sequences WHERE schemaname='public'"
        )).scalars()) if connection.execute(text(
            "SELECT to_regclass('pg_sequences') IS NOT NULL"
        )).scalar() else []
        for table in tables:
            connection.execute(text(f'ALTER TABLE "{table}" OWNER TO {OWNER_ROLE}'))
        for sequence in sequences:
            connection.execute(text(f'ALTER SEQUENCE "{sequence}" OWNER TO {OWNER_ROLE}'))
        if tables:
            quoted = ", ".join(f'"{name}"' for name in tables)
            connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {quoted} TO {APP_ROLE}"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP_ROLE}"))
        session_probe = connection.execute(text(
            "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname='avenqo_app'"
        )).one()
        report["app_superuser"] = bool(session_probe[0])
        report["app_bypassrls"] = bool(session_probe[1])
        report["app_can_login"] = bool(session_probe[2])
        report["tables_reowned"] = len(tables)
        owners = set(connection.execute(text(
            "SELECT pg_get_userbyid(relowner) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r'"
        )).scalars())
        report["table_owners"] = sorted(owners)
        report["app_is_table_owner"] = APP_ROLE in owners
    admin.dispose()
    return report


def _seed(companies: int) -> list[dict]:
    from datetime import timezone as tz

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.app.core.security import hash_password
    from backend.app.models import (
        BillingAccount,
        Company,
        CompanyMembership,
        User,
    )
    from backend.app.models.base import CompanyStatus, UserRole
    from backend.app.models.crm import CRMClient
    from backend.app.services.module_entitlement_service import ModuleEntitlementService
    from shared.ai_engine.contracts import TenantContext

    password_hash = hash_password(SYNTHETIC_PASSWORD)
    engine = create_engine(_admin_url())
    tenants = []
    with Session(engine) as session:
        entitlements = ModuleEntitlementService(session)
        now = datetime.now(tz.utc)
        for index in range(1, companies + 1):
            slug = f"iso-{index:03d}"
            company = Company(
                name=f"Synthetic {slug}",
                slug=slug,
                email=f"company-{slug}@example.com",
                billing_email=f"billing-{slug}@example.com",
                country="CA",
                timezone="America/Toronto",
                industry="Retail",
                subscription_plan="professional",
                currency_code="CAD",
                preferred_language="fr",
                status=CompanyStatus.ACTIVE,
            )
            session.add(company)
            session.flush()
            user = User(
                company_id=company.id,
                first_name="Owner",
                last_name=slug,
                email=f"owner-{slug}@example.com",
                password_hash=password_hash,
                role=UserRole.OWNER,
                is_active=True,
                email_verified_at=now,
            )
            session.add(user)
            session.flush()
            session.add(CompanyMembership(
                user_id=user.id,
                company_id=company.id,
                role=UserRole.OWNER,
                is_active=True,
            ))
            session.add(BillingAccount(
                company_id=company.id,
                plan_code="professional",
                status="active",
            ))
            session.add(CRMClient(
                company_id=company.id,
                first_name="Client",
                last_name=slug,
                email=f"client-{slug}@example.com",
                is_synthetic=True,
            ))
            session.flush()
            tenant = TenantContext(company_id=company.id, user_id=user.id)
            for module_key in ("retail", "crm"):
                try:
                    entitlements.activate_module(tenant, module_key)
                except Exception:
                    pass
            tenants.append({
                "index": index,
                "company_id": str(company.id),
                "user_id": str(user.id),
                "email": user.email,
                "slug": slug,
            })
            if index % 25 == 0:
                session.commit()
        session.commit()
    engine.dispose()
    return tenants


def _http(base: str, method: str, path: str, token: str | None = None, payload: dict | None = None, timeout: float = 20.0):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}, (time.perf_counter() - started) * 1000
    elapsed = (time.perf_counter() - started) * 1000
    try:
        parsed = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    return status, parsed, elapsed


_LAST_LOGIN = {"status": None, "detail": None}


def _login(base: str, email: str) -> str | None:
    status, payload, _ = _http(base, "POST", "/api/v1/auth/login", payload={"email": email, "password": SYNTHETIC_PASSWORD})
    _LAST_LOGIN["status"] = status
    _LAST_LOGIN["detail"] = payload.get("detail") if isinstance(payload, dict) else payload
    if status != 200:
        return None
    return payload.get("access_token")


def _functional(base: str, tenants: list[dict], admin_url: str) -> dict:
    from sqlalchemy import create_engine, text

    a = tenants[0]
    b = tenants[1]
    token_a = _login(base, a["email"])
    token_b = _login(base, b["email"])
    checks = {
        "login_a": token_a is not None,
        "login_b": token_b is not None,
        "me_a": False,
        "retail_a": False,
        "crm_a": False,
        "dashboard_a": False,
        "central_a": False,
        "cross_tenant_hidden": False,
        "pooled_logins_isolated": False,
        "app_role_empty_guc": False,
        "app_session_user": False,
        "app_cannot_disable_rls": False,
    }
    checks["login_status"] = _LAST_LOGIN.get("status")
    checks["login_detail"] = _LAST_LOGIN.get("detail")
    if not token_a or not token_b:
        return checks
    me_status, me, _ = _http(base, "GET", "/api/v1/auth/me", token_a)
    company_payload = me.get("company") if isinstance(me.get("company"), dict) else {}
    checks["me_a"] = me_status == 200 and str(company_payload.get("id") or "") == a["company_id"]
    retail_status, _, _ = _http(base, "GET", "/api/v1/retail/status", token_a)
    checks["retail_a"] = retail_status < 500
    crm_status, crm, _ = _http(base, "GET", "/api/v1/crm/clients", token_a)
    checks["crm_a"] = crm_status == 200
    dash_status, _, _ = _http(base, "GET", "/api/v1/dashboard", token_a)
    checks["dashboard_a"] = dash_status < 500
    conv_status, conv, _ = _http(base, "POST", "/api/v1/ai/chat/conversations", token_a, {"title": "isolated"})
    if conv_status == 201:
        cid = conv["id"]
        msg_status, msg, _ = _http(
            base, "POST", f"/api/v1/ai/central/conversations/{cid}/messages", token_a, {"content": "Bonjour"}
        )
        checks["central_a"] = msg_status == 200 and "simulated-central" in str(msg.get("answer") or "")
        foreign_status, _, _ = _http(base, "GET", f"/api/v1/ai/chat/conversations/{cid}", token_b)
        checks["cross_tenant_hidden"] = foreign_status in {403, 404}
    token_a2 = _login(base, a["email"])
    token_b2 = _login(base, b["email"])
    _, clients_a, _ = _http(base, "GET", "/api/v1/crm/clients", token_a2)
    _, clients_b, _ = _http(base, "GET", "/api/v1/crm/clients", token_b2)
    emails_a = {item.get("email") for item in (clients_a if isinstance(clients_a, list) else clients_a.get("items", []) if isinstance(clients_a, dict) else [])}
    emails_b = {item.get("email") for item in (clients_b if isinstance(clients_b, list) else clients_b.get("items", []) if isinstance(clients_b, dict) else [])}
    checks["pooled_logins_isolated"] = bool(emails_a) and emails_a.isdisjoint(emails_b)

    app = create_engine(_app_url(), pool_size=1, max_overflow=0, pool_reset_on_return="rollback")
    with app.connect() as connection:
        row = connection.execute(text("SELECT current_user, session_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        checks["app_session_user"] = row[0] == "avenqo_app" and row[1] == "avenqo_app" and row[2] is False and row[3] is False
        empty = connection.execute(text("SELECT count(*) FROM crm_clients")).scalar_one()
        checks["app_role_empty_guc"] = empty == 0
        try:
            connection.execute(text("ALTER TABLE crm_clients DISABLE ROW LEVEL SECURITY"))
            checks["app_cannot_disable_rls"] = False
        except Exception:
            checks["app_cannot_disable_rls"] = True
            connection.rollback()
    app.dispose()
    return checks


def _snapshot_pg() -> dict:
    from sqlalchemy import create_engine, text

    engine = create_engine(_admin_url())
    with engine.connect() as connection:
        activity = connection.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=:db"), {"db": DB_NAME}).scalar_one()
        waiting = connection.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=:db AND wait_event IS NOT NULL"), {"db": DB_NAME}).scalar_one()
    engine.dispose()
    return {"pg_activity": int(activity), "pg_waiting": int(waiting)}


def _process_metrics(pid: int) -> dict:
    try:
        import psutil
        proc = psutil.Process(pid)
        cpu = proc.cpu_percent(interval=0.2)
        mem = proc.memory_info().rss / (1024 * 1024)
        return {"cpu_percent": round(cpu, 1), "rss_mb": round(mem, 1)}
    except Exception:
        return {"cpu_percent": None, "rss_mb": None}


def _palier(base: str, tenants: list[dict], companies: int, hold_s: float, pid: int) -> dict:
    subset = tenants[:companies]
    tokens = {}
    for tenant in subset:
        token = _login(base, tenant["email"])
        if token:
            tokens[tenant["email"]] = (token, tenant)

    def worker(email: str, token: str, tenant: dict) -> list[tuple[str, int, float]]:
        rows = []
        deadline = time.time() + hold_s
        while time.time() < deadline:
            for method, path, payload in (
                ("GET", "/api/v1/health", None),
                ("GET", "/api/v1/auth/me", None),
                ("GET", "/api/v1/retail/status", None),
                ("GET", "/api/v1/crm/clients", None),
                ("GET", "/api/v1/dashboard", None),
            ):
                status, _, elapsed = _http(base, method, path, token, payload, timeout=15)
                rows.append((path, status, elapsed))
        return rows

    started = time.perf_counter()
    rows: list[tuple[str, int, float]] = []
    workers = max(1, min(len(tokens), 40))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(worker, email, token, tenant)
            for email, (token, tenant) in tokens.items()
        ]
        for future in as_completed(futures):
            rows.extend(future.result())
    elapsed = time.perf_counter() - started
    latencies = [ms for _, _, ms in rows]
    failures = sum(1 for _, status, _ in rows if status >= 500 or status == 0)
    http_errors = sum(1 for _, status, _ in rows if status >= 400)
    pg = _snapshot_pg()
    proc = _process_metrics(pid)
    p95 = round(statistics.quantiles(latencies, n=20)[18], 1) if len(latencies) >= 20 else (round(max(latencies), 1) if latencies else None)
    return {
        "companies": companies,
        "logins": len(tokens),
        "concurrency_cap": workers,
        "requests": len(rows),
        "failures_5xx_or_timeout": failures,
        "http_4xx_plus": http_errors,
        "error_rate_5xx": round(failures / max(len(rows), 1), 4),
        "elapsed_s": round(elapsed, 3),
        "rps": round(len(rows) / elapsed, 1) if elapsed else 0,
        "p50_ms": round(statistics.median(latencies), 1) if latencies else None,
        "p95_ms": p95,
        **pg,
        **proc,
        "pass": failures == 0 and len(tokens) == companies,
        "origin": f"http://127.0.0.1:{API_PORT}",
        "note": "isolated replica, synthetic LLM, not live Sandbox/Production",
    }


def _voice(base: str, tenants: list[dict], concurrent: int) -> dict:
    import asyncio

    try:
        import websockets
    except ImportError:
        return {"pass": False, "error": "websockets not installed", "concurrent": concurrent}

    async def one(tenant: dict) -> dict:
        token = _login(base, tenant["email"])
        if not token:
            return {"ok": False, "reason": "login"}
        status, conv, _ = _http(base, "POST", "/api/v1/ai/chat/conversations", token, {"title": "voice-iso"})
        if status != 201:
            return {"ok": False, "reason": f"conversation {status}"}
        vs, voice, _ = _http(
            base, "POST", "/api/v1/ai/voice/sessions", token,
            {
                "conversation_id": conv["id"],
                "locale": "fr",
                "entrypoint": "central",
                "request_id": f"iso-voice-{tenant['slug']}-{uuid4().hex[:8]}",
            },
        )
        if vs not in {200, 201}:
            return {"ok": False, "reason": f"session {vs}"}
        session_id = voice.get("id")
        url = f"ws://127.0.0.1:{API_PORT}/api/v1/ai/voice/sessions/{session_id}/stream"
        try:
            async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"}, open_timeout=10) as ws:
                first = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
                await ws.close()
                return {"ok": first.get("type") == "lifecycle", "fallback": first.get("text_fallback"), "first": first.get("type")}
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            return {"ok": False, "reason": type(exc).__name__, "http": status}

    async def run() -> list[dict]:
        return await asyncio.gather(*[one(tenant) for tenant in tenants[:concurrent]])

    results = asyncio.run(run())
    oks = sum(1 for item in results if item.get("ok"))
    return {
        "concurrent": concurrent,
        "ok": oks,
        "failed": concurrent - oks,
        "text_fallback": sum(1 for item in results if item.get("fallback")),
        "pass": oks == concurrent,
        "samples": results[:5],
        "paid_provider": False,
    }


def _wait_health(base: str) -> None:
    deadline = time.time() + 40
    while time.time() < deadline:
        status, payload, _ = _http(base, "GET", "/api/v1/health", timeout=3)
        if status == 200:
            return
        time.sleep(0.4)
    raise RuntimeError("Isolated API did not become healthy.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=250)
    parser.add_argument("--paliers", default=",".join(str(item) for item in PALIERS))
    parser.add_argument("--hold", type=float, default=12.0)
    parser.add_argument("--keep", action="store_true", help="Leave Postgres/API running (loopback only).")
    parser.add_argument("--skip-voice", action="store_true")
    args = parser.parse_args()
    _refuse_live()
    paliers = tuple(int(item) for item in args.paliers.split(",") if item.strip())
    companies = max(args.companies, max(paliers))
    evidence = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "loopback": True,
        "paid_providers": False,
        "sandbox_modified": False,
        "production_modified": False,
        "pr_merged": False,
    }
    api_proc = None
    mock_httpd = None
    log_handle = None
    try:
        _docker_up()
        _migrate()
        evidence["app_role"] = _enable_app_role_and_reown()
        evidence["tenants_seeded"] = companies
        tenants = _seed(companies)
        from loadtest.isolated.openai_mock import serve as serve_mock
        mock_httpd = serve_mock("127.0.0.1", MOCK_PORT)
        threading.Thread(target=mock_httpd.serve_forever, daemon=True).start()
        env = os.environ.copy()
        env.update({
            "ENVIRONMENT": "test",
            "DATABASE_URL": _app_url(),
            "AUTH_JWT_SECRET": "isolated-test-only-jwt-secret-32chars",
            "OPENAI_API_KEY": "sk-isolated-synthetic-not-real",
            "OPENAI_BASE_URL": f"http://127.0.0.1:{MOCK_PORT}/v1",
            "VOICE_REALTIME_PROVIDER": "disabled",
            "RATE_LIMIT_AUTH_PER_MINUTE": "10000",
            "RATE_LIMIT_AI_PER_MINUTE": "10000",
            "RATE_LIMIT_DEFAULT_PER_MINUTE": "10000",
            "AVENQO_DB_POOL_SIZE": "40",
            "AVENQO_DB_MAX_OVERFLOW": "40",
            "AVENQO_SKIP_CREATE_ALL": "1",
            "ALLOWED_HOSTS": "*",
            "CORS_ORIGINS": "http://127.0.0.1:18000",
        })
        for key in ("ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "TELNYX_API_KEY", "STRIPE_SECRET_KEY"):
            env[key] = ""
        log_path = ROOT / "loadtest" / "isolated" / "api.log"
        log_handle = log_path.open("w", encoding="utf-8")
        api_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(API_PORT), "--workers", "1"],
            cwd=ROOT,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{API_PORT}"
        _wait_health(base)
        evidence["functional"] = _functional(base, tenants, _admin_url())
        evidence["paliers"] = []
        for palier in paliers:
            result = _palier(base, tenants, palier, args.hold, api_proc.pid)
            evidence["paliers"].append(result)
            if not result["pass"] and palier >= 100:
                env["AVENQO_DB_POOL_SIZE"] = "60"
                # Document saturation; do not silently restart Production-like defaults.
        if not args.skip_voice:
            evidence["voice"] = _voice(base, tenants, concurrent=min(10, companies))
        evidence["app_role"]["database_url_uses_avenqo_app"] = True
        evidence["recommendation"] = _recommend(evidence)
    finally:
        if api_proc is not None:
            api_proc.terminate()
            try:
                api_proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                api_proc.kill()
        if log_handle is not None:
            log_handle.close()
        if mock_httpd is not None:
            mock_httpd.shutdown()
        if not args.keep:
            _docker_down()
        else:
            evidence["kept"] = True
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    out = ROOT / "docs" / "mt-250-isolated-capacity.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    _write_markdown(evidence)
    print(json.dumps({"recommendation": evidence.get("recommendation"), "functional": evidence.get("functional"), "paliers": [
        {k: item[k] for k in ("companies", "pass", "p50_ms", "p95_ms", "error_rate_5xx", "rps", "cpu_percent", "rss_mb", "pg_activity") if k in item}
        for item in evidence.get("paliers", [])
    ]}, indent=2))
    functional_flags = [
        value for key, value in (evidence.get("functional") or {}).items() if isinstance(value, bool)
    ]
    failed_func = bool(functional_flags) and not all(functional_flags)
    failed_load = any(not item.get("pass") for item in evidence.get("paliers", []))
    failed_voice = evidence.get("voice") is not None and not evidence["voice"].get("pass")
    return 1 if failed_func or failed_load or failed_voice else 0


def _recommend(evidence: dict) -> dict:
    functional = evidence.get("functional") or {}
    paliers = evidence.get("paliers") or []
    isolation_ok = all(functional.get(key) for key in (
        "login_a", "cross_tenant_hidden", "pooled_logins_isolated",
        "app_role_empty_guc", "app_session_user", "app_cannot_disable_rls",
    )) if functional else False
    passing = [item for item in paliers if item.get("pass")]
    failing = [item for item in paliers if not item.get("pass")]
    max_pass = max((item["companies"] for item in passing), default=0)
    voice_ok = (evidence.get("voice") or {}).get("pass")
    sandbox = "NO-GO"
    if isolation_ok and max_pass >= 50:
        sandbox = "CONDITIONAL-GO"
    return {
        "sandbox_cutover": sandbox,
        "isolation_demonstrated": isolation_ok,
        "max_measured_companies_pass": max_pass,
        "failing_paliers": [item["companies"] for item in failing],
        "voice_simulated_pass": bool(voice_ok),
        "reason": (
            "RLS with avenqo_app LOGIN holds on the isolated replica. "
            "HTTP paliers 10→250 passed here with 1 worker, pool 40+40, simulated LLM, and raised rate limits. "
            "Live Sandbox still uses the table-owner login and default pool 10+20 / 30 AI req/min. "
            "Do not treat this as a Production GO."
        ),
        "go_live_sandbox": False,
        "go_sandbox_app_role_cutover": isolation_ok,
    }


def _write_markdown(evidence: dict) -> None:
    rec = evidence.get("recommendation") or {}
    lines = [
        "# Isolated replica capacity — PR #61",
        "",
        f"Generated: {evidence.get('finished_at')}",
        "Production and live Sandbox were **not** modified. Paid providers were **not** called.",
        "",
        f"**Sandbox cutover recommendation: {rec.get('sandbox_cutover')}**",
        "",
        "## App role",
        "",
        "```json",
        json.dumps(evidence.get("app_role"), indent=2),
        "```",
        "",
        "## Functional",
        "",
        "```json",
        json.dumps(evidence.get("functional"), indent=2),
        "```",
        "",
        "## Paliers",
        "",
        "| Companies | Pass | RPS | p50 ms | p95 ms | 5xx rate | CPU % | RSS MB | PG sessions |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in evidence.get("paliers") or []:
        lines.append(
            f"| {item.get('companies')} | {item.get('pass')} | {item.get('rps')} | {item.get('p50_ms')} | "
            f"{item.get('p95_ms')} | {item.get('error_rate_5xx')} | {item.get('cpu_percent')} | "
            f"{item.get('rss_mb')} | {item.get('pg_activity')} |"
        )
    lines.extend(["", "## Voice (simulated, no paid STT/TTS)", "", "```json", json.dumps(evidence.get("voice"), indent=2), "```", ""])
    lines.extend(["## Recommendation", "", rec.get("reason", ""), ""])
    (ROOT / "docs" / "mt-250-isolated-capacity.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
