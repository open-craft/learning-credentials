"""API v1 URLs."""

from django.urls import path

from .views import CredentialConfigurationCheckView

urlpatterns = [
    path(
        'configured/<str:learning_context_key>/',
        CredentialConfigurationCheckView.as_view(),
        name='credential_configuration_check',
    ),
]
