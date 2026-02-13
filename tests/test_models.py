"""Tests for the `learning-credentials` models."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
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


@pytest.fixture(autouse=True)
def patch_compat_functions(monkeypatch: pytest.MonkeyPatch):
    """Patch Open edX compatibility functions used in learning_credentials.compat."""
    monkeypatch.setattr('learning_credentials.models.get_learning_context_name', lambda _: "Test Course")


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
            retrieval_func="tests.conftest._mock_retrieval_func",
            generation_func="tests.conftest._mock_generation_func",
        )
        credential_type.clean()

    @pytest.mark.parametrize("function_path", ["", "invalid_format_func"])
    def test_clean_with_invalid_function_format(self, function_path: str):
        """Test the clean method with invalid function format."""
        credential_type = CredentialType(
            name="Test Type",
            retrieval_func="tests.conftest._mock_retrieval_func",
            generation_func=function_path,
        )
        with pytest.raises(ValidationError) as exc:
            credential_type.clean()
        assert "Function path must be in format 'module.function_name'" in str(exc.value)

    def test_clean_with_invalid_function(self):
        """Test the clean method with invalid function paths."""
        credential_type = CredentialType(
            name="Test Type",
            retrieval_func="tests.conftest._mock_retrieval_func",
            generation_func="invalid.module.path",
        )
        with pytest.raises(ValidationError) as exc:
            credential_type.clean()
        assert f"The function {credential_type.generation_func} could not be found. Please provide a valid path" in str(
            exc.value,
        )


class TestCredentialConfiguration:
    """Tests for the CredentialConfiguration model."""

    @pytest.mark.django_db
    def test_periodic_task_is_auto_created(self, mock_credential_config: CredentialConfiguration):
        """Test that a periodic task is automatically created for the new configuration."""
        mock_credential_config.refresh_from_db()

        assert (periodic_task := mock_credential_config.periodic_task) is not None
        assert periodic_task.enabled is False
        assert periodic_task.name == str(mock_credential_config)
        assert periodic_task.args == f'[{mock_credential_config.id}]'
        assert periodic_task.task == 'learning_credentials.tasks.generate_credentials_for_config_task'

    @pytest.mark.django_db
    def test_periodic_task_is_deleted_on_deletion(self, mock_credential_config: CredentialConfiguration):
        """Test that the periodic task is deleted when the configuration is deleted."""
        assert PeriodicTask.objects.count() == 1

        mock_credential_config.delete()
        assert not PeriodicTask.objects.exists()

    @pytest.mark.django_db
    def test_periodic_task_deletion_removes_the_configuration(self, mock_credential_config: CredentialConfiguration):
        """Test that the configuration is deleted when the periodic task is deleted."""
        assert PeriodicTask.objects.count() == 1

        mock_credential_config.periodic_task.delete()
        assert not CredentialConfiguration.objects.exists()

    @pytest.mark.django_db
    @pytest.mark.usefixtures("mock_credential_config", "grade_config")
    @pytest.mark.parametrize(
        ("deleted_model", "verified_model"),
        [
            (CredentialConfiguration, PeriodicTask),  # `post_delete` signal.
            (PeriodicTask, CredentialConfiguration),  # Cascade deletion of the `OneToOneField`.
        ],
    )
    def test_bulk_delete(self, deleted_model: type[Model], verified_model: type[Model]):
        """Test that the bulk deletion of configurations removes the periodic tasks (and vice versa)."""
        assert PeriodicTask.objects.count() == 2

        deleted_model.objects.all().delete()
        assert not verified_model.objects.exists()

    @pytest.mark.django_db
    def test_str_representation(self, mock_credential_config: CredentialConfiguration):
        """Test the string representation of the model."""
        expected = f'{mock_credential_config.credential_type.name} in {mock_credential_config.learning_context_key}'
        assert str(mock_credential_config) == expected

    @pytest.mark.django_db
    def test_get_eligible_user_ids(self, mock_credential_config: CredentialConfiguration):
        """Test the get_eligible_user_ids method."""
        eligible_user_ids = mock_credential_config.get_eligible_user_ids()
        assert eligible_user_ids == [1, 2, 3]

    @pytest.mark.django_db
    @patch('tests.conftest._mock_retrieval_func')
    def test_custom_options_deep_merge(
        self,
        mock_retrieval_func: Mock,
        mock_credential_type: CredentialType,
        mock_credential_config: CredentialConfiguration,
    ):
        """Test that custom_options are deep-merged between CredentialType and CredentialConfiguration."""
        mock_credential_type.custom_options = {
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
        mock_credential_type.save()
        mock_credential_config.custom_options = {
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
        mock_credential_config.save()

        mock_credential_config.get_eligible_user_ids()

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
    def test_filter_out_user_ids_with_credentials(self, mock_credential_config: CredentialConfiguration):
        """Test the filter_out_user_ids_with_credentials method."""
        credential_data = {
            "configuration": mock_credential_config,
        }

        Credential.objects.create(
            uuid=uuid4(),
            user=UserFactory.create(id=1),
            status=Credential.Status.GENERATING,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user=UserFactory.create(id=2),
            status=Credential.Status.AVAILABLE,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user=UserFactory.create(id=3),
            status=Credential.Status.ERROR,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user=UserFactory.create(id=4),
            status=Credential.Status.INVALIDATED,
            **credential_data,
        )
        Credential.objects.create(
            uuid=uuid4(),
            user=UserFactory.create(id=5),
            status=Credential.Status.ERROR,
            **credential_data,
        )

        filtered_users = mock_credential_config.filter_out_user_ids_with_credentials([1, 2, 3, 4, 6])
        assert filtered_users == [3, 6]

    @pytest.mark.django_db
    def test_generate_credential_for_user(
        self, patch_send_email: Mock, mock_credential_config: CredentialConfiguration, user: User
    ):
        """Test the generate_credential_for_user method."""
        task_id = 123

        mock_credential_config.generate_credential_for_user(user.id, task_id)
        assert Credential.objects.filter(
            user_id=user.id,
            learning_context_name="Test Course",
            configuration=mock_credential_config,
            user_full_name=f"{user.first_name} {user.last_name}",
            status=Credential.Status.AVAILABLE,
            generation_task_id=task_id,
            download_url="http://example.com/mock_credential.pdf",
        ).exists()
        patch_send_email.assert_called_once()

        # For now, we only prevent the generation task from sending emails to inactive users.
        # In the future, we may want to prevent the generation task from generating credentials for inactive users.

        inactive_user = UserFactory.create(is_active=False)

        mock_credential_config.generate_credential_for_user(inactive_user.id, task_id)
        assert Credential.objects.filter(configuration=mock_credential_config).count() == 2
        patch_send_email.assert_called_once()

        user_without_password = UserFactory.create()
        user_without_password.set_unusable_password()
        user_without_password.save()

        mock_credential_config.generate_credential_for_user(user_without_password.id, task_id)
        assert Credential.objects.filter(configuration=mock_credential_config).count() == 3
        patch_send_email.assert_called_once()

    @pytest.mark.django_db
    def test_generate_credential_for_user_update_existing(
        self, patch_send_email: Mock, mock_credential_config: CredentialConfiguration, user: User
    ):
        """Test the generate_credential_for_user method updates an existing credential."""
        Credential.objects.create(
            user=user,
            configuration=mock_credential_config,
            user_full_name="Random Name",
            status=Credential.Status.ERROR,
            generation_task_id=123,
            download_url="random_url",
        )

        mock_credential_config.generate_credential_for_user(user.id)
        assert Credential.objects.filter(
            user_id=user.id,
            learning_context_name="Test Course",
            configuration=mock_credential_config,
            user_full_name=f"{user.first_name} {user.last_name}",
            status=Credential.Status.AVAILABLE,
            generation_task_id=0,
            download_url="http://example.com/mock_credential.pdf",
        ).exists()
        patch_send_email.assert_called_once()

    @pytest.mark.django_db
    @patch('learning_credentials.models.import_module')
    def test_generate_credential_for_user_with_exception(
        self, mock_module: Mock, mock_credential_config: CredentialConfiguration, user: User
    ):
        """Test the generate_credential_for_user handles the case when the generation function raises an exception."""
        task_id = 123

        def mock_func_raise_exception(*_args, **_kwargs):
            msg = "Test Exception"
            raise RuntimeError(msg)

        mock_module.return_value = mock_func_raise_exception

        # Call the method under test and check that it raises the correct exception.
        with pytest.raises(CredentialGenerationError) as exc:
            mock_credential_config.generate_credential_for_user(user.id, task_id)

        assert 'Failed to generate the' in str(exc.value)
        assert Credential.objects.filter(
            user_id=user.id,
            learning_context_name="Test Course",
            configuration=mock_credential_config,
            user_full_name=f"{user.first_name} {user.last_name}",
            status=Credential.Status.ERROR,
            generation_task_id=task_id,
            download_url='',
        ).exists()

    @pytest.mark.django_db
    def test_generate_credentials(self, patch_send_email: Mock, mock_credential_config: CredentialConfiguration):
        """Test the generate_credentials method that processes all eligible users."""
        # Create users that match the mock retrieval function (returns [1, 2, 3]).
        user1 = UserFactory.create(id=1)
        user2 = UserFactory.create(id=2)
        user3 = UserFactory.create(id=3)
        user4 = UserFactory.create(id=4)

        mock_credential_config.generate_credentials()

        assert Credential.objects.filter(configuration=mock_credential_config).count() == 3
        assert Credential.objects.filter(user_id=user1.id).exists()
        assert Credential.objects.filter(user_id=user2.id).exists()
        assert Credential.objects.filter(user_id=user3.id).exists()
        assert not Credential.objects.filter(user_id=user4.id).exists()
        assert patch_send_email.call_count == 3

    @pytest.mark.django_db
    def test_get_enabled_configurations(self, mock_credential_config: CredentialConfiguration):
        """Test the get_enabled_configurations classmethod."""
        assert CredentialConfiguration.get_enabled_configurations().count() == 0

        mock_credential_config.periodic_task.enabled = True
        mock_credential_config.periodic_task.save()

        enabled_configs = CredentialConfiguration.get_enabled_configurations()
        assert enabled_configs.count() == 1
        assert enabled_configs.first() == mock_credential_config

    @pytest.mark.django_db
    def test_save_updates_existing_periodic_task(self, mock_credential_config: CredentialConfiguration):
        """Test that saving an existing CredentialConfiguration updates the periodic task."""
        original_task_id = mock_credential_config.periodic_task.id
        original_task_name = mock_credential_config.periodic_task.name
        original_modified = mock_credential_config.periodic_task.date_changed

        mock_credential_config.save()
        mock_credential_config.refresh_from_db()

        assert mock_credential_config.periodic_task.id == original_task_id
        assert mock_credential_config.periodic_task.name == original_task_name
        assert mock_credential_config.periodic_task.date_changed > original_modified

    def test_post_delete_signal_handles_missing_periodic_task(self):
        """Test that the post_delete signal handles the case when periodic_task is None."""
        mock_instance = Mock(spec=CredentialConfiguration, periodic_task=None)
        post_delete_periodic_task(sender=CredentialConfiguration, instance=mock_instance)


class TestCredential:
    """Tests for the Credential model."""

    @pytest.mark.django_db
    def test_str_representation(self, mock_credential_config: CredentialConfiguration, user: User):
        """Test the string representation of a credential."""
        credential = Credential(
            uuid=uuid4(),
            user=user,
            user_full_name='Test User',
            configuration=mock_credential_config,
            status=Credential.Status.GENERATING,
            download_url='http://www.test.com',
            generation_task_id='12345',
        )
        expected = (
            f'{mock_credential_config.credential_type.name} for Test User '
            f'in {mock_credential_config.learning_context_key}'
        )
        assert str(credential) == expected

    @pytest.mark.django_db
    @patch('learning_credentials.models.settings')
    @patch('learning_credentials.models.ace')
    def test_send_email(self, mock_ace: Mock, mock_settings: Mock, credential: Credential):
        """Test the send_email method sends an email to the user."""
        mock_settings.PLATFORM_NAME = "Test Platform"

        credential.send_email()

        mock_ace.send.assert_called_once()
        message = mock_ace.send.call_args[0][0]
        assert message.name == "certificate_generated"
        assert message.context['certificate_link'] == credential.download_url
        assert message.context['course_name'] == "Test Course"

    @pytest.mark.django_db
    def test_save_invalidates_when_reason_provided(self, credential: Credential):
        """Test that setting invalidation_reason automatically invalidates the credential."""
        assert credential.status == Credential.Status.AVAILABLE
        assert credential.invalidated_at is None

        credential.invalidation_reason = "Name change requested"
        credential.save()

        assert credential.status == Credential.Status.INVALIDATED
        assert credential.download_url == "invalidated_url"
        assert credential.invalidated_at is not None

    @pytest.mark.django_db
    def test_save_does_not_invalidate_when_already_invalidated(self, credential: Credential):
        """Test that _invalidate is not called when credential is already invalidated."""
        credential.invalidation_reason = "First reason"
        credential.save()
        credential.refresh_from_db()
        original_invalidated_at = credential.invalidated_at

        with patch.object(credential, '_invalidate') as mock_invalidate:
            credential.invalidation_reason = "First reason\nSecond reason"
            credential.save()
            credential.refresh_from_db()

            assert credential.invalidated_at == original_invalidated_at
            mock_invalidate.assert_not_called()

    @pytest.mark.django_db
    @pytest.mark.usefixtures("patch_send_email")
    def test_reissue_creates_new_credential(self, credential: Credential):
        """Test that reissue() invalidates the current credential and creates a new one."""
        new_credential = credential.reissue()
        assert new_credential.uuid != credential.uuid
        assert new_credential.user == credential.user
        assert new_credential.configuration == credential.configuration
        assert new_credential.status == Credential.Status.AVAILABLE

        credential.refresh_from_db()
        assert credential.status == Credential.Status.INVALIDATED
        assert credential.invalidation_reason == "Reissued"
        assert credential.invalidated_at is not None

    @pytest.mark.django_db
    @pytest.mark.usefixtures("patch_send_email")
    def test_reissue_appends_to_existing_invalidation_reason(self, credential: Credential):
        """Test that reissue() appends to existing invalidation_reason with newline."""
        credential.invalidation_reason = "Name change"
        credential.save()

        credential.reissue()

        credential.refresh_from_db()
        assert credential.invalidation_reason == "Name change\nReissued"


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
