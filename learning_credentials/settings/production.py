"""App-specific settings for production environments."""

from django.conf import Settings


def plugin_settings(settings: Settings):
    """
    Use the database scheduler for Celery Beat.

    The default scheduler is celery.beat.PersistentScheduler, which stores the schedule in a local file. It does not
    work in a multi-server environment, so we use the database scheduler instead.
    """
    settings.CELERYBEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
