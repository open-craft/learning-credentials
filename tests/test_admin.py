"""Tests for the admin module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from learning_credentials.admin import (
    CredentialAdmin,
    CredentialAssetAdmin,
    CredentialConfigurationAdmin,
    CredentialConfigurationForm,
    CredentialTypeAdmin,
    CredentialTypeAdminForm,
    DocstringOptionsMixin,
)
from learning_credentials.models import (
    Credential,
    CredentialAsset,
    CredentialConfiguration,
    CredentialType,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import User


@pytest.fixture
def admin_site() -> AdminSite:
    """Return admin site."""
    return AdminSite()


@pytest.fixture
def request_factory() -> RequestFactory:
    """Return request factory."""
    return RequestFactory()


@pytest.fixture
def admin_credential_type(admin_site: AdminSite) -> CredentialTypeAdmin:
    """Return CredentialType admin instance."""
    return CredentialTypeAdmin(CredentialType, admin_site)


@pytest.fixture
def admin_credential_config(admin_site: AdminSite) -> CredentialConfigurationAdmin:
    """Return CredentialConfiguration admin instance."""
    return CredentialConfigurationAdmin(CredentialConfiguration, admin_site)


@pytest.fixture
def admin_credential(admin_site: AdminSite) -> CredentialAdmin:
    """Return Credential admin instance."""
    return CredentialAdmin(Credential, admin_site)


@pytest.fixture
def admin_credential_asset(admin_site: AdminSite) -> CredentialAssetAdmin:
    """Return CredentialAsset admin instance."""
    return CredentialAssetAdmin(CredentialAsset, admin_site)


@pytest.fixture(autouse=True)
def patch_compat_functions(monkeypatch: pytest.MonkeyPatch):
    """Patch Open edX compatibility functions used in learning_credentials.compat."""
    monkeypatch.setattr('learning_credentials.models.get_learning_context_name', lambda _: "Test Course")


class TestDocstringOptionsMixin:
    """Tests for DocstringOptionsMixin."""

    def test_get_docstring_custom_options(self):
        """Test extraction of Options section from docstring."""

        def mock_func():
            """
            Some description.

            Options:
                - option1: Description 1
                - option2: Description 2
            """

        with patch('learning_credentials.admin.importlib.import_module') as mock_import:
            mock_module = Mock()
            mock_module.mock_func = mock_func
            mock_import.return_value = mock_module

            result = DocstringOptionsMixin._get_docstring_custom_options('some_module.mock_func')

            assert 'Custom options:' in result
            assert 'option1' in result
            assert '<pre>' in result

    def test_get_docstring_custom_options_without_options(self):
        """Test fallback message when Options section is not found."""

        def mock_func():
            """Some description without options."""

        with patch('learning_credentials.admin.importlib.import_module') as mock_import:
            mock_module = Mock()
            mock_module.mock_func = mock_func
            mock_import.return_value = mock_module

            result = DocstringOptionsMixin._get_docstring_custom_options('some_module.mock_func')

            assert 'Custom options are not documented' in result


@pytest.mark.django_db
class TestCredentialTypeAdminForm:
    """Tests for CredentialTypeAdminForm."""

    def test_form_initializes_with_function_choices(self):
        """Test that the form initializes with available function choices."""
        form = CredentialTypeAdminForm()

        retrieval_choices = list(form.fields['retrieval_func'].choices)
        generation_choices = list(form.fields['generation_func'].choices)

        assert len(retrieval_choices) > 0
        assert len(generation_choices) > 0
        assert any('retrieve_' in choice[0] for choice in retrieval_choices)
        assert any('generate_' in choice[0] for choice in generation_choices)

    def test_form_with_existing_instance_shows_help_text(self, grade_credential_type: CredentialType):
        """Test that form shows help text for existing instance functions."""
        form = CredentialTypeAdminForm(instance=grade_credential_type)

        assert form.fields['retrieval_func'].help_text is not None
        assert form.fields['generation_func'].help_text is not None

    def test_available_functions_returns_prefixed_functions(self):
        """Test that _available_functions returns only functions with specified prefix."""
        functions = list(CredentialTypeAdminForm._available_functions('learning_credentials.processors', 'retrieve_'))

        assert len(functions) > 0
        for func_path, _ in functions:
            assert 'retrieve_' in func_path


@pytest.mark.django_db
class TestCredentialConfigurationForm:
    """Tests for CredentialConfigurationForm."""

    def test_form_initializes_without_instance(self):
        """Test that form initializes correctly without an instance."""
        form = CredentialConfigurationForm()

        assert 'custom_options' in form.fields

    def test_form_with_instance_shows_options_help_text(self, grade_config: CredentialConfiguration):
        """Test that form shows combined options help text for existing configuration."""
        form = CredentialConfigurationForm(instance=grade_config)

        help_text = form.fields['custom_options'].help_text
        assert 'Generation options' in help_text or 'Retrieval options' in help_text

    def test_form_with_instance_without_generation_func(self):
        """Test form when credential type has no generation_func."""
        credential_type = CredentialType.objects.create(
            name="No Generation Func Type",
            retrieval_func="learning_credentials.processors.retrieve_completions",
            generation_func="",
        )
        config = CredentialConfiguration.objects.create(
            learning_context_key="course-v1:Test+T101+2024",
            credential_type=credential_type,
        )

        form = CredentialConfigurationForm(instance=config)

        help_text = form.fields['custom_options'].help_text
        assert 'Retrieval options' in help_text
        assert 'Generation options' not in help_text

    def test_form_with_instance_without_retrieval_func(self):
        """Test form when credential type has no retrieval_func."""
        credential_type = CredentialType.objects.create(
            name="No Retrieval Func Type",
            retrieval_func="",
            generation_func="learning_credentials.generators.generate_pdf_credential",
        )
        config = CredentialConfiguration.objects.create(
            learning_context_key="course-v1:Test+T102+2024",
            credential_type=credential_type,
        )

        form = CredentialConfigurationForm(instance=config)

        help_text = form.fields['custom_options'].help_text
        assert 'Generation options' in help_text
        assert 'Retrieval options' not in help_text

    def test_clean_learning_context_key_valid_course_key(self):
        """Test that valid course key passes validation."""
        form = CredentialConfigurationForm(
            data={
                'learning_context_key': 'course-v1:TestOrg+Test101+2024',
                'credential_type': None,
                'custom_options': '{}',
            }
        )
        form.is_valid()

        cleaned = form.clean_learning_context_key()
        assert cleaned == 'course-v1:TestOrg+Test101+2024'

    def test_clean_learning_context_key_valid_learning_path_key(self):
        """Test that valid learning path key passes validation."""
        form = CredentialConfigurationForm(
            data={
                'learning_context_key': 'path-v1:TestOrg+Test101+2024+Group',
                'credential_type': None,
                'custom_options': '{}',
            }
        )
        form.is_valid()

        cleaned = form.clean_learning_context_key()
        assert cleaned == 'path-v1:TestOrg+Test101+2024+Group'

    def test_clean_learning_context_key_invalid_key(self):
        """Test that invalid key raises ValidationError."""
        form = CredentialConfigurationForm(
            data={
                'learning_context_key': 'invalid-key-format',
                'credential_type': None,
                'custom_options': '{}',
            }
        )
        form.is_valid()

        with pytest.raises(ValidationError) as exc:
            form.clean_learning_context_key()

        assert 'Invalid key format' in str(exc.value)


@pytest.mark.django_db
class TestCredentialConfigurationAdmin:
    """Tests for CredentialConfigurationAdmin."""

    def test_get_inline_instances_on_add_view(
        self, admin_credential_config: CredentialConfigurationAdmin, request_factory: RequestFactory, staff_user: User
    ):
        """Test that inlines are hidden on the add view."""
        request = request_factory.get('/admin/learning_credentials/credentialconfiguration/add/')
        request.user = staff_user

        inlines = admin_credential_config.get_inline_instances(request, obj=None)

        assert inlines == []

    def test_get_inline_instances_on_change_view_calls_super(
        self,
        admin_credential_config: CredentialConfigurationAdmin,
        request_factory: RequestFactory,
        staff_user: User,
        grade_config: CredentialConfiguration,
    ):
        """Test that inlines call super() on the change view (not add view)."""
        request = request_factory.get(f'/admin/learning_credentials/credentialconfiguration/{grade_config.pk}/change/')
        request.user = staff_user

        with patch.object(
            CredentialConfigurationAdmin.__bases__[1],  # ReverseModelAdmin
            'get_inline_instances',
            return_value=['mock_inline'],
        ) as mock_super:
            inlines = admin_credential_config.get_inline_instances(request, obj=grade_config)

            mock_super.assert_called_once_with(request, grade_config)
            assert inlines == ['mock_inline']

    def test_enabled_returns_periodic_task_status(
        self, admin_credential_config: CredentialConfigurationAdmin, grade_config: CredentialConfiguration
    ):
        """Test that enabled() returns the periodic task enabled status."""
        grade_config.periodic_task.enabled = True
        grade_config.periodic_task.save()

        assert admin_credential_config.enabled(grade_config) is True

        grade_config.periodic_task.enabled = False
        grade_config.periodic_task.save()

        assert admin_credential_config.enabled(grade_config) is False

    def test_interval_returns_periodic_task_interval(
        self, admin_credential_config: CredentialConfigurationAdmin, grade_config: CredentialConfiguration
    ):
        """Test that interval() returns the periodic task interval."""
        result = admin_credential_config.interval(grade_config)

        assert result == grade_config.periodic_task.interval

    def test_get_readonly_fields_for_new_object(
        self, admin_credential_config: CredentialConfigurationAdmin, request_factory: RequestFactory, staff_user: User
    ):
        """Test that readonly_fields returns default for new object."""
        request = request_factory.get('/admin/')
        request.user = staff_user

        readonly = admin_credential_config.get_readonly_fields(request, obj=None)

        assert 'learning_context_key' not in readonly
        assert 'credential_type' not in readonly

    def test_get_readonly_fields_for_existing_object(
        self,
        admin_credential_config: CredentialConfigurationAdmin,
        request_factory: RequestFactory,
        staff_user: User,
        grade_config: CredentialConfiguration,
    ):
        """Test that readonly_fields includes key fields for existing object."""
        request = request_factory.get('/admin/')
        request.user = staff_user

        readonly = admin_credential_config.get_readonly_fields(request, obj=grade_config)

        assert 'learning_context_key' in readonly
        assert 'credential_type' in readonly

    @patch('learning_credentials.admin.generate_credentials_for_config_task')
    def test_generate_credentials_action(
        self,
        mock_task: Mock,
        admin_credential_config: CredentialConfigurationAdmin,
        request_factory: RequestFactory,
        staff_user: User,
        grade_config: CredentialConfiguration,
    ):
        """Test that generate_credentials action triggers the task."""
        request = request_factory.post('/admin/')
        request.user = staff_user

        admin_credential_config.generate_credentials(request, grade_config)

        mock_task.delay.assert_called_once_with(grade_config.id)


@pytest.mark.django_db
class TestCredentialAdmin:
    """Tests for CredentialAdmin."""

    def test_add_button_not_displayed(self, admin_credential: CredentialAdmin):
        """Test that the add button is not displayed."""
        assert not admin_credential.has_add_permission(Mock())

    def test_delete_button_not_displayed(self, admin_credential: CredentialAdmin):
        """Test that the delete button is not displayed."""
        assert not admin_credential.has_delete_permission(Mock())

    def test_url(self, admin_credential: CredentialAdmin, credential: Credential):
        """Test that url() returns a clickable link when download_url is set."""
        result = admin_credential.url(credential)

        assert '<a href=' in result
        assert 'http://example.com/credential.pdf' in result

    def test_url_without_download_url(self, admin_credential: CredentialAdmin, credential: Credential):
        """Test that url() returns '-' when download_url is not set."""
        credential.download_url = ""
        credential.save()

        result = admin_credential.url(credential)

        assert result == "-"

    def test_get_form_hides_download_url(
        self, admin_credential: CredentialAdmin, request_factory: RequestFactory, staff_user: User
    ):
        """Test that get_form() hides the download_url field."""
        request = request_factory.get('/admin/')
        request.user = staff_user

        form = admin_credential.get_form(request, obj=None)

        assert form.base_fields['download_url'].widget.__class__.__name__ == 'HiddenInput'

    def test_reissue_credential_action_displayed(self, admin_credential: CredentialAdmin, credential: Credential):
        """Test that reissue_credential action is shown for non-invalidated credentials."""
        actions = admin_credential.get_change_actions(Mock(), str(credential.pk), '')

        assert 'reissue_credential' in actions

    def test_reissue_credential_action_hidden_for_invalidated(
        self, admin_credential: CredentialAdmin, credential: Credential
    ):
        """Test that reissue_credential action is hidden for invalidated credentials."""
        credential.status = Credential.Status.INVALIDATED
        credential.save()

        actions = admin_credential.get_change_actions(Mock(), str(credential.pk), '')

        assert 'reissue_credential' not in actions

    @pytest.mark.usefixtures("patch_send_email")
    def test_reissue_credential_action(
        self,
        admin_credential: CredentialAdmin,
        request_factory: RequestFactory,
        staff_user: User,
        credential: Credential,
    ):
        """Test that reissue_credential action creates a new credential."""
        request = request_factory.post('/admin/')
        request.user = staff_user
        request._messages = Mock()

        with patch('learning_credentials.admin.reverse', return_value='/admin/credential/1/change/'):
            admin_credential.reissue_credential(request, credential)

        credential.refresh_from_db()
        assert credential.status == Credential.Status.INVALIDATED

        request._messages.add.assert_called()
        call_args = request._messages.add.call_args
        assert call_args[0][0] == messages.SUCCESS


@pytest.mark.django_db
class TestCredentialAssetAdmin:
    """Tests for CredentialAssetAdmin."""

    def test_list_display(self, admin_credential_asset: CredentialAssetAdmin):
        """Test that list_display includes expected fields."""
        assert 'description' in admin_credential_asset.list_display
        assert 'asset_slug' in admin_credential_asset.list_display

    def test_prepopulated_fields(self, admin_credential_asset: CredentialAssetAdmin):
        """Test that asset_slug is prepopulated from description."""
        assert admin_credential_asset.prepopulated_fields == {"asset_slug": ("description",)}
