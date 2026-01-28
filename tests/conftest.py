"""Shared pytest fixtures for learning_credentials tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.test import override_settings
from learning_paths.keys import LearningPathKey
from learning_paths.models import LearningPath, LearningPathEnrollment
from opaque_keys.edx.keys import CourseKey

from learning_credentials.models import CredentialConfiguration, CredentialType
from test_utils.factories import UserFactory

if TYPE_CHECKING:
    from pathlib import Path

    from django.contrib.auth.models import User


# =============================================================================
# User fixtures
# =============================================================================


@pytest.fixture
def user() -> User:
    """Create a regular test user."""
    return UserFactory()


@pytest.fixture
def staff_user() -> User:
    """Create a staff user."""
    return UserFactory(is_staff=True)


@pytest.fixture
def users() -> list[User]:
    """Create a batch of users."""
    return UserFactory.create_batch(6)


# =============================================================================
# Learning context fixtures
# =============================================================================


@pytest.fixture
def course_key() -> CourseKey:
    """Return a course key."""
    return CourseKey.from_string("course-v1:OpenedX+DemoX+DemoCourse")


@pytest.fixture
def learning_path_key() -> LearningPathKey:
    """Return a learning path key."""
    return LearningPathKey.from_string("path-v1:OpenedX+DemoX+DemoPath+Demo")


@pytest.fixture
def learning_path(learning_path_key: LearningPathKey) -> LearningPath:
    """Create an invite-only learning path."""
    return LearningPath.objects.create(key=learning_path_key)


@pytest.fixture
def public_learning_path(learning_path_key: LearningPathKey) -> LearningPath:
    """Create a public (non-invite-only) learning path."""
    return LearningPath.objects.create(key=learning_path_key, invite_only=False)


@pytest.fixture
def learning_path_enrollment(user: User, learning_path: LearningPath) -> LearningPathEnrollment:
    """Enroll user in the learning path."""
    return LearningPathEnrollment.objects.create(learning_path=learning_path, user=user)


@pytest.fixture
def learning_path_with_courses(users: list[User]) -> LearningPath:
    """Create a LearningPath with multiple course steps and enrolled users."""
    learning_path = LearningPath.objects.create(key='path-v1:test+number+run+group')

    for i in range(3):
        learning_path.steps.create(course_key=f"course-v1:TestX+Test101+2023_{i}", order=i)

    # Enroll all users except the last one.
    for i in range(len(users) - 1):
        learning_path.enrolled_users.add(users[i])

    # Mark the second last user's enrollment as inactive.
    learning_path.learningpathenrollment_set.filter(user=users[-2]).update(is_active=False)

    return learning_path


# =============================================================================
# Credential type fixtures
# =============================================================================


@pytest.fixture
def grade_credential_type() -> CredentialType:
    """Create a grade-based credential type."""
    return CredentialType.objects.create(
        name="Certificate of Achievement",
        retrieval_func="learning_credentials.processors.retrieve_subsection_grades",
        generation_func="learning_credentials.generators.generate_pdf_credential",
        custom_options={},
    )


@pytest.fixture
def completion_credential_type() -> CredentialType:
    """Create a completion-based credential type."""
    return CredentialType.objects.create(
        name="Certificate of Completion",
        retrieval_func="learning_credentials.processors.retrieve_completions",
        generation_func="learning_credentials.generators.generate_pdf_credential",
        custom_options={},
    )


# =============================================================================
# Credential configuration fixtures
# =============================================================================


@pytest.fixture
def grade_config(course_key: CourseKey, grade_credential_type: CredentialType) -> CredentialConfiguration:
    """Create grade-based credential configuration."""
    return CredentialConfiguration.objects.create(
        learning_context_key=course_key,
        credential_type=grade_credential_type,
        custom_options={'required_grades': {'Final Exam': 65, 'Overall Grade': 80}},
    )


@pytest.fixture
def completion_config(course_key: CourseKey, completion_credential_type: CredentialType) -> CredentialConfiguration:
    """Create completion-based credential configuration."""
    return CredentialConfiguration.objects.create(
        learning_context_key=course_key,
        credential_type=completion_credential_type,
        custom_options={'required_completion': 100},
    )


# =============================================================================
# Media/Storage fixtures
# =============================================================================


@pytest.fixture
def temp_media(tmp_path: Path):
    """Temporarily override MEDIA_ROOT to a pytest tmp_path for automatic cleanup."""
    temp_dir = tmp_path / "media"
    temp_dir.mkdir()

    with override_settings(MEDIA_ROOT=str(temp_dir)):
        yield str(temp_dir)
