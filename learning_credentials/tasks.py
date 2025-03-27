"""Asynchronous Celery tasks."""

from __future__ import annotations

import logging

from learning_credentials.compat import get_celery_app
from learning_credentials.models import CredentialConfiguration

app = get_celery_app()
log = logging.getLogger(__name__)


@app.task
def generate_credential_for_user_task(config_id: int, user_id: int):
    """
    Celery task for processing a single user's credential.

    :param config_id: The ID of the CredentialConfiguration object to process.
    :param user_id: The ID of the user to process the credential for.
    """
    config = CredentialConfiguration.objects.get(id=config_id)
    config.generate_credential_for_user(user_id, generate_credential_for_user_task.request.id)


@app.task
def generate_credentials_for_config_task(config_id: int):
    """
    Celery task for processing a single context's credentials.

    :param config_id: The ID of the CredentialConfiguration object to process.
    """
    config = CredentialConfiguration.objects.get(id=config_id)
    user_ids = config.get_eligible_user_ids()
    log.info("The following users are eligible in %s: %s", config.learning_context_key, user_ids)
    filtered_user_ids = config.filter_out_user_ids_with_credentials(user_ids)
    log.info("The filtered users eligible in %s: %s", config.learning_context_key, filtered_user_ids)

    for user_id in filtered_user_ids:
        generate_credential_for_user_task.delay(config_id, user_id)


@app.task
def generate_all_credentials_task():
    """
    Celery task for initiating the processing of credentials for all enabled contexts.

    This function fetches all enabled CredentialConfiguration objects,
    and initiates a separate Celery task for each of them.
    """
    config_ids = CredentialConfiguration.get_enabled_configurations().values_list('id', flat=True)
    for config_id in config_ids:
        generate_credentials_for_config_task.delay(config_id)
