"""Locust paliers 10→250. Non-prod / loopback only. Simulated AI, no paid providers.

  locust -f loadtest/locustfile.py --headless -u 10 -r 10 -t 20s --host http://127.0.0.1:18080
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

FORBIDDEN = (
    "https://api.avenqo.ca",
    "https://avenqo.ca",
    "https://www.avenqo.ca",
)
PALIERS = (10, 25, 50, 100, 150, 200, 250)


class SimulatedTenantUser(HttpUser):
    wait_time = between(0.1, 0.4)

    def on_start(self) -> None:
        host = (self.host or os.getenv("AVENQO_LOADTEST_BASE_URL") or "").rstrip("/")
        lowered = host.lower()
        if not host:
            raise RuntimeError("Set --host or AVENQO_LOADTEST_BASE_URL to a non-prod origin.")
        if any(lowered.startswith(item) for item in FORBIDDEN):
            raise RuntimeError("Production origins are forbidden for Lot 7 load tests.")
        users = int(os.getenv("LOCUST_USERS") or os.getenv("AVENQO_LOADTEST_VUS") or "1")
        if users >= 50 and not (lowered.startswith("http://127.0.0.1") or lowered.startswith("http://localhost")):
            raise RuntimeError("Paliers ≥50 must target loopback. Shared infrastructure is forbidden.")
        self.tenant_id = f"company-{self.environment.runner.user_count if self.environment.runner else 1}"

    def _headers(self) -> dict[str, str]:
        return {"X-Simulated-Company-Id": self.tenant_id, "Content-Type": "application/json"}

    @task(3)
    def health(self) -> None:
        self.client.get("/api/v1/health", headers=self._headers())

    @task(1)
    def login(self) -> None:
        self.client.post(
            "/api/v1/auth/login",
            json={"email": f"{self.tenant_id}@loadtest.local"},
            headers=self._headers(),
        )

    @task(2)
    def simulated_central(self) -> None:
        self.client.post(
            "/api/v1/ai/chat",
            json={"message": "ping simulated central"},
            headers=self._headers(),
        )
