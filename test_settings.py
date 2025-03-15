"""
These settings are here to use during tests, because django requires them.

In a real-world use case, apps in this project are installed into other
Django applications, so these settings will not be used.
"""

from pathlib import Path


def root(path: Path) -> Path:
    """Get the absolute path of the given path relative to the project root."""
    return Path(__file__).parent.resolve() / path


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'default.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    },
}

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.sessions',
    'completion',
    'completion_aggregator',
    'django_celery_beat',
    'openedx_certificates',
    'learning_credentials',
    'django_object_actions',
    'event_routing_backends',
)

MIGRATION_MODULES = {
    # the module 'third_party_app' is the one you want to skip
    'completion_aggregator': None,
}

LOCALE_PATHS = [
    root(Path('learning_credentials/conf/locale')),
]

ROOT_URLCONF = 'learning_credentials.urls'

SECRET_KEY = 'insecure-secret-key'  # noqa: S105

MIDDLEWARE = (
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': False,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',  # this is required for admin
                'django.contrib.messages.context_processors.messages',  # this is required for admin
                'django.template.context_processors.request',  # this is required for admin
            ],
        },
    },
]

TESTING = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'loggers': {
        'event_routing_backends': {
            'level': 'CRITICAL',
            'propagate': True,
        },
    },
}
