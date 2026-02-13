from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def populate_user_fk(apps, schema_editor):
    """Copy user_id values to the new user FK field."""
    Credential = apps.get_model("learning_credentials", "Credential")
    for credential in Credential.objects.all():
        credential.user_id = credential.user_id_old
        credential.save(update_fields=["user_id"])


def reverse_populate_user_fk(apps, schema_editor):
    """Copy user FK values back to user_id_old."""
    Credential = apps.get_model("learning_credentials", "Credential")
    for credential in Credential.objects.all():
        credential.user_id_old = credential.user_id
        credential.save(update_fields=["user_id_old"])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("learning_credentials", "0008_validation"),
    ]

    operations = [
        # Rename the old user_id field to user_id_old.
        migrations.RenameField(
            model_name="credential",
            old_name="user_id",
            new_name="user_id_old",
        ),
        # Add the new user FK field (nullable initially).
        migrations.AddField(
            model_name="credential",
            name="user",
            field=models.ForeignKey(
                help_text="User receiving the credential",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Populate the user FK from user_id_old.
        migrations.RunPython(populate_user_fk, reverse_code=reverse_populate_user_fk),
        # Make the user FK non-nullable.
        migrations.AlterField(
            model_name="credential",
            name="user",
            field=models.ForeignKey(
                help_text="User receiving the credential",
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Remove the old user_id_old field.
        migrations.RemoveField(
            model_name="credential",
            name="user_id_old",
        ),
    ]
