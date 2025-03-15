"""Asynchronous Celery tasks."""

from __future__ import annotations

import logging

from learning_credentials.compat import get_celery_app
from learning_credentials.models import ExternalCertificateCourseConfiguration

app = get_celery_app()
log = logging.getLogger(__name__)


@app.task
def generate_certificate_for_user_task(course_config_id: int, user_id: int):
    """
    Celery task for processing a single user's certificate.

    This function retrieves an ExternalCertificateCourse object based on course_id and certificate_type_id,
    retrieves the data using the retrieval_func specified in the associated ExternalCertificateType object,
    and passes this data to the function specified in the generation_func field.

    :param course_config_id: The ID of the ExternalCertificateCourseConfiguration object to process.
    :param user_id: The ID of the user to process the certificate for.
    """
    course_config = ExternalCertificateCourseConfiguration.objects.get(id=course_config_id)
    course_config.generate_certificate_for_user(user_id, generate_certificate_for_user_task.request.id)


@app.task
def generate_certificates_for_course_task(course_config_id: int):
    """
    Celery task for processing a single course's certificates.

    This function retrieves an ExternalCertificateCourse object based on course_id and certificate_type_id,
    retrieves the data using the retrieval_func specified in the associated ExternalCertificateType object,
    and passes this data to the function specified in the generation_func field.

    :param course_config_id: The ID of the ExternalCertificateCourseConfiguration object to process.
    """
    course_config = ExternalCertificateCourseConfiguration.objects.get(id=course_config_id)
    user_ids = course_config.get_eligible_user_ids()
    log.info("The following users are eligible in %s: %s", course_config.course_id, user_ids)
    filtered_user_ids = course_config.filter_out_user_ids_with_certificates(user_ids)
    log.info("The filtered users eligible in %s: %s", course_config.course_id, filtered_user_ids)

    for user_id in filtered_user_ids:
        generate_certificate_for_user_task.delay(course_config_id, user_id)


@app.task
def generate_all_certificates_task():
    """
    Celery task for initiating the processing of certificates for all enabled courses.

    This function fetches all enabled ExternalCertificateCourse objects,
    and initiates a separate Celery task (process_certificate_for_course) for each of them.
    """
    course_config_ids = ExternalCertificateCourseConfiguration.get_enabled_configurations().values_list('id', flat=True)
    for config_id in course_config_ids:
        generate_certificates_for_course_task.delay(config_id)
