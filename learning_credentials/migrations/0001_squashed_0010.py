from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import jsonfield.fields
import learning_credentials.models
import model_utils.fields
import opaque_keys.edx.django.models
import uuid


class Migration(migrations.Migration):
    replaces = [
        ('learning_credentials', '0001_initial'),
        ('learning_credentials', '0002_migrate_to_learning_credentials'),
        ('learning_credentials', '0003_rename_certificates_to_credentials'),
        ('learning_credentials', '0004_replace_course_keys_with_learning_context_keys'),
        ('learning_credentials', '0005_rename_processors_and_generators'),
        ('learning_credentials', '0006_cleanup_openedx_certificates_tables'),
        ('learning_credentials', '0007_migrate_to_text_elements_format'),
        ('learning_credentials', '0008_validation'),
        ('learning_credentials', '0009_credential_user_fk'),
        ('learning_credentials', '0010_credential_configuration_fk'),
    ]

    initial = True

    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CredentialAsset",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                ("description", models.CharField(blank=True, help_text="Description of the asset.", max_length=255)),
                (
                    "asset",
                    models.FileField(
                        help_text="Asset file. It could be a PDF template, image or font file.",
                        max_length=255,
                        upload_to=learning_credentials.models.CredentialAsset.template_assets_path,
                    ),
                ),
                (
                    "asset_slug",
                    models.SlugField(
                        help_text="Asset's unique slug. We can reference the asset in templates using this value.",
                        max_length=255,
                        unique=True,
                    ),
                ),
            ],
            options={"get_latest_by": "created"},
        ),
        migrations.CreateModel(
            name="CredentialType",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                ("name", models.CharField(help_text="Name of the credential type.", max_length=255, unique=True)),
                (
                    "retrieval_func",
                    models.CharField(help_text="A name of the function to retrieve eligible users.", max_length=200),
                ),
                (
                    "generation_func",
                    models.CharField(help_text="A name of the function to generate credentials.", max_length=200),
                ),
                (
                    "custom_options",
                    jsonfield.fields.JSONField(blank=True, default=dict, help_text="Custom options for the functions."),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="CredentialConfiguration",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "learning_context_key",
                    opaque_keys.edx.django.models.LearningContextKeyField(
                        help_text="ID of a learning context (e.g., a course or a Learning Path).",
                        max_length=255,
                    ),
                ),
                (
                    "custom_options",
                    jsonfield.fields.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Custom options for the functions. If specified, they are merged with the options defined in the credential type.",
                    ),
                ),
                (
                    "credential_type",
                    models.ForeignKey(
                        help_text="Associated credential type.",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="learning_credentials.credentialtype",
                    ),
                ),
                (
                    "periodic_task",
                    models.OneToOneField(
                        help_text="Associated periodic task.",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="django_celery_beat.periodictask",
                    ),
                ),
            ],
            options={"unique_together": {("learning_context_key", "credential_type")}},
        ),
        migrations.CreateModel(
            name="Credential",
            fields=[
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Auto-generated UUID of the credential",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "verify_uuid",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, help_text="UUID used for verifying the credential"
                    ),
                ),
                (
                    "user_full_name",
                    models.CharField(
                        editable=False,
                        help_text="User receiving the credential. This field is used for validation purposes.",
                        max_length=255,
                    ),
                ),
                (
                    "learning_context_name",
                    models.CharField(
                        editable=False,
                        help_text="Name of the learning context for which the credential was issued. This field is used for validation purposes.",
                        max_length=255,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("generating", "Generating"),
                            ("available", "Available"),
                            ("error", "Error"),
                            ("invalidated", "Invalidated"),
                        ],
                        default="generating",
                        help_text="Status of the credential generation task",
                        max_length=32,
                    ),
                ),
                (
                    "download_url",
                    models.URLField(blank=True, help_text="URL of the generated credential PDF (e.g., to S3)"),
                ),
                (
                    "legacy_id",
                    models.IntegerField(
                        help_text="Legacy ID of the credential imported from another system", null=True
                    ),
                ),
                ("generation_task_id", models.CharField(help_text="Task ID from the Celery queue", max_length=255)),
                (
                    "invalidated_at",
                    models.DateTimeField(
                        editable=False, help_text="Timestamp when the credential was invalidated", null=True
                    ),
                ),
                (
                    "invalidation_reason",
                    models.CharField(blank=True, help_text="Reason for invalidating the credential", max_length=255),
                ),
                (
                    "configuration",
                    models.ForeignKey(
                        help_text="Associated credential configuration",
                        on_delete=django.db.models.deletion.PROTECT,
                        to="learning_credentials.credentialconfiguration",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="User receiving the credential",
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"abstract": False},
        ),
    ]
