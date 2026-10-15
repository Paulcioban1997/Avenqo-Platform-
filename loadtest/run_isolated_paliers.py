"""Run synthetic paliers 10→250 against the loopback mock. Never Production/Sandbox.

Measures the mock origin, not live Avenqo capacity. Prints FAIL if a palier errors.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loadtest.mock_mt_server import serve

PALIERS = (10, 25, 50, 100, 150, 200, 250)
FORBIDDEN = ("https://api.avenqo.ca", "https://avenqo.ca", "https://www.avenqo.ca")


def _request(base: str, path: str, company: str, data: bytes | None = None) -> tuple[int, float]:
    started = time.perf_counter()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={"X-Simulated-Company-Id": company, "Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        status = 0
    elapsed_ms = (time.perf_counter() - started) * 1000
    return status, elapsed_ms


def _worker(base: str, company: str, iterations: int) -> list[tuple[str, int, float]]:
    rows: list[tuple[str, int, float]] = []
    for _ in range(iterations):
        for path, payload in (
            ("/api/v1/health", None),
            ("/api/v1/auth/login", b'{"email":"load@test.local"}'),
            ("/api/v1/ai/chat", b'{"message":"ping simulated central"}'),
        ):
            status, elapsed = _request(base, path, company, payload)
            rows.append((path, status, elapsed))
    return rows


def run_palier(base: str, companies: int, iterations: int, max_concurrency: int | None = None) -> dict:
    started = time.perf_counter()
    rows: list[tuple[str, int, float]] = []
    workers = companies if max_concurrency is None else max(1, min(companies, max_concurrency))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_worker, base, f"company-{index}", iterations)
            for index in range(1, companies + 1)
        ]
        for future in as_completed(futures):
            rows.extend(future.result())
    elapsed = time.perf_counter() - started
    statuses = [status for _, status, _ in rows]
    latencies = [ms for _, _, ms in rows]
    failures = sum(1 for status in statuses if status >= 500 or status == 0)
    return {
        "companies": companies,
        "requests": len(rows),
        "failures": failures,
        "error_rate": round(failures / max(len(rows), 1), 4),
        "elapsed_s": round(elapsed, 3),
        "rps": round(len(rows) / elapsed, 1) if elapsed else 0,
        "p50_ms": round(statistics.median(latencies), 1) if latencies else None,
        "p95_ms": round(statistics.quantiles(latencies, n=20)[18], 1) if len(latencies) >= 20 else round(max(latencies), 1),
        "pass": failures == 0,
        "concurrency": workers,
        "origin": "loopback-mock",
        "note": "synthetic mock; not live Avenqo API capacity",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paliers", default=",".join(str(item) for item in PALIERS))
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--max-concurrency", type=int, default=0, help="0 = one worker per company")
    args = parser.parse_args()
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    if environment in {"sandbox", "production"}:
        print("Refused: isolated loopback only.", file=sys.stderr)
        return 2
    paliers = tuple(int(item) for item in args.paliers.split(",") if item.strip())
    for palier in paliers:
        if palier not in PALIERS:
            print(f"Unsupported palier {palier}. Allowed: {PALIERS}", file=sys.stderr)
            return 2

    host, port = "127.0.0.1", args.port
    httpd = serve(host, port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://{host}:{port}"
    if any(base.lower().startswith(item) for item in FORBIDDEN):
        print("Production forbidden.", file=sys.stderr)
        return 2
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base}/api/v1/health", timeout=1).read()
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.05)
    else:
        print("Mock server failed to start on loopback.", file=sys.stderr)
        httpd.shutdown()
        return 1
    results = []
    try:
        for palier in paliers:
            cap = args.max_concurrency or None
            results.append(run_palier(base, palier, args.iterations, cap))
    finally:
        httpd.shutdown()
        httpd.server_close()

    payload = {
        "tool": "python-thread-pool",
        "k6": "not-required",
        "locust": "not-required",
        "shared_infra": False,
        "results": results,
    }
    print(json.dumps(payload, indent=2))
    return 0 if all(item["pass"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
