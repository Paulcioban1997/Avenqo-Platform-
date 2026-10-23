"""One-shot Sandbox proof: private ephemeral PG18 + real, namespaced test S3.

Never reads DATABASE_URL. No active database, production bucket or object deletion.
The imported backup service is byte-identical to PR67 aad34bf.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlencode
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.services.backup_service import BackupService, S3BackupStorage, _postgres_run

SANDBOX = "e5adc24d-23b9-4275-84de-91a7801649b8"
TEST_BUCKET = "avenqo-sandbox-backups-atkgdg"


class PrefixClient:
    """Test-only key namespace adapter; signing/upload/verification stay unmodified."""
    def __init__(self, client, bucket, prefix):
        assert prefix.startswith("qa/pr67/") and prefix.endswith("/")
        self.client, self.bucket, self.prefix = client, bucket, prefix

    def _args(self, kwargs):
        assert kwargs["Bucket"] == self.bucket
        return {**kwargs, "Key": self.prefix + kwargs["Key"]}

    def upload_file(self, filename, bucket, key):
        assert bucket == self.bucket
        return self.client.upload_file(filename, bucket, self.prefix + key)

    def download_file(self, bucket, key, filename):
        assert bucket == self.bucket
        return self.client.download_file(bucket, self.prefix + key, filename)

    def head_object(self, **kwargs):
        return self.client.head_object(**self._args(kwargs))

    def get_object(self, **kwargs):
        return self.client.get_object(**self._args(kwargs))

    def delete_object(self, **kwargs):
        raise AssertionError("S3 deletion forbidden in validation")

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        owner = self
        class Pages:
            def paginate(self, **kwargs):
                assert kwargs["Bucket"] == owner.bucket
                for page in owner.client.get_paginator(operation).paginate(**kwargs, Prefix=owner.prefix):
                    yield {**page, "Contents": [
                        {**item, "Key": item["Key"][len(owner.prefix):]}
                        for item in page.get("Contents", [])]}
        return Pages()


def inventory(client, bucket):
    return {item["Key"]: (item["Size"], item["ETag"])
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
            for item in page.get("Contents", [])}


def diagnostic(step, result, log_path=None):
    # Never print commands, DSNs, environment values or raw provider/SQL output.
    output = result.stderr or ""
    if log_path and log_path.exists():
        output += log_path.read_text(errors="replace")[-8192:]
    reasons = {"cannot be run as root": "root_user_forbidden", "Permission denied": "permission_denied",
               "No such file or directory": "path_missing", "invalid locale": "invalid_locale",
               "could not create shared memory": "shared_memory_unavailable",
               "database": "database_connection_failed"}
    reason = next((code for marker, code in reasons.items() if marker in output), "command_failed")
    print(json.dumps({"event": "qa_postgres_command_failed", "step": step,
                      "returncode": result.returncode, "reason": reason}))


def pg(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=90, **kwargs)
    if result.returncode:
        log_path = Path(command[command.index("-l") + 1]) if "-l" in command else None
        diagnostic(Path(command[0]).name, result, log_path)
        raise RuntimeError("isolated_postgres_command_failed")
    return result.stdout.strip()


def sql(dsn, statement):
    result = _postgres_run(dsn, ["psql", "-X", "-A", "-t", "--set=ON_ERROR_STOP=1", "-c", statement], timeout=30)
    if result.returncode:
        diagnostic("psql", result)
        raise RuntimeError("isolated_sql_failed")
    return result.stdout.strip()


def fixture_dsn(db, socket):
    if db not in {"postgres", "backup_fixture", "restore_fixture"}:
        raise ValueError("fixture_database_required")
    # A nonempty authority survives backup_service._postgres_run URL normalization.
    # The explicit Unix socket overrides localhost; the private server has TCP off.
    return "postgresql://qa_runtime@localhost/" + db + "?" + urlencode(
        {"host": str(socket), "port": "55432", "user": "qa_runtime"})


@contextmanager
def private_postgres():
    with tempfile.TemporaryDirectory(prefix="avenqo-pr67-") as root:
        root = Path(root)
        data, socket = root / "pgdata", root / "socket"
        socket.mkdir(mode=0o700)
        binaries = {name: shutil.which(name) is not None for name in ("initdb", "pg_ctl", "psql", "pg_dump")}
        print(json.dumps({"event": "qa_postgres_preflight", "uid": os.geteuid(),
                          "private_root_writable": os.access(root, os.W_OK), "binaries": binaries}))
        if os.geteuid() == 0 or not all(binaries.values()):
            raise RuntimeError("non_root_postgres18_binaries_required")
        pg(["initdb", "-D", str(data), "--username=qa_runtime", "--auth-local=trust", "--auth-host=reject"])
        try:
            pg(["pg_ctl", "-D", str(data), "-l", str(root / "postgres.log"),
                "-o", f"-F -c listen_addresses='' -k {socket} -p 55432", "-w", "start"])
            admin = fixture_dsn("postgres", socket)
            assert sql(admin, "SELECT inet_server_addr() IS NULL") == "t"
            assert sql(admin, "SHOW server_version_num").startswith("18")
            sql(admin, "CREATE DATABASE backup_fixture")
            sql(admin, "CREATE DATABASE restore_fixture")
            source, target = fixture_dsn("backup_fixture", socket), fixture_dsn("restore_fixture", socket)
            sql(source, "CREATE TABLE tenant_fixture (tenant text PRIMARY KEY, value integer); "
                "INSERT INTO tenant_fixture VALUES ('fixture-a',17),('fixture-b',29)")
            sql(source, "CREATE TABLE alembic_version (version_num text); INSERT INTO alembic_version VALUES ('fixture_only')")
            yield root, source, target, socket
        finally:
            if (data / "postmaster.pid").exists():
                pg(["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"])


def postgres_smoke():
    """Same Python lifecycle as Railway, no S3 credentials or network required."""
    with private_postgres() as (root, source, target, socket):
        old = "postgresql:///postgres?" + urlencode({"host": str(socket), "port": "55432", "user": "qa_runtime"})
        broken = _postgres_run(old, ["psql", "-X", "-c", "SELECT 1"], timeout=10)
        assert broken.returncode != 0, "old empty-authority URI must reproduce the regression"
        config = SimpleNamespace(database_url=source, environment="sandbox", app_version="qa-smoke",
            backup_root=str(root / "staging"), backup_s3_bucket=None, backup_s3_enabled=False, backup_retention_enabled=False,
            artifact_root=str(root / "no-artifacts"))
        service = BackupService(config)
        metadata = service.create_backup()
        service.restore_backup(metadata.backup_id, target)
        assert sql(target, "SELECT string_agg(tenant || ':' || value::text, ',' ORDER BY tenant) FROM tenant_fixture") == "fixture-a:17,fixture-b:29"
        assert sql(target, "SELECT version_num FROM alembic_version") == "fixture_only"
        print(json.dumps({"status": "PASS", "old_dsn_regression_reproduced": True,
                          "private_postgres18": True, "real_pg_dump_restore": True,
                          "size_bytes": metadata.size_bytes, "external_services_used": False}))


def run():
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    if os.getenv("RAILWAY_ENVIRONMENT_ID") != SANDBOX:
        raise RuntimeError("sandbox_environment_required")
    bucket = os.environ["BACKUP_S3_BUCKET"]
    endpoint = os.environ["BACKUP_S3_ENDPOINT_URL"]
    if bucket != TEST_BUCKET or endpoint != "https://t3.storageapi.dev":
        raise RuntimeError("distinct_sandbox_bucket_required")
    prefix = "qa/pr67/" + uuid4().hex + "/"
    report = {"environment": "sandbox", "test_bucket": bucket, "prefix": prefix,
              "production_modified": False, "active_database_used": False,
              "source_service_sha256": hashlib.sha256(Path(__file__).resolve().parents[1].joinpath(
                  "backend/app/services/backup_service.py").read_bytes()).hexdigest()}
    stage = "ephemeral_postgres_init"
    try:
        with private_postgres() as (root, source, target, socket):
            config = SimpleNamespace(database_url=source, environment="sandbox", app_version="pr67-proof",
                backup_root=str(root / "staging"), backup_retention_days=30, backup_retention_enabled=False,
                backup_s3_enabled=True, backup_s3_bucket=bucket, backup_s3_endpoint_url=endpoint,
                backup_s3_access_key=os.environ["BACKUP_S3_ACCESS_KEY"],
                backup_s3_secret_key=os.environ["BACKUP_S3_SECRET_KEY"], backup_s3_region="auto",
                artifact_root=str(root / "no-artifacts"))
            stage = "s3_auto_authentication"
            store = S3BackupStorage(config, Path(config.backup_root))
            raw = store._client
            before = inventory(raw, bucket)
            report["auto_region_read"] = "PASS"
            report["signing_version"] = raw.meta.config.signature_version
            stage = "read_only_iad_comparison"
            wrong = boto3.client("s3", endpoint_url=endpoint, region_name="iad",
                aws_access_key_id=config.backup_s3_access_key, aws_secret_access_key=config.backup_s3_secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style":"virtual"},
                              connect_timeout=10, read_timeout=15, retries={"total_max_attempts":1}))
            try:
                wrong.list_objects_v2(Bucket=bucket, MaxKeys=1)
                report["iad_region_read"] = "accepted_by_provider"
            except ClientError as exc:
                report["iad_region_read"] = exc.response.get("Error", {}).get("Code", "provider_error")
            store._client = PrefixClient(raw, bucket, prefix)
            service = BackupService(config, storage=store)
            def retention_forbidden():
                raise AssertionError("retention forbidden")
            service._apply_retention = retention_forbidden
            stage = "real_pg_dump_and_s3_upload"
            metadata = service.create_backup()
            report.update(backup_id=metadata.backup_id, size_bytes=metadata.size_bytes,
                          checksum_sha256=metadata.checksum_sha256, pg_dump="PASS")
            assert metadata.size_bytes > 0
            assert not list(service.root.iterdir())
            stage = "independent_remote_sha256"
            body = raw.get_object(Bucket=bucket, Key=prefix + metadata.backup_id + ".sql")["Body"]
            try:
                actual = hashlib.sha256(body.read()).hexdigest()
            finally:
                body.close()
            assert actual == metadata.checksum_sha256
            report["remote_sha256"] = "PASS"
            stage = "restore_from_test_bucket"
            service.restore_backup(metadata.backup_id, target)
            assert sql(target, "SELECT string_agg(tenant || ':' || value::text, ',' ORDER BY tenant) FROM tenant_fixture") == "fixture-a:17,fixture-b:29"
            assert sql(target, "SELECT version_num FROM alembic_version") == "fixture_only"
            report["isolated_postgres18_restore"] = "PASS"
            stage = "old_archive_preservation"
            after = inventory(raw, bucket)
            assert all(after.get(key) == value for key, value in before.items())
            assert all(key.startswith(prefix) for key in after.keys() - before.keys())
            report.update(old_objects=len(before), old_objects_preserved=True,
                added_objects=sorted(after.keys() - before.keys()), retention_executed=False, status="PASS")
        print(json.dumps(report, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status":"FAIL", "stage":stage, "error_class":type(exc).__name__,
                          "production_modified":False, "sensitive_details_withheld":True}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    if sys.argv[1:] == ["--postgres-smoke"]:
        postgres_smoke()
    elif not sys.argv[1:]:
        run()
    else:
        raise SystemExit("unsupported_qa_arguments")
