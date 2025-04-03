"""Admin page configuration for the learning-credentials app."""

from __future__ import annotations

import importlib
import inspect
from typing import TYPE_CHECKING

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django_object_actions import DjangoObjectActions, action
from django_reverse_admin import ReverseModelAdmin
from learning_paths.keys import LearningPathKey
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

from .models import (
    Credential,
    CredentialAsset,
    CredentialConfiguration,
    CredentialType,
)
from .tasks import generate_credentials_for_config_task

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Generator

    from django.http import HttpRequest
    from django_celery_beat.models import IntervalSchedule


class DocstringOptionsMixin:
    """A mixin to add the docstring of the function to the help text of the function field."""

    @staticmethod
    def _get_docstring_custom_options(func: str) -> str:
        """
        Get the docstring of the function and return the "Options:" section.

        :param func: The function to get the docstring for.
        :returns: The "Options:" section of the docstring.
        """
        try:
            docstring = (
                'Custom options:'
                + inspect.getdoc(
                    getattr(
                        importlib.import_module(func.rsplit('.', 1)[0]),
                        func.rsplit('.', 1)[1],
                    ),
                ).split("Options:")[1]
            )
        except IndexError:
            docstring = (
                'Custom options are not documented for this function. If you selected a different function, '
                'you need to save your changes to see an updated docstring.'
            )
        # Use pre to preserve the newlines and indentation.
        return f'<pre>{docstring}</pre>'


class CredentialTypeAdminForm(forms.ModelForm, DocstringOptionsMixin):
    """Generate a list of available functions for the function fields."""

    retrieval_func = forms.ChoiceField(choices=[])
    generation_func = forms.ChoiceField(choices=[])

    @staticmethod
    def _available_functions(module: str, prefix: str) -> Generator[tuple[str, str], None, None]:
        """
        Import a module and return all functions in it that start with a specific prefix.

        :param module: The name of the module to import.
        :param prefix: The prefix of the function names to return.

        :return: A tuple containing the functions that start with the prefix in the module.
        """
        # TODO: Implement plugin support for the functions.
        _module = importlib.import_module(module)
        return (
            (f'{obj.__module__}.{name}', f'{obj.__module__}.{name}')
            for name, obj in inspect.getmembers(_module, inspect.isfunction)
            if name.startswith(prefix)
        )

    def __init__(self, *args, **kwargs):
        """Initializes the choices for the retrieval and generation function selection fields."""
        super().__init__(*args, **kwargs)
        self.fields['retrieval_func'].choices = self._available_functions(
            'learning_credentials.processors',
            'retrieve_',
        )
        if self.instance.retrieval_func:
            self.fields['retrieval_func'].help_text = self._get_docstring_custom_options(self.instance.retrieval_func)
        self.fields['generation_func'].choices = self._available_functions(
            'learning_credentials.generators',
            'generate_',
        )
        if self.instance.generation_func:
            self.fields['generation_func'].help_text = self._get_docstring_custom_options(self.instance.generation_func)

    class Meta:  # noqa: D106
        model = CredentialType
        fields = '__all__'  # noqa: DJ007


@admin.register(CredentialType)
class CredentialTypeAdmin(admin.ModelAdmin):  # noqa: D101
    form = CredentialTypeAdminForm
    list_display = ('name', 'retrieval_func', 'generation_func')


@admin.register(CredentialAsset)
class CredentialAssetAdmin(admin.ModelAdmin):  # noqa: D101
    list_display = ('description', 'asset_slug')
    prepopulated_fields = {"asset_slug": ("description",)}  # noqa: RUF012


