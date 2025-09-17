"""Tests for the Learning Credentials API views."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from django.urls import reverse
from learning_paths.keys import LearningPathKey
from opaque_keys.edx.keys import CourseKey
from rest_framework import status
from rest_framework.test import APIClient

from learning_credentials.models import Credential, CredentialConfiguration, CredentialType
from test_utils.factories import UserFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import User


# Base fixtures
@pytest.fixture
def api_client() -> APIClient:
    """Return API client."""
    return APIClient()


@pytest.fixture
def user() -> User:
    """Return a test user."""
    return UserFactory()  # ty: ignore[invalid-return-type]


@pytest.fixture
def staff_user() -> User:
    """Return a staff user."""
    return UserFactory(is_staff=True)  # ty: ignore[invalid-return-type]


@pytest.fixture
def other_user() -> User:
    """Return another test user."""
    return UserFactory()  # ty: ignore[invalid-return-type]


@pytest.fixture
def authenticated_client(user: User) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def staff_client(staff_user: User) -> APIClient:
    """Return authenticated staff API client."""
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


@pytest.fixture
def course_key() -> CourseKey:
    """Return a course key."""
    return CourseKey.from_string("course-v1:OpenedX+DemoX+DemoCourse")


@pytest.fixture
def learning_path_key() -> LearningPathKey:
    """Return a learning path key."""
    return LearningPathKey.from_string("path-v1:OpenedX+DemoX+DemoPath+Demo")


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


@pytest.fixture
def credential_instance(user: User, course_key: CourseKey) -> Credential:
    """Create a credential instance."""
    return Credential.objects.create(
        user_id=user.id,
        user_full_name=user.get_full_name() or user.username,
        learning_context_key=course_key,
        credential_type="Certificate of Achievement",
        status=Credential.Status.AVAILABLE,
        download_url="https://example.com/credential.pdf",
    )


# Test classes
@pytest.mark.django_db
class TestCredentialConfigurationCheckViewAuthentication:
    """Test authentication requirements for credential configuration check endpoint."""

    def test_unauthenticated_user_gets_403(self, api_client: APIClient, course_key: CourseKey):
        """Test that unauthenticated user gets 403."""
        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCredentialConfigurationCheckViewPermissions:
    """Test permission requirements for credential configuration check endpoint."""

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_enrolled_user_can_access_course_check(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, user: User, course_key: CourseKey
    ):
        """Test that enrolled user can access course configuration check."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['has_credentials'] is False
        assert data['credential_count'] == 0
        mock_course_enrollments.assert_called_once_with(course_key, user.id)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_non_enrolled_user_denied_course_access(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, course_key: CourseKey
    ):
        """Test that non-enrolled user is denied course access."""
        mock_course_enrollments.return_value = []

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Course not found or user does not have access' in str(response.data)

    @patch('learning_paths.models.LearningPathEnrollment.objects')
    def test_enrolled_user_can_access_learning_path_check(
        self, mock_learning_path_enrollment: Mock, authenticated_client: APIClient, learning_path_key: LearningPathKey
    ):
        """Test that enrolled user can access learning path configuration check."""
        mock_learning_path_enrollment.filter.return_value.exists.return_value = True

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(learning_path_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['has_credentials'] is False
        assert data['credential_count'] == 0

    @patch('learning_paths.models.LearningPathEnrollment.objects')
    def test_non_enrolled_user_denied_learning_path_access(
        self, mock_learning_path_enrollment: Mock, authenticated_client: APIClient, learning_path_key: LearningPathKey
    ):
        """Test that non-enrolled user is denied learning path access."""
        mock_learning_path_enrollment.filter.return_value.exists.return_value = False

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(learning_path_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Learning path not found or user does not have access' in str(response.data)

    def test_invalid_learning_context_key_returns_400(self, authenticated_client: APIClient):
        """Test that invalid learning context key returns 400."""
        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': 'invalid-key'},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Invalid learning context key' in str(response.data)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_staff_can_view_any_context_check(
        self, mock_course_enrollments: Mock, staff_client: APIClient, course_key: CourseKey
    ):
        """Test that staff can view configuration check for any context without enrollment check."""
        # Staff users bypass enrollment checks, so we don't need to mock enrollment
        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = staff_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['has_credentials'] is False
        assert data['credential_count'] == 0
        # Staff users don't trigger enrollment checks
        mock_course_enrollments.assert_not_called()


@pytest.mark.django_db
class TestCredentialConfigurationCheckView:
    """Test the CredentialConfigurationCheckView functionality."""

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_no_credentials_configured(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, user: User, course_key: CourseKey
    ):
        """Test response when no credentials are configured for a learning context."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['has_credentials'] is False
        assert data['credential_count'] == 0

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_single_credential_configured(
        self,
        mock_course_enrollments: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
    ):
        """Test response when one credential is configured for a learning context."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['has_credentials'] is True
        assert data['credential_count'] == 1

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_multiple_credentials_configured(
        self,
        mock_course_enrollments: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
        completion_config: CredentialConfiguration,
    ):
        """Test response when multiple credentials are configured for a learning context."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['has_credentials'] is True
        assert data['credential_count'] == 2

    @patch('learning_paths.models.LearningPathEnrollment.objects')
    def test_learning_path_credentials_configured(
        self, mock_learning_path_enrollment: Mock, authenticated_client: APIClient, learning_path_key: LearningPathKey
    ):
        """Test response for learning path context with configured credentials."""
        mock_learning_path_enrollment.filter.return_value.exists.return_value = True

        # Create a credential configuration for the learning path
        credential_type = CredentialType.objects.create(
            name="Learning Path Certificate",
            retrieval_func="learning_credentials.processors.retrieve_completions",
            generation_func="learning_credentials.generators.generate_pdf_credential",
        )
        CredentialConfiguration.objects.create(
            learning_context_key=learning_path_key,
            credential_type=credential_type,
        )

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(learning_path_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['has_credentials'] is True
        assert data['credential_count'] == 1

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_response_structure(
        self,
        mock_course_enrollments: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
    ):
        """Test that response has the correct structure and field types."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify all expected fields are present
        assert 'has_credentials' in data
        assert 'credential_count' in data

        # Verify field types
        assert isinstance(data['has_credentials'], bool)
        assert isinstance(data['credential_count'], int)

        # Verify values
        assert data['has_credentials'] is True
        assert data['credential_count'] == 1

    def test_staff_can_check_any_context(
        self, staff_client: APIClient, course_key: CourseKey, grade_config: CredentialConfiguration
    ):
        """Test that staff can check configuration for any context without enrollment."""
        url = reverse(
            'learning_credentials_api_v1:credential-configuration-check',
            kwargs={'learning_context_key': str(course_key)},
        )
        response = staff_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['has_credentials'] is True
        assert data['credential_count'] == 1


@pytest.mark.django_db
class TestCredentialEligibilityViewAuthentication:
    """Test authentication requirements for credential eligibility endpoints."""

    def test_get_eligibility_requires_authentication(self, api_client: APIClient, course_key: CourseKey):
        """Test that GET eligibility endpoint requires authentication."""
        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': str(course_key)}
        )
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_post_generation_requires_authentication(self, api_client: APIClient, course_key: CourseKey):
        """Test that POST generation endpoint requires authentication."""
        url = reverse(
            'learning_credentials_api_v1:credential-generation',
            kwargs={'learning_context_key': str(course_key), 'credential_type_id': 1},
        )
        response = api_client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCredentialEligibilityViewPermissions:
    """Test permission requirements for credential eligibility endpoints."""

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_enrolled_user_can_access_course_eligibility(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, user: User, course_key: CourseKey
    ):
        """Test that enrolled user can access course eligibility."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': str(course_key)}
        )
        response = authenticated_client.get(url)

        # Should return 200 with empty credentials list (no configurations exist)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['context_key'] == str(course_key)
        assert data['credentials'] == []
        mock_course_enrollments.assert_called_once_with(course_key, user.id)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_non_enrolled_user_denied_course_access(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, course_key: CourseKey
    ):
        """Test that non-enrolled user is denied course access."""
        mock_course_enrollments.return_value = []

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': str(course_key)}
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Course not found or user does not have access' in str(response.data)

    @patch('learning_paths.models.LearningPathEnrollment.objects')
    def test_enrolled_user_can_access_learning_path_eligibility(
        self, mock_learning_path_enrollment: Mock, authenticated_client: APIClient, learning_path_key: LearningPathKey
    ):
        """Test that enrolled user can access learning path eligibility."""
        mock_learning_path_enrollment.filter.return_value.exists.return_value = True

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility',
            kwargs={'learning_context_key': str(learning_path_key)},
        )
        response = authenticated_client.get(url)

        # Will return 200 with empty credentials list since no configs exist
        assert response.status_code == status.HTTP_200_OK

    @patch('learning_paths.models.LearningPathEnrollment.objects')
    def test_non_enrolled_user_denied_learning_path_access(
        self, mock_learning_path_enrollment: Mock, authenticated_client: APIClient, learning_path_key: LearningPathKey
    ):
        """Test that non-enrolled user is denied learning path access."""
        mock_learning_path_enrollment.filter.return_value.exists.return_value = False

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility',
            kwargs={'learning_context_key': str(learning_path_key)},
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Learning path not found or user does not have access' in str(response.data)

    def test_invalid_learning_context_key_returns_400(self, authenticated_client: APIClient):
        """Test that invalid learning context key returns 400."""
        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': 'invalid-key'}
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Invalid learning context key' in str(response.data)


@pytest.mark.django_db
class TestCredentialEligibilityViewGET:
    """Test GET endpoint for credential eligibility."""

    @patch('learning_credentials.models.CredentialConfiguration.get_user_eligibility_details')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_grade_based_eligible_credential(
        self,
        mock_course_enrollments: Mock,
        mock_eligibility_details: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
    ):
        """Test eligibility response for eligible grade-based credential."""
        mock_course_enrollments.return_value = [user]
        mock_eligibility_details.return_value = {
            'is_eligible': True,
            'current_grades': {'Final Exam': 90, 'Overall Grade': 85},
            'required_grades': {'Final Exam': 65, 'Overall Grade': 80},
        }

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': str(course_key)}
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['context_key'] == str(course_key)
        assert len(data['credentials']) == 1

        credential = data['credentials'][0]
        assert credential['name'] == 'Certificate of Achievement'
        assert credential['is_eligible'] is True
        assert credential['current_grades'] == {'Final Exam': 90, 'Overall Grade': 85}
        assert credential['required_grades'] == {'Final Exam': 65, 'Overall Grade': 80}
        # existing_credential is filtered out when None
        assert 'existing_credential' not in credential

    @patch('learning_credentials.models.CredentialConfiguration.get_user_eligibility_details')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_completion_based_not_eligible_credential(
        self,
        mock_course_enrollments: Mock,
        mock_eligibility_details: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        completion_config: CredentialConfiguration,
    ):
        """Test eligibility response for non-eligible completion-based credential."""
        mock_course_enrollments.return_value = [user]
        mock_eligibility_details.return_value = {
            'is_eligible': False,
            'current_completion': 75.0,
            'required_completion': 100.0,
        }

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': str(course_key)}
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        credential = data['credentials'][0]
        assert credential['name'] == 'Certificate of Completion'
        assert credential['is_eligible'] is False
        assert credential['current_completion'] == 75.0
        assert credential['required_completion'] == 100.0
        # Should not include grade fields
        assert 'current_grades' not in credential
        assert 'required_grades' not in credential

    @patch('learning_credentials.models.CredentialConfiguration.get_user_eligibility_details')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_existing_credential_shown_in_response(
        self,
        mock_course_enrollments: Mock,
        mock_eligibility_details: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
        credential_instance: Credential,
    ):
        """Test that existing credential UUID is shown in eligibility response."""
        mock_course_enrollments.return_value = [user]
        mock_eligibility_details.return_value = {'is_eligible': True}

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': str(course_key)}
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        credential = data['credentials'][0]
        assert credential['existing_credential'] == str(credential_instance.uuid)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_no_credential_configurations_returns_empty_list(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, user: User, course_key: CourseKey
    ):
        """Test that contexts with no credential configurations return empty list."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-eligibility', kwargs={'learning_context_key': str(course_key)}
        )
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data['context_key'] == str(course_key)
        assert data['credentials'] == []


