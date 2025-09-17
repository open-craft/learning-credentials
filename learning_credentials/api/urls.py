"""API URLs."""

from django.urls import include, path

urlpatterns = [
    path(
        "v1/",
        include(
            ("learning_credentials.api.v1.urls", "learning_credentials_api_v1"), namespace="learning_credentials_api_v1"
        ),
    ),
]
