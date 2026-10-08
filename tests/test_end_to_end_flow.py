from datetime import date
import io
import uuid
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.job import GenerationJob, JobStatus
from app.models.recipient import Recipient, RecipientStatus
from app.models.certificate import Certificate


def test_full_bulk_generation_lifecycle(client: TestClient):
    """
    Tests end-to-end flow:
    1. POST /api/v1/jobs with a bulk payload (mixed valid and invalid)
    2. Celery executes in background (eager mode in test)
    3. GET /api/v1/jobs/{job_id} tracks progress and verifies COMPLETED_WITH_ERRORS
    4. GET /api/v1/jobs/{job_id}/results returns both recipients
    5. GET /api/v1/certificates/{cert_id} downloads the actual PDF and validates PDF structure
    """
    payload = {
        "recipients": [
            {
                "name": "Sarah Connor",
                "email": "sarah@resistance.org",
                "event_name": "Cybernetics 101",
                "completion_date": "2026-10-07",
            },
            {
                "name": "Kyle Reese",
                "email": "kyle@resistance.org",
                "event_name": "Cybernetics 101",
                "completion_date": "2026-10-07",
            },
            {
                "name": "Invalid Member",
                "email": "bad_email_format",
                "event_name": "Cybernetics 101",
                "completion_date": "2026-10-07",
            },
        ]
    }

    # 1. Post job
    create_res = client.post("/api/v1/jobs", json=payload)
    assert create_res.status_code == 202
    job_info = create_res.json()
    job_id = job_info["job_id"]
    assert job_info["total"] == 3
    assert job_info["valid"] == 2
    assert job_info["invalid"] == 1

    # 2. Check job status
    status_res = client.get(f"/api/v1/jobs/{job_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["total"] == 3
    assert status_data["successful"] == 2
    assert status_data["failed"] == 0
    assert status_data["invalid"] == 1
    assert status_data["pending"] == 0
    assert status_data["progress_percentage"] == 100.0
    assert status_data["status"] == "COMPLETED_WITH_ERRORS"
    assert status_data["started_at"] is not None
    assert status_data["completed_at"] is not None

    # 3. Check job results
    results_res = client.get(f"/api/v1/jobs/{job_id}/results")
    assert results_res.status_code == 200
    results_data = results_res.json()
    assert len(results_data["results"]) == 3

    # Check Sarah
    sarah = next(r for r in results_data["results"] if r["name"] == "Sarah Connor")
    assert sarah["status"] == "SUCCESS"
    assert sarah["certificate_id"] is not None
    assert sarah["download_url"] == f"/api/v1/certificates/{sarah['certificate_id']}"

    # Check Kyle
    kyle = next(r for r in results_data["results"] if r["name"] == "Kyle Reese")
    assert kyle["status"] == "SUCCESS"
    assert kyle["certificate_id"] is not None

    # Check Invalid Member
    invalid_mem = next(r for r in results_data["results"] if r["name"] == "Invalid Member")
    assert invalid_mem["status"] == "INVALID"
    assert invalid_mem["certificate_id"] is None
    assert invalid_mem["download_url"] is None
    assert "email" in invalid_mem["error"].lower()

    # 4. Download Sarah's certificate
    cert_res = client.get(f"/api/v1/certificates/{sarah['certificate_id']}")
    assert cert_res.status_code == 200
    assert cert_res.headers["content-type"] == "application/pdf"
    assert f"certificate_{sarah['certificate_id']}.pdf" in cert_res.headers.get("content-disposition", "")

    # 5. Verify PDF content
    pdf_reader = PdfReader(io.BytesIO(cert_res.content))
    assert len(pdf_reader.pages) == 1
    text = pdf_reader.pages[0].extract_text()
    assert "CERTIFICATE OF COMPLETION" in text
    assert "Sarah Connor" in text
    assert "Cybernetics 101" in text


def test_database_relationships_and_cascades(db_session: Session):
    """Verifies SQLAlchemy foreign key cascades and relationships."""
    job_id = uuid.uuid4()
    job = GenerationJob(id=job_id, status=JobStatus.COMPLETED, total_count=1, successful_count=1)
    db_session.add(job)

    rec_id = uuid.uuid4()
    recipient = Recipient(
        id=rec_id,
        job_id=job_id,
        name="Cascade Test",
        email="cascade@example.com",
        event_name="DB Cascades",
        completion_date=date(2026, 10, 7),
        status=RecipientStatus.SUCCESS,
    )
    db_session.add(recipient)

    cert_id = uuid.uuid4()
    cert = Certificate(
        id=cert_id,
        recipient_id=rec_id,
        file_path="dummy/path.pdf",
    )
    db_session.add(cert)
    db_session.commit()

    # Check relationship traversal
    queried_job = db_session.get(GenerationJob, job_id)
    assert len(queried_job.recipients) == 1
    assert queried_job.recipients[0].certificate.id == cert_id

    # Test delete cascade: deleting job deletes recipients and certificates
    db_session.delete(queried_job)
    db_session.commit()

    assert db_session.get(Recipient, rec_id) is None
    assert db_session.get(Certificate, cert_id) is None
