"""Custom exceptions for the learning-credentials app."""


class AssetNotFoundError(Exception):
    """Raised when the asset_slug is not found in the CredentialAsset model."""


class CredentialGenerationError(Exception):
    """Raised when the credential generation Celery task fails."""
