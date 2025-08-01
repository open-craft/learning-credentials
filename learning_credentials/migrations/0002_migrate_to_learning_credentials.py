from django.db import migrations


def migrate_data_if_tables_exist(apps, schema_editor):
    """Migrate data from openedx_certificates to learning_credentials tables if the source tables exist."""
    connection = schema_editor.connection
    cursor = connection.cursor()
    table_names = connection.introspection.table_names(cursor)

    tables_to_migrate = [
        (
            "openedx_certificates_externalcertificatetype",
            "learning_credentials_externalcertificatetype",
            "id, created, modified, name, retrieval_func, generation_func, custom_options",
        ),
        (
            "openedx_certificates_externalcertificatecourseconfiguration",
            "learning_credentials_externalcertificatecourseconfiguration",
            "id, created, modified, course_id, custom_options, certificate_type_id, periodic_task_id",
        ),
        (
            "openedx_certificates_externalcertificateasset",
            "learning_credentials_externalcertificateasset",
            "id, created, modified, description, asset, asset_slug",
        ),
        (
            "openedx_certificates_externalcertificate",
            "learning_credentials_externalcertificate",
            "uuid, created, modified, user_id, user_full_name, course_id, certificate_type, status, download_url, legacy_id, generation_task_id",
        ),
    ]

    for source_table, target_table, fields in tables_to_migrate:
        if source_table in table_names:
            cursor.execute(f"INSERT INTO {target_table} ({fields}) SELECT {fields} FROM {source_table};")


class Migration(migrations.Migration):
    dependencies = [("learning_credentials", "0001_initial")]
    operations = [migrations.RunPython(migrate_data_if_tables_exist, migrations.RunPython.noop)]
