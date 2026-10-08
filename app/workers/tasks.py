import uuid
from datetime import datetime, timezone
from celery.utils.log import get_task_logger

from app.core.database import get_db_session
from app.models.job import JobStatus
from app.models.recipient import RecipientStatus
from app.repositories.job_repository import JobRepository
from app.repositories.recipient_repository import RecipientRepository
from app.services.certificate_service import CertificateService
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="app.workers.tasks.process_bulk_job", bind=True)
def process_bulk_job(self, job_id_str: str) -> dict[str, str | int]:
    """
    Background Celery task that processes all pending recipients for a bulk job.
    Uses independent database sessions per recipient for complete failure isolation,
    atomic counter increments, and top-level fatal exception recovery.
    """
    job_uuid = uuid.UUID(job_id_str)
    logger.info("Starting processing for bulk job %s", job_uuid)

    try:
        # 1. Transition job status to PROCESSING and retrieve pending recipient IDs
        with get_db_session() as init_db:
            job_repo = JobRepository(init_db)
            recipient_repo = RecipientRepository(init_db)

            job = job_repo.get_by_id(job_uuid)
            if not job:
                logger.error("Job %s not found in database. Aborting worker task.", job_uuid)
                return {"status": "NOT_FOUND", "job_id": job_id_str}

            job_repo.update_status(
                job_id=job_uuid,
                status=JobStatus.PROCESSING,
                started_at=datetime.now(timezone.utc),
            )

            pending_recipients = recipient_repo.get_pending_by_job_id(job_uuid)
            pending_ids = [r.id for r in pending_recipients]
            logger.info(
                "Found %d pending recipients to generate certificates for job %s",
                len(pending_ids),
                job_uuid,
            )

        # 2. Process each recipient ID with an independent database session
        for recipient_id in pending_ids:
            try:
                with get_db_session() as rec_db:
                    rec_repo = RecipientRepository(rec_db)
                    job_repo = JobRepository(rec_db)
                    cert_service = CertificateService(rec_db)

                    recipient = rec_repo.get_by_id(recipient_id)
                    if not recipient:
                        logger.warning("Recipient %s not found, skipping.", recipient_id)
                        continue

                    logger.info("Processing recipient %s (%s) for job %s", recipient.id, recipient.name, job_uuid)

                    # Mark recipient as PROCESSING
                    recipient.status = RecipientStatus.PROCESSING
                    rec_db.commit()

                    # Generate and persist certificate PDF & database record
                    cert = cert_service.generate_and_store_certificate(recipient)

                    # Mark recipient as SUCCESS
                    recipient.status = RecipientStatus.SUCCESS
                    recipient.error_message = None
                    rec_db.commit()

                    # Atomic SQL counter increment
                    job_repo.increment_counts(job_uuid, successful_increment=1)
                    logger.info(
                        "Successfully generated certificate %s for recipient %s",
                        cert.id,
                        recipient.id,
                    )

            except Exception as exc:
                logger.exception(
                    "Failed to process recipient %s in job %s: %s",
                    recipient_id,
                    job_uuid,
                    exc,
                )
                # Record failure in a fresh, independent database session
                try:
                    with get_db_session() as fail_db:
                        fail_rec_repo = RecipientRepository(fail_db)
                        fail_job_repo = JobRepository(fail_db)

                        r = fail_rec_repo.get_by_id(recipient_id)
                        if r:
                            r.status = RecipientStatus.FAILED
                            r.error_message = f"Certificate generation failed: {exc}"
                            fail_db.commit()

                        # Atomic SQL counter increment
                        fail_job_repo.increment_counts(job_uuid, failed_increment=1)
                except Exception as record_err:
                    logger.critical(
                        "Critical error while recording failure for recipient %s: %s",
                        recipient_id,
                        record_err,
                        exc_info=True,
                    )
                # Continue loop for remaining recipients!

        # 3. Finalize job status based on persisted database counts and sync counters
        with get_db_session() as final_db:
            job_repo = JobRepository(final_db)
            stats = job_repo.get_persisted_progress_stats(job_uuid)

            total = stats["total"]
            successful = stats["successful"]
            failed = stats["failed"]
            invalid = stats["invalid"]

            if failed > 0 or invalid > 0:
                final_status = JobStatus.COMPLETED_WITH_ERRORS
            elif successful == total and total > 0:
                final_status = JobStatus.COMPLETED
            elif total == 0:
                final_status = JobStatus.COMPLETED
            else:
                final_status = JobStatus.COMPLETED_WITH_ERRORS

            # Synchronize job columns with exact database row counts
            job = job_repo.get_by_id(job_uuid)
            if job:
                job.status = final_status
                job.successful_count = successful
                job.failed_count = failed
                job.completed_at = datetime.now(timezone.utc)
                final_db.commit()

            logger.info(
                "Bulk job %s completed with status '%s'. Success=%d, Failed=%d, Invalid=%d, Total=%d",
                job_uuid,
                final_status.value,
                successful,
                failed,
                invalid,
                total,
            )

        return {
            "status": final_status.value,
            "job_id": job_id_str,
            "successful": successful,
            "failed": failed,
            "invalid": invalid,
            "total": total,
        }

    except Exception as fatal_exc:
        logger.critical(
            "Fatal error processing bulk job %s: %s",
            job_uuid,
            fatal_exc,
            exc_info=True,
        )
        try:
            with get_db_session() as error_db:
                JobRepository(error_db).update_status(
                    job_id=job_uuid,
                    status=JobStatus.FAILED,
                    completed_at=datetime.now(timezone.utc),
                )
        except Exception:
            logger.exception("Unable to persist FAILED status for job %s", job_uuid)
        raise
