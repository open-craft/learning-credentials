"""URLs for learning_credentials."""

from django.urls import include, path
from django.views.generic import TemplateView

from .api import urls as api_urls

urlpatterns = [
    path('api/learning_credentials/', include(api_urls)),
    path('learning_credentials/verify/', TemplateView.as_view(template_name="learning_credentials/verify.html")),
]
