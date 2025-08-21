"""API functions for the Learning Credentials app."""

import logging
from typing import TYPE_CHECKING

from .models import Credential, CredentialConfiguration
from .tasks import generate_credential_for_user_task

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from opaque_keys.edx.keys import CourseKey

logger = logging.getLogger(__name__)


def get_eligible_users_by_credential_type(
    course_id: 'CourseKey', user_id: int | None = None
) -> dict[str, list['User']]:
    """
    Retrieve eligible users for each credential type in the given course.

    :param course_id: The key of the course for which to check eligibility.
    :param user_id: Optional. If provided, will check eligibility for the specific user.
    :return: A dictionary with credential type as the key and eligible users as the value.
    """
    credential_configs = CredentialConfiguration.objects.filter(course_id=course_id)

    if not credential_configs:
        return {}

    eligible_users_by_type = {}
    for credential_config in credential_configs:
        user_ids = credential_config.get_eligible_user_ids(user_id)
        filtered_user_ids = credential_config.filter_out_user_ids_with_credentials(user_ids)

        if user_id:
            eligible_users_by_type[credential_config.credential_type.name] = list(set(filtered_user_ids) & {user_id})
        else:
            eligible_users_by_type[credential_config.credential_type.name] = filtered_user_ids

    return eligible_users_by_type


def get_user_credentials_by_type(course_id: 'CourseKey', user_id: int) -> dict[str, dict[str, str]]:
    """
    Retrieve the available credentials for a given user in a course.

    :param course_id: The course ID for which to retrieve credentials.
    :param user_id: The ID of the user for whom credentials are being retrieved.
    :return: A dict where keys are credential types and values are dicts with the download link and status.
    """
    credentials = Credential.objects.filter(user_id=user_id, course_id=course_id)

    return {cred.credential_type: {'download_url': cred.download_url, 'status': cred.status} for cred in credentials}


def generate_credential_for_user(course_id: 'CourseKey', credential_type: str, user_id: int, force: bool = False):
    """
    Generate a credential for a user in a course.

    :param course_id: The course ID for which to generate the credential.
    :param credential_type: The type of credential to generate.
    :param user_id: The ID of the user for whom the credential is being generated.
    :param force: If True, will generate the credential even if the user is not eligible.
    """
    credential_config = CredentialConfiguration.objects.get(course_id=course_id, credential_type__name=credential_type)

    if not credential_config:
        logger.error('No course configuration found for course %s', course_id)
        return

    if not force and not credential_config.get_eligible_user_ids(user_id):
        logger.error('User %s is not eligible for the credential in course %s', user_id, course_id)
        msg = 'User is not eligible for the credential.'
        raise ValueError(msg)

    generate_credential_for_user_task.delay(credential_config.id, user_id)
