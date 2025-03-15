"""Asynchronous Celery tasks."""

from __future__ import annotations

import logging

from learning_credentials.compat import get_celery_app
from learning_credentials.models import CredentialConfiguration

app = get_celery_app()
log = logging.getLogger(__name__)


@app.task
def generate_credential_for_user_task(course_config_id: int, user_id: int):
    """
    Celery task for processing a single user's credential.

    :param course_config_id: The ID of the CredentialConfiguration object to process.
    :param user_id: The ID of the user to process the credential for.
    """
    course_config = CredentialConfiguration.objects.get(id=course_config_id)
    course_config.generate_credential_for_user(user_id, generate_credential_for_user_task.request.id)


@app.task
def generate_credentials_for_course_task(course_config_id: int):
    """
    Celery task for processing a single course's credentials.

    :param course_config_id: The ID of the CredentialConfiguration object to process.
    """
    course_config = CredentialConfiguration.objects.get(id=course_config_id)
    user_ids = course_config.get_eligible_user_ids()
    log.info("The following users are eligible in %s: %s", course_config.course_id, user_ids)
    filtered_user_ids = course_config.filter_out_user_ids_with_credentials(user_ids)
    log.info("The filtered users eligible in %s: %s", course_config.course_id, filtered_user_ids)

    for user_id in filtered_user_ids:
        generate_credential_for_user_task.delay(course_config_id, user_id)


@app.task
def generate_all_credentials_task():
    """
    Celery task for initiating the processing of credentials for all enabled courses.

    This function fetches all enabled CredentialConfiguration objects,
    and initiates a separate Celery task for each of them.
    """
    course_config_ids = CredentialConfiguration.get_enabled_configurations().values_list('id', flat=True)
    for config_id in course_config_ids:
        generate_credentials_for_course_task.delay(config_id)
