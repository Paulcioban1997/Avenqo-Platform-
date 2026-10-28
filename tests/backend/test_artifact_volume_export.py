"""No Production credentials, files or services are used by these tests."""

import os
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import boto3
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from moto import mock_aws

from scripts import export_artifact_volume as exporter


@pytest.fixture
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    class RedactedKeyPair:
        def __getitem__(self, index):
            return (public_pem, private_pem)[index]

        def __repr__(self):
            return "<fictional RSA test keypair redacted>"

    return RedactedKeyPair()


def test_encrypted_round_trip_with_inventory_and_empty_directory(tmp_path, keys):
    root = tmp_path / "source"
    (root / "tenant-a" / "empty").mkdir(parents=True)
    (root / "tenant-b").mkdir()
    (root / "tenant-a" / "report.csv").write_bytes(b"fictitious,non-sensitive\n")
    (root / "tenant-b" / "binary.bin").write_bytes(bytes(range(256)) * 4096)
    plain, cipher = tmp_path / "archive.tar.gz", tmp_path / "archive.avq"
    summary = exporter.make_archive(root, plain)
    assert summary["file_count"] == 2
    assert summary["directory_count"] == 3
    exporter.encrypt_archive(plain, cipher, keys[0])
    assert b"fictitious" not in cipher.read_bytes()
    decrypted = tmp_path / "decrypted.tar.gz"
    exporter.decrypt_archive(cipher, decrypted, keys[1])
    restored = tmp_path / "isolated-restore"
    result = exporter.restore_isolated(decrypted, restored)
    assert result == {"files_verified": 2, "directories_verified": 3}
    assert (restored / "artifacts" / "tenant-a" / "report.csv").read_bytes() == b"fictitious,non-sensitive\n"
    assert hashlib.sha256((restored / "artifacts" / "tenant-b" / "binary.bin").read_bytes()).hexdigest() == hashlib.sha256((root / "tenant-b" / "binary.bin").read_bytes()).hexdigest()
    assert (restored / "artifacts" / "tenant-a" / "empty").is_dir()
    with pytest.raises(ValueError, match="already exists"):
        exporter.restore_isolated(decrypted, restored)


def test_ciphertext_tamper_and_wrong_private_key_fail(tmp_path, keys):
    root = tmp_path / "source"
    root.mkdir()
    (root / "one.txt").write_text("fixture only", encoding="utf-8")
    plain, cipher = tmp_path / "archive.tar.gz", tmp_path / "archive.avq"
    exporter.make_archive(root, plain)
    exporter.encrypt_archive(plain, cipher, keys[0])
    altered = bytearray(cipher.read_bytes())
    altered[-20] ^= 1
    cipher.write_bytes(altered)
    with pytest.raises(Exception):
        exporter.decrypt_archive(cipher, tmp_path / "tampered.tar.gz", keys[1])
    other = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    other_pem = other.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with pytest.raises(Exception):
        exporter.decrypt_archive(cipher, tmp_path / "wrong-key.tar.gz", other_pem)


def test_symlink_and_hardlink_cannot_escape_export_root(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    original = root / "original.txt"
    original.write_text("fixture", encoding="utf-8")
    hardlink = root / "hardlink.txt"
    os.link(original, hardlink)
    with pytest.raises(ValueError, match="hardlink"):
        exporter.make_archive(root, tmp_path / "unsafe.tar.gz")
    hardlink.unlink()
    (root / "link.txt").symlink_to(original)
    with pytest.raises(ValueError, match="Symlink"):
        exporter.make_archive(root, tmp_path / "unsafe-symlink.tar.gz")


@mock_aws
def test_remote_full_sha256_and_no_overwrite(tmp_path, monkeypatch):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=exporter.BUCKET)
    client.put_object(Bucket=exporter.BUCKET, Key="historic-backups/previous.sql.gz", Body=b"preserve historic fixture")
    cipher = tmp_path / "archive.avq"
    cipher.write_bytes(b"encrypted fixture bytes")
    key = exporter.KEY_PREFIX + "fictional-run.avq"
    result = exporter.upload_and_verify(cipher, key, client)
    assert result["cipher_bytes"] == cipher.stat().st_size
    assert result["cipher_sha256"] == exporter._sha256(cipher)
    with pytest.raises(FileExistsError):
        exporter.upload_and_verify(cipher, key, client)
    assert client.get_object(Bucket=exporter.BUCKET, Key=key)["Body"].read() == cipher.read_bytes()
    assert client.get_object(Bucket=exporter.BUCKET, Key="historic-backups/previous.sql.gz")["Body"].read() == b"preserve historic fixture"


def test_production_identity_guard_refuses_fixture_context(monkeypatch):
    for name in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID",
                 "RAILWAY_ENVIRONMENT_NAME", "ENVIRONMENT", "ARTIFACT_ROOT", "BACKUP_S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="identity mismatch"):
        exporter._production_guard()


