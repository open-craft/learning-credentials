"""Custom exceptions for the learning-credentials app."""


class AssetNotFoundError(Exception):
    """Raised when the asset_slug is not found in the ExternalCertificateAsset model."""


class CertificateGenerationError(Exception):
    """Raised when the certificate generation Celery task fails."""
