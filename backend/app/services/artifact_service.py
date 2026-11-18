"""Stockage tenant-isolé des fichiers bruts et artefacts AI Engine."""

from pathlib import Path
import re
import shutil
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
        content: bytes | Path,
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
                temporary_path = Path(temporary.name)
            if isinstance(content, Path):
                shutil.copyfile(content, temporary_path)
            else:
                temporary_path.write_bytes(content)
            temporary_path.replace(destination)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
        return destination

    @staticmethod
    def delete(path: Path) -> None:
        path.unlink(missing_ok=True)

    def get_tenant_storage_bytes(self, tenant: TenantContext | UUID | str) -> int:
        """Calcule la taille totale en octets de tous les fichiers stockés pour ce tenant."""
        if isinstance(tenant, TenantContext):
            company_id = str(tenant.company_id)
        else:
            company_id = str(tenant)
        total = 0
        tenant_dirs = [
            self._root / company_id,
            self._root / "company_datasets" / company_id,
        ]
        for t_dir in tenant_dirs:
            if t_dir.exists() and t_dir.is_dir():
                for p in t_dir.rglob("*"):
                    if p.is_file():
                        try:
                            total += p.stat().st_size
                        except OSError:
                            pass
        return total
