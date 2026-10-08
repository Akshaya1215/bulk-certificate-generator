import uuid
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.exceptions.custom_exceptions import (
    CertificateFileNotFoundError,
    CertificateNotFoundError,
)
from app.models.certificate import Certificate
from app.models.recipient import Recipient
from app.repositories.certificate_repository import CertificateRepository
from app.storage.file_storage import FileStorage, file_storage
from app.templates.certificate_template import CertificateTemplate


class CertificateService:
    """Service orchestrating certificate generation, persistence, and retrieval."""

    def __init__(self, db: Session, storage: FileStorage = file_storage):
        self.db = db
        self.storage = storage
        self.repo = CertificateRepository(db)

    def generate_and_store_certificate(self, recipient: Recipient) -> Certificate:
        """
        Renders the PDF certificate for a recipient, saves it to storage,
        and saves the Certificate record in the database.
        """
        cert_id = uuid.uuid4()

        # 1. Generate PDF bytes using predefined template
        pdf_bytes = CertificateTemplate.generate_pdf_bytes(
            certificate_id=cert_id,
            recipient_name=recipient.name,
            event_name=recipient.event_name,
            completion_date=recipient.completion_date,
        )

        # 2. Persist PDF to filesystem
        saved_file_path = self.storage.save_certificate_file(
            job_id=recipient.job_id,
            certificate_id=cert_id,
            file_bytes=pdf_bytes,
        )

        # 3. Create database record
        cert = Certificate(
            id=cert_id,
            recipient_id=recipient.id,
            file_path=saved_file_path,
        )
        self.repo.create(cert)
        return cert

    def get_certificate_file_for_download(
        self,
        certificate_id: uuid.UUID,
    ) -> tuple[Path, str]:
        """
        Retrieves certificate file path and sanitized download filename.
        Raises CertificateNotFoundError if DB record is missing.
        Raises CertificateFileNotFoundError if file is missing on storage.
        """
        cert = self.repo.get_by_id(certificate_id)
        if not cert:
            raise CertificateNotFoundError(str(certificate_id))

        if not self.storage.file_exists(cert.file_path):
            logger.error(
                "Certificate %s found in DB with file_path '%s', but file is missing on disk.",
                certificate_id,
                cert.file_path,
            )
            raise CertificateFileNotFoundError(str(certificate_id))

        resolved_path = self.storage.get_resolved_path(cert.file_path)
        download_filename = f"certificate_{certificate_id}.pdf"
        return resolved_path, download_filename
