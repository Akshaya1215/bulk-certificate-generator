import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.certificate import Certificate


class CertificateRepository:
    """Repository for database operations on Certificate."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, certificate: Certificate) -> Certificate:
        """Persists a new Certificate."""
        self.db.add(certificate)
        self.db.flush()
        return certificate

    def get_by_id(self, certificate_id: uuid.UUID) -> Certificate | None:
        """Retrieves a certificate by its UUID."""
        stmt = select(Certificate).where(Certificate.id == certificate_id)
        return self.db.scalars(stmt).first()

    def get_by_recipient_id(self, recipient_id: uuid.UUID) -> Certificate | None:
        """Retrieves a certificate by recipient UUID."""
        stmt = select(Certificate).where(Certificate.recipient_id == recipient_id)
        return self.db.scalars(stmt).first()
