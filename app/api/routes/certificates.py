import uuid
from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.certificate_service import CertificateService

router = APIRouter(prefix="/api/v1/certificates", tags=["Certificates"])


@router.get(
    "/{certificate_id}",
    summary="Download certificate PDF",
    description="Downloads the generated PDF certificate for a successful recipient.",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Returns the certificate PDF as a downloadable attachment.",
        },
        404: {"description": "Certificate record not found."},
        500: {"description": "Certificate record found but physical file is missing."},
    },
)
def download_certificate(
    certificate_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    cert_service = CertificateService(db)
    file_path, filename = cert_service.get_certificate_file_for_download(certificate_id)

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=filename,
    )
