import uuid
from datetime import datetime
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus


class JobRepository:
    """Repository for database operations on GenerationJob."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, job: GenerationJob) -> GenerationJob:
        """Persists a new GenerationJob."""
        self.db.add(job)
        self.db.flush()
        return job

    def get_by_id(self, job_id: uuid.UUID) -> GenerationJob | None:
        """Retrieves a job by its UUID."""
        stmt = select(GenerationJob).where(GenerationJob.id == job_id)
        return self.db.scalars(stmt).first()

    def update_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Updates status and timestamps for a job."""
        values = {"status": status}
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at

        stmt = update(GenerationJob).where(GenerationJob.id == job_id).values(**values)
        self.db.execute(stmt)
        self.db.commit()

    def increment_counts(
        self,
        job_id: uuid.UUID,
        successful_increment: int = 0,
        failed_increment: int = 0,
    ) -> None:
        """Safely increments job counts using atomic SQL expressions."""
        values = {}
        if successful_increment > 0:
            values["successful_count"] = GenerationJob.successful_count + successful_increment
        if failed_increment > 0:
            values["failed_count"] = GenerationJob.failed_count + failed_increment

        if values:
            stmt = update(GenerationJob).where(GenerationJob.id == job_id).values(**values)
            self.db.execute(stmt)
            self.db.commit()

    def get_persisted_progress_stats(self, job_id: uuid.UUID) -> dict[str, int]:
        """Calculates exact recipient counts from persisted recipient rows."""
        stmt = (
            select(
                Recipient.status,
                func.count(Recipient.id),
            )
            .where(Recipient.job_id == job_id)
            .group_by(Recipient.status)
        )
        results = self.db.execute(stmt).all()
        status_map = {row[0]: row[1] for row in results}

        return {
            "total": sum(status_map.values()),
            "successful": status_map.get(RecipientStatus.SUCCESS, 0),
            "failed": status_map.get(RecipientStatus.FAILED, 0),
            "invalid": status_map.get(RecipientStatus.INVALID, 0),
            "pending": status_map.get(RecipientStatus.PENDING, 0),
            "processing": status_map.get(RecipientStatus.PROCESSING, 0),
        }
