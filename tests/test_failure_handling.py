import uuid
from datetime import date
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus
from app.services.certificate_service import CertificateService
from app.storage.file_storage import FileStorage
from app.templates.certificate_template import CertificateTemplate
from app.workers.tasks import process_bulk_job


def test_isolated_failure_handling_a_success_b_failed_c_success(
    db_session: Session,
    test_storage: FileStorage,
    monkeypatch,
):
    """
    VERY IMPORTANT TEST:
    Proves:
    Recipient A -> success
    Recipient B -> failure (simulated generator exception)
    Recipient C -> success

    Verifies:
    A = SUCCESS
    B = FAILED
    C = SUCCESS
    Final Job Status = COMPLETED_WITH_ERRORS
    """
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED,
        total_count=3,
        successful_count=0,
        failed_count=0,
    )
    db_session.add(job)

    rec_a = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="Recipient A",
        email="a@example.com",
        event_name="Resilience in Python",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PENDING,
    )
    rec_b = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="Recipient B",
        email="b@example.com",
        event_name="Resilience in Python",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PENDING,
    )
    rec_c = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="Recipient C",
        email="c@example.com",
        event_name="Resilience in Python",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PENDING,
    )
    db_session.add_all([rec_a, rec_b, rec_c])
    db_session.commit()

    # Monkeypatch CertificateTemplate.generate_pdf_bytes to intentionally fail ONLY for Recipient B
    original_generate = CertificateTemplate.generate_pdf_bytes

    def selective_generator(certificate_id, recipient_name, event_name, completion_date):
        if recipient_name == "Recipient B":
            raise RuntimeError("Injected generation exception for Recipient B")
        return original_generate(certificate_id, recipient_name, event_name, completion_date)

    monkeypatch.setattr(CertificateTemplate, "generate_pdf_bytes", selective_generator)

    # Execute background processing
    result = process_bulk_job(str(job_id))

    # Refresh entities from db
    db_session.expire_all()
    job_updated = db_session.get(GenerationJob, job_id)
    recipient_a = db_session.get(Recipient, rec_a.id)
    recipient_b = db_session.get(Recipient, rec_b.id)
    recipient_c = db_session.get(Recipient, rec_c.id)

    # 1. Assert individual statuses
    assert recipient_a.status == RecipientStatus.SUCCESS
    assert recipient_a.error_message is None
    assert recipient_a.certificate is not None
    assert test_storage.file_exists(recipient_a.certificate.file_path)

    # Verify Recipient A certificate is a valid PDF
    path_a = test_storage.get_resolved_path(recipient_a.certificate.file_path)
    with open(path_a, "rb") as f:
        reader = PdfReader(f)
        assert len(reader.pages) == 1

    assert recipient_b.status == RecipientStatus.FAILED
    assert recipient_b.certificate is None
    assert "Injected generation exception for Recipient B" in recipient_b.error_message

    assert recipient_c.status == RecipientStatus.SUCCESS
    assert recipient_c.error_message is None
    assert recipient_c.certificate is not None
    assert test_storage.file_exists(recipient_c.certificate.file_path)

    # Verify Recipient C certificate is a valid PDF
    path_c = test_storage.get_resolved_path(recipient_c.certificate.file_path)
    with open(path_c, "rb") as f:
        reader = PdfReader(f)
        assert len(reader.pages) == 1

    # 2. Assert counts
    assert job_updated.successful_count == 2
    assert job_updated.failed_count == 1
    assert job_updated.total_count == 3

    # 3. Assert final job status
    assert job_updated.status == JobStatus.COMPLETED_WITH_ERRORS
    assert result["status"] == "COMPLETED_WITH_ERRORS"
