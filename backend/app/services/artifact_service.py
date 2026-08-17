"""Stockage tenant-isolé des fichiers bruts et artefacts AI Engine."""

from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from uuid import UUID

from shared.ai_engine.contracts import TenantContext

_SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9._-]+")


class ArtifactService:
    """Écrit les artefacts uniquement dans l'espace du tenant courant."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def save_dataset(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
        filename: str,
        content: bytes,
    ) -> Path:
        safe_name = _SAFE_FILENAME.sub("_", Path(filename).name) or "dataset.csv"
        directory = self._root / str(tenant.company_id) / "datasets" / str(dataset_id)
        directory.mkdir(parents=True, exist_ok=True)
        destination = (directory / safe_name).resolve()
        if self._root not in destination.parents:
            raise ValueError("Chemin d'artefact invalide")
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(dir=directory, delete=False) as temporary:
                temporary.write(content)
                temporary.flush()
                temporary_path = Path(temporary.name)
            temporary_path.replace(destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return destination

    @staticmethod
    def delete(path: Path) -> None:
        path.unlink(missing_ok=True)