@mock_aws
def test_download_decrypt_and_restore_from_mock_s3(tmp_path, keys):
    source = tmp_path / "source"
    source.mkdir()
    payload = bytes(range(256)) * 8192
    (source / "sample.bin").write_bytes(payload)
    plain = tmp_path / "source.tar.gz"
    cipher = tmp_path / "source.avq"
    exporter.make_archive(source, plain)
    cipher_summary = exporter.encrypt_archive(plain, cipher, keys[0])
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=exporter.BUCKET)
    key = exporter.KEY_PREFIX + "fictional-restore.avq"
    upload_summary = exporter.upload_and_verify(cipher, key, client)
    downloaded = tmp_path / "downloaded.avq"
    downloaded.write_bytes(client.get_object(Bucket=exporter.BUCKET, Key=key)["Body"].read())
    assert hashlib.sha256(downloaded.read_bytes()).hexdigest() == cipher_summary["cipher_sha256"] == upload_summary["cipher_sha256"]
    decrypted = tmp_path / "downloaded.tar.gz"
    exporter.decrypt_archive(downloaded, decrypted, keys[1])
    isolated = tmp_path / "restored"
    assert exporter.restore_isolated(decrypted, isolated)["files_verified"] == 1
    assert (isolated / "artifacts" / "sample.bin").read_bytes() == payload
    assert (source / "sample.bin").read_bytes() == payload


def test_encrypted_private_key_can_restore(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.BestAvailableEncryption(b"fixture-passphrase"))
    root = tmp_path / "source"
    root.mkdir()
    (root / "fixture.txt").write_text("only fictitious data", encoding="utf-8")
    plain, cipher = tmp_path / "source.tar.gz", tmp_path / "source.avq"
    exporter.make_archive(root, plain)
    exporter.encrypt_archive(plain, cipher, public_pem)
    decrypted = tmp_path / "decrypted.tar.gz"
    exporter.decrypt_archive(cipher, decrypted, private_pem, password=b"fixture-passphrase")
    assert exporter.restore_isolated(decrypted, tmp_path / "isolated")["files_verified"] == 1


def test_cli_error_never_logs_environment_secret(tmp_path):
    marker = "FICTIONAL_SECRET_MUST_NOT_APPEAR"
    environment = os.environ.copy()
    environment["BACKUP_S3_SECRET_KEY"] = marker
    environment.pop("RAILWAY_PROJECT_ID", None)
    run = subprocess.run([sys.executable, str(Path(exporter.__file__)), "export"],
                         cwd=tmp_path, env=environment, capture_output=True, text=True, check=False)
    assert run.returncode == 1
    assert marker not in run.stdout + run.stderr
    assert '"error_class": "ValueError"' in run.stderr


def test_keygen_creates_encrypted_local_private_key_only(tmp_path, monkeypatch, capsys):
    private_path = tmp_path / "recipient-private.pem"
    public_path = tmp_path / "recipient-public.pem"
    monkeypatch.setattr(exporter.getpass, "getpass", lambda _: "fictional long passphrase 123")
    monkeypatch.setattr(sys, "argv", ["export_artifact_volume.py", "keygen-local",
                                     "--private-key", str(private_path), "--public-key", str(public_path)])
    exporter.main()
    assert b"ENCRYPTED PRIVATE KEY" in private_path.read_bytes()
    assert b"PRIVATE KEY" not in public_path.read_bytes()
    output = capsys.readouterr().out
    assert "fictional long passphrase" not in output
    assert "BEGIN" not in output


def test_rescue_image_and_railway_config_exclude_application_startup():
    repository = Path(exporter.__file__).resolve().parents[1]
    dockerfile = (repository / "backend" / "Dockerfile.artifact-export").read_text(encoding="utf-8")
    inherited_dockerfile = (repository / "backend" / "Dockerfile").read_text(encoding="utf-8")
    config = json.loads((repository / "railway.json").read_text(encoding="utf-8"))
    assert inherited_dockerfile == dockerfile  # Existing RAILWAY_DOCKERFILE_PATH points here.
    copy_lines = [line for line in dockerfile.splitlines() if line.startswith("COPY ")]
    assert copy_lines == ["COPY scripts/export_artifact_volume.py /srv/export_artifact_volume.py"]
    assert "docker-entrypoint.sh" not in "\n".join(copy_lines)
    assert config["build"]["dockerfilePath"] == "backend/Dockerfile.artifact-export"
    assert config["deploy"]["startCommand"] == "python /srv/export_artifact_volume.py export"
    assert config["deploy"]["preDeployCommand"] == []
    assert config["deploy"]["cronSchedule"] is None
    assert config["deploy"]["restartPolicyType"] == "NEVER"
