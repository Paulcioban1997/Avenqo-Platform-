"""Locust paliers against an isolated loopback API. Real JWT login, no client tenant headers.

  locust -f loadtest/locustfile.py --headless -u 10 -r 10 -t 20s --host http://127.0.0.1:18000
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

FORBIDDEN = (
    "https://api.avenqo.ca",
    "https://avenqo.ca",
    "https://www.avenqo.ca",
)


class IsolatedTenantUser(HttpUser):
    wait_time = between(0.1, 0.4)

    def on_start(self) -> None:
        host = (self.host or os.getenv("AVENQO_LOADTEST_BASE_URL") or "").rstrip("/")
        lowered = host.lower()
        if not host:
            raise RuntimeError("Set --host or AVENQO_LOADTEST_BASE_URL to a loopback origin.")
        if any(lowered.startswith(item) for item in FORBIDDEN) or "railway" in lowered:
            raise RuntimeError("Production and live Sandbox origins are forbidden.")
        if not (lowered.startswith("http://127.0.0.1") or lowered.startswith("http://localhost")):
            raise RuntimeError("Locust load tests must target loopback.")
        users = max(1, int(os.getenv("LOCUST_USERS") or os.getenv("AVENQO_LOADTEST_VUS") or "1"))
        index = ((self.environment.runner.user_count if self.environment.runner else 1) % users) + 1
        email = f"owner-iso-{index:03d}@example.com"
        password = os.getenv("AVENQO_LOADTEST_PASSWORD") or "Isolated-Synthetic-Pass-1!"
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        payload = response.json() if response.status_code == 200 else {}
        self.token = payload.get("access_token")

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {"Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    @task(3)
    def health(self) -> None:
        self.client.get("/api/v1/health")

    @task(2)
    def me_retail_crm(self) -> None:
        headers = self._headers()
        self.client.get("/api/v1/auth/me", headers=headers)
        self.client.get("/api/v1/retail/status", headers=headers)
        self.client.get("/api/v1/crm/clients", headers=headers)

    @task(1)
    def simulated_central(self) -> None:
        headers = self._headers()
        created = self.client.post(
            "/api/v1/ai/chat/conversations",
            json={"title": "locust-iso"},
            headers=headers,
        )
        if created.status_code != 201:
            return
        conversation_id = created.json().get("id")
        self.client.post(
            f"/api/v1/ai/central/conversations/{conversation_id}/messages",
            json={"content": "Bonjour"},
            headers=headers,
        )
