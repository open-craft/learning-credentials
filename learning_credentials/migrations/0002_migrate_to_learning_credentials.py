from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('openedx_certificates', '0001_initial'),
        ('learning_credentials', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "INSERT INTO learning_credentials_externalcertificatetype (id, created, modified, name, retrieval_func, generation_func, custom_options) "
                "SELECT id, created, modified, name, retrieval_func, generation_func, custom_options FROM openedx_certificates_externalcertificatetype;",

                "INSERT INTO learning_credentials_externalcertificatecourseconfiguration (id, created, modified, course_id, custom_options, certificate_type_id, periodic_task_id) "
                "SELECT id, created, modified, course_id, custom_options, certificate_type_id, periodic_task_id FROM openedx_certificates_externalcertificatecourseconfiguration;",

                "INSERT INTO learning_credentials_externalcertificateasset (id, created, modified, description, asset, asset_slug) "
                "SELECT id, created, modified, description, asset, asset_slug FROM openedx_certificates_externalcertificateasset;",

                "INSERT INTO learning_credentials_externalcertificate (uuid, created, modified, user_id, user_full_name, course_id, certificate_type, status, download_url, legacy_id, generation_task_id) "
                "SELECT uuid, created, modified, user_id, user_full_name, course_id, certificate_type, status, download_url, legacy_id, generation_task_id FROM openedx_certificates_externalcertificate;",
            ],
            reverse_sql=[
                "DELETE FROM learning_credentials_externalcertificate;",
                "DELETE FROM learning_credentials_externalcertificatecourseconfiguration;",
                "DELETE FROM learning_credentials_externalcertificateasset;",
                "DELETE FROM learning_credentials_externalcertificatetype;",
            ],
        ),
    ]
