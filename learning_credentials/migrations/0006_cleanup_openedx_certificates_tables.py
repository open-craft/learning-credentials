# Clean up legacy `openedx_certificates` tables.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("learning_credentials", "0005_rename_processors_and_generators"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP TABLE IF EXISTS openedx_certificates_externalcertificate;",
                "DROP TABLE IF EXISTS openedx_certificates_externalcertificateasset;",
                "DROP TABLE IF EXISTS openedx_certificates_externalcertificatecourseconfiguration;",
                "DROP TABLE IF EXISTS openedx_certificates_externalcertificatetype;",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
