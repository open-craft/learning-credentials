from django.db import migrations


def update_function_references_and_json_keys(apps, schema_editor):
    """
    Update both function references and JSON field keys:
    1. Replace 'openedx_certificates' prefix with 'learning_credentials'.
    2. Replace 'retrieve_course_completions' with 'retrieve_completions'.
    3. Replace JSON keys 'course_name*' with 'context_name*'.
    4. Replace the task path in PeriodicTask records.
    """
    CredentialType = apps.get_model('learning_credentials', 'CredentialType')
    CredentialConfiguration = apps.get_model('learning_credentials', 'CredentialConfiguration')

    for credential_type in CredentialType.objects.all():
        credential_type.retrieval_func = credential_type.retrieval_func.replace(
            'openedx_certificates', 'learning_credentials'
        ).replace(
            'retrieve_course_completions', 'retrieve_completions'
        )

        credential_type.generation_func = credential_type.generation_func.replace(
            'openedx_certificates', 'learning_credentials'
        ).replace(
            'generate_pdf_certificate', 'generate_pdf_credential'
        )

        if credential_type.custom_options:
            if 'course_name' in credential_type.custom_options:
                credential_type.custom_options['context_name'] = credential_type.custom_options.pop('course_name')
            if 'course_name_y' in credential_type.custom_options:
                credential_type.custom_options['context_name_y'] = credential_type.custom_options.pop('course_name_y')
            if 'course_name_color' in credential_type.custom_options:
                credential_type.custom_options['context_name_color'] = credential_type.custom_options.pop('course_name_color')

        credential_type.save()

    for config in CredentialConfiguration.objects.all():
        if config.custom_options:
            if 'course_name' in config.custom_options:
                config.custom_options['context_name'] = config.custom_options.pop('course_name')
            if 'course_name_y' in config.custom_options:
                config.custom_options['context_name_y'] = config.custom_options.pop('course_name_y')
            if 'course_name_color' in config.custom_options:
                config.custom_options['context_name_color'] = config.custom_options.pop('course_name_color')

        if config.periodic_task.task == 'openedx_certificates.tasks.generate_certificates_for_course_task':
            config.periodic_task.task = 'learning_credentials.tasks.generate_credentials_for_config_task'
            config.periodic_task.save()

        config.save()


def reverse_function_references_and_json_keys(apps, schema_editor):
    """Reverse the changes made to function references and JSON keys."""
    CredentialType = apps.get_model('learning_credentials', 'CredentialType')
    CredentialConfiguration = apps.get_model('learning_credentials', 'CredentialConfiguration')

    for credential_type in CredentialType.objects.all():
        credential_type.retrieval_func = credential_type.retrieval_func.replace(
            'learning_credentials', 'openedx_certificates'
        ).replace(
            'retrieve_completions', 'retrieve_course_completions'
        )

        credential_type.generation_func = credential_type.generation_func.replace(
            'learning_credentials', 'openedx_certificates'
        ).replace(
            'generate_pdf_credential', 'generate_pdf_certificate'
        )

        if credential_type.custom_options:
            if 'context_name' in credential_type.custom_options:
                credential_type.custom_options['course_name'] = credential_type.custom_options.pop('context_name')
            if 'context_name_y' in credential_type.custom_options:
                credential_type.custom_options['course_name_y'] = credential_type.custom_options.pop('context_name_y')
            if 'context_name_color' in credential_type.custom_options:
                credential_type.custom_options['course_name_color'] = credential_type.custom_options.pop('context_name_color')

        credential_type.save()

    for config in CredentialConfiguration.objects.all():
        if config.custom_options:
            if 'context_name' in config.custom_options:
                config.custom_options['course_name'] = config.custom_options.pop('context_name')
            if 'context_name_y' in config.custom_options:
                config.custom_options['course_name_y'] = config.custom_options.pop('context_name_y')
            if 'context_name_color' in config.custom_options:
                config.custom_options['course_name_color'] = config.custom_options.pop('context_name_color')

        if config.periodic_task.task == 'learning_credentials.tasks.generate_credentials_for_config_task':
            config.periodic_task.task = 'openedx_certificates.tasks.generate_certificates_for_course_task'
            config.periodic_task.save()

        config.save()


class Migration(migrations.Migration):

    dependencies = [
        ('learning_credentials', '0004_replace_course_keys_with_learning_context_keys'),
    ]

    operations = [
        migrations.RunPython(update_function_references_and_json_keys, reverse_function_references_and_json_keys),
    ]