@pytest.mark.django_db
class TestCredentialEligibilityViewPOST:
    """Test POST endpoint for credential generation."""

    @patch('learning_credentials.models.CredentialConfiguration.generate_credential_for_user')
    @patch('learning_credentials.models.CredentialConfiguration.get_eligible_user_ids')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_eligible_user_credential_generation_success(
        self,
        mock_course_enrollments: Mock,
        mock_eligible_user_ids: Mock,
        mock_generate_credential: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
    ):
        """Test successful credential generation for eligible user."""
        mock_course_enrollments.return_value = [user]
        mock_eligible_user_ids.return_value = [user.id]

        url = reverse(
            'learning_credentials_api_v1:credential-generation',
            kwargs={'learning_context_key': str(course_key), 'credential_type_id': grade_config.credential_type.pk},
        )
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        assert 'detail' in data
        assert 'generation started' in data['detail'].lower() or 'generation' in data['detail'].lower()

        mock_generate_credential.assert_called_once()
        args, kwargs = mock_generate_credential.call_args
        assert args[0] == user.id

    @patch('learning_credentials.models.CredentialConfiguration.get_eligible_user_ids')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_not_eligible_user_returns_400(
        self,
        mock_course_enrollments: Mock,
        mock_eligible_user_ids: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
    ):
        """Test that non-eligible user gets 400 error."""
        mock_course_enrollments.return_value = [user]
        mock_eligible_user_ids.return_value = []  # User not eligible

        url = reverse(
            'learning_credentials_api_v1:credential-generation',
            kwargs={'learning_context_key': str(course_key), 'credential_type_id': grade_config.credential_type.pk},
        )
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not eligible' in response.json()['detail'].lower()

    @patch('learning_credentials.models.CredentialConfiguration.get_eligible_user_ids')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_existing_credential_returns_409(
        self,
        mock_course_enrollments: Mock,
        mock_eligible_user_ids: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
        credential_instance: Credential,
    ):
        """Test that user with existing credential gets 409 error."""
        mock_course_enrollments.return_value = [user]
        mock_eligible_user_ids.return_value = [user.id]

        url = reverse(
            'learning_credentials_api_v1:credential-generation',
            kwargs={'learning_context_key': str(course_key), 'credential_type_id': grade_config.credential_type.pk},
        )
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert 'already has a credential' in response.json()['detail'].lower()

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_invalid_credential_type_returns_404(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, user: User, course_key: CourseKey
    ):
        """Test that invalid credential type ID returns 404."""
        mock_course_enrollments.return_value = [user]

        url = reverse(
            'learning_credentials_api_v1:credential-generation',
            kwargs={'learning_context_key': str(course_key), 'credential_type_id': 999},
        )
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch('learning_credentials.models.CredentialConfiguration.generate_credential_for_user')
    @patch('learning_credentials.models.CredentialConfiguration.get_eligible_user_ids')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_generation_failure_returns_500(
        self,
        mock_course_enrollments: Mock,
        mock_eligible_user_ids: Mock,
        mock_generate_credential: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        grade_config: CredentialConfiguration,
    ):
        """Test that generation failure returns 500 error."""
        mock_course_enrollments.return_value = [user]
        mock_eligible_user_ids.return_value = [user.id]
        mock_generate_credential.side_effect = Exception("Generation failed")

        url = reverse(
            'learning_credentials_api_v1:credential-generation',
            kwargs={'learning_context_key': str(course_key), 'credential_type_id': grade_config.credential_type.pk},
        )
        response = authenticated_client.post(url)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert 'detail' in data


