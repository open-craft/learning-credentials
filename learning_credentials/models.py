"""Database models for learning_credentials."""

from __future__ import annotations

import json
import logging
import uuid
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import jsonfield
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from edx_ace import Message, Recipient, ace
from model_utils.models import TimeStampedModel
from opaque_keys.edx.django.models import LearningContextKeyField

from learning_credentials.compat import get_learning_context_name
from learning_credentials.exceptions import AssetNotFoundError, CredentialGenerationError

if TYPE_CHECKING:  # pragma: no cover
    from django.core.files import File
    from django.db.models import QuerySet


log = logging.getLogger(__name__)


class CredentialType(TimeStampedModel):
    """
    Model to store global credential configurations for each type.

    .. no_pii:
    """

    name = models.CharField(max_length=255, unique=True, help_text=_('Name of the credential type.'))
    retrieval_func = models.CharField(max_length=200, help_text=_('A name of the function to retrieve eligible users.'))
    generation_func = models.CharField(max_length=200, help_text=_('A name of the function to generate credentials.'))
    custom_options = jsonfield.JSONField(default=dict, blank=True, help_text=_('Custom options for the functions.'))

    # TODO: Document how to add custom functions to the credential generation pipeline.

    def __str__(self):
        """Get a string representation of this model's instance."""
        return self.name

    def clean(self):
        """Ensure that the `retrieval_func` and `generation_func` exist."""
        for func_field in ['retrieval_func', 'generation_func']:
            func_path = getattr(self, func_field)
            try:
                # TODO: Move the function retrieval to a method to avoid code duplication.
                module_path, func_name = func_path.rsplit('.', 1)
                module = import_module(module_path)
                getattr(module, func_name)  # Will raise AttributeError if the function does not exist.
            except ValueError as exc:
                raise ValidationError({func_field: "Function path must be in format 'module.function_name'."}) from exc
            except (ImportError, AttributeError) as exc:
                raise ValidationError(
                    {func_field: f"The function {func_path} could not be found. Please provide a valid path."},
                ) from exc


