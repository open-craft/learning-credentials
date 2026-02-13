"""API v1 URLs."""

from django.urls import path

from .views import CredentialConfigurationCheckView, CredentialMetadataView

urlpatterns = [
    path(
        'configured/<str:learning_context_key>/',
        CredentialConfigurationCheckView.as_view(),
        name='credential_configuration_check',
    ),
    path('metadata/<uuid:uuid>/', CredentialMetadataView.as_view(), name='credential-metadata'),
]
