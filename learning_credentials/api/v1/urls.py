"""API v1 URLs."""

from django.urls import path

from .views import CredentialEligibilityView, CredentialListView

urlpatterns = [
    # Credential eligibility endpoints
    path('eligibility/<str:learning_context_key>/', CredentialEligibilityView.as_view(), name='credential-eligibility'),
    path(
        'eligibility/<str:learning_context_key>/<int:credential_type_id>/',
        CredentialEligibilityView.as_view(),
        name='credential-generation',
    ),
    # Credential listing endpoints
    path('credentials/', CredentialListView.as_view(), name='credential-list'),
]
