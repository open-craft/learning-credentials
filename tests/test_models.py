"""Tests for the `learning-credentials` models."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django_celery_beat.models import PeriodicTask

from learning_credentials.exceptions import AssetNotFoundError, CredentialGenerationError
from learning_credentials.models import (
    Credential,
    CredentialAsset,
    CredentialConfiguration,
    CredentialType,
    post_delete_periodic_task,
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

    @patch('test_models._mock_retrieval_func')
    def test_custom_options_deep_merge(self, mock_retrieval_func: Mock):
        """Test that custom_options are deep-merged between CredentialType and CredentialConfiguration."""
        self.credential_type.custom_options = {
            'top_level': 'base_value',
            'nested': {
                'key1': 'base_key1',
                'key2': 'base_key2',
                'key3': {
                    'sub_key1': 'sub_value1',
                    'sub_key2': 'sub_value2',
                },
                'key4': False,
                'key5': {
                    'sub_key1': 'sub_value1',
                    'sub_key2': 'sub_value2',
                },
            },
        }
        self.config.custom_options = {
            'top_level': 'override_value',
            'nested': {
                'key2': 'override_key2',
                'key6': 'new_key5',
                'key3': {
                    'sub_key1': 'sub_override_value1',
                },
                'key4': {
                    'sub_key': 'sub_value',
                },
                'key5': False,
            },
            'new_top': 'new_value',
        }

        self.config.get_eligible_user_ids()

        assert mock_retrieval_func.call_args[0][1] == {
            'top_level': 'override_value',  # Overridden.
            'nested': {
                'key1': 'base_key1',  # Preserved from type.
                'key2': 'override_key2',  # Overridden.
                'key3': {  # Merged into type, with an override.
                    'sub_key1': 'sub_override_value1',
                    'sub_key2': 'sub_value2',
                },
                'key4': {  # Overridden non-dict with dict.
                    'sub_key': 'sub_value',
                },
                'key5': False,  # Overridden dict with non-dict.
                'key6': 'new_key5',  # Added from override.
            },
            'new_top': 'new_value',  # Added from override.
        }

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
    def test_generate_credential_for_user(self, mock_send_email: Mock, user: User):
        """Test the generate_credential_for_user method."""
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

        inactive_user = UserFactory.create(is_active=False)

        self.config.generate_credential_for_user(inactive_user.id, task_id)
        assert Credential.objects.filter(learning_context_key=self.config.learning_context_key).count() == 2
        mock_send_email.assert_called_once()

        user_without_password = UserFactory.create()
        user_without_password.set_unusable_password()
        user_without_password.save()

        self.config.generate_credential_for_user(user_without_password.id, task_id)
        assert Credential.objects.filter(learning_context_key=self.config.learning_context_key).count() == 3
        mock_send_email.assert_called_once()

    @pytest.mark.django_db
    @patch.object(Credential, 'send_email')
    def test_generate_credential_for_user_update_existing(self, mock_send_email: Mock, user: User):
        """Test the generate_credential_for_user method updates an existing credential."""
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
    def test_generate_credential_for_user_with_exception(self, mock_module: Mock, user: User):
        """Test the generate_credential_for_user handles the case when the generation function raises an exception."""
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

    @pytest.mark.django_db
    @patch.object(Credential, 'send_email')
    def test_generate_credentials(self, mock_send_email: Mock):
        """Test the generate_credentials method that processes all eligible users."""
        self.credential_type.save()
        self.config.save()

        # Create users that match the mock retrieval function (returns [1, 2, 3]).
        user1 = UserFactory.create(id=1)
        user2 = UserFactory.create(id=2)
        user3 = UserFactory.create(id=3)
        user4 = UserFactory.create(id=4)

        self.config.generate_credentials()

        assert Credential.objects.filter(learning_context_key=self.config.learning_context_key).count() == 3
        assert Credential.objects.filter(user_id=user1.id).exists()
        assert Credential.objects.filter(user_id=user2.id).exists()
        assert Credential.objects.filter(user_id=user3.id).exists()
        assert not Credential.objects.filter(user_id=user4.id).exists()
        assert mock_send_email.call_count == 3

    @pytest.mark.django_db
    def test_get_enabled_configurations(self):
        """Test the get_enabled_configurations classmethod."""
        self.credential_type.save()
        self.config.save()

        assert CredentialConfiguration.get_enabled_configurations().count() == 0

        self.config.periodic_task.enabled = True
        self.config.periodic_task.save()

        enabled_configs = CredentialConfiguration.get_enabled_configurations()
        assert enabled_configs.count() == 1
        assert enabled_configs.first() == self.config

    @pytest.mark.django_db
    def test_save_updates_existing_periodic_task(self):
        """Test that saving an existing CredentialConfiguration updates the periodic task."""
        self.credential_type.save()
        self.config.save()

        original_task_id = self.config.periodic_task.id
        original_task_name = self.config.periodic_task.name
        original_modified = self.config.periodic_task.date_changed

        self.config.save()
        self.config.refresh_from_db()

        assert self.config.periodic_task.id == original_task_id
        assert self.config.periodic_task.name == original_task_name
        assert self.config.periodic_task.date_changed > original_modified

    def test_post_delete_signal_handles_missing_periodic_task(self):
        """Test that the post_delete signal handles the case when periodic_task is None."""
        mock_instance = Mock(spec=CredentialConfiguration, periodic_task=None)
        post_delete_periodic_task(sender=CredentialConfiguration, instance=mock_instance)


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

    @pytest.mark.django_db
    @patch('learning_credentials.models.settings')
    @patch('learning_credentials.models.get_learning_context_name')
    @patch('learning_credentials.models.ace')
    def test_send_email(self, mock_ace: Mock, mock_get_learning_context_name: Mock, mock_settings: Mock, user: User):
        """Test the send_email method sends an email to the user."""
        mock_get_learning_context_name.return_value = "Test Course"
        mock_settings.PLATFORM_NAME = "Test Platform"

        credential = Credential.objects.create(
            user_id=user.id,
            user_full_name=f"{user.first_name} {user.last_name}",
            learning_context_key='course-v1:TestX+T101+2023',
            credential_type='Test Type',
            status=Credential.Status.AVAILABLE,
            download_url='http://www.test.com/credential.pdf',
            generation_task_id='12345',
        )

        credential.send_email()

        mock_ace.send.assert_called_once()
        message = mock_ace.send.call_args[0][0]
        assert message.name == "certificate_generated"
        assert message.context['certificate_link'] == credential.download_url
        assert message.context['course_name'] == "Test Course"


class TestCredentialAsset:
    """Tests for the CredentialAsset model."""

    @pytest.mark.django_db
    def test_str_representation(self, temp_media: str):
        """Test the string representation of a CredentialAsset."""
        asset = CredentialAsset(
            description="Test Asset",
            asset_slug="test-asset",
        )
        asset.asset = ContentFile(b"test content", name="test.pdf")
        asset.save()

        assert "test.pdf" in str(asset)

    @pytest.mark.django_db
    def test_save_creates_asset_correctly(self, temp_media: str):
        """Test that saving a new CredentialAsset handles the asset field correctly."""
        asset = CredentialAsset(
            description="Test Asset",
            asset_slug="test-asset-save",
        )
        asset.asset = ContentFile(b"test content", name="test.pdf")
        asset.save()
        asset.refresh_from_db()

        assert asset.id is not None
        assert asset.asset is not None
        assert "test.pdf" in asset.asset.name

    @pytest.mark.django_db
    def test_get_asset_by_slug(self, temp_media: str):
        """Test retrieving an asset by its slug."""
        asset = CredentialAsset(
            description="Test Asset",
            asset_slug="test-asset-slug",
        )
        asset.asset = ContentFile(b"test content", name="test.pdf")
        asset.save()

        retrieved_asset = CredentialAsset.get_asset_by_slug("test-asset-slug")
        assert retrieved_asset.name == asset.asset.name

    @pytest.mark.django_db
    def test_get_asset_by_slug_not_found(self):
        """Test that getting a non-existent asset raises AssetNotFoundError."""
        with pytest.raises(AssetNotFoundError) as exc:
            CredentialAsset.get_asset_by_slug("non-existent-slug")

        assert "Asset with slug non-existent-slug does not exist" in str(exc.value)

    @pytest.mark.django_db
    def test_template_assets_path_deletes_existing_file(self, temp_media: str):
        """Test that template_assets_path deletes an existing file before returning the path."""
        asset = CredentialAsset(description="Test Asset", asset_slug="test-asset-delete")
        asset.asset = ContentFile(b"original content", name="original.pdf")
        asset.save()

        target_filename = "test_file.pdf"
        target_path = Path(temp_media) / 'learning_credentials_template_assets' / str(asset.id) / target_filename

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"existing content")

        assert target_path.exists()

        # This should delete the existing file.
        new_path = asset.template_assets_path(target_filename)

        assert not target_path.exists()
        assert target_filename in new_path

    @pytest.mark.django_db
    def test_template_assets_path_when_file_does_not_exist(self, temp_media: str):
        """Test that template_assets_path works when no file exists at the target path."""
        asset = CredentialAsset(description="Test Asset", asset_slug="test-asset-no-file")
        asset.asset = ContentFile(b"content", name="initial.pdf")
        asset.save()

        new_path = asset.template_assets_path("nonexistent.pdf")

        assert "nonexistent.pdf" in new_path
        assert str(asset.id) in new_path

    @pytest.mark.django_db
    def test_save_updates_existing_asset(self, temp_media: str):
        """Test that saving an existing CredentialAsset updates it correctly (as it has some custom logic)."""
        asset = CredentialAsset(description="Original Description", asset_slug="test-asset-update")
        asset.asset = ContentFile(b"original content", name="original.pdf")
        asset.save()

        original_id = asset.id

        asset.description = "Updated Description"
        asset.save()
        asset.refresh_from_db()

        assert asset.id == original_id
        assert asset.description == "Updated Description"
