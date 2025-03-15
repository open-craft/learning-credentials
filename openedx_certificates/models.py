"""
Proxy models for backward compatibility with the old app structure.

These will redirect to the new models in learning_credentials.
"""

from learning_credentials.models import Credential as LearningCredential
from learning_credentials.models import CredentialAsset as LearningCredentialAsset
from learning_credentials.models import CredentialConfiguration as LearningCredentialConfiguration
from learning_credentials.models import CredentialType as LearningCredentialType


class ExternalCertificate(LearningCredential):
    """Proxy model for backward compatibility."""

    class Meta:  # noqa: D106
        proxy = True


class ExternalCertificateAsset(LearningCredentialAsset):
    """Proxy model for backward compatibility."""

    class Meta:  # noqa: D106
        proxy = True


class ExternalCertificateType(LearningCredentialType):
    """Proxy model for backward compatibility."""

    class Meta:  # noqa: D106
        proxy = True


class ExternalCertificateCourseConfiguration(LearningCredentialConfiguration):
    """Proxy model for backward compatibility."""

    class Meta:  # noqa: D106
        proxy = True
