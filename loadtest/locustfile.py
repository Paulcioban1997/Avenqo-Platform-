"""Lot 7 Locust scenarios. Non-prod only. Do not invent measured numbers.

Run against localhost or Sandbox after an explicit GO. Never Production.
Never saturate paid provider APIs — health and auth-gated reads only.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

FORBIDDEN = (
    "https://api.avenqo.ca",
    "https://avenqo.ca",
    "https://www.avenqo.ca",
)


class TenantHealthUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self) -> None:
        host = (self.host or os.getenv("AVENQO_LOADTEST_BASE_URL") or "").rstrip("/")
        lowered = host.lower()
        if not host:
            raise RuntimeError("Set --host or AVENQO_LOADTEST_BASE_URL to a non-prod origin.")
        if any(lowered.startswith(item) for item in FORBIDDEN):
            raise RuntimeError("Production origins are forbidden for Lot 7 load tests.")

    @task
    def health(self) -> None:
        self.client.get("/api/v1/health")