@pytest.mark.django_db
class TestCredentialListViewAuthentication:
    """Test authentication requirements for credential list endpoint."""

    def test_credential_list_requires_authentication(self, api_client: APIClient):
        """Test that credential list endpoint requires authentication."""
        url = reverse('learning_credentials_api_v1:credential-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCredentialListViewPermissions:
    """Test permission requirements for credential list endpoint."""

    def test_user_can_view_own_credentials(self, authenticated_client: APIClient, credential_instance: Credential):
        """Test that user can view their own credentials."""
        url = reverse('learning_credentials_api_v1:credential-list')
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data['credentials']) == 1
        credential_data = data['credentials'][0]
        assert credential_data['credential_id'] == str(credential_instance.uuid)
        assert credential_data['credential_type'] == credential_instance.credential_type
        assert credential_data['context_key'] == str(credential_instance.learning_context_key)
        assert credential_data['status'] == credential_instance.status

    def test_user_cannot_view_other_user_credentials(self, authenticated_client: APIClient, other_user: User):
        """Test that user cannot view other user's credentials."""
        url = reverse('learning_credentials_api_v1:credential-list')
        response = authenticated_client.get(url, {'username': other_user.username})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_view_any_user_credentials(
        self, staff_client: APIClient, user: User, credential_instance: Credential
    ):
        """Test that staff can view any user's credentials."""
        url = reverse('learning_credentials_api_v1:credential-list')
        response = staff_client.get(url, {'username': user.username})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data['credentials']) == 1
        assert data['credentials'][0]['credential_id'] == str(credential_instance.uuid)

    def test_invalid_username_returns_404(self, staff_client: APIClient):
        """Test that invalid username returns 404."""
        url = reverse('learning_credentials_api_v1:credential-list')
        response = staff_client.get(url, {'username': 'nonexistent'})

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_user_can_filter_by_enrolled_context(
        self,
        mock_course_enrollments: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
        credential_instance: Credential,
    ):
        """Test that user can filter by learning context they're enrolled in."""
        mock_course_enrollments.return_value = [user]

        url = reverse('learning_credentials_api_v1:credential-list')
        response = authenticated_client.get(url, {'learning_context_key': str(course_key)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data['credentials']) == 1

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_user_denied_filter_by_non_enrolled_context(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, course_key: CourseKey
    ):
        """Test that user is denied when filtering by non-enrolled context."""
        mock_course_enrollments.return_value = []

        url = reverse('learning_credentials_api_v1:credential-list')
        response = authenticated_client.get(url, {'learning_context_key': str(course_key)})

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestCredentialListViewFunctionality:
    """Test functionality of credential list endpoint."""

    def test_empty_credential_list(self, authenticated_client: APIClient):
        """Test response when user has no credentials."""
        url = reverse('learning_credentials_api_v1:credential-list')
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['credentials'] == []

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_multiple_credentials_serialization(
        self, mock_course_enrollments: Mock, authenticated_client: APIClient, user: User, course_key: CourseKey
    ):
        """Test serialization of multiple credentials."""
        mock_course_enrollments.return_value = [user]

        Credential.objects.create(
            user_id=user.id,
            user_full_name=user.username,
            learning_context_key=course_key,
            credential_type="Certificate A",
            status=Credential.Status.AVAILABLE,
            download_url="https://example.com/cert_a.pdf",
        )
        Credential.objects.create(
            user_id=user.id,
            user_full_name=user.username,
            learning_context_key=course_key,
            credential_type="Certificate B",
            status=Credential.Status.GENERATING,
            download_url="https://example.com/cert_b.pdf",
        )

        url = reverse('learning_credentials_api_v1:credential-list')
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data['credentials']) == 2

        for credential_data in data['credentials']:
            assert 'credential_id' in credential_data
            assert 'credential_type' in credential_data
            assert 'context_key' in credential_data
            assert 'status' in credential_data
            assert 'created_date' in credential_data
            assert 'download_url' in credential_data

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_filter_by_learning_context(
        self,
        mock_course_enrollments: Mock,
        authenticated_client: APIClient,
        user: User,
        course_key: CourseKey,
    ):
        """Test filtering credentials by learning context."""
        course_key2 = CourseKey.from_string("course-v1:OpenedX+DemoX+DemoCourse2")
        mock_course_enrollments.return_value = [user]

        Credential.objects.create(
            user_id=user.id,
            user_full_name=user.username,
            learning_context_key=course_key,
            credential_type="Cert 1",
            status=Credential.Status.AVAILABLE,
            download_url="https://example.com/1.pdf",
        )
        Credential.objects.create(
            user_id=user.id,
            user_full_name=user.username,
            learning_context_key=course_key2,
            credential_type="Cert 2",
            status=Credential.Status.AVAILABLE,
            download_url="https://example.com/2.pdf",
        )

        url = reverse('learning_credentials_api_v1:credential-list')
        response = authenticated_client.get(url, {'learning_context_key': str(course_key)})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data['credentials']) == 1
        assert data['credentials'][0]['context_key'] == str(course_key)
