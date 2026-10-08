import uuid
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models.recipient import Recipient, RecipientStatus


class RecipientRepository:
    """Repository for database operations on Recipient."""

    def __init__(self, db: Session):
        self.db = db

    def create_all(self, recipients: list[Recipient]) -> list[Recipient]:
        """Bulk inserts recipient records."""
        self.db.add_all(recipients)
        self.db.flush()
        return recipients

    def get_by_id(self, recipient_id: uuid.UUID) -> Recipient | None:
        """Retrieves a single recipient by ID."""
        stmt = (
            select(Recipient)
            .options(selectinload(Recipient.certificate))
            .where(Recipient.id == recipient_id)
        )
        return self.db.scalars(stmt).first()

    def get_all_by_job_id(self, job_id: uuid.UUID) -> list[Recipient]:
        """Retrieves all recipients for a job including certificate relationships."""
        stmt = (
            select(Recipient)
            .options(selectinload(Recipient.certificate))
            .where(Recipient.job_id == job_id)
            .order_by(Recipient.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def get_pending_by_job_id(self, job_id: uuid.UUID) -> list[Recipient]:
        """Retrieves all PENDING recipients for a job."""
        stmt = (
            select(Recipient)
            .where(
                Recipient.job_id == job_id,
                Recipient.status == RecipientStatus.PENDING,
            )
            .order_by(Recipient.created_at)
        )
        return list(self.db.scalars(stmt).all())

    def update_status(
        self,
        recipient_id: uuid.UUID,
        status: RecipientStatus,
        error_message: str | None = None,
    ) -> None:
        """Updates the status and optional error message of a recipient."""
        stmt = (
            update(Recipient)
            .where(Recipient.id == recipient_id)
            .values(status=status, error_message=error_message)
        )
        self.db.execute(stmt)
        self.db.commit()
