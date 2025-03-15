from django.db import migrations, models
import django.utils.timezone
import jsonfield.fields
import opaque_keys.edx.django.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('django_celery_beat', '0019_alter_periodictasks_options'),
        ('learning_credentials', '0002_migrate_to_learning_credentials'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ExternalCertificateCourseConfiguration',
            new_name='CredentialConfiguration',
        ),
        migrations.RenameModel(
            old_name='ExternalCertificateAsset',
            new_name='CredentialAsset',
        ),
        migrations.RenameModel(
            old_name='ExternalCertificateType',
            new_name='CredentialType',
        ),
        migrations.RenameModel(
            old_name='ExternalCertificate',
            new_name='Credential',
        ),
        migrations.RenameField(
            model_name='Credential',
            old_name='certificate_type',
            new_name='credential_type',
        ),
        migrations.RenameField(
            model_name='CredentialConfiguration',
            old_name='certificate_type',
            new_name='credential_type',
        ),
        migrations.AlterField(
            model_name='credential',
            name='course_id',
            field=opaque_keys.edx.django.models.CourseKeyField(
                help_text='ID of a course for which the credential was issued', max_length=255
            ),
        ),
        migrations.AlterField(
            model_name='credential',
            name='credential_type',
            field=models.CharField(help_text='Type of the credential', max_length=255),
        ),
        migrations.AlterField(
            model_name='credential',
            name='download_url',
            field=models.URLField(blank=True, help_text='URL of the generated credential PDF (e.g., to S3)'),
        ),
        migrations.AlterField(
            model_name='credential',
            name='legacy_id',
            field=models.IntegerField(help_text='Legacy ID of the credential imported from another system', null=True),
        ),
        migrations.AlterField(
            model_name='credential',
            name='status',
            field=models.CharField(
                choices=[
                    ('generating', 'Generating'),
                    ('available', 'Available'),
                    ('error', 'Error'),
                    ('invalidated', 'Invalidated'),
                ],
                default='generating',
                help_text='Status of the credential generation task',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='credential',
            name='user_full_name',
            field=models.CharField(help_text='User receiving the credential', max_length=255),
        ),
        migrations.AlterField(
            model_name='credential',
            name='user_id',
            field=models.IntegerField(help_text='ID of the user receiving the credential'),
        ),
        migrations.AlterField(
            model_name='credential',
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text='Auto-generated UUID of the credential',
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name='credentialconfiguration',
            name='credential_type',
            field=models.ForeignKey(
                help_text='Associated credential type.',
                on_delete=django.db.models.deletion.CASCADE,
                to='learning_credentials.credentialtype',
            ),
        ),
        migrations.AlterField(
            model_name='credentialconfiguration',
            name='custom_options',
            field=jsonfield.fields.JSONField(
                blank=True,
                default=dict,
                help_text='Custom options for the functions. If specified, they are merged with the options defined in the credential type.',
            ),
        ),
        migrations.AlterField(
            model_name='credentialtype',
            name='generation_func',
            field=models.CharField(help_text='A name of the function to generate credentials.', max_length=200),
        ),
        migrations.AlterField(
            model_name='credentialtype',
            name='name',
            field=models.CharField(help_text='Name of the credential type.', max_length=255, unique=True),
        ),
    ]
