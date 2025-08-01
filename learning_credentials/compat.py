"""
Proxies and compatibility code for edx-platform features.

This module moderates access to all edx-platform features allowing for cross-version compatibility code.
It also simplifies running tests outside edx-platform's environment by stubbing these functions in unit tests.
"""

# ruff: noqa: PLC0415

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING

import pytz
from celery import Celery
from django.conf import settings
from learning_paths.models import LearningPath

if TYPE_CHECKING:  # pragma: no cover
    from django.contrib.auth.models import User
    from learning_paths.keys import LearningPathKey
    from opaque_keys.edx.keys import CourseKey, LearningContextKey


def get_celery_app() -> Celery:
    """Get Celery app to reuse configuration and queues."""
    if getattr(settings, "TESTING", False):
        # We can ignore this in the testing environment.
        return Celery(task_always_eager=True)

    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from lms import CELERY_APP

    return CELERY_APP  # pragma: no cover


def get_default_storage_url() -> str:
    """Get the default storage URL from Open edX."""
    return f"{settings.LMS_ROOT_URL}{settings.MEDIA_URL}"


def get_course_grading_policy(course_id: CourseKey) -> dict:
    """Get the course grading policy from Open edX."""
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from xmodule.modulestore.django import modulestore

    return modulestore().get_course(course_id).grading_policy["GRADER"]


def _get_course_name(course_id: CourseKey) -> str:
    """Get the course name from Open edX."""
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from openedx.core.djangoapps.content.learning_sequences.api import get_course_outline

    course_outline = get_course_outline(course_id)
    return (course_outline and course_outline.title) or str(course_id)


def _get_learning_path_name(learning_path_key: LearningPathKey) -> str:
    """Get the Learning Path name from the plugin."""
    try:
        return LearningPath.objects.get(key=learning_path_key).display_name
    except LearningPath.DoesNotExist:
        return str(learning_path_key)


def get_learning_context_name(learning_context_key: LearningContextKey) -> str:
    """Get the learning context (course or Learning Path) name."""
    if learning_context_key.is_course:
        return _get_course_name(learning_context_key)
    return _get_learning_path_name(learning_context_key)


def get_course_enrollments(course_id: CourseKey) -> list[User]:
    """Get the course enrollments from Open edX."""
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from common.djangoapps.student.models import CourseEnrollment

    enrollments = CourseEnrollment.objects.filter(course_id=course_id, is_active=True).select_related('user')
    return [enrollment.user for enrollment in enrollments]


@contextmanager
def prefetch_course_grades(course_id: CourseKey, users: list[User]):
    """
    Prefetch the course grades from Open edX.

    This optimizes retrieving grades for multiple users.
    """
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from lms.djangoapps.grades.api import clear_prefetched_course_grades, prefetch_course_and_subsection_grades

    prefetch_course_and_subsection_grades(course_id, users)
    try:
        yield
    finally:
        # This uses `clear_prefetched_course_grades` instead of `clear_prefetched_course_and_subsection_grades` because
        # these function names were accidentally swapped in the Open edX codebase.
        # Ref: https://github.com/openedx/edx-platform/blob/1fe67d3f6b40233791d4599bae28df8c0ac91c4d/lms/djangoapps/grades/models_api.py#L30-L36
        clear_prefetched_course_grades(course_id)


def get_course_grade(user: User, course_id: CourseKey):  # noqa: ANN201
    """Get the `CourseGrade` instance from Open edX."""
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from lms.djangoapps.grades.api import CourseGradeFactory

    return CourseGradeFactory().read(user, course_key=course_id)


def get_localized_credential_date() -> str:
    """Get the localized date from Open edX."""
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from common.djangoapps.util.date_utils import strftime_localized

    date = datetime.now(pytz.timezone(settings.TIME_ZONE))
    return strftime_localized(date, settings.CERTIFICATE_DATE_FORMAT)
