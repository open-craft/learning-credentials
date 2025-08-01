from django.db import migrations, models
import django.utils.timezone
import jsonfield.fields
import model_utils.fields
import opaque_keys.edx.django.models
import uuid

import learning_credentials.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('django_celery_beat', '0019_alter_periodictasks_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalCertificateAsset',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'created',
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='created'
                    ),
                ),
                (
                    'modified',
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='modified'
                    ),
                ),
                ('description', models.CharField(blank=True, help_text='Description of the asset.', max_length=255)),
                (
                    'asset',
                    models.FileField(
                        help_text='Asset file. It could be a PDF template, image or font file.',
                        max_length=255,
                        upload_to=learning_credentials.models.CredentialAsset.template_assets_path,
                    ),
                ),
                (
                    'asset_slug',
                    models.SlugField(
                        help_text="Asset's unique slug. We can reference the asset in templates using this value.",
                        max_length=255,
                        unique=True,
                    ),
                ),
            ],
            options={
                'get_latest_by': 'created',
            },
        ),
        migrations.CreateModel(
            name='ExternalCertificateType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'created',
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='created'
                    ),
                ),
                (
                    'modified',
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='modified'
                    ),
                ),
                ('name', models.CharField(help_text='Name of the certificate type.', max_length=255, unique=True)),
                (
                    'retrieval_func',
                    models.CharField(help_text='A name of the function to retrieve eligible users.', max_length=200),
                ),
                (
                    'generation_func',
                    models.CharField(help_text='A name of the function to generate certificates.', max_length=200),
                ),
                (
                    'custom_options',
                    jsonfield.fields.JSONField(blank=True, default=dict, help_text='Custom options for the functions.'),
                ),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ExternalCertificate',
            fields=[
                (
                    'created',
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='created'
                    ),
                ),
                (
                    'modified',
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='modified'
                    ),
                ),
                (
                    'uuid',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text='Auto-generated UUID of the certificate',
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('user_id', models.IntegerField(help_text='ID of the user receiving the certificate')),
                ('user_full_name', models.CharField(help_text='User receiving the certificate', max_length=255)),
                (
                    'course_id',
                    opaque_keys.edx.django.models.CourseKeyField(
                        help_text='ID of a course for which the certificate was issued', max_length=255
                    ),
                ),
                ('certificate_type', models.CharField(help_text='Type of the certificate', max_length=255)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('generating', 'Generating'),
                            ('available', 'Available'),
                            ('error', 'Error'),
                            ('invalidated', 'Invalidated'),
                        ],
                        default='generating',
                        help_text='Status of the certificate generation task',
                        max_length=32,
                    ),
                ),
                (
                    'download_url',
                    models.URLField(blank=True, help_text='URL of the generated certificate PDF (e.g., to S3)'),
                ),
                (
                    'legacy_id',
                    models.IntegerField(
                        help_text='Legacy ID of the certificate imported from another system', null=True
                    ),
                ),
                ('generation_task_id', models.CharField(help_text='Task ID from the Celery queue', max_length=255)),
            ],
            options={
                'unique_together': {('user_id', 'course_id', 'certificate_type')},
            },
        ),
        migrations.CreateModel(
            name='ExternalCertificateCourseConfiguration',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'created',
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='created'
                    ),
                ),
                (
                    'modified',
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name='modified'
                    ),
                ),
                (
                    'course_id',
                    opaque_keys.edx.django.models.CourseKeyField(help_text='The ID of the course.', max_length=255),
                ),
                (
                    'custom_options',
                    jsonfield.fields.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Custom options for the functions. If specified, they are merged with the options defined in the certificate type.',
                    ),
                ),
                (
                    'certificate_type',
                    models.ForeignKey(
                        help_text='Associated certificate type.',
                        on_delete=django.db.models.deletion.CASCADE,
                        to='learning_credentials.externalcertificatetype',
                    ),
                ),
                (
                    'periodic_task',
                    models.OneToOneField(
                        help_text='Associated periodic task.',
                        on_delete=django.db.models.deletion.CASCADE,
                        to='django_celery_beat.periodictask',
                    ),
                ),
            ],
            options={
                'unique_together': {('course_id', 'certificate_type')},
            },
        ),
    ]
