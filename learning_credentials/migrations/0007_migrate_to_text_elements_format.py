"""Migration to convert credential options from flat format to text_elements format."""

from django.db import migrations

# Mapping from old option names to new text_elements structure.
# Format: (old_key, element_key, property_name)
_OPTION_MAPPINGS = [
    # Name element mappings.
    ('name_y', 'name', 'y'),
    ('name_color', 'name', 'color'),
    ('name_size', 'name', 'size'),
    ('name_font', 'name', 'font'),
    ('name_uppercase', 'name', 'uppercase'),
    # Context element mappings.
    ('context_name', 'context', 'text'),
    ('context_name_y', 'context', 'y'),
    ('context_name_color', 'context', 'color'),
    ('context_name_size', 'context', 'size'),
    ('context_name_font', 'context', 'font'),
    # Date element mappings.
    ('issue_date_y', 'date', 'y'),
    ('issue_date_color', 'date', 'color'),
    ('issue_date_size', 'date', 'size'),
    ('issue_date_font', 'date', 'font'),
    ('issue_date_char_space', 'date', 'char_space'),
    ('issue_date_uppercase', 'date', 'uppercase'),
]


def _convert_to_text_elements(options):
    """
    Convert old flat options format to new text_elements format in-place.

    :param options: The options dictionary to convert.
    """
    if not options:
        return

    # If already in new format, skip conversion.
    if 'text_elements' in options or 'defaults' in options:
        return

    text_elements = {}

    # Handle template_two_lines -> template_multiline rename.
    if 'template_two_lines' in options:
        template_two_lines = options.pop('template_two_lines')
        # Only set template_multiline if it doesn't already exist.
        if 'template_multiline' not in options:
            options['template_multiline'] = template_two_lines

    # Handle global font -> defaults.font.
    if 'font' in options:
        options['defaults'] = {'font': options.pop('font')}

    # Convert element-specific options by popping them from the options dict.
    for old_key, element_key, prop_name in _OPTION_MAPPINGS:
        if old_key in options:
            if element_key not in text_elements:
                text_elements[element_key] = {}
            text_elements[element_key][prop_name] = options.pop(old_key)

    # Only add text_elements if we have any.
    if text_elements:
        options['text_elements'] = text_elements


def _convert_to_flat_format(options):
    """
    Convert new text_elements format back to old flat options format in-place.

    :param options: The options dictionary to convert.
    """
    if not options:
        return

    # If not in new format, skip conversion.
    if 'text_elements' not in options and 'defaults' not in options:
        return

    # Handle template_multiline -> template_two_lines for backward compatibility.
    if 'template_multiline' in options:
        options['template_two_lines'] = options.pop('template_multiline')

    # Handle defaults.font -> font.
    defaults = options.pop('defaults', {})
    if 'font' in defaults:
        options['font'] = defaults['font']

    # Convert text_elements back to flat format.
    text_elements = options.pop('text_elements', {})

    for old_key, element_key, prop_name in _OPTION_MAPPINGS:
        element_config = text_elements.get(element_key, {})
        if isinstance(element_config, dict) and prop_name in element_config:
            options[old_key] = element_config[prop_name]


def _migrate_all_options(apps, convert_func):
    """
    Apply a conversion function to all credential configurations.

    :param apps: Django apps registry.
    :param convert_func: Function to apply to each custom_options dict.
    """
    CredentialType = apps.get_model('learning_credentials', 'CredentialType')
    CredentialConfiguration = apps.get_model('learning_credentials', 'CredentialConfiguration')

    for credential_type in CredentialType.objects.all():
        if credential_type.custom_options:
            convert_func(credential_type.custom_options)
            credential_type.save()

    for config in CredentialConfiguration.objects.all():
        if config.custom_options:
            convert_func(config.custom_options)
            config.save()


def _migrate_forward(apps, schema_editor):
    """Convert all credential configurations to the new text_elements format."""
    _migrate_all_options(apps, _convert_to_text_elements)


def _migrate_backward(apps, schema_editor):
    """Convert all credential configurations back to the old flat format."""
    _migrate_all_options(apps, _convert_to_flat_format)


class Migration(migrations.Migration):

    dependencies = [
        ('learning_credentials', '0006_cleanup_openedx_certificates_tables'),
    ]

    operations = [
        migrations.RunPython(_migrate_forward, _migrate_backward),
    ]
