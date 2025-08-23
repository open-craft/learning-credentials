"""Tests for the Learning Credentials API serializers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from opaque_keys.edx.keys import CourseKey

from learning_credentials.api.v1.serializers import (
    CredentialEligibilityResponseSerializer,
    CredentialEligibilitySerializer,
    CredentialListResponseSerializer,
    CredentialModelSerializer,
)
from learning_credentials.models import Credential, CredentialConfiguration, CredentialType
from test_utils.factories import UserFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import User


@pytest.fixture
def user() -> User:
    """Return a test user."""
    return UserFactory()  # ty: ignore[invalid-return-type]


@pytest.fixture
def course_key() -> CourseKey:
    """Return a course key."""
    return CourseKey.from_string("course-v1:OpenedX+DemoX+DemoCourse")


@pytest.fixture
def credential_type() -> CredentialType:
    """Create a credential type."""
    return CredentialType.objects.create(
        name="Certificate of Achievement",
        retrieval_func="learning_credentials.processors.retrieve_subsection_grades",
        generation_func="learning_credentials.generators.generate_pdf_credential",
        custom_options={},
    )


@pytest.fixture
def credential_config(course_key: CourseKey, credential_type: CredentialType) -> CredentialConfiguration:
    """Create credential configuration."""
    return CredentialConfiguration.objects.create(
        learning_context_key=course_key,
        credential_type=credential_type,
        custom_options={'required_grades': {'Final Exam': 65, 'Overall Grade': 80}},
    )


@pytest.fixture
def credential(user: User, course_key: CourseKey) -> Credential:
    """Create a credential instance."""
    return Credential.objects.create(
        user_id=user.id,
        user_full_name=user.get_full_name() or user.username,
        learning_context_key=course_key,
        credential_type="Certificate of Achievement",
        status=Credential.Status.AVAILABLE,
        download_url="https://example.com/credential.pdf",
    )


@pytest.mark.django_db
class TestCredentialModelSerializer:
    """Test the CredentialModelSerializer."""

    def test_serialization_fields(self, credential: Credential):
        """Test that all expected fields are serialized correctly."""
        serializer = CredentialModelSerializer(credential)
        data = serializer.data

        assert data['credential_id'] == str(credential.uuid)
        assert data['credential_type'] == credential.credential_type
        assert data['context_key'] == str(credential.learning_context_key)
        assert data['status'] == credential.status

        assert 'created_date' in data
        assert isinstance(data['created_date'], str)
        assert data['download_url'] == credential.download_url

    def test_serialization_multiple_credentials(self, user: User, course_key: CourseKey):
        """Test serialization of multiple credentials."""
        credential1 = Credential.objects.create(
            user_id=user.id,
            user_full_name=user.username,
            learning_context_key=course_key,
            credential_type="Certificate A",
            status=Credential.Status.AVAILABLE,
            download_url="https://example.com/cert_a.pdf",
        )
        credential2 = Credential.objects.create(
            user_id=user.id,
            user_full_name=user.username,
            learning_context_key=course_key,
            credential_type="Certificate B",
            status=Credential.Status.GENERATING,
            download_url="https://example.com/cert_b.pdf",
        )

        serializer = CredentialModelSerializer([credential1, credential2], many=True)
        data = serializer.data

        assert len(data) == 2
        assert data[0]['credential_type'] == "Certificate A"
        assert data[0]['status'] == Credential.Status.AVAILABLE
        assert data[1]['credential_type'] == "Certificate B"
        assert data[1]['status'] == Credential.Status.GENERATING


class TestCredentialEligibilitySerializer:
    """Test the CredentialEligibilitySerializer."""

    def test_serialization_with_all_fields(self):
        """Test serialization with all possible fields."""
        data = {
            'credential_type_id': 1,
            'name': 'Certificate of Achievement',
            'is_eligible': True,
            'existing_credential': '123e4567-e89b-12d3-a456-426614174000',
            'current_grades': {'Final Exam': 86, 'Overall Grade': 82},
            'required_grades': {'Final Exam': 65, 'Overall Grade': 80},
            'current_completion': 95.0,
            'required_completion': 100.0,
            'steps': {'step1': {'is_eligible': True}},
        }

        serializer = CredentialEligibilitySerializer(data)
        result = serializer.to_representation(data)

        for key, value in data.items():
            assert result[key] == value

    def test_serialization_filters_null_empty_values(self):
        """Test that null and empty values are filtered out."""
        data = {
            'credential_type_id': 1,
            'name': 'Certificate',
            'is_eligible': False,
            'existing_credential': None,
            'current_grades': {},
            'required_grades': None,
            'current_completion': None,
            'steps': {},
        }

        serializer = CredentialEligibilitySerializer()
        result = serializer.to_representation(data)

        assert result == {
            'credential_type_id': 1,
            'name': 'Certificate',
            'is_eligible': False,
        }


class TestCredentialEligibilityResponseSerializer:
    """Test the CredentialEligibilityResponseSerializer."""

    def test_serialization_structure(self):
        """Test the overall response structure."""
        credentials_data = [
            {
                'credential_type_id': 1,
                'name': 'Certificate A',
                'is_eligible': True,
            },
            {
                'credential_type_id': 2,
                'name': 'Certificate B',
                'is_eligible': False,
            },
        ]
        data = {
            'context_key': 'course-v1:OpenedX+DemoX+DemoCourse',
            'credentials': credentials_data,
        }

        serializer = CredentialEligibilityResponseSerializer(data=data)
        assert serializer.is_valid()

        result = serializer.validated_data
        assert result['context_key'] == 'course-v1:OpenedX+DemoX+DemoCourse'
        assert len(result['credentials']) == 2


class TestCredentialListResponseSerializer:
    """Test the CredentialListResponseSerializer."""

    @pytest.mark.django_db
    def test_serialization_with_credential_list(self, credential: Credential):
        """Test serialization with list of credentials."""
        credentials_data = CredentialModelSerializer([credential], many=True).data
        data = {'credentials': credentials_data}

        serializer = CredentialListResponseSerializer(data=data)
        assert serializer.is_valid()

        result = serializer.validated_data
        assert len(result['credentials']) == 1
