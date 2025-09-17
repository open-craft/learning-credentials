"""API URLs."""

from django.urls import include, path

from .v1 import urls as v1_urls

urlpatterns = [
    path("v1/", include((v1_urls, "learning_credentials_api_v1"), namespace="learning_credentials_api_v1")),
]
