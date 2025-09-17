"""learning_credentials Django application initialization."""

from __future__ import annotations

from typing import ClassVar

from django.apps import AppConfig
from edx_django_utils.plugins.constants import PluginSettings, PluginURLs


class LearningCredentialsConfig(AppConfig):
    """Configuration for the learning_credentials Django application."""

    name = 'learning_credentials'
    verbose_name = 'Learning Credentials'

    # https://edx.readthedocs.io/projects/edx-django-utils/en/latest/plugins/how_tos/how_to_create_a_plugin_app.html
    plugin_app: ClassVar[dict[str, dict[str, dict]]] = {
        PluginURLs.CONFIG: {
            'lms.djangoapp': {
                PluginURLs.NAMESPACE: name,
                PluginURLs.APP_NAME: name,
            }
        },
        PluginSettings.CONFIG: {
            'lms.djangoapp': {
                'common': {PluginSettings.RELATIVE_PATH: 'settings.common'},
                'production': {PluginSettings.RELATIVE_PATH: 'settings.production'},
            },
        },
    }
