"""App-specific settings for all environments."""

from django.conf import Settings


def plugin_settings(settings: Settings):
    """Add `django_celery_beat` to `INSTALLED_APPS`."""
    if 'django_celery_beat' not in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS += ('django_celery_beat',)
    # Temporary app to handle migrations.
    if 'openedx_certificates' not in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS += ('openedx_certificates',)
