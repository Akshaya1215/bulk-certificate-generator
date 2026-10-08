class AppException(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class JobNotFoundError(AppException):
    """Raised when a generation job is not found."""

    def __init__(self, job_id: str):
        super().__init__(f"Job with ID '{job_id}' not found.", status_code=404)
        self.job_id = job_id


class CertificateNotFoundError(AppException):
    """Raised when a certificate record is not found."""

    def __init__(self, certificate_id: str):
        super().__init__(f"Certificate with ID '{certificate_id}' not found.", status_code=404)
        self.certificate_id = certificate_id


class CertificateFileNotFoundError(AppException):
    """Raised when a certificate database record exists but the underlying PDF file is missing."""

    def __init__(self, certificate_id: str):
        super().__init__(
            f"Certificate file for ID '{certificate_id}' is missing on server storage.",
            status_code=500,
        )
        self.certificate_id = certificate_id


class BatchSizeExceededError(AppException):
    """Raised when batch size exceeds maximum allowed limit."""

    def __init__(self, current_size: int, max_size: int):
        super().__init__(
            f"Batch size of {current_size} exceeds the maximum limit of {max_size}.",
            status_code=400,
        )


class InvalidBatchError(AppException):
    """Raised when the bulk request batch is invalid."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class StorageError(AppException):
    """Raised when storage operations fail."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500)


class CertificateGenerationError(AppException):
    """Raised when PDF certificate generation fails."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500)
