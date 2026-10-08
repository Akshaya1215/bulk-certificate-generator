import os
import uuid
from pathlib import Path
from app.core.config import settings
from app.core.logging import logger
from app.exceptions.custom_exceptions import StorageError


class FileStorage:
    """Handles local filesystem persistence for generated certificates with path traversal protection."""

    def __init__(self, base_dir: Path | str | None = None):
        if base_dir is None:
            self.base_dir = settings.storage_absolute_path
        else:
            self.base_dir = Path(base_dir).resolve()
        self._ensure_base_dir()

    def _ensure_base_dir(self) -> None:
        """Ensures the base storage directory exists."""
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create base storage directory %s: %s", self.base_dir, e)
            raise StorageError(f"Cannot initialize storage directory: {e}") from e

    def _safe_resolve(self, target_path: Path) -> Path:
        """Resolves target path and ensures it does not escape base_dir (prevents path traversal)."""
        resolved = target_path.resolve()
        try:
            # Python 3.9+ is_relative_to
            if not resolved.is_relative_to(self.base_dir.resolve()):
                logger.warning("Path traversal attempt detected: %s", target_path)
                raise StorageError("Access denied: path traversal attempt detected.")
        except AttributeError:
            # Fallback for older python
            common = os.path.commonpath([str(resolved), str(self.base_dir.resolve())])
            if common != str(self.base_dir.resolve()):
                raise StorageError("Access denied: path traversal attempt detected.")
        return resolved

    def get_job_dir(self, job_id: uuid.UUID | str) -> Path:
        """Gets or creates the directory for a specific job."""
        job_dir = self.base_dir / str(job_id)
        safe_job_dir = self._safe_resolve(job_dir)
        safe_job_dir.mkdir(parents=True, exist_ok=True)
        return safe_job_dir

    def save_certificate_file(
        self,
        job_id: uuid.UUID | str,
        certificate_id: uuid.UUID | str,
        file_bytes: bytes,
    ) -> str:
        """Saves certificate PDF bytes to generated/<job_id>/<certificate_id>.pdf and returns relative or absolute path."""
        job_dir = self.get_job_dir(job_id)
        filename = f"{certificate_id}.pdf"
        file_path = job_dir / filename
        safe_path = self._safe_resolve(file_path)

        try:
            with open(safe_path, "wb") as f:
                f.write(file_bytes)
            logger.info("Successfully saved certificate file to %s", safe_path)
            # Store relative path in database for portability across host/docker
            rel_path = safe_path.relative_to(self.base_dir.resolve())
            return str(rel_path).replace("\\", "/")
        except OSError as e:
            logger.error("Failed to write certificate file %s: %s", safe_path, e)
            raise StorageError(f"Failed to save certificate: {e}") from e

    def file_exists(self, file_path_str: str) -> bool:
        """Checks if a certificate file exists safely."""
        path = Path(file_path_str)
        if not path.is_absolute():
            path = self.base_dir / path
        try:
            safe_path = self._safe_resolve(path)
            return safe_path.is_file()
        except StorageError:
            return False

    def get_resolved_path(self, file_path_str: str) -> Path:
        """Returns the safely resolved Path object."""
        path = Path(file_path_str)
        if not path.is_absolute():
            path = self.base_dir / path
        return self._safe_resolve(path)


file_storage = FileStorage()