class CredentialConfiguration(TimeStampedModel):
    """
    Model to store context-specific credential configurations for each credential type.

    .. no_pii:
    """

    learning_context_key = LearningContextKeyField(
        max_length=255,
        help_text=_('ID of a learning context (e.g., a course or a Learning Path).'),
    )
    credential_type = models.ForeignKey(
        CredentialType,
        on_delete=models.CASCADE,
        help_text=_('Associated credential type.'),
    )
    periodic_task = models.OneToOneField(
        PeriodicTask,
        on_delete=models.CASCADE,
        help_text=_('Associated periodic task.'),
    )
    custom_options = jsonfield.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            'Custom options for the functions. If specified, they are merged with the options defined in the '
            'credential type.',
        ),
    )

    class Meta:  # noqa: D106
        unique_together = (('learning_context_key', 'credential_type'),)

    def __str__(self):  # noqa: D105
        return f'{self.credential_type.name} in {self.learning_context_key}'

    def save(self, *args, **kwargs):
        """Create a new PeriodicTask every time a new CredentialConfiguration is created."""
        from learning_credentials.tasks import generate_credentials_for_config_task as task  # noqa: PLC0415

        # Use __wrapped__ to get the original function, as the task is wrapped by the @app.task decorator.
        task_path = f"{task.__wrapped__.__module__}.{task.__wrapped__.__name__}"

        if self._state.adding:
            schedule, created = IntervalSchedule.objects.get_or_create(every=10, period=IntervalSchedule.DAYS)
            self.periodic_task = PeriodicTask.objects.create(
                enabled=False,
                interval=schedule,
                name=f'{self.credential_type} in {self.learning_context_key}',
                task=task_path,
            )

        super().save(*args, **kwargs)

        # Update the task on each save to prevent it from getting out of sync (e.g., after changing a task definition).
        self.periodic_task.task = task_path
        # Update the args of the PeriodicTask to include the ID of the CredentialConfiguration.
        self.periodic_task.args = json.dumps([self.id])
        self.periodic_task.save()

    # Replace the return type with `QuerySet[Self]` after migrating to Python 3.10+.
    @classmethod
    def get_enabled_configurations(cls) -> QuerySet[CredentialConfiguration]:
        """
        Get the list of enabled configurations.

        :return: A list of CredentialConfiguration objects.
        """
        return CredentialConfiguration.objects.filter(periodic_task__enabled=True)

    def generate_credentials(self):
        """This method allows manual credential generation from the Django admin."""
        user_ids = self.get_eligible_user_ids()
        log.info("The following users are eligible in %s: %s", self.learning_context_key, user_ids)
        filtered_user_ids = self.filter_out_user_ids_with_credentials(user_ids)
        log.info("The filtered users eligible in %s: %s", self.learning_context_key, filtered_user_ids)
        for user_id in filtered_user_ids:
            self.generate_credential_for_user(user_id)

    def filter_out_user_ids_with_credentials(self, user_ids: list[int]) -> list[int]:
        """
        Filter out user IDs that already have a credential for this course and credential type.

        :param user_ids: A list of user IDs to filter.
        :return: A list of user IDs that either:
                 1. Do not have a credential for this course and credential type.
                 2. Have such a credential with an error status.
        """
        users_ids_with_credentials = Credential.objects.filter(
            models.Q(learning_context_key=self.learning_context_key),
            models.Q(credential_type=self.credential_type),
            ~(models.Q(status=Credential.Status.ERROR)),
        ).values_list('user_id', flat=True)

        filtered_user_ids_set = set(user_ids) - set(users_ids_with_credentials)
        return list(filtered_user_ids_set)

    def get_eligible_user_ids(self) -> list[int]:
        """
        Get the list of eligible learners for the given course.

        :return: A list of user IDs.
        """
        func_path = self.credential_type.retrieval_func
        module_path, func_name = func_path.rsplit('.', 1)
        module = import_module(module_path)
        func = getattr(module, func_name)

        custom_options = {**self.credential_type.custom_options, **self.custom_options}
        return func(self.learning_context_key, custom_options)

    def generate_credential_for_user(self, user_id: int, celery_task_id: int = 0):
        """
        Celery task for processing a single user's credential.

        This function retrieves an CredentialConfiguration object based on context ID and credential type,
        retrieves the data using the retrieval_func specified in the associated CredentialType object,
        and passes this data to the function specified in the generation_func field.

        Args:
            user_id: The ID of the user to process the credential for.
            celery_task_id (optional): The ID of the Celery task that is running this function.
        """
        user = get_user_model().objects.get(id=user_id)
        # Use the name from the profile if it is not empty. Otherwise, use the first and last name.
        # We check if the profile exists because it may not exist in some cases (e.g., when a User is created manually).
        user_full_name = getattr(getattr(user, 'profile', None), 'name', f"{user.first_name} {user.last_name}")
        custom_options = {**self.credential_type.custom_options, **self.custom_options}

        credential, _ = Credential.objects.update_or_create(
            user_id=user_id,
            learning_context_key=self.learning_context_key,
            credential_type=self.credential_type.name,
            defaults={
                'user_full_name': user_full_name,
                'status': Credential.Status.GENERATING,
                'generation_task_id': celery_task_id,
            },
        )

        try:
            generation_module_name, generation_func_name = self.credential_type.generation_func.rsplit('.', 1)
            generation_module = import_module(generation_module_name)
            generation_func = getattr(generation_module, generation_func_name)

            # Run the functions. We do not validate them here, as they are validated in the model's clean() method.
            credential.download_url = generation_func(self.learning_context_key, user, credential.uuid, custom_options)
            credential.status = Credential.Status.AVAILABLE
            credential.save()
        except Exception as exc:
            credential.status = Credential.Status.ERROR
            credential.save()
            msg = f'Failed to generate the {credential.uuid=} for {user_id=} with {self.id=}.'
            raise CredentialGenerationError(msg) from exc
        else:
            # TODO: In the future, we want to check this before generating the credential.
            #       Perhaps we could even include this in a processor to optimize it.
            if user.is_active and user.has_usable_password():
                credential.send_email()


# noinspection PyUnusedLocal
@receiver(post_delete, sender=CredentialConfiguration)
def post_delete_periodic_task(sender, instance, *_args, **_kwargs):  # noqa: ANN001, ARG001
    """Delete the associated periodic task when the object is deleted."""
    if instance.periodic_task:
        instance.periodic_task.delete()


