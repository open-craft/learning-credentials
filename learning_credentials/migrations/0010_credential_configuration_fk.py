from django.db import migrations, models
import django.db.models.deletion


def populate_configuration_fk(apps, schema_editor):
    """
    Populate the configuration FK by finding the matching CredentialConfiguration.
    """
    Credential = apps.get_model("learning_credentials", "Credential")
    CredentialConfiguration = apps.get_model("learning_credentials", "CredentialConfiguration")

    for credential in Credential.objects.all():
        try:
            config = CredentialConfiguration.objects.get(
                learning_context_key=credential.learning_context_key,
                credential_type__name=credential.credential_type,
            )
            credential.configuration = config
            credential.save(update_fields=["configuration"])
        except CredentialConfiguration.DoesNotExist:
            # If no matching configuration exists, we cannot migrate this credential.
            # This should not happen in normal circumstances.
            raise ValueError(
                f"No CredentialConfiguration found for Credential {credential.uuid} "
                f"with learning_context_key={credential.learning_context_key} "
                f"and credential_type={credential.credential_type}"
            )


def reverse_populate_configuration_fk(apps, schema_editor):
    """Reverse migration: populate credential_type and learning_context_key from configuration."""
    Credential = apps.get_model("learning_credentials", "Credential")

    for credential in Credential.objects.select_related("configuration__credential_type").all():
        credential.credential_type = credential.configuration.credential_type.name
        credential.learning_context_key = credential.configuration.learning_context_key
        credential.save(update_fields=["credential_type", "learning_context_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("learning_credentials", "0009_credential_user_fk"),
    ]

    operations = [
        # Add the new configuration FK field (nullable initially).
        migrations.AddField(
            model_name="credential",
            name="configuration",
            field=models.ForeignKey(
                help_text="Associated credential configuration",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="learning_credentials.credentialconfiguration",
            ),
        ),
        # Populate the configuration FK from credential_type and learning_context_key.
        migrations.RunPython(populate_configuration_fk, reverse_code=reverse_populate_configuration_fk),
        # Make the configuration FK non-nullable
        migrations.AlterField(
            model_name="credential",
            name="configuration",
            field=models.ForeignKey(
                help_text="Associated credential configuration",
                on_delete=django.db.models.deletion.PROTECT,
                to="learning_credentials.credentialconfiguration",
            ),
        )
    ]
