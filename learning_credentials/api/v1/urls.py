"""API v1 URLs."""

from django.urls import path

from .views import (
    CredentialConfigurationCheckView,
    CredentialEligibilityView,
    CredentialListView,
    CredentialMetadataView,
)

urlpatterns = [
    path(
        'configured/<str:learning_context_key>/',
        CredentialConfigurationCheckView.as_view(),
        name='credential_configuration_check',
    ),
    path('metadata/<uuid:uuid>/', CredentialMetadataView.as_view(), name='credential-metadata'),
    path(
        'eligibility/<str:learning_context_key>/',
        CredentialEligibilityView.as_view(),
        name='credential-eligibility',
    ),
    path(
        'eligibility/<str:learning_context_key>/<int:credential_type_id>/',
        CredentialEligibilityView.as_view(),
        name='credential-generation',
    ),
    path('credentials/', CredentialListView.as_view(), name='credential-list'),
]