class CredentialConfigurationForm(forms.ModelForm, DocstringOptionsMixin):  # noqa: D101
    class Meta:  # noqa: D106
        model = CredentialConfiguration
        fields = ('learning_context_key', 'credential_type', 'custom_options')

    def __init__(self, *args, **kwargs):
        """Initializes the choices for the retrieval and generation function selection fields."""
        super().__init__(*args, **kwargs)
        options = ''

        if self.instance and getattr(self.instance, 'credential_type', None):
            if self.instance.credential_type.generation_func:
                generation_options = self._get_docstring_custom_options(self.instance.credential_type.generation_func)
                options += generation_options.replace('Custom options:', '\nGeneration options:')
            if self.instance.credential_type.retrieval_func:
                retrieval_options = self._get_docstring_custom_options(self.instance.credential_type.retrieval_func)
                options += retrieval_options.replace('Custom options:', '\nRetrieval options:')

            self.fields['custom_options'].help_text += options

    def clean_learning_context_key(self) -> str:
        """Validate the learning_context_key field to ensure it is a valid CourseKey or LearningPathKey."""
        learning_context_key = self.cleaned_data.get('learning_context_key')
        try:
            try:
                CourseKey.from_string(learning_context_key)
            except InvalidKeyError:
                LearningPathKey.from_string(learning_context_key)
        except InvalidKeyError as exc:
            msg = (
                "Invalid key format. Must be either a valid course key ('course-v1:{org}+{course}+{run}') "
                "or a valid Learning Path key ('path-v1:{org}+{number}+{run}+{group}')."
            )
            raise ValidationError(msg) from exc
        return learning_context_key


@admin.register(CredentialConfiguration)
class CredentialConfigurationAdmin(DjangoObjectActions, ReverseModelAdmin):
    """
    Admin page for the context-specific credential configuration for each credential type.

    It manages the associations between configuration and its corresponding periodic task.
    The reverse inline provides a way to manage the periodic task from the configuration page.
    """

    form = CredentialConfigurationForm
    inline_type = 'stacked'
    inline_reverse = [  # noqa: RUF012
        (
            'periodic_task',
            {'fields': ['enabled', 'interval', 'crontab', 'clocked', 'start_time', 'expires', 'one_off']},
        ),
    ]
    list_display = ('learning_context_key', 'credential_type', 'enabled', 'interval')
    search_fields = ('learning_context_key', 'credential_type__name')
    list_filter = ('learning_context_key', 'credential_type')

    def get_inline_instances(
        self,
        request: HttpRequest,
        obj: CredentialConfiguration = None,
    ) -> list[admin.ModelAdmin]:
        """
        Hide inlines on the "Add" view in Django admin, and show them on the "Change" view.

        It differentiates "add" and change "view" based on the requested path because the `obj` parameter can be `None`
        in the "Change" view when rendering the inlines.

        :param request: HttpRequest object
        :param obj: The object being changed, None for add view
        :return: A list of InlineModelAdmin instances to be rendered for add/changing an object
        """
        return super().get_inline_instances(request, obj) if '/add/' not in request.path else []

    def enabled(self, obj: CredentialConfiguration) -> bool:
        """Return the 'enabled' status of the periodic task."""
        return obj.periodic_task.enabled

    enabled.boolean = True

    # noinspection PyMethodMayBeStatic
    def interval(self, obj: CredentialConfiguration) -> IntervalSchedule:
        """Return the interval of the credentialedential generation task."""
        return obj.periodic_task.interval

    def get_readonly_fields(self, _request: HttpRequest, obj: CredentialConfiguration = None) -> tuple:
        """Make the learning_context_key field read-only."""
        if obj:  # editing an existing object
            return *self.readonly_fields, 'learning_context_key', 'credential_type'
        return self.readonly_fields

    @action(label="Generate credentials")
    def generate_credentials(self, _request: HttpRequest, obj: CredentialConfiguration):
        """
        Custom action to generate credential for the current CredentialConfiguration instance.

        Args:
            _request: The request object.
            obj: The CredentialConfiguration instance.
        """
        generate_credentials_for_config_task.delay(obj.id)

    change_actions = ('generate_credentials',)


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):  # noqa: D101
    list_display = (
        'user_id',
        'user_full_name',
        'learning_context_key',
        'credential_type',
        'status',
        'url',
        'created',
        'modified',
    )
    readonly_fields = (
        'user_id',
        'created',
        'modified',
        'user_full_name',
        'learning_context_key',
        'credential_type',
        'status',
        'url',
        'legacy_id',
        'generation_task_id',
    )
    search_fields = ("learning_context_key", "user_id", "user_full_name")
    list_filter = ("learning_context_key", "credential_type", "status")

    def get_form(self, request: HttpRequest, obj: Credential | None = None, **kwargs) -> forms.ModelForm:
        """Hide the download_url field."""
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['download_url'].widget = forms.HiddenInput()
        return form

    # noinspection PyMethodMayBeStatic
    def url(self, obj: Credential) -> str:
        """Display the download URL as a clickable link."""
        if obj.download_url:
            return format_html("<a href='{url}'>{url}</a>", url=obj.download_url)
        return "-"