class Credential(TimeStampedModel):
    """
    Model to represent each credential awarded to a user for a course.

    This model contains information about the related course, the user who earned the credential,
    the download URL for the credential PDF, and the associated credential generation task.

    .. note:: Credentials are identified by UUIDs rather than integer keys to prevent enumeration attacks
       or privacy leaks.

    .. pii: The User's name is stored in this model.
    .. pii_types: id, name
    .. pii_retirement: retained
    """

    class Status(models.TextChoices):
        """Status of the credential generation task."""

        GENERATING = 'generating', _('Generating')
        AVAILABLE = 'available', _('Available')
        ERROR = 'error', _('Error')
        INVALIDATED = 'invalidated', _('Invalidated')

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Auto-generated UUID of the credential'),
    )
    user_id = models.IntegerField(help_text=_('ID of the user receiving the credential'))
    user_full_name = models.CharField(max_length=255, help_text=_('User receiving the credential'))
    learning_context_key = LearningContextKeyField(
        max_length=255,
        help_text=_('ID of a learning context (e.g., a course or a Learning Path) for which the credential was issued'),
    )
    credential_type = models.CharField(max_length=255, help_text=_('Type of the credential'))
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.GENERATING,
        help_text=_('Status of the credential generation task'),
    )
    download_url = models.URLField(blank=True, help_text=_('URL of the generated credential PDF (e.g., to S3)'))
    legacy_id = models.IntegerField(null=True, help_text=_('Legacy ID of the credential imported from another system'))
    generation_task_id = models.CharField(max_length=255, help_text=_('Task ID from the Celery queue'))

    class Meta:  # noqa: D106
        unique_together = (('user_id', 'learning_context_key', 'credential_type'),)

    def __str__(self):  # noqa: D105
        return f"{self.credential_type} for {self.user_full_name} in {self.learning_context_key}"

    def send_email(self):
        """Send a credential link to the student."""
        learning_context_name = get_learning_context_name(self.learning_context_key)
        user = get_user_model().objects.get(id=self.user_id)
        msg = Message(
            name="certificate_generated",
            app_label="learning_credentials",
            recipient=Recipient(lms_user_id=user.id, email_address=user.email),
            language='en',
            context={
                'certificate_link': self.download_url,
                'course_name': learning_context_name,
                'platform_name': settings.PLATFORM_NAME,
            },
        )
        ace.send(msg)


class CredentialAsset(TimeStampedModel):
    """
    A set of assets to be used in custom credential templates.

    This model stores assets used during credential generation process, such as PDF templates, images, fonts.

    .. no_pii:
    """

    def template_assets_path(self, filename: str) -> str:
        """
        Delete the file if it already exists and returns the credential template asset file path.

        :param filename: File to upload.
        :return path: Path of asset file e.g. `credential_template_assets/1/filename`.
        """
        name = Path('learning_credentials_template_assets') / str(self.id) / filename
        fullname = Path(settings.MEDIA_ROOT) / name
        if fullname.exists():
            fullname.unlink()
        return str(name)

    description = models.CharField(
        max_length=255,
        null=False,
        blank=True,
        help_text=_('Description of the asset.'),
    )
    asset = models.FileField(
        max_length=255,
        upload_to=template_assets_path,
        help_text=_('Asset file. It could be a PDF template, image or font file.'),
    )
    asset_slug = models.SlugField(
        max_length=255,
        unique=True,
        null=False,
        help_text=_('Asset\'s unique slug. We can reference the asset in templates using this value.'),
    )

    class Meta:  # noqa: D106
        get_latest_by = 'created'

    def __str__(self):  # noqa: D105
        return f'{self.asset.url}'

    def save(self, *args, **kwargs):
        """If the object is being created, save the asset first, then save the object."""
        if self._state.adding:
            asset_image = self.asset
            self.asset = None
            super().save(*args, **kwargs)
            self.asset = asset_image

        super().save(*args, **kwargs)

    @classmethod
    def get_asset_by_slug(cls, asset_slug: str) -> File:
        """
        Fetch a credential template asset by its slug from the database.

        :param asset_slug: The slug of the asset to be retrieved.
        :returns: The file associated with the asset slug.
        :raises AssetNotFound: If no asset exists with the provided slug in the CredentialAsset database model.
        """
        try:
            template_asset = cls.objects.get(asset_slug=asset_slug)
            asset = template_asset.asset
        except cls.DoesNotExist as exc:
            msg = f'Asset with slug {asset_slug} does not exist.'
            raise AssetNotFoundError(msg) from exc
        return asset
