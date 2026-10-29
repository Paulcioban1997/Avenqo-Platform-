"""One-shot, read-only export of the existing Production artifact volume.

This script intentionally imports no Avenqo application, database, billing, or
telephony code. It never deletes or writes under ARTIFACT_ROOT. Production use
requires a separately approved, pinned rescue deployment.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import io
import json
import os
import re
import stat
import struct
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PROJECT_ID = "062bbe91-68e7-4e79-8de7-cffeb8a5f5cd"
ENVIRONMENT_ID = "b9b03d41-2a67-4aab-a6f6-32939d8b81e0"
SERVICE_ID = "24a2afc3-36f8-46d0-b79d-b323755a83f3"
BUCKET = "avenqo-backups-u7bgklgz2"
ROOT = Path("/data/artifacts")
MAGIC = b"AVENQO-ARTIFACTS-ENC-V1\n"
CHUNK = 1024 * 1024
KEY_PREFIX = "p0-volume-export/v1/"
MAX_SOURCE_BYTES = 500 * 1024 * 1024
MAX_FILE_COUNT = 50000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


class _HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, count=-1):
        block = self.stream.read(count)
        self.digest.update(block)
        self.size += len(block)
        return block


def make_archive(root: Path, destination: Path) -> dict:
    """Package regular files and a per-file manifest without writing to root."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Artifact root is missing or is a symlink")
    files = []
    directories = []
    source_bytes = 0
    with tarfile.open(destination, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        for current, dirs, names in os.walk(root, followlinks=False):
            dirs.sort()
            names.sort()
            current_path = Path(current)
            for name in dirs:
                child = current_path / name
                if not stat.S_ISDIR(child.lstat().st_mode):
                    raise ValueError("Non-directory or symlink encountered in artifact tree")
                relative = child.relative_to(root).as_posix()
                info = tarfile.TarInfo(f"artifacts/{relative}/")
                info.type = tarfile.DIRTYPE
                info.mode = 0o700
                tar.addfile(info)
                directories.append(relative)
            for name in names:
                child = current_path / name
                before = child.lstat()
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise ValueError("Symlink, hardlink or special file encountered in artifact tree")
                if len(files) >= MAX_FILE_COUNT or source_bytes + before.st_size > MAX_SOURCE_BYTES:
                    raise ValueError("Artifact export safety limit exceeded")
                relative = child.relative_to(root).as_posix()
                info = tarfile.TarInfo(f"artifacts/{relative}")
                info.size = before.st_size
                info.mode = 0o600
                info.mtime = int(before.st_mtime)
                with child.open("rb") as source:
                    reader = _HashingReader(source)
                    tar.addfile(info, reader)
                after = child.lstat()
                if (reader.size != before.st_size or before.st_size != after.st_size
                        or before.st_mtime_ns != after.st_mtime_ns
                        or before.st_ino != after.st_ino):
                    raise RuntimeError("Artifact changed during export")
                files.append({"path": relative, "size": reader.size, "sha256": reader.digest.hexdigest()})
                source_bytes += reader.size
        manifest = {"version": 1, "directories": directories, "files": files}
        raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(raw)
        info.mode = 0o600
        tar.addfile(info, io.BytesIO(raw))
    return {
        "file_count": len(files),
        "directory_count": len(directories),
        "source_bytes": source_bytes,
        "archive_bytes": destination.stat().st_size,
        "archive_sha256": _sha256(destination),
    }


def encrypt_archive(plain: Path, encrypted: Path, public_pem: bytes) -> dict:
    recipient = serialization.load_pem_public_key(public_pem)
    if not isinstance(recipient, rsa.RSAPublicKey) or recipient.key_size < 3072:
        raise ValueError("A dedicated RSA public key of at least 3072 bits is required")
    key = os.urandom(32)
    nonce = os.urandom(12)
    wrapped = recipient.encrypt(
        key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    header = json.dumps({
        "algorithm": "AES-256-GCM+RSA-OAEP-SHA256",
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "wrapped_key": base64.b64encode(wrapped).decode("ascii"),
        "plain_bytes": plain.stat().st_size,
        "plain_sha256": _sha256(plain),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    with plain.open("rb") as source, encrypted.open("xb") as target:
        target.write(prefix)
        for block in iter(lambda: source.read(CHUNK), b""):
            target.write(encryptor.update(block))
        target.write(encryptor.finalize())
        target.write(encryptor.tag)
    return {"cipher_bytes": encrypted.stat().st_size, "cipher_sha256": _sha256(encrypted)}


def decrypt_archive(encrypted: Path, plain: Path, private_pem: bytes, password: bytes | None = None) -> None:
    private = serialization.load_pem_private_key(private_pem, password=password)
    with encrypted.open("rb") as source:
        if source.read(len(MAGIC)) != MAGIC:
            raise ValueError("Invalid encrypted archive format")
        header_size_bytes = source.read(4)
        if len(header_size_bytes) != 4:
            raise ValueError("Truncated encrypted archive")
        header_size = struct.unpack(">I", header_size_bytes)[0]
        if not 0 < header_size <= 8192:
            raise ValueError("Invalid encrypted archive header size")
        header_bytes = source.read(header_size)
        header = json.loads(header_bytes)
        if header.get("algorithm") != "AES-256-GCM+RSA-OAEP-SHA256":
            raise ValueError("Unsupported encryption algorithm")
        prefix = MAGIC + header_size_bytes + header_bytes
        key = private.decrypt(
            base64.b64decode(header["wrapped_key"], validate=True),
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        nonce = base64.b64decode(header["nonce"], validate=True)
        cipher_end = encrypted.stat().st_size - 16
        if cipher_end < source.tell():
            raise ValueError("Truncated encrypted archive body")
        source.seek(cipher_end)
        tag = source.read(16)
        source.seek(len(prefix))
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(prefix)
        with plain.open("xb") as target:
            remaining = cipher_end - source.tell()
            while remaining:
                block = source.read(min(CHUNK, remaining))
                if not block:
                    raise ValueError("Truncated ciphertext")
                remaining -= len(block)
                target.write(decryptor.update(block))
            target.write(decryptor.finalize())
    if plain.stat().st_size != header["plain_bytes"] or _sha256(plain) != header["plain_sha256"]:
        raise ValueError("Decrypted archive checksum mismatch")


def restore_isolated(plain: Path, target: Path) -> dict:
    """Extract only into a new directory, then verify every file against manifest."""
    if target.exists():
        raise ValueError("Restore target already exists")
    with tarfile.open(plain, "r:gz") as tar:
        members = tar.getmembers()
        if not members or members[-1].name != "manifest.json":
            raise ValueError("Archive manifest missing")
        manifest = json.load(tar.extractfile(members[-1]))
        if manifest.get("version") != 1:
            raise ValueError("Unsupported archive manifest version")
        expected = {f"artifacts/{row['path']}" for row in manifest["files"]}
        expected_dirs = {f"artifacts/{row}" for row in manifest["directories"]}
        actual = {m.name for m in members if m.isfile() and m.name != "manifest.json"}
        actual_dirs = {m.name.rstrip("/") for m in members if m.isdir()}
        if actual != expected or actual_dirs != expected_dirs:
            raise ValueError("Archive inventory does not match manifest")
        for member in members[:-1]:
            relative = PurePosixPath(member.name)
            if (relative.is_absolute() or ".." in relative.parts or not relative.parts
                    or relative.parts[0] != "artifacts"
                    or any("\\" in part or ":" in part for part in relative.parts)):
                raise ValueError("Unsafe archive path")
            destination = target.joinpath(*relative.parts)
            if not destination.resolve().is_relative_to(target.resolve()):
                raise ValueError("Archive path escapes isolated target")
            if not (member.isdir() or member.isfile()):
                raise ValueError("Unsupported archive member")
        target.mkdir(parents=True, exist_ok=False)
        for member in members[:-1]:
            relative = PurePosixPath(member.name)
            destination = target.joinpath(*relative.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, destination.open("xb") as output:
                    for block in iter(lambda: source.read(CHUNK), b""):
                        output.write(block)
    for row in manifest["files"]:
        restored = target / "artifacts" / row["path"]
        if restored.stat().st_size != row["size"] or _sha256(restored) != row["sha256"]:
            raise ValueError("Restored file checksum mismatch")
    return {"files_verified": len(manifest["files"]), "directories_verified": len(manifest["directories"])}


def _s3_client():
    import boto3
    from botocore.config import Config

    endpoint = os.environ["BACKUP_S3_ENDPOINT_URL"]
    if not endpoint.startswith("https://"):
        raise ValueError("S3 endpoint must use HTTPS")
    return boto3.client(
        "s3", endpoint_url=endpoint, region_name="auto",
        aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["BACKUP_S3_SECRET_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def upload_and_verify(encrypted: Path, key: str, client=None) -> dict:
    """Use a fresh key; verify the complete remotely read ciphertext, never delete."""
    if not key.startswith(KEY_PREFIX) or not re.fullmatch(r"[A-Za-z0-9/_-]+\.avq", key):
        raise ValueError("Unsafe backup object key")
    client = client or _s3_client()
    try:
        client.head_object(Bucket=BUCKET, Key=key)
    except client.exceptions.ClientError as error:
        if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
            raise
    else:
        raise FileExistsError("Backup object key already exists")
    local_hash = _sha256(encrypted)
    client.upload_file(str(encrypted), BUCKET, key, ExtraArgs={"Metadata": {"sha256": local_hash}})
    remote = client.get_object(Bucket=BUCKET, Key=key)
    digest = hashlib.sha256()
    byte_count = 0
    for block in remote["Body"].iter_chunks(CHUNK):
        digest.update(block)
        byte_count += len(block)
    if byte_count != encrypted.stat().st_size or digest.hexdigest() != local_hash:
        raise RuntimeError("Remote backup bytes or SHA-256 differ from local ciphertext")
    return {"object_key": key, "cipher_bytes": byte_count, "cipher_sha256": local_hash}


def _production_guard() -> None:
    expected = {
        "RAILWAY_PROJECT_ID": PROJECT_ID,
        "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT_ID,
        "RAILWAY_SERVICE_ID": SERVICE_ID,
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "ENVIRONMENT": "production",
        "ARTIFACT_ROOT": str(ROOT),
        "BACKUP_S3_BUCKET": BUCKET,
    }
    if any(os.getenv(name) != value for name, value in expected.items()):
        raise ValueError("Production export identity mismatch")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Encrypted, read-only artifact volume exporter")
    parser.add_argument("command", choices=("export", "restore-local", "keygen-local"))
    parser.add_argument("--archive", type=Path, help="Encrypted archive downloaded from S3 for local restore")
    parser.add_argument("--private-key", type=Path, help="Local private PEM; never sent to Railway")
    parser.add_argument("--public-key", type=Path, help="Local public PEM; safe to configure as recipient")
    parser.add_argument("--target", type=Path, help="New isolated directory for local restore")
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "export":
        # Railway's service-level startCommand is appended after Docker ENTRYPOINT.
        # In export mode, ignore any trailing arguments so inherited commands
        # (such as `sh -c "python -m alembic ... && exec uvicorn ..."`) can never
        # block or divert the one-shot read-only export.
        args = parser.parse_args(["export"])
    else:
        args = parser.parse_args(raw_argv)
    if args.command == "keygen-local":
        if not args.private_key or not args.public_key:
            parser.error("keygen-local requires --private-key and --public-key")
        if args.private_key.exists() or args.public_key.exists():
            raise FileExistsError("Key output already exists")
        password = getpass.getpass("New private key passphrase: ").encode("utf-8")
        confirmed = getpass.getpass("Confirm private key passphrase: ").encode("utf-8")
        if len(password) < 16 or password != confirmed:
            raise ValueError("Passphrase must match and contain at least 16 bytes")
        private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        private_pem = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password),
        )
        public_pem = private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with os.fdopen(os.open(args.private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
            output.write(private_pem)
        with os.fdopen(os.open(args.public_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), "wb") as output:
            output.write(public_pem)
        print(json.dumps({"status": "local_keypair_created", "public_key_sha256": hashlib.sha256(public_pem).hexdigest()}))
    elif args.command == "export":
        _production_guard()
        recipient_b64 = os.environ["ARTIFACT_EXPORT_RECIPIENT_PUBLIC_KEY_B64"]
        public_pem = base64.b64decode(recipient_b64, validate=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex
        with tempfile.TemporaryDirectory(prefix="avenqo-artifact-export-") as staging:
            plain = Path(staging) / "artifacts.tar.gz"
            encrypted = Path(staging) / "artifacts.avq"
            summary = make_archive(ROOT, plain)
            summary.update(encrypt_archive(plain, encrypted, public_pem))
            summary.update(upload_and_verify(encrypted, f"{KEY_PREFIX}{run_id}.avq"))
            print(json.dumps({"status": "uploaded_and_remote_sha256_verified", **summary}, sort_keys=True))
    else:
        if not all((args.archive, args.private_key, args.target)):
            parser.error("restore-local requires --archive, --private-key and --target")
        with tempfile.TemporaryDirectory(prefix="avenqo-artifact-restore-") as staging:
            plain = Path(staging) / "artifacts.tar.gz"
            private_pem = args.private_key.read_bytes()
            password = None
            if b"ENCRYPTED PRIVATE KEY" in private_pem:
                password = getpass.getpass("Private key passphrase: ").encode("utf-8")
            decrypt_archive(args.archive, plain, private_pem, password=password)
            summary = restore_isolated(plain, args.target)
            print(json.dumps({"status": "isolated_restore_verified", **summary}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never include exception text: SDK errors may contain endpoint or key data.
        print(json.dumps({"status": "FAIL", "error_class": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1)
