"""Tests for the Learning Credentials API views."""

from typing import TYPE_CHECKING, Union
from unittest.mock import Mock, patch

import pytest
from django.urls import reverse
from learning_paths.keys import LearningPathKey
from learning_paths.models import LearningPath, LearningPathEnrollment, LearningPathStep
from opaque_keys.edx.keys import CourseKey
from rest_framework import status
from rest_framework.test import APIClient

from learning_credentials.models import CredentialConfiguration, CredentialType
from test_utils.factories import UserFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from opaque_keys.edx.keys import LearningContextKey
    from requests import Response


@pytest.fixture
def user() -> UserFactory:
    """Return a test user."""
    return UserFactory()


@pytest.fixture
def staff_user() -> UserFactory:
    """Return a staff user."""
    return UserFactory(is_staff=True)


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
def learning_path_enrollment(user: "User", learning_path: LearningPath) -> LearningPathEnrollment:
    """Enroll user in the learning path."""
    return LearningPathEnrollment.objects.create(learning_path=learning_path, user=user)


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


def _get_api_client(user: Union["User", None]) -> APIClient:
    """Return API client for the given user."""
    client = APIClient()
    if user:
        client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestCredentialConfigurationCheckViewPermissions:
    """Test permission requirements for credential configuration check endpoint."""

    def _make_request(self, user: Union["User", None], learning_context_key: "LearningContextKey") -> "Response":
        """Helper to make GET request to the endpoint."""
        client = _get_api_client(user)
        url = reverse(
            'learning_credentials_api_v1:credential_configuration_check',
            kwargs={'learning_context_key': str(learning_context_key)},
        )
        return client.get(url)

    def test_unauthenticated_user_gets_403(self, course_key: CourseKey):
        """Test that unauthenticated user gets 403."""
        response = self._make_request(None, course_key)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_enrolled_user_can_access_course_check(
        self, mock_course_enrollments: Mock, user: "User", course_key: CourseKey
    ):
        """Test that enrolled user can access course configuration check."""
        mock_course_enrollments.return_value = [user]
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}
        mock_course_enrollments.assert_called_once_with(course_key, user.id)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments', return_value=[])
    def test_non_enrolled_user_denied_course_access(
        self, mock_course_enrollments: Mock, user: "User", course_key: CourseKey
    ):
        """Test that non-enrolled user is denied course access."""
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Course not found or user does not have access' in str(response.data)

    def test_enrolled_user_can_access_learning_path_check(
        self, user: "User", learning_path_enrollment: LearningPathEnrollment
    ):
        """Test that enrolled user can access learning path configuration check."""
        response = self._make_request(user, learning_path_enrollment.learning_path.key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    def test_non_enrolled_user_denied_learning_path_access(self, user: "User", learning_path: LearningPath):
        """Test that non-enrolled user is denied learning path access."""
        response = self._make_request(user, learning_path.key)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Learning path not found or user does not have access' in str(response.data)

    def test_invalid_learning_context_key_returns_400(self, user: "User"):
        """Test that invalid learning context key returns 400."""
        response = self._make_request(user, "invalid-key")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Invalid learning context key' in str(response.data)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_staff_can_view_any_context_check(
        self, mock_course_enrollments: Mock, staff_user: "User", course_key: CourseKey
    ):
        """Test that staff can view configuration check for any context without enrollment check."""
        response = self._make_request(staff_user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}
        # Staff users bypass enrollment checks.
        mock_course_enrollments.assert_not_called()

    def test_user_can_access_public_learning_path(self, user: "User", public_learning_path: LearningPath):
        """Test that any user can access a public (non-invite-only) learning path."""
        response = self._make_request(user, public_learning_path.key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    def test_user_cannot_access_invite_only_learning_path_without_enrollment(
        self, user: "User", learning_path: LearningPath
    ):
        """Test that user cannot access invite-only learning path without enrollment."""
        response = self._make_request(user, learning_path.key)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Learning path not found or user does not have access' in str(response.data)

    def test_enrolled_user_can_access_invite_only_learning_path(self, learning_path_enrollment: LearningPathEnrollment):
        """Test that enrolled user can access invite-only learning path."""
        response = self._make_request(learning_path_enrollment.user, learning_path_enrollment.learning_path.key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments', return_value=[])
    def test_user_can_access_course_via_public_learning_path(
        self, mock_course_enrollments: Mock, user: "User", course_key: CourseKey, public_learning_path: LearningPath
    ):
        """Test that user can access course through membership in a public learning path."""
        LearningPathStep.objects.create(course_key=course_key, learning_path=public_learning_path)
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments', return_value=[])
    def test_user_can_access_course_via_enrolled_learning_path(
        self, mock_course_enrollments: Mock, course_key: CourseKey, learning_path_enrollment: LearningPathEnrollment
    ):
        """Test that user can access course through enrollment in learning path containing that course."""
        LearningPathStep.objects.create(course_key=course_key, learning_path=learning_path_enrollment.learning_path)
        response = self._make_request(learning_path_enrollment.user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}


@pytest.mark.django_db
class TestCredentialConfigurationCheckView:
    """Test the CredentialConfigurationCheckView functionality."""

    def _make_request(self, user: Union["User", None], learning_context_key: "LearningContextKey") -> "Response":
        """Helper to make GET request to the endpoint."""
        client = _get_api_client(user)
        url = reverse(
            'learning_credentials_api_v1:credential_configuration_check',
            kwargs={'learning_context_key': str(learning_context_key)},
        )
        return client.get(url)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_no_credentials_configured(self, mock_course_enrollments: Mock, user: "User", course_key: CourseKey):
        """Test response when no credentials are configured for a learning context."""
        mock_course_enrollments.return_value = [user]
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_single_credential_configured(
        self, mock_course_enrollments: Mock, user: "User", course_key: CourseKey, grade_config: CredentialConfiguration
    ):
        """Test response when one credential is configured for a learning context."""
        mock_course_enrollments.return_value = [user]
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': True, 'credential_count': 1}

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_multiple_credentials_configured(
        self,
        mock_course_enrollments: Mock,
        user: "User",
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
        completion_config: CredentialConfiguration,
    ):
        """Test response when multiple credentials are configured for a learning context."""
        mock_course_enrollments.return_value = [user]
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': True, 'credential_count': 2}

    def test_learning_path_credentials_configured(
        self, completion_credential_type: CredentialType, learning_path_enrollment: LearningPathEnrollment
    ):
        """Test response for learning path context with configured credentials."""
        CredentialConfiguration.objects.create(
            learning_context_key=learning_path_enrollment.learning_path.key, credential_type=completion_credential_type
        )
        response = self._make_request(learning_path_enrollment.user, learning_path_enrollment.learning_path.key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': True, 'credential_count': 1}

    def test_staff_can_check_any_context(
        self, staff_user: "User", course_key: CourseKey, grade_config: CredentialConfiguration
    ):
        """Test that staff can check configuration for any context without enrollment."""
        response = self._make_request(staff_user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': True, 'credential_count': 1}
