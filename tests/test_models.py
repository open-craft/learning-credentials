"""Tests for the `learning-credentials` models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django_celery_beat.models import PeriodicTask

from learning_credentials.exceptions import CredentialGenerationError
from learning_credentials.models import (
    Credential,
    CredentialConfiguration,
    CredentialType,
)
from test_utils.factories import UserFactory

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.db.models import Model
    from opaque_keys.edx.keys import LearningContextKey


def _mock_retrieval_func(_context_id: LearningContextKey, _options: dict[str, Any]) -> list[int]:
    return [1, 2, 3]


def _mock_generation_func(
    _context_id: LearningContextKey,
    _user: User,
    _credential_uuid: UUID,
    _options: dict[str, Any],
) -> str:
    return "test_url"


class TestCredentialType:
    """Tests for the CredentialType model."""

    def test_str(self):
        """Test the string representation of the model."""
        credential_type = CredentialType(name="Test Type")
        assert str(credential_type) == "Test Type"

    def test_clean_with_valid_functions(self):
        """Test the clean method with valid function paths."""
        credential_type = CredentialType(
            name="Test Type",
            retrieval_func="test_models._mock_retrieval_func",
            generation_func="test_models._mock_generation_func",
        )
        credential_type.clean()

    @pytest.mark.parametrize("function_path", ["", "invalid_format_func"])
    def test_clean_with_invalid_function_format(self, function_path: str):
        """Test the clean method with invalid function format."""
        credential_type = CredentialType(
            name="Test Type",
            retrieval_func="test_models._mock_retrieval_func",
            generation_func=function_path,
        )
        with pytest.raises(ValidationError) as exc:
            credential_type.clean()
        assert "Function path must be in format 'module.function_name'" in str(exc.value)

    def test_clean_with_invalid_function(self):
        """Test the clean method with invalid function paths."""
        credential_type = CredentialType(
            name="Test Type",
            retrieval_func="test_models._mock_retrieval_func",
            generation_func="invalid.module.path",
        )
        with pytest.raises(ValidationError) as exc:
            credential_type.clean()
        assert f"The function {credential_type.generation_func} could not be found. Please provide a valid path" in str(
            exc.value,
        )


class TestCredentialConfiguration:
    """Tests for the CredentialConfiguration model."""

    def setup_method(self):
        """Prepare the test data."""
        self.credential_type = CredentialType(
            name="Test Type",
            retrieval_func="test_models._mock_retrieval_func",
            generation_func="test_models._mock_generation_func",
        )
        self.config = CredentialConfiguration(
            learning_context_key="course-v1:TestX+T101+2023",
            credential_type=self.credential_type,
        )

    @pytest.mark.django_db
    def test_periodic_task_is_auto_created(self):
        """Test that a periodic task is automatically created for the new configuration."""
        self.credential_type.save()
        self.config.save()
        self.config.refresh_from_db()

        assert (periodic_task := self.config.periodic_task) is not None
        assert periodic_task.enabled is False
        assert periodic_task.name == str(self.config)
        assert periodic_task.args == f'[{self.config.id}]'
        assert periodic_task.task == 'learning_credentials.tasks.generate_credentials_for_config_task'

    @pytest.mark.django_db
    def test_periodic_task_is_deleted_on_deletion(self):
        """Test that the periodic task is deleted when the configuration is deleted."""
        self.credential_type.save()
        self.config.save()
        assert PeriodicTask.objects.count() == 1

        self.config.delete()
        assert not PeriodicTask.objects.exists()

    @pytest.mark.django_db
    def test_periodic_task_deletion_removes_the_configuration(self):
        """Test that the configuration is deleted when the periodic task is deleted."""
        self.credential_type.save()
        self.config.save()
        assert PeriodicTask.objects.count() == 1

        self.config.periodic_task.delete()
        assert not CredentialConfiguration.objects.exists()

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("deleted_model", "verified_model"),
        [
            (CredentialConfiguration, PeriodicTask),  # `post_delete` signal.
            (PeriodicTask, CredentialConfiguration),  # Cascade deletion of the `OneToOneField`.
        ],
    )
    def test_bulk_delete(self, deleted_model: type[Model], verified_model: type[Model]):
        """Test that the bulk deletion of configurations removes the periodic tasks (and vice versa)."""
        self.credential_type.save()
        self.config.save()

        CredentialConfiguration(
            learning_context_key="course-v1:TestX+T101+2024",
            credential_type=self.credential_type,
        ).save()
        assert PeriodicTask.objects.count() == 2

        deleted_model.objects.all().delete()
        assert not verified_model.objects.exists()

    def test_str_representation(self):
        """Test the string representation of the model."""
        assert str(self.config) == f'{self.credential_type.name} in course-v1:TestX+T101+2023'

    def test_get_eligible_user_ids(self):
        """Test the get_eligible_user_ids method."""
        eligible_user_ids = self.config.get_eligible_user_ids()
        assert eligible_user_ids == [1, 2, 3]

    @pytest.mark.django_db
    def test_filter_out_user_ids_with_credentials(self):
        """Test the filter_out_user_ids_with_credentials method."""
        self.credential_type.save()
        self.config.save()

        credential_data = {
            "learning_context_key": self.config.learning_context_key,
            "credential_type": self.credential_type.name,
        }

        Credential.objects.create(
            uuid=uuid4(),
            user_id=1,
            status=Credential.Status.GENERATING,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user_id=2,
            status=Credential.Status.AVAILABLE,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user_id=3,
            status=Credential.Status.ERROR,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user_id=4,
            status=Credential.Status.INVALIDATED,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user_id=5,
            status=Credential.Status.ERROR,
            **credential_data,
        )

        filtered_users = self.config.filter_out_user_ids_with_credentials([1, 2, 3, 4, 6])
        assert filtered_users == [3, 6]

    @pytest.mark.django_db
    @patch.object(Credential, 'send_email')
    def test_generate_credential_for_user(self, mock_send_email: Mock):
        """Test the generate_credential_for_user method."""
        user = UserFactory.create()
        task_id = 123

        self.config.generate_credential_for_user(user.id, task_id)
        assert Credential.objects.filter(
            user_id=user.id,
            learning_context_key=self.config.learning_context_key,
            credential_type=self.credential_type,
            user_full_name=f"{user.first_name} {user.last_name}",
            status=Credential.Status.AVAILABLE,
            generation_task_id=task_id,
            download_url="test_url",
        ).exists()
        mock_send_email.assert_called_once()

        # For now, we only prevent the generation task from sending emails to inactive users.
        # In the future, we may want to prevent the generation task from generating credentials for inactive users.

        user = UserFactory.create(is_active=False)

        self.config.generate_credential_for_user(user.id, task_id)
        assert Credential.objects.filter(learning_context_key=self.config.learning_context_key).count() == 2
        mock_send_email.assert_called_once()

        user = UserFactory.create()
        user.set_unusable_password()
        user.save()

        self.config.generate_credential_for_user(user.id, task_id)
        assert Credential.objects.filter(learning_context_key=self.config.learning_context_key).count() == 3
        mock_send_email.assert_called_once()

    @pytest.mark.django_db
    @patch.object(Credential, 'send_email')
    def test_generate_credential_for_user_update_existing(self, mock_send_email: Mock):
        """Test the generate_credential_for_user method updates an existing credential."""
        user = UserFactory.create()

        Credential.objects.create(
            user_id=user.id,
            learning_context_key=self.config.learning_context_key,
            credential_type=self.credential_type,
            user_full_name="Random Name",
            status=Credential.Status.ERROR,
            generation_task_id=123,
            download_url="random_url",
        )

        self.config.generate_credential_for_user(user.id)
        assert Credential.objects.filter(
            user_id=user.id,
            learning_context_key=self.config.learning_context_key,
            credential_type=self.credential_type,
            user_full_name=f"{user.first_name} {user.last_name}",
            status=Credential.Status.AVAILABLE,
            generation_task_id=0,
            download_url="test_url",
        ).exists()
        mock_send_email.assert_called_once()

    @pytest.mark.django_db
    @patch('learning_credentials.models.import_module')
    def test_generate_credential_for_user_with_exception(self, mock_module: Mock):
        """Test the generate_credential_for_user handles the case when the generation function raises an exception."""
        user = UserFactory.create()
        task_id = 123

        def mock_func_raise_exception(*_args, **_kwargs):
            msg = "Test Exception"
            raise RuntimeError(msg)

        mock_module.return_value = mock_func_raise_exception

        # Call the method under test and check that it raises the correct exception.
        with pytest.raises(CredentialGenerationError) as exc:
            self.config.generate_credential_for_user(user.id, task_id)

        assert 'Failed to generate the' in str(exc.value)
        assert Credential.objects.filter(
            user_id=user.id,
            learning_context_key=self.config.learning_context_key,
            credential_type=self.credential_type,
            user_full_name=f"{user.first_name} {user.last_name}",
            status=Credential.Status.ERROR,
            generation_task_id=task_id,
            download_url='',
        ).exists()


class TestCredential:
    """Tests for the Credential model."""

    def setup_method(self):
        """Prepare the test data."""
        self.credential = Credential(
            uuid=uuid4(),
            user_id=1,
            user_full_name='Test User',
            learning_context_key='course-v1:TestX+T101+2023',
            credential_type='Test Type',
            status=Credential.Status.GENERATING,
            download_url='http://www.test.com',
            generation_task_id='12345',
        )

    def test_str_representation(self):
        """Test the string representation of a credential."""
        assert str(self.credential) == 'Test Type for Test User in course-v1:TestX+T101+2023'

    @pytest.mark.django_db
    def test_unique_together_constraint(self):
        """Test that the unique_together constraint is enforced."""
        self.credential.save()
        credential_2_info = {
            "uuid": uuid4(),
            "user_id": 1,
            "user_full_name": 'Test User 2',
            "learning_context_key": 'course-v1:TestX+T101+2023',
            "credential_type": 'Test Type',
            "status": Credential.Status.GENERATING,
            "download_url": 'http://www.test2.com',
            "generation_task_id": '122345',
        }
        with pytest.raises(IntegrityError):
            Credential.objects.create(**credential_2_info)
