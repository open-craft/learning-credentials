"""URLs for learning_credentials."""

from django.urls import include, path

from .api import urls as api_urls

urlpatterns = [
    path('api/learning_credentials/', include(api_urls)),
]
