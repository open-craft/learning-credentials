"""
This module provides functions to generate credentials.

The functions prefixed with `generate_` are automatically detected by the admin page and are used to generate the
credentials for the users.

We will move this module to an external repository (a plugin).
"""

from __future__ import annotations

import copy
import io
import logging
import re
import secrets
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, default_storage
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from reportlab.pdfbase.pdfmetrics import FontError, FontNotFoundError, registerFont
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.pdfgen.canvas import Canvas

from .compat import get_default_storage_url, get_learning_context_name, get_localized_credential_date
from .exceptions import AssetNotFoundError
from .models import CredentialAsset

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from uuid import UUID

    from django.contrib.auth.models import User
    from opaque_keys.edx.keys import CourseKey
    from pypdf import PageObject


def _get_defaults() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """
    Get default styling and text element configurations.

    Evaluated lazily to avoid accessing Django settings at import time.

    :returns: A tuple of (default_styling, default_text_elements).
    """
    default_styling = {
        'font': 'Helvetica',
        'color': '#000',
        'size': 12,
        'char_space': 0,
        'uppercase': False,
        'line_height': 1.1,
    }

    default_text_elements = {
        'name': {
            'text': '{name}',
            'y': 290,
            'size': 32,
            'uppercase': getattr(settings, 'LEARNING_CREDENTIALS_NAME_UPPERCASE', False),
        },
        'context': {
            'text': '{context_name}',
            'y': 220,
            'size': 28,
            'line_height': 1.1,
        },
        'date': {
            'text': '{issue_date}',
            'y': 120,
            'size': 12,
            'uppercase': getattr(settings, 'LEARNING_CREDENTIALS_DATE_UPPERCASE', False),
            'char_space': getattr(settings, 'LEARNING_CREDENTIALS_DATE_CHAR_SPACE', 0),
        },
    }

    return default_styling, default_text_elements


def _get_user_name(user: User) -> str:
    """
    Retrieve the user's name.

    :param user: The user to generate the credential for.
    :return: Username.
    """
    return user.profile.name or f"{user.first_name} {user.last_name}"


def _register_font(pdf_canvas: Canvas, font_name: str) -> str:
    """
    Register a custom font if not already available.

    Built-in fonts (like Helvetica) are already available and don't need registration.
    Custom fonts are loaded from CredentialAsset.

    :param pdf_canvas: The canvas to check available fonts on.
    :param font_name: The name of the font to register.
    :returns: The font name if available, otherwise use 'Helvetica' as fallback.
    """
    # Check if font is already available (built-in or previously registered).
    if font_name in pdf_canvas.getAvailableFonts():
        return font_name

    try:
        registerFont(TTFont(font_name, CredentialAsset.get_asset_by_slug(font_name)))
    except AssetNotFoundError:
        log.warning("Font asset not found: %s", font_name)
    except (FontError, FontNotFoundError, TTFError):
        log.exception("Error registering font %s", font_name)
    else:
        return font_name

    return 'Helvetica'


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """
    Convert a hexadecimal color code to an RGB tuple with floating-point values.

    :param hex_color: A hexadecimal color string, which can start with '#' and be either 3 or 6 characters long.
    :returns: A tuple representing the RGB color as (red, green, blue), with each value ranging from 0.0 to 1.0.
    """
    hex_color = hex_color.lstrip('#')
    # Expand shorthand form (e.g. "158" to "115588")
    if len(hex_color) == 3:
        hex_color = ''.join([c * 2 for c in hex_color])

    # noinspection PyTypeChecker
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in range(0, 6, 2))


def _substitute_placeholders(text: str, placeholders: dict[str, str]) -> str:
    """
    Substitute placeholders in text using {placeholder} syntax.

    Supports escaping with {{ for literal braces.

    :param text: The text containing placeholders.
    :param placeholders: A dictionary mapping placeholder names to their values.
    :returns: The text with placeholders substituted.
    """

    def replace_placeholder(match: re.Match) -> str:
        key = match.group(1)
        return placeholders.get(key, match.group(0))

    # Use negative lookbehind to skip escaped braces ({{).
    # Match {word} but not {{word}.
    text = re.sub(r'(?<!\{)\{(\w+)\}', replace_placeholder, text)

    # Replace escaped braces with literal braces.
    return text.replace('{{', '{').replace('}}', '}')


