"""Tests for the Learning Credentials API views."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from django.urls import reverse
from learning_paths.models import LearningPathStep
from rest_framework import status
from rest_framework.test import APIClient

from learning_credentials.models import Credential, CredentialConfiguration
from test_utils.factories import UserFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from learning_paths.models import LearningPath, LearningPathEnrollment
    from opaque_keys.edx.keys import CourseKey, LearningContextKey
    from requests import Response

    from learning_credentials.models import CredentialType


def _get_api_client(user: User | None) -> APIClient:
    """Return API client for the given user."""
    client = APIClient()
    if user:
        client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestCredentialConfigurationCheckViewPermissions:
    """Test permission requirements for credential configuration check endpoint."""

    def _make_request(self, user: User | None, learning_context_key: LearningContextKey) -> Response:
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
        self, mock_course_enrollments: Mock, user: User, course_key: CourseKey
    ):
        """Test that enrolled user can access course configuration check."""
        mock_course_enrollments.return_value = [user]
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}
        mock_course_enrollments.assert_called_once_with(course_key, user.id)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments', return_value=[])
    def test_non_enrolled_user_denied_course_access(
        self, mock_course_enrollments: Mock, user: User, course_key: CourseKey
    ):
        """Test that non-enrolled user is denied course access."""
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Course not found or user does not have access' in str(response.data)

    def test_enrolled_user_can_access_learning_path_check(
        self, user: User, learning_path_enrollment: LearningPathEnrollment
    ):
        """Test that enrolled user can access learning path configuration check."""
        response = self._make_request(user, learning_path_enrollment.learning_path.key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    def test_non_enrolled_user_denied_learning_path_access(self, user: User, learning_path: LearningPath):
        """Test that non-enrolled user is denied learning path access."""
        response = self._make_request(user, learning_path.key)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'Learning path not found or user does not have access' in str(response.data)

    def test_invalid_learning_context_key_returns_400(self, user: User):
        """Test that invalid learning context key returns 400."""
        response = self._make_request(user, "invalid-key")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Invalid learning context key' in str(response.data)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_staff_can_view_any_context_check(
        self, mock_course_enrollments: Mock, staff_user: User, course_key: CourseKey
    ):
        """Test that staff can view configuration check for any context without enrollment check."""
        response = self._make_request(staff_user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}
        # Staff users bypass enrollment checks.
        mock_course_enrollments.assert_not_called()

    def test_user_can_access_public_learning_path(self, user: User, public_learning_path: LearningPath):
        """Test that any user can access a public (non-invite-only) learning path."""
        response = self._make_request(user, public_learning_path.key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    def test_user_cannot_access_invite_only_learning_path_without_enrollment(
        self, user: User, learning_path: LearningPath
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
        self, mock_course_enrollments: Mock, user: User, course_key: CourseKey, public_learning_path: LearningPath
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

    def _make_request(self, user: User | None, learning_context_key: LearningContextKey) -> Response:
        """Helper to make GET request to the endpoint."""
        client = _get_api_client(user)
        url = reverse(
            'learning_credentials_api_v1:credential_configuration_check',
            kwargs={'learning_context_key': str(learning_context_key)},
        )
        return client.get(url)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_no_credentials_configured(self, mock_course_enrollments: Mock, user: User, course_key: CourseKey):
        """Test response when no credentials are configured for a learning context."""
        mock_course_enrollments.return_value = [user]
        response = self._make_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': False, 'credential_count': 0}

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_single_credential_configured(
        self, mock_course_enrollments: Mock, user: User, course_key: CourseKey, grade_config: CredentialConfiguration
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
        user: User,
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
        self, staff_user: User, course_key: CourseKey, grade_config: CredentialConfiguration
    ):
        """Test that staff can check configuration for any context without enrollment."""
        response = self._make_request(staff_user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'has_credentials': True, 'credential_count': 1}


@pytest.mark.django_db
class TestCredentialMetadataView:
    """Test the CredentialMetadataView functionality."""

    def _make_request(self, uuid: str) -> Response:
        """Helper to make GET request to the metadata endpoint."""
        client = APIClient()
        url = reverse('learning_credentials_api_v1:credential-metadata', kwargs={'uuid': uuid})
        return client.get(url)

    def test_credential_metadata(self, credential: Credential):
        """Test that valid credential metadata is returned."""
        response = self._make_request(str(credential.verify_uuid))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 5
        assert response.data['user_full_name'] == "Test User"
        assert response.data['learning_context_name'] == "Test Course"
        assert response.data['status'] == Credential.Status.AVAILABLE
        assert 'created' in response.data
        assert response.data['invalidation_reason'] == ""

    def test_credential_metadata_not_found(self):
        """Test that 404 is returned for non-existent credential."""
        response = self._make_request("00000000-0000-0000-0000-000000000000")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data == {'error': 'Credential not found.'}

    def test_invalidated_credential_metadata(self, user: User, credential: Credential):
        """Test that invalidated credential returns the invalidation reason."""
        credential.invalidation_reason = "Reissued due to name change."
        credential.save()

        response = self._make_request(str(credential.verify_uuid))

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == Credential.Status.INVALIDATED
        assert response.data['invalidation_reason'] == "Reissued due to name change."


@pytest.mark.django_db
class TestCredentialEligibilityView:
    """Tests for the CredentialEligibilityView (GET eligibility and POST generation)."""

    def _make_get_request(
        self, user: User | None, learning_context_key: LearningContextKey, **query_params
    ) -> Response:
        """Helper to make GET request to the eligibility endpoint."""
        client = _get_api_client(user)
        url = reverse(
            'learning_credentials_api_v1:credential-eligibility',
            kwargs={'learning_context_key': str(learning_context_key)},
        )
        return client.get(url, query_params)

    def _make_post_request(
        self, user: User | None, learning_context_key: LearningContextKey, credential_type_id: int
    ) -> Response:
        """Helper to make POST request to the generation endpoint."""
        client = _get_api_client(user)
        url = reverse(
            'learning_credentials_api_v1:credential-generation',
            kwargs={
                'learning_context_key': str(learning_context_key),
                'credential_type_id': credential_type_id,
            },
        )
        return client.post(url)

    # --- GET tests ---

    def test_get_unauthenticated_returns_403(self, course_key: CourseKey):
        """Test that unauthenticated users get 403."""
        response = self._make_get_request(None, course_key)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_get_no_configurations(self, mock_enrollments: Mock, user: User, course_key: CourseKey):
        """Test that an empty credentials list is returned when no configurations exist."""
        mock_enrollments.return_value = [user]
        response = self._make_get_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'context_key': str(course_key), 'credentials': []}

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_get_eligible_user(
        self, mock_enrollments: Mock, user: User, course_key: CourseKey, mock_credential_config: CredentialConfiguration
    ):
        """Test eligibility response for an eligible user with no existing credential."""
        mock_enrollments.return_value = [user]
        with patch.object(CredentialConfiguration, 'get_user_eligibility_details', return_value={'is_eligible': True}):
            response = self._make_get_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        credentials = response.data['credentials']
        assert len(credentials) == 1
        cred = credentials[0]
        assert cred['credential_type_id'] == mock_credential_config.credential_type.pk
        assert cred['name'] == mock_credential_config.credential_type.name
        assert cred['is_eligible'] is True
        # None values should be stripped by serializer's to_representation.
        assert 'existing_credential' not in cred
        assert 'existing_credential_url' not in cred

    @pytest.mark.usefixtures('mock_credential_config')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_get_strips_empty_dicts(self, mock_enrollments: Mock, user: User, course_key: CourseKey):
        """Test that the serializer strips empty dict values from the response."""
        mock_enrollments.return_value = [user]
        with patch.object(
            CredentialConfiguration,
            'get_user_eligibility_details',
            return_value={'is_eligible': False, 'current_grades': {}, 'steps': {}},
        ):
            response = self._make_get_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        cred = response.data['credentials'][0]
        assert cred['is_eligible'] is False
        assert 'current_grades' not in cred
        assert 'steps' not in cred

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_get_with_existing_credential(
        self, mock_enrollments: Mock, user: User, course_key: CourseKey, credential: Credential
    ):
        """Test that existing credential info is included in the response."""
        mock_enrollments.return_value = [user]
        with patch.object(CredentialConfiguration, 'get_user_eligibility_details', return_value={'is_eligible': True}):
            response = self._make_get_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        cred = response.data['credentials'][0]
        assert str(cred['existing_credential']) == str(credential.uuid)
        assert cred['existing_credential_url'] == credential.download_url

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_get_excludes_error_credentials(
        self, mock_enrollments: Mock, user: User, course_key: CourseKey, mock_credential_config: CredentialConfiguration
    ):
        """Test that credentials with ERROR status are not returned as existing."""
        mock_enrollments.return_value = [user]
        Credential.objects.create(
            user=user,
            configuration=mock_credential_config,
            status=Credential.Status.ERROR,
        )
        with patch.object(CredentialConfiguration, 'get_user_eligibility_details', return_value={'is_eligible': True}):
            response = self._make_get_request(user, course_key)

        assert response.status_code == status.HTTP_200_OK
        cred = response.data['credentials'][0]
        assert 'existing_credential' not in cred

    @pytest.mark.usefixtures('mock_credential_config')
    def test_staff_get_for_other_user(self, staff_user: User, user: User, course_key: CourseKey):
        """Test that staff can view eligibility for another user via username param."""
        with patch.object(CredentialConfiguration, 'get_user_eligibility_details', return_value={'is_eligible': False}):
            response = self._make_get_request(staff_user, course_key, username=user.username)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['credentials']) == 1

    def test_non_staff_cannot_get_for_other_user(self, user: User, course_key: CourseKey):
        """Test that non-staff users cannot view eligibility for another user."""
        other_user = UserFactory()
        response = self._make_get_request(user, course_key, username=other_user.username)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.usefixtures('mock_credential_config')
    def test_get_user_not_found_returns_404(self, staff_user: User, course_key: CourseKey):
        """Test that 404 is returned when the specified username doesn't exist."""
        response = self._make_get_request(staff_user, course_key, username='nonexistent_user')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # --- POST tests ---

    def test_post_unauthenticated_returns_403(
        self, course_key: CourseKey, mock_credential_config: CredentialConfiguration
    ):
        """Test that unauthenticated users get 403 on POST."""
        response = self._make_post_request(None, course_key, mock_credential_config.credential_type_id)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch('learning_credentials.api.v1.views.generate_credential_for_user_task')
    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_post_starts_generation(
        self,
        mock_enrollments: Mock,
        mock_task: Mock,
        user: User,
        course_key: CourseKey,
        mock_credential_config: CredentialConfiguration,
    ):
        """Test that POST triggers credential generation for an eligible user."""
        mock_enrollments.return_value = [user]
        with patch.object(CredentialConfiguration, 'get_eligible_user_ids', return_value=[user.id]):
            response = self._make_post_request(user, course_key, mock_credential_config.credential_type_id)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == {'detail': 'Credential generation started.'}
        mock_task.delay.assert_called_once_with(mock_credential_config.id, user.id)

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_post_existing_credential_returns_409(
        self, mock_enrollments: Mock, user: User, course_key: CourseKey, credential: Credential
    ):
        """Test that POST returns 409 when user already has a valid credential."""
        mock_enrollments.return_value = [user]
        response = self._make_post_request(user, course_key, credential.configuration.credential_type_id)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert 'already has a credential' in response.data['detail']

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_post_ineligible_user_returns_400(
        self, mock_enrollments: Mock, user: User, course_key: CourseKey, mock_credential_config: CredentialConfiguration
    ):
        """Test that POST returns 400 when user is not eligible."""
        mock_enrollments.return_value = [user]
        with patch.object(CredentialConfiguration, 'get_eligible_user_ids', return_value=[]):
            response = self._make_post_request(user, course_key, mock_credential_config.credential_type_id)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'not eligible' in response.data['detail']

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_post_config_not_found_returns_404(self, mock_enrollments: Mock, user: User, course_key: CourseKey):
        """Test that POST returns 404 when credential configuration doesn't exist."""
        mock_enrollments.return_value = [user]
        response = self._make_post_request(user, course_key, 99999)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestCredentialListView:
    """Tests for the CredentialListView."""

    def _make_request(self, user: User | None, **query_params) -> Response:
        """Helper to make GET request to the credential list endpoint."""
        client = _get_api_client(user)
        url = reverse('learning_credentials_api_v1:credential-list')
        return client.get(url, query_params)

    def test_unauthenticated_returns_403(self):
        """Test that unauthenticated users get 403."""
        response = self._make_request(None)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_own_credentials(self, user: User, credential: Credential):
        """Test that a user can list their own credentials."""
        response = self._make_request(user)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['credentials']) == 1
        assert str(response.data['credentials'][0]['credential_id']) == str(credential.uuid)

    def test_list_empty(self, user: User):
        """Test that an empty list is returned when user has no credentials."""
        response = self._make_request(user)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'credentials': []}

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_filter_by_learning_context(
        self, mock_enrollments: Mock, user: User, course_key: CourseKey, mock_credential_config: CredentialConfiguration
    ):
        """Test filtering credentials by learning context key."""
        mock_enrollments.return_value = [user]
        Credential.objects.create(
            user=user,
            configuration=mock_credential_config,
            learning_context_key=course_key,
            status=Credential.Status.AVAILABLE,
            download_url='http://example.com/cred.pdf',
        )
        response = self._make_request(user, learning_context_key=str(course_key))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['credentials']) == 1

    @patch('learning_credentials.api.v1.permissions.get_course_enrollments')
    def test_filter_by_learning_context_no_match(
        self, mock_enrollments: Mock, user: User, course_key: CourseKey, mock_credential_config: CredentialConfiguration
    ):
        """Test that filtering by a different learning context returns no credentials."""
        mock_enrollments.return_value = [user]
        Credential.objects.create(
            user=user,
            configuration=mock_credential_config,
            learning_context_key=course_key,
            status=Credential.Status.AVAILABLE,
        )
        response = self._make_request(user, learning_context_key='course-v1:Other+Course+Key')

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'credentials': []}

    @pytest.mark.usefixtures('credential')
    def test_non_staff_can_get_own_by_username(self, user: User):
        """Test that a non-staff user can pass their own username."""
        response = self._make_request(user, username=user.username)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['credentials']) == 1

    def test_non_staff_cannot_view_other_user(self, user: User):
        """Test that a non-staff user cannot view another user's credentials."""
        other_user = UserFactory()
        response = self._make_request(user, username=other_user.username)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.usefixtures('credential')
    def test_staff_view_other_user(self, staff_user: User, user: User):
        """Test that staff can view another user's credentials."""
        response = self._make_request(staff_user, username=user.username)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['credentials']) == 1

    def test_username_not_found_returns_404(self, staff_user: User):
        """Test that 404 is returned when the specified username doesn't exist."""
        response = self._make_request(staff_user, username='nonexistent_user')
        assert response.status_code == status.HTTP_404_NOT_FOUND
