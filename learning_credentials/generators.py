"""
This module provides functions to generate credentials.

The functions prefixed with `generate_` are automatically detected by the admin page and are used to generate the
credentials for the users.

We will move this module to an external repository (a plugin).
"""

from __future__ import annotations

import io
import logging
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
from .models import CredentialAsset

log = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from uuid import UUID

    from django.contrib.auth.models import User
    from opaque_keys.edx.keys import CourseKey
    from pypdf import PageObject


def _get_user_name(user: User) -> str:
    """
    Retrieve the user's name.

    :param user: The user to generate the credential for.
    :return: Username.
    """
    return user.profile.name or f"{user.first_name} {user.last_name}"


def _register_font(font_name: str) -> str | None:
    """
    Register a custom font if specified in options. If not specified, use the default font (Helvetica).

    :param font_name: The name of the font to register.
    :returns: The font name if registered successfully, otherwise None.
    """
    if not font_name:
        return None

    try:
        registerFont(TTFont(font_name, CredentialAsset.get_asset_by_slug(font_name)))
    except (FontError, FontNotFoundError, TTFError):
        log.exception("Error registering font %s", font_name)
    else:
        return font_name


def _write_text_on_template(template: PageObject, username: str, context_name: str, options: dict[str, Any]) -> Canvas:
    """
    Prepare a new canvas and write the user and course name onto it.

    :param template: Pdf template.
    :param username: The name of the user to generate the credential for.
    :param context_name: The name of the learning context.
    :param options: A dictionary documented in the `generate_pdf_credential` function.
    :returns: A canvas with written data.
    """

    def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
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

    template_width, template_height = template.mediabox[2:]
    pdf_canvas = Canvas(io.BytesIO(), pagesize=(template_width, template_height))
    font = _register_font(options.get('font')) or 'Helvetica'

    # Write the learner name.
    if options.get('name_uppercase', getattr(settings, 'LEARNING_CREDENTIALS_NAME_UPPERCASE', False)):
        username = username.upper()

    name_font = _register_font(options.get('name_font')) or font
    pdf_canvas.setFont(name_font, options.get('name_size', 32))
    name_color = options.get('name_color', '#000')
    pdf_canvas.setFillColorRGB(*hex_to_rgb(name_color))

    name_x = (template_width - pdf_canvas.stringWidth(username)) / 2
    name_y = options.get('name_y', 290)

    pdf_canvas.drawString(name_x, name_y, username)

    # Write the learning context name.
    context_name_font = _register_font(options.get('context_name_font')) or font
    pdf_canvas.setFont(context_name_font, options.get('context_name_size', 28))
    context_name_color = options.get('context_name_color', '#000')
    pdf_canvas.setFillColorRGB(*hex_to_rgb(context_name_color))

    context_name_y = options.get('context_name_y', 220)
    context_name_line_height = 28 * 1.1

    # Split the learning context name into lines and write each of them in the center of the template.
    for line_number, line in enumerate(context_name.split('\n')):
        line_x = (template_width - pdf_canvas.stringWidth(line)) / 2
        line_y = context_name_y - (line_number * context_name_line_height)
        pdf_canvas.drawString(line_x, line_y, line)

    # Write the issue date.
    issue_date = get_localized_credential_date()
    if options.get('issue_date_uppercase', getattr(settings, 'LEARNING_CREDENTIALS_ISSUE_DATE_UPPERCASE', False)):
        issue_date = issue_date.upper()

    issue_date_font = _register_font(options.get('issue_date_font')) or font
    pdf_canvas.setFont(issue_date_font, options.get('issue_date_size', 12))
    issue_date_color = options.get('issue_date_color', '#000')
    pdf_canvas.setFillColorRGB(*hex_to_rgb(issue_date_color))

    issue_date_x = (template_width - pdf_canvas.stringWidth(issue_date)) / 2
    issue_date_x += options.get('issue_date_x', 0)
    issue_date_y = options.get('issue_date_y', 120)

    issue_date_char_space = options.get(
        'issue_date_char_space', getattr(settings, 'LEARNING_CREDENTIALS_ISSUE_DATE_CHAR_SPACE', 0)
    )

    pdf_canvas.drawString(issue_date_x, issue_date_y, issue_date, charSpace=issue_date_char_space)

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
      - template: The path to the PDF template file.
      - template_multiline: The path to the PDF template file for multiline context names.
        A multiline context name is specified by using '\n' or ';' as a separator.
      - font: The name of the font to use. The default font is Helvetica.
      - name_y: The Y coordinate of the name on the credential (vertical position on the template).
      - name_color: The color of the name on the credential (hexadecimal color code).
      - name_size: The font size of the name on the credential. The default value is 32.
      - name_font: The font of the name on the credential. It overrides the `font` option.
      - name_uppercase: If set to true (without quotes), the name will be converted to uppercase.
        The default value is False, unless specified otherwise in the instance settings.
      - context_name: Specify the custom course or Learning Path name. If not provided, it will be retrieved
        automatically from the "cert_name_long" or "display_name" fields for courses, or from the Learning Path model.
      - context_name_y: The Y coordinate of the context name on the credential (vertical position on the template).
      - context_name_color: The color of the context name on the credential (hexadecimal color code).
      - context_name_size: The font size of the context name on the credential. The default value is 28.
      - context_name_font: The font of the context name on the credential. It overrides the `font` option.
      - issue_date_x: The horizontal offset for the issue date from its centered position
        (positive values move right, negative values move left; default is 0).
      - issue_date_y: The Y coordinate of the issue date on the credential (vertical position on the template).
      - issue_date_color: The color of the issue date on the credential (hexadecimal color code).
      - issue_date_size: The font size of the issue date on the credential. The default value is 12.
      - issue_date_font: The font of the issue date on the credential. It overrides the `font` option.
      - issue_date_char_space: The character spacing of the issue date on the credential
        (default is 0.0, unless specified otherwise in the instance settings).
      - issue_date_uppercase: If set to true (without quotes), the issue date will be converted to uppercase.
        The default value is False, unless specified otherwise in the instance settings.
    """
    log.info("Starting credential generation for user %s", user.id)

    username = _get_user_name(user)
    context_name = options.get('context_name') or get_learning_context_name(learning_context_key)
    template_path = options.get('template')

    # Handle multiline context name (we support semicolon as a separator to preserve backward compatibility).
    context_name = context_name.replace(';', '\n').replace(r'\n', '\n')
    if '\n' in context_name:
        # `template_two_lines` is kept for backward compatibility.
        template_path = options.get('template_multiline', options.get('template_two_lines', template_path))

    if not template_path:
        msg = "Template path must be specified in options."
        raise ValueError(msg)

    # Get template from the CredentialAsset.
    template_file = CredentialAsset.get_asset_by_slug(template_path)

    # Load the PDF template.
    with template_file.open('rb') as template_file:
        template = PdfReader(template_file).pages[0]

        credential = PdfWriter()

        # Create a new canvas, prepare the page and write the data
        pdf_canvas = _write_text_on_template(template, username, context_name, options)

        overlay_pdf = PdfReader(io.BytesIO(pdf_canvas.getpdfdata()))
        template.merge_page(overlay_pdf.pages[0])
        credential.add_page(template)

        url = _save_credential(credential, credential_uuid)

        log.info("Credential saved to %s", url)
    return url