def _build_text_elements(options: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Build the final text elements configuration by merging defaults with user options.

    Standard elements (name, context, date) use defaults that are deep-merged with user overrides.
    Custom elements (any other key) must provide at least 'text' and 'y'.

    :param options: The options dictionary from the credential configuration.
    :returns: A dictionary of element configurations ready for rendering.
    """
    default_styling, default_text_elements = _get_defaults()
    user_elements = options.get('text_elements', {})
    defaults_config = {**default_styling, **options.get('defaults', {})}
    result = {}

    # Process standard elements (they have defaults).
    for key, default_config in default_text_elements.items():
        user_config = user_elements.get(key, {})

        if user_config is False:
            continue

        # Merge: element defaults -> global defaults -> user config.
        element_config = {**copy.deepcopy(default_config), **defaults_config, **user_config}
        result[key] = element_config

    # Process custom elements (non-standard keys).
    for key, user_config in user_elements.items():
        if key in default_text_elements:
            continue

        # Skip disabled elements.
        if user_config is False:
            continue

        if not isinstance(user_config, dict):
            log.warning("Invalid custom element configuration for key '%s': expected dict", key)
            continue

        # Custom elements must have 'text' and 'y'.
        if 'text' not in user_config or 'y' not in user_config:
            log.warning("Custom element '%s' must have 'text' and 'y' properties", key)
            continue

        # Merge with global defaults only.
        element_config = {**defaults_config, **user_config}
        result[key] = element_config

    return result


def _render_text_element(
    pdf_canvas: Canvas,
    template_width: float,
    config: dict[str, Any],
    placeholders: dict[str, str],
) -> None:
    """
    Render a single text element on the canvas.

    :param pdf_canvas: The canvas to draw on.
    :param template_width: Width of the template for centering.
    :param config: The element configuration (all defaults are already merged).
    :param placeholders: Dictionary of placeholder values.
    """
    text = _substitute_placeholders(config['text'], placeholders)

    if config['uppercase']:
        text = text.upper()

    font_name = _register_font(pdf_canvas, config['font'])
    pdf_canvas.setFont(font_name, config['size'])

    pdf_canvas.setFillColorRGB(*_hex_to_rgb(config['color']))

    y = config['y']
    char_space = config['char_space']
    line_height = config['line_height']
    size = config['size']

    # Handle multiline text (for context element).
    lines = text.split('\n')
    for line_number, line in enumerate(lines):
        text_width = pdf_canvas.stringWidth(line) + (char_space * max(0, len(line) - 1))
        line_x = (template_width - text_width) / 2
        line_y = y - (line_number * size * line_height)
        pdf_canvas.drawString(line_x, line_y, line, charSpace=char_space)


def _write_text_on_template(
    template: PageObject,
    username: str,
    context_name: str,
    issue_date: str,
    options: dict[str, Any],
) -> Canvas:
    """
    Prepare a new canvas and write text elements onto it.

    :param template: PDF template.
    :param username: The name of the user to generate the credential for.
    :param context_name: The name of the learning context.
    :param issue_date: The formatted issue date string.
    :param options: A dictionary documented in the ``generate_pdf_credential`` function.
    :returns: A canvas with written data.
    """
    template_width, template_height = template.mediabox[2:]
    pdf_canvas = Canvas(io.BytesIO(), pagesize=(template_width, template_height))

    # Build placeholder values.
    placeholders = {
        'name': username,
        'context_name': context_name,
        'issue_date': issue_date,
    }

    # Build and render text elements.
    elements = _build_text_elements(options)

    for config in elements.values():
        _render_text_element(pdf_canvas, template_width, config, placeholders)

    return pdf_canvas


def _save_credential(credential: PdfWriter, credential_uuid: UUID) -> str:
    """
    Save the final PDF file to BytesIO and upload it using Django default storage.

    :param credential: Pdf credential.
    :param credential_uuid: The UUID of the credential.
    :returns: The URL of the saved credential.
    """
    # Save the final PDF file to BytesIO.
    output_path = f'external_certificates/{credential_uuid}.pdf'

    view_print_extract_permission = (
        UserAccessPermissions.PRINT
        | UserAccessPermissions.PRINT_TO_REPRESENTATION
        | UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS
    )
    credential.encrypt('', secrets.token_hex(32), permissions_flag=view_print_extract_permission, algorithm='AES-256')

    pdf_bytes = io.BytesIO()
    credential.write(pdf_bytes)
    pdf_bytes.seek(0)  # Rewind to start.
    # Upload with Django default storage.
    credential_file = ContentFile(pdf_bytes.read())
    # Delete the file if it already exists.
    if default_storage.exists(output_path):
        default_storage.delete(output_path)
    default_storage.save(output_path, credential_file)
    if isinstance(default_storage, FileSystemStorage):
        url = f"{get_default_storage_url()}{output_path}"
    else:
        url = default_storage.url(output_path)

    if custom_domain := getattr(settings, 'LEARNING_CREDENTIALS_CUSTOM_DOMAIN', None):
        url = f"{custom_domain}/{credential_uuid}.pdf"

    return url


def generate_pdf_credential(
    learning_context_key: CourseKey,
    user: User,
    credential_uuid: UUID,
    options: dict[str, Any],
) -> str:
    r"""
    Generate a PDF credential.

    :param learning_context_key: The ID of the course or learning path the credential is for.
    :param user: The user to generate the credential for.
    :param credential_uuid: The UUID of the credential to generate.
    :param options: The custom options for the credential.
    :returns: The URL of the saved credential.

    Options:

      - template (required): The slug of the PDF template asset.
      - template_multiline: Alternative template for multiline context names (when using '\n').
      - defaults: Global defaults for all text elements.
          - font: Font name (asset slug). Default: Helvetica.
          - color: Hex color code. Default: #000.
          - size: Font size in points. Default: 12.
          - char_space: Character spacing. Default: 0.
          - uppercase: Convert text to uppercase. Default: false.
          - line_height: Line height multiplier for multiline text. Default: 1.1.
      - text_elements: Configuration for text elements. Standard elements (name, context, date) have
          defaults and render automatically. Set to false to hide.
          Custom elements require 'text' and 'y' properties.
          Element properties:
          - text: Text content with {placeholder} substitution. Available: {name}, {context_name}, {issue_date}.
          - y: Vertical position (PDF coordinates from bottom).
          - size: Font size (inherited from defaults.size).
          - font: Font name (inherited from defaults.font).
          - color: Hex color (inherited from defaults.color).
          - char_space: Character spacing (inherited from defaults.char_space).
          - uppercase: Convert text to uppercase (inherited from defaults.uppercase).
          - line_height: Line height multiplier for multiline text (inherited from defaults.line_height).

    Example::

      {
        "template": "certificate-template",
        "defaults": {"font": "CustomFont", "color": "#333"},
        "text_elements": {
          "name": {"y": 300, "uppercase": true},
          "context": {"text": "Custom Course Name"},
          "date": false,
          "award_line": {"text": "Awarded on {issue_date}", "y": 140, "size": 14}
        }
      }
    """
    log.info("Starting credential generation for user %s", user.id)

    username = _get_user_name(user)

    # Handle multiline context name.
    context_name = get_learning_context_name(learning_context_key)
    custom_context_name = ''
    custom_context_text_element = options.get('text_elements', {}).get('context', {})
    if isinstance(custom_context_text_element, dict):
        custom_context_name = custom_context_text_element.get('text', '')

    template_path = options.get('template')
    if '\n' in context_name or '\n' in custom_context_name:
        template_path = options.get('template_multiline', template_path)

    if not template_path:
        msg = "Template path must be specified in options."
        raise ValueError(msg)

    # Get template from the CredentialAsset.
    template_file = CredentialAsset.get_asset_by_slug(template_path)

    # Get the issue date.
    issue_date = get_localized_credential_date()

    # Load the PDF template.
    with template_file.open('rb') as template_file:
        template = PdfReader(template_file).pages[0]

        credential = PdfWriter()

        # Create a new canvas, prepare the page and write the data.
        pdf_canvas = _write_text_on_template(template, username, context_name, issue_date, options)

        overlay_pdf = PdfReader(io.BytesIO(pdf_canvas.getpdfdata()))
        template.merge_page(overlay_pdf.pages[0])
        credential.add_page(template)

        url = _save_credential(credential, credential_uuid)

        log.info("Credential saved to %s", url)
    return url
