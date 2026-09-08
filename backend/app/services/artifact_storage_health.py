from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ArtifactStorageStatus:
    status: str
    readable: bool
    writable: bool
    nested_directories: bool


class ArtifactStorageHealth:
    def __init__(self) -> None:
        self._status: ArtifactStorageStatus | None = None

    @property
    def status(self) -> ArtifactStorageStatus | None:
        return self._status

    def check(self, root: Path) -> ArtifactStorageStatus:
        probe_root: Path | None = None
        readable = False
        writable = False
        nested_directories = False
        try:
            root.mkdir(parents=True, exist_ok=True)
            next(root.iterdir(), None)
            readable = True
            probe_root = Path(tempfile.mkdtemp(prefix=".storage-probe-", dir=root))
            probe_file = probe_root / "probe.tmp"
            probe_file.write_bytes(b"avenqo-storage-probe")
            if probe_file.read_bytes() != b"avenqo-storage-probe":
                raise OSError("Artifact storage probe read did not match")
            probe_file.unlink()
            writable = True
            nested = probe_root / "company_datasets" / "tenant" / "datasets" / "dataset" / "v1" / "raw"
            nested.mkdir(parents=True)
            nested_directories = True
        except OSError as exc:
            logger.error("Artifact storage permission validation failed: %s", exc)
        finally:
            if probe_root is not None:
                try:
                    shutil.rmtree(probe_root)
                except OSError as exc:
                    logger.error("Artifact storage probe cleanup failed: %s", exc)
                    writable = False
        status = ArtifactStorageStatus(
            status="ok" if readable and writable and nested_directories else "unavailable",
            readable=readable,
            writable=writable,
            nested_directories=nested_directories,
        )
        self._status = status
        return status


artifact_storage_health = ArtifactStorageHealth()