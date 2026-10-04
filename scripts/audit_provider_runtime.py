"""Read-only provider evidence. No generation, messaging, payment or business writes."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))

from backend.app.config.settings import Settings


def presence(settings: Settings) -> dict[str, str]:
    names = (
        "openai_api_key", "anthropic_api_key", "google_ai_api_key",
        "vertex_enabled", "vertex_project", "vertex_location", "vertex_model",
        "vertex_service_account_email", "google_service_account_json",
        "retell_api_key", "telnyx_api_key", "telnyx_public_key",
        "stripe_secret_key", "stripe_webhook_secret",
        "google_calendar_client_id", "google_calendar_client_secret",
        "google_calendar_redirect_uri", "shopify_client_id", "shopify_client_secret",
        "shopify_redirect_uri", "woocommerce_callback_uri", "woocommerce_webhook_uri",
        "connector_encryption_keys", "smtp_host", "smtp_username", "smtp_password",
        "email_api_key", "backup_s3_endpoint_url", "backup_s3_bucket",
        "backup_s3_access_key", "backup_s3_secret_key",
    )
    return {name.upper(): "CONFIGURED" if getattr(settings, name, None) else "MISSING" for name in names}


def read_only_database(settings: Settings) -> dict[str, object]:
    from sqlalchemy import create_engine, text

    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10})
    if engine.dialect.name != "postgresql":
        engine.dispose()
        return {"status": "NOT_RUN", "reason": "production_postgresql_required"}
    queries = {
        "llm_last_24_hours": """
            SELECT provider, success, failure_category, request_status,
                   count(*) AS attempts, max(created_at)::text AS last_observed,
                   count(*) FILTER (WHERE provider_request_id IS NOT NULL) AS response_ids
            FROM tenant_ai_provider_attempts
            WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            GROUP BY provider, success, failure_category, request_status
            ORDER BY provider, success
        """,
        "commerce": """
            SELECT provider, status, count(*) AS connections,
                   count(*) FILTER (WHERE encrypted_credentials IS NOT NULL) AS credentials_present,
                   count(*) FILTER (WHERE last_successful_sync IS NOT NULL) AS historical_syncs
            FROM commerce_connections GROUP BY provider, status ORDER BY provider, status
        """,
        "calendar": """
            SELECT provider, sync_status, count(*) AS connections,
                   count(*) FILTER (WHERE last_synced_at IS NOT NULL) AS historical_syncs
            FROM crm_calendar_connections GROUP BY provider, sync_status ORDER BY provider
        """,
        "migrations": "SELECT version_num FROM alembic_version",
    }
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '10000ms'")
            return {label: [dict(row) for row in connection.execute(text(query)).mappings()] for label, query in queries.items()}
    finally:
        engine.dispose()


def connectivity(settings: Settings) -> list[dict[str, object]]:
    from backend.app.ai.llm.failure_classification import classify_exception

    results: list[dict[str, object]] = []

    def check(provider: str, operation: str, configured: bool, probe) -> None:
        if not configured:
            results.append({"provider": provider, "operation": operation, "configuration": "MISSING", "status": "NOT_RUN"})
            return
        try:
            probe()
            results.append({"provider": provider, "operation": operation, "configuration": "CONFIGURED", "status": "READ_ONLY_SUCCESS", "inference_or_delivery_verified": False})
        except Exception as exc:
            results.append({"provider": provider, "operation": operation, "configuration": "CONFIGURED", "status": "READ_ONLY_FAILED", "category": classify_exception(exc).value, "http_status": getattr(exc, "status_code", None), "inference_or_delivery_verified": False})

    def openai_metadata():
        from openai import OpenAI
        with OpenAI(api_key=settings.openai_api_key, timeout=10, max_retries=0) as client:
            client.models.retrieve(settings.openai_model)

    def anthropic_metadata():
        from anthropic import Anthropic
        with Anthropic(api_key=settings.anthropic_api_key, timeout=10, max_retries=0) as client:
            client.models.retrieve(settings.anthropic_model)

    def gemini_metadata():
        from google import genai
        from google.genai import types
        with genai.Client(enterprise=False, vertexai=False, api_key=settings.google_ai_api_key,
                          http_options=types.HttpOptions(timeout=10000, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            client.models.get(model=settings.gemini_model)

    def stripe_balance():
        import httpx
        with httpx.Client(timeout=10) as client:
            response = client.get("https://api.stripe.com/v1/balance", headers={"Authorization": f"Bearer {settings.stripe_secret_key}"})
            response.raise_for_status()

    def s3_head():
        import boto3
        from botocore.config import Config
        client = boto3.client("s3", endpoint_url=settings.backup_s3_endpoint_url,
                              aws_access_key_id=settings.backup_s3_access_key,
                              aws_secret_access_key=settings.backup_s3_secret_key,
                              region_name=settings.backup_s3_region,
                              config=Config(connect_timeout=8, read_timeout=8, retries={"max_attempts": 0}))
        try:
            client.head_bucket(Bucket=settings.backup_s3_bucket)
        finally:
            client.close()

    check("openai", "configured_model_metadata", bool(settings.openai_api_key), openai_metadata)
    check("anthropic", "configured_model_metadata", bool(settings.anthropic_api_key), anthropic_metadata)
    check("gemini", "configured_model_metadata", bool(settings.google_ai_api_key), gemini_metadata)
    check("stripe", "balance_read", bool(settings.stripe_secret_key), stripe_balance)
    check("s3", "bucket_head", bool(settings.backup_s3_enabled), s3_head)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only-production", action="store_true")
    parser.add_argument("--connectivity", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    result: dict[str, object] = {"configuration": presence(settings), "mutating_actions": 0}
    result["google_adc_environment"] = "CONFIGURED" if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") else "MISSING"
    result["sdk"] = {name: importlib.metadata.version(name) for name in ("google-genai", "google-auth", "openai", "anthropic")}
    if args.read_only_production:
        try:
            result["database_read_only"] = read_only_database(settings)
        except Exception:
            result["database_read_only"] = {"status": "UNKNOWN", "reason": "read_only_inspection_failed"}
    if args.connectivity:
        result["connectivity"] = connectivity(settings)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())