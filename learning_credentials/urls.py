"""URLs for learning_credentials."""

from django.urls import include, path

urlpatterns = [
    path('api/learning_credentials/', include('learning_credentials.api.urls')),
]
