import io
import uuid
from datetime import date
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus
from app.services.certificate_service import CertificateService
from app.storage.file_storage import FileStorage
from app.templates.certificate_template import CertificateTemplate


def test_template_generates_valid_pdf():
    cert_id = uuid.uuid4()
    pdf_bytes = CertificateTemplate.generate_pdf_bytes(
        certificate_id=cert_id,
        recipient_name="John Doe",
        event_name="Advanced Python Engineering",
        completion_date=date(2026, 10, 7),
    )

    # 1. Check header magic bytes
    assert pdf_bytes.startswith(b"%PDF-")

    # 2. Check readability with pypdf
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1

    page = reader.pages[0]
    # Landscape A4 width is greater than height
    assert page.mediabox.width > page.mediabox.height


def test_certificate_service_generate_and_store(db_session: Session, test_storage: FileStorage):
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.PROCESSING,
        total_count=1,
    )
    db_session.add(job)

    recipient = Recipient(
        id=uuid.uuid4(),
        job_id=job_id,
        name="Jane Developer",
        email="jane@example.com",
        event_name="Clean Architecture in Python",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.PROCESSING,
    )
    db_session.add(recipient)
    db_session.commit()

    service = CertificateService(db_session, storage=test_storage)
    cert = service.generate_and_store_certificate(recipient)
    db_session.commit()

    # Verify certificate DB record
    assert cert.id is not None
    assert cert.recipient_id == recipient.id
    assert cert.file_path is not None

    # Verify physical file existence
    assert test_storage.file_exists(cert.file_path)
    file_path = test_storage.get_resolved_path(cert.file_path)
    assert file_path.exists()
    assert file_path.stat().st_size > 0

    # Verify physical file is a valid PDF
    with open(file_path, "rb") as f:
        reader = PdfReader(f)
        assert len(reader.pages) == 1
