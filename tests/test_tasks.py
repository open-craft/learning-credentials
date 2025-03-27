"""Tests for the learning-credentials Celery tasks."""

from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from learning_credentials.tasks import (
    generate_all_credentials_task,
    generate_credential_for_user_task,
    generate_credentials_for_config_task,
)


@pytest.mark.django_db
def test_generate_credential_for_user():
    """Test if the `generate_credential_for_user` method is called with correct parameters."""
    config_id = 123
    user_id = 456
    task_id = 789

    with (
        patch('learning_credentials.models.CredentialConfiguration.objects.get') as mock_get,
        patch('learning_credentials.tasks.generate_credential_for_user_task') as mock_task,
    ):
        mock_config = Mock()
        mock_get.return_value = mock_config

        mock_request = Mock()
        type(mock_request).id = PropertyMock(return_value=task_id)
        type(mock_task).request = PropertyMock(return_value=mock_request)

        # Call the actual task
        generate_credential_for_user_task(config_id, user_id)

        mock_config.generate_credential_for_user.assert_called_once_with(user_id, task_id)


@pytest.mark.django_db
def test_generate_credentials_for_course_with_filtering():
    """Test if `generate_credential_for_user_task.delay` is called for each filtered eligible user."""
    config_id = 123
    all_eligible_user_ids = [1, 2, 3, 4]  # Initial set of eligible user IDs
    filtered_user_ids = [1, 3]  # User IDs after filtering (e.g., users 2 and 4 already have credentials)

    with (
        patch('learning_credentials.models.CredentialConfiguration.objects.get') as mock_get,
        patch('learning_credentials.tasks.generate_credential_for_user_task.delay') as mock_delay,
    ):
        mock_config = Mock()
        mock_get.return_value = mock_config

        # Mocking the methods to return predefined lists
        mock_config.get_eligible_user_ids.return_value = all_eligible_user_ids
        mock_config.filter_out_user_ids_with_credentials.return_value = filtered_user_ids

        generate_credentials_for_config_task(config_id)

        # Ensure that the delay method is called only for filtered user IDs
        assert mock_delay.call_count == len(filtered_user_ids)
        for user_id in filtered_user_ids:
            mock_delay.assert_any_call(config_id, user_id)


@pytest.mark.django_db
def test_generate_all_credentials():
    """Test if `generate_credentials_for_config_task.delay` is called for each enabled configuration."""
    config_ids = [101, 102, 103]

    # Create a mock QuerySet
    mock_queryset = MagicMock()
    mock_queryset.values_list.return_value = config_ids

    with (
        patch(
            'learning_credentials.models.CredentialConfiguration.get_enabled_configurations',
            return_value=mock_queryset,
        ),
        patch('learning_credentials.tasks.generate_credentials_for_config_task.delay') as mock_delay,
    ):
        generate_all_credentials_task()

        assert mock_delay.call_count == len(config_ids)
        for config_id in config_ids:
            mock_delay.assert_any_call(config_id)
