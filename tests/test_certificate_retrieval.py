import io
import uuid
from datetime import date
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.certificate import Certificate
from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus
from app.storage.file_storage import FileStorage


def test_certificate_not_found(client: TestClient):
    random_id = uuid.uuid4()
    response = client.get(f"/api/v1/certificates/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert f"Certificate with ID '{random_id}' not found." in data["detail"]


def test_certificate_file_missing_returns_500(client: TestClient, db_session: Session):
    job_id = uuid.uuid4()
    job = GenerationJob(id=job_id, status=JobStatus.COMPLETED, total_count=1)
    db_session.add(job)

    rec_id = uuid.uuid4()
    recipient = Recipient(
        id=rec_id,
        job_id=job_id,
        name="Missing File User",
        email="missing@example.com",
        event_name="Cloud Architecture",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.SUCCESS,
    )
    db_session.add(recipient)

    cert_id = uuid.uuid4()
    # Point file_path to a non-existent file
    cert = Certificate(
        id=cert_id,
        recipient_id=rec_id,
        file_path="non_existent_folder/missing_file.pdf",
    )
    db_session.add(cert)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{cert_id}")
    assert response.status_code == 500
    data = response.json()
    # Make sure internal path is NOT leaked to user
    assert "non_existent_folder" not in data["detail"]
    assert "missing on server storage" in data["detail"]


def test_certificate_download_successful(
    client: TestClient,
    db_session: Session,
    test_storage: FileStorage,
):
    job_id = uuid.uuid4()
    job = GenerationJob(id=job_id, status=JobStatus.COMPLETED, total_count=1)
    db_session.add(job)

    rec_id = uuid.uuid4()
    recipient = Recipient(
        id=rec_id,
        job_id=job_id,
        name="Successful Recipient",
        email="success@example.com",
        event_name="FastAPI Mastery",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.SUCCESS,
    )
    db_session.add(recipient)

    # Write a real PDF file
    cert_id = uuid.uuid4()
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
    file_path = test_storage.save_certificate_file(
        job_id=job_id,
        certificate_id=cert_id,
        file_bytes=pdf_bytes,
    )

    cert = Certificate(
        id=cert_id,
        recipient_id=rec_id,
        file_path=file_path,
    )
    db_session.add(cert)
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{cert_id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert f"certificate_{cert_id}.pdf" in response.headers.get("content-disposition", "")
    assert response.content.startswith(b"%PDF-")
