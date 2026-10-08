import io
import uuid
from datetime import date
from pypdf import PdfReader
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.certificate import Certificate
from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus
from app.services.certificate_service import CertificateService
from app.services.validation_service import ValidationService
from app.storage.file_storage import FileStorage
from app.templates.certificate_template import CertificateTemplate
from app.workers.tasks import process_bulk_job


def test_validation_explicit_none_fallbacks():
    """FIX 6: Verifies explicit None values produce 'Unknown' rather than the string 'None'."""
    job_id = uuid.uuid4()
    raw = [
        {
            "name": None,
            "email": None,
            "event_name": None,
            "completion_date": None,
        }
    ]

    valid, invalid = ValidationService.partition_recipients(raw, job_id)
    assert len(valid) == 0
    assert len(invalid) == 1

    inv = invalid[0]
    assert inv.status == RecipientStatus.INVALID
    # Verify fallback is 'Unknown' and not 'None'
    assert inv.name == "Unknown"
    assert inv.name != "None"
    assert inv.email == "invalid@format"
    assert inv.email != "None"
    assert inv.event_name == "Unknown"
    assert inv.event_name != "None"
    assert inv.error_message is not None


def test_certificate_text_fitting_edge_cases():
    """FIX 5: Verifies dynamic font sizing prevents overflow for long names and events."""
    test_cases = [
        # Normal
        ("John Doe", "Python 101"),
        # Long name
        ("Dr. Maximillian Alexander von Hohenzollern-Sigmaringen", "Software Architecture"),
        # Long event
        ("Jane Smith", "Advanced High-Throughput Distributed Microservices Architecture & Engineering"),
        # Very long name and event
        ("Prof. Christopher Bartholomew Montgomery-Huntington Jr.", "International Certification in Advanced Distributed Cloud Native Computing"),
    ]

    for name, event in test_cases:
        cert_id = uuid.uuid4()
        pdf_bytes = CertificateTemplate.generate_pdf_bytes(
            certificate_id=cert_id,
            recipient_name=name,
            event_name=event,
            completion_date=date(2026, 10, 7),
        )

        assert pdf_bytes.startswith(b"%PDF-")
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) == 1
        page_text = reader.pages[0].extract_text()
        assert "CERTIFICATE OF COMPLETION" in page_text
        assert name in page_text or name[:20] in page_text


def test_relative_file_path_storage(db_session: Session, test_storage: FileStorage):
    """FIX 4: Verifies certificate file paths are stored as relative paths for portability."""
    job_id = uuid.uuid4()
    job = GenerationJob(id=job_id, status=JobStatus.PROCESSING, total_count=1)
    db_session.add(job)

    rec = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="Portability User",
        email="portability@example.com",
        event_name="Cloud Standards",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PROCESSING,
    )
    db_session.add(rec)
    db_session.commit()

    service = CertificateService(db_session, storage=test_storage)
    cert = service.generate_and_store_certificate(rec)
    db_session.commit()

    # Must be relative path, not absolute
    assert not cert.file_path.startswith("/")
    assert not cert.file_path.startswith("C:")
    assert not cert.file_path.startswith("D:")
    assert f"{job_id}/{cert.id}.pdf" == cert.file_path

    # Retrieval must work seamlessly
    assert test_storage.file_exists(cert.file_path)
    resolved = test_storage.get_resolved_path(cert.file_path)
    assert resolved.is_file()

    # Download service resolves successfully
    path, filename = service.get_certificate_file_for_download(cert.id)
    assert path.is_file()
    assert filename == f"certificate_{cert.id}.pdf"


def test_fatal_job_exception_recovery(db_session: Session, monkeypatch):
    """FIX 3: Verifies fatal unhandled job-level failure marks the job as FAILED and re-raises."""
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED,
        total_count=1,
    )
    db_session.add(job)
    db_session.commit()

    # Monkeypatch to inject a catastrophic error before processing
    from app.repositories import recipient_repository

    def broken_get_pending(*args, **kwargs):
        raise RuntimeError("Catastrophic connection pool drop")

    monkeypatch.setattr(recipient_repository.RecipientRepository, "get_pending_by_job_id", broken_get_pending)

    # Must re-raise fatal exception so Celery knows it failed
    with pytest.raises(RuntimeError, match="Catastrophic connection pool drop"):
        process_bulk_job(str(job_id))

    # Job in database must be persisted as FAILED
    db_session.expire_all()
    updated_job = db_session.get(GenerationJob, job_id)
    assert updated_job.status == JobStatus.FAILED
    assert updated_job.completed_at is not None


def test_database_failure_isolation_and_atomic_counters(
    db_session: Session,
    test_storage: FileStorage,
    monkeypatch,
):
    """FIX 1 & 2: Verifies independent DB sessions per recipient and atomic count sync."""
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED,
        total_count=3,
    )
    db_session.add(job)

    r1 = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="User One",
        email="one@example.com",
        event_name="Resilience",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PENDING,
    )
    r2 = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="User Two (Fails)",
        email="two@example.com",
        event_name="Resilience",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PENDING,
    )
    r3 = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="User Three",
        email="three@example.com",
        event_name="Resilience",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PENDING,
    )
    db_session.add_all([r1, r2, r3])
    db_session.commit()

    # Invalidate User Two during certificate generation
    orig_generate = CertificateTemplate.generate_pdf_bytes

    def selective_failure(certificate_id, recipient_name, event_name, completion_date):
        if "User Two" in recipient_name:
            raise ValueError("Intentional PDF crash for User Two")
        return orig_generate(certificate_id, recipient_name, event_name, completion_date)

    monkeypatch.setattr(CertificateTemplate, "generate_pdf_bytes", selective_failure)

    result = process_bulk_job(str(job_id))

    db_session.expire_all()
    updated_job = db_session.get(GenerationJob, job_id)
    u1 = db_session.get(Recipient, r1.id)
    u2 = db_session.get(Recipient, r2.id)
    u3 = db_session.get(Recipient, r3.id)

    assert u1.status == RecipientStatus.SUCCESS
    assert u2.status == RecipientStatus.FAILED
    assert "Intentional PDF crash" in u2.error_message
    assert u3.status == RecipientStatus.SUCCESS

    # Atomic counts must match exact DB state
    assert updated_job.successful_count == 2
    assert updated_job.failed_count == 1
    assert updated_job.total_count == 3
    assert updated_job.status == JobStatus.COMPLETED_WITH_ERRORS
    assert result["status"] == "COMPLETED_WITH_ERRORS"


def test_health_check_degraded_status_503(client: TestClient, monkeypatch):
    """FIX 8: Verifies /health returns 503 when the database is unavailable."""
    from sqlalchemy.orm import Session

    def broken_execute(self, *args, **kwargs):
        raise ConnectionError("Database unreachable")

    monkeypatch.setattr(Session, "execute", broken_execute)

    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "unhealthy"
