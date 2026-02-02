"""This module contains unit tests for the generator functions."""

from __future__ import annotations

import io
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import DefaultStorage, FileSystemStorage
from django.test import override_settings
from inmemorystorage import InMemoryStorage
from pypdf import PdfWriter
from pypdf.constants import UserAccessPermissions

from learning_credentials.exceptions import AssetNotFoundError
from learning_credentials.generators import (
    FontError,
    _build_text_elements,
    _get_credential_paths,
    _get_defaults,
    _hex_to_rgb,
    _invalidate_credential,
    _register_font,
    _save_credential,
    _substitute_placeholders,
    _write_text_on_template,
    generate_pdf_credential,
)


@patch("learning_credentials.generators.CredentialAsset.get_asset_by_slug")
def test_register_font_already_available(mock_get_asset_by_slug: Mock):
    """Test that _register_font returns True when font is already available."""
    mock_canvas = Mock(getAvailableFonts=Mock(return_value=['Helvetica', 'Times-Roman']))

    assert _register_font(mock_canvas, 'Times-Roman') == 'Times-Roman'
    mock_canvas.getAvailableFonts.assert_called_once()
    mock_get_asset_by_slug.assert_not_called()


@patch("learning_credentials.generators.CredentialAsset.get_asset_by_slug")
def test_register_font_without_custom_font(mock_get_asset_by_slug: Mock):
    """Test the _register_font falls back to the default font when no custom font is specified."""
    mock_canvas = Mock(getAvailableFonts=Mock(return_value=['Helvetica', 'Times-Roman']))
    assert _register_font(mock_canvas, '') == "Helvetica"
    mock_get_asset_by_slug.assert_called_once()


@patch("learning_credentials.generators.CredentialAsset.get_asset_by_slug")
@patch('learning_credentials.generators.TTFont')
@patch("learning_credentials.generators.registerFont")
def test_register_font_with_custom_font(mock_register_font: Mock, mock_font_class: Mock, mock_get_asset_by_slug: Mock):
    """Test that _register_font registers a custom font when not already available."""
    mock_canvas = Mock(getAvailableFonts=Mock(return_value=[]))
    custom_font = "MyFont"
    mock_get_asset_by_slug.return_value = "font_path"

    assert _register_font(mock_canvas, custom_font) == custom_font
    mock_get_asset_by_slug.assert_called_once_with(custom_font)
    mock_font_class.assert_called_once_with(custom_font, mock_get_asset_by_slug.return_value)
    mock_register_font.assert_called_once_with(mock_font_class.return_value)


@patch("learning_credentials.generators.CredentialAsset.get_asset_by_slug")
@patch('learning_credentials.generators.TTFont', side_effect=FontError("Font registration failed"))
@patch("learning_credentials.generators.registerFont")
def test_register_font_with_registration_failure(
    mock_register_font: Mock, mock_font_class: Mock, mock_get_asset_by_slug: Mock
):
    """Test that _register_font returns False when font registration fails."""
    mock_canvas = Mock(getAvailableFonts=Mock(return_value=[]))
    custom_font = "MyFont"
    mock_get_asset_by_slug.return_value = "font_path"

    assert _register_font(mock_canvas, custom_font) == 'Helvetica'
    mock_get_asset_by_slug.assert_called_once_with(custom_font)
    mock_font_class.assert_called_once_with(custom_font, mock_get_asset_by_slug.return_value)
    mock_register_font.assert_not_called()


@patch(
    "learning_credentials.generators.CredentialAsset.get_asset_by_slug",
    side_effect=AssetNotFoundError("Font not found"),
)
def test_register_font_with_asset_not_found(mock_get_asset_by_slug: Mock):
    """Test that _register_font returns False when font asset is not found."""
    mock_canvas = Mock(getAvailableFonts=Mock(return_value=[]))
    custom_font = "MissingFont"

    assert _register_font(mock_canvas, custom_font) == 'Helvetica'
    mock_get_asset_by_slug.assert_called_once_with(custom_font)


@pytest.mark.parametrize(
    ("hex_color", "expected"),
    [
        ('#000', (0, 0, 0)),
        ('#fff', (1, 1, 1)),
        ('#000000', (0, 0, 0)),
        ('#ffffff', (1, 1, 1)),
        ('123', (17 / 255, 34 / 255, 51 / 255)),
        ('#9B192A', (155 / 255, 25 / 255, 42 / 255)),
        ('#f59a8e', (245 / 255, 154 / 255, 142 / 255)),
    ],
)
def test_hex_to_rgb(hex_color: str, expected: tuple[float, float, float]):
    """Test the _hex_to_rgb function."""
    result = _hex_to_rgb(hex_color)
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("text", "placeholders", "expected"),
    [
        ('Hello {name}!', {'name': 'John'}, 'Hello John!'),
        ('{name} earned {context_name}', {'name': 'Jane', 'context_name': 'Python 101'}, 'Jane earned Python 101'),
        ('Issued on {issue_date}', {'issue_date': 'April 1, 2021'}, 'Issued on April 1, 2021'),
        ('No placeholders', {}, 'No placeholders'),
        ('Unknown {unknown}', {'name': 'John'}, 'Unknown {unknown}'),  # Unknown placeholder kept as-is.
        ('Escaped {{braces}}', {}, 'Escaped {braces}'),  # Escaped braces.
        ('{{name}} is {name}', {'name': 'John'}, '{name} is John'),  # Mixed escaped and real.
    ],
)
def test_substitute_placeholders(text: str, placeholders: dict[str, str], expected: str):
    """Test the _substitute_placeholders function."""
    assert _substitute_placeholders(text, placeholders) == expected


def test_build_text_elements_defaults():
    """Test that _build_text_elements returns default elements when no options specified."""
    elements = _build_text_elements({})
    _, default_text_elements = _get_defaults()

    assert 'name' in elements
    assert 'context' in elements
    assert 'date' in elements
    assert elements['name']['y'] == default_text_elements['name']['y']
    assert elements['context']['y'] == default_text_elements['context']['y']
    assert elements['date']['y'] == default_text_elements['date']['y']


def test_build_text_elements_with_overrides():
    """Test that _build_text_elements merges user overrides with defaults."""
    options = {
        'text_elements': {
            'name': {'y': 300, 'uppercase': True},
            'context': {'size': 24},
        },
    }
    elements = _build_text_elements(options)
    _, default_text_elements = _get_defaults()

    assert elements['name']['y'] == 300
    assert elements['name']['uppercase'] is True
    assert elements['name']['text'] == '{name}'  # Default preserved.
    assert elements['context']['size'] == 24
    assert elements['context']['y'] == default_text_elements['context']['y']  # Default preserved.


def test_build_text_elements_hidden():
    """Test that _build_text_elements excludes hidden elements."""
    options = {
        'text_elements': {
            'date': False,
            'name': False,
        },
    }
    elements = _build_text_elements(options)

    assert 'date' not in elements
    assert 'name' not in elements
    assert 'context' in elements


def test_build_text_elements_custom():
    """Test that _build_text_elements includes custom elements."""
    options = {
        'defaults': {'color': '#333'},
        'text_elements': {
            'award_line': {'text': 'Awarded on {issue_date}', 'y': 140},
        },
    }
    elements = _build_text_elements(options)

    assert 'award_line' in elements
    assert elements['award_line']['text'] == 'Awarded on {issue_date}'
    assert elements['award_line']['y'] == 140
    assert elements['award_line']['color'] == '#333'  # Inherited from defaults.


def test_build_text_elements_custom_missing_required():
    """Test that _build_text_elements logs warning for custom elements missing required properties."""
    options = {
        'text_elements': {
            'invalid': {'text': 'No y coordinate'},
        },
    }
    elements = _build_text_elements(options)

    assert 'invalid' not in elements


def test_build_text_elements_custom_disabled():
    """Test that _build_text_elements skips custom elements set to False."""
    options = {
        'text_elements': {
            'custom_element': False,
        },
    }
    elements = _build_text_elements(options)

    assert 'custom_element' not in elements


def test_build_text_elements_custom_invalid_type():
    """Test that _build_text_elements logs warning for custom elements with invalid type."""
    options = {
        'text_elements': {
            'invalid_string': 'not a dict',
            'invalid_number': 42,
        },
    }
    elements = _build_text_elements(options)

    assert 'invalid_string' not in elements
    assert 'invalid_number' not in elements


@pytest.mark.parametrize(
    ("context_name", "options"),
    [
        ('Programming 101', {}),  # No options - use defaults.
        (
            'Programming 101',
            {
                'text_elements': {
                    'name': {'y': 250, 'color': '123', 'size': 24},
                    'context': {'y': 200, 'color': '#9B192A', 'size': 20},
                    'date': {'y': 150, 'color': '#f59a8e'},
                },
            },
        ),  # Custom coordinates and colors.
        ('Programming\n101\nAdvanced Programming', {}),  # Multiline context name.
    ],
)
@patch('learning_credentials.generators._register_font', return_value="Helvetica")
@patch('learning_credentials.generators.Canvas', return_value=Mock(stringWidth=Mock(return_value=10)))
def test_write_text_on_template(mock_canvas_class: Mock, mock_register_font: Mock, context_name: str, options: dict):
    """Test the _write_text_on_template function."""
    username = 'John Doe'
    template_height = 300
    template_width = 200
    font = 'Helvetica'
    test_date = 'April 1, 2021'

    # Reset the mock to discard calls list from previous tests.
    mock_canvas_class.reset_mock()

    template_mock = Mock()
    template_mock.mediabox = [0, 0, template_width, template_height]

    # Call the function with test parameters and mocks.
    _write_text_on_template(template_mock, username, context_name, test_date, Mock(), options)

    # Verify that Canvas was created with the correct pagesize.
    # Use `call_args_list` to ignore the first argument, which is an instance of io.BytesIO.
    assert mock_canvas_class.call_args_list[0][1]['pagesize'] == (template_width, template_height)

    # Mock Canvas object retrieved from Canvas constructor call.
    canvas_object = mock_canvas_class.return_value

    # The number of calls to drawString: 1 (name) + lines in context + 1 (date).
    context_lines = context_name.count('\n') + 1
    expected_draw_count = 1 + context_lines + 1
    assert canvas_object.drawString.call_count == expected_draw_count

    # Check that setFont was called for each element (name, context, date).
    assert canvas_object.setFont.call_count == 3

    # Check font was set correctly (default Helvetica).
    for font_call in canvas_object.setFont.call_args_list:
        assert font_call[0][0] == font

    # Check that _register_font was called for each element with the default font (second argument).
    assert all(call[0][1] == font for call in mock_register_font.call_args_list)


@pytest.mark.parametrize(
    ("uppercase_option", "expected_text"),
    [
        (False, "John Doe"),  # Lowercase.
        (True, "JOHN DOE"),  # Uppercase.
    ],
)
@patch('learning_credentials.generators._register_font', return_value=True)
@patch('learning_credentials.generators.Canvas', return_value=Mock(stringWidth=Mock(return_value=10)))
def test_write_text_on_template_uppercase(
    mock_canvas_class: Mock,
    mock_register_font: Mock,
    uppercase_option: bool,
    expected_text: str,
):
    """Test the _write_text_on_template function with uppercase option."""
    mock_canvas_class.reset_mock()

    username = "John Doe"
    context_name = "Programming 101"
    test_date = "April 1, 2021"
    template_mock = Mock(mediabox=[0, 0, 300, 200])
    options = {
        'text_elements': {
            'name': {'uppercase': uppercase_option},
        },
    }

    _write_text_on_template(template_mock, username, context_name, test_date, Mock(), options)

    drawn_texts = [call[1][2] for call in mock_canvas_class.return_value.drawString.mock_calls]
    assert expected_text in drawn_texts

    assert mock_register_font.call_count == 3


@pytest.mark.parametrize(
    ("char_space", "expected_char_space"),
    [
        (2, 2),  # Custom value.
        (0.5, 0.5),  # Float value.
    ],
)
@patch('learning_credentials.generators._register_font', return_value=True)
@patch('learning_credentials.generators.Canvas', return_value=Mock(stringWidth=Mock(return_value=10)))
def test_write_text_on_template_char_space(
    mock_canvas_class: Mock,
    mock_register_font: Mock,
    char_space: float,
    expected_char_space: float,
):
    """Test the _write_text_on_template function with char_space option."""
    mock_canvas_class.reset_mock()

    username = "John Doe"
    context_name = "Programming 101"
    test_date = "April 1, 2021"
    template_mock = Mock(mediabox=[0, 0, 300, 200])
    options = {
        'text_elements': {
            'date': {'char_space': char_space},
        },
    }

    _write_text_on_template(template_mock, username, context_name, test_date, Mock(), options)

    date_calls = [call for call in mock_canvas_class.return_value.drawString.mock_calls if call[1][2] == test_date]
    assert len(date_calls) == 1
    assert date_calls[0][2]['charSpace'] == expected_char_space

    assert mock_register_font.call_count == 3


@patch('learning_credentials.generators._register_font', return_value="Helvetica")
@patch('learning_credentials.generators.Canvas', return_value=Mock(stringWidth=Mock(return_value=10)))
def test_write_text_on_template_custom_element(mock_canvas_class: Mock, mock_register_font: Mock):
    """Test the _write_text_on_template function with a custom text element."""
    username = "John Doe"
    context_name = "Programming 101"
    test_date = "April 1, 2021"
    template_mock = Mock(mediabox=[0, 0, 300, 200])
    options = {
        'text_elements': {
            'date': False,
            'award_line': {'text': 'Awarded on {issue_date}', 'y': 140, 'size': 14},
        },
    }

    _write_text_on_template(template_mock, username, context_name, test_date, Mock(), options)

    canvas_object = mock_canvas_class.return_value

    assert canvas_object.drawString.call_count == 3

    drawn_texts = [call[1][2] for call in canvas_object.drawString.mock_calls]
    assert f'Awarded on {test_date}' in drawn_texts
    assert test_date not in drawn_texts

    assert mock_register_font.call_count == 3


@override_settings(LMS_ROOT_URL="https://example.com", MEDIA_URL="media/")
@pytest.mark.parametrize(
    "storage",
    [
        (InMemoryStorage()),  # Test a real storage, without mocking.
        (Mock(spec=FileSystemStorage, exists=Mock(return_value=False))),  # Test calls in a mocked storage.
        # Test calls in a mocked storage when the file already exists.
        (Mock(spec=FileSystemStorage, exists=Mock(return_value=True))),
    ],
)
@patch('learning_credentials.generators.secrets.token_hex', return_value='test_token')
@patch('learning_credentials.generators.ContentFile', autospec=True)
def test_save_credential(mock_contentfile: Mock, mock_token_hex: Mock, storage: DefaultStorage | Mock, temp_media: str):  # noqa: ARG001
    """Test the _save_credential function."""
    # Mock the credential.
    credential = Mock(spec=PdfWriter)
    credential_uuid = uuid4()
    output_path = f'learning_credentials/{credential_uuid}.pdf'
    pdf_bytes = io.BytesIO()
    credential.write.return_value = pdf_bytes
    content_file = ContentFile(pdf_bytes.getvalue())
    mock_contentfile.return_value = content_file

    # Expected values for the encrypt method
    expected_pdf_permissions = (
        UserAccessPermissions.PRINT
        | UserAccessPermissions.PRINT_TO_REPRESENTATION
        | UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS
    )

    # Run the function.
    with patch('learning_credentials.generators.default_storage', storage):
        url = _save_credential(credential, credential_uuid)

    # Check the calls in a mocked storage.
    if isinstance(storage, Mock):
        storage.exists.assert_called_once_with(output_path)
        storage.save.assert_called_once_with(output_path, content_file)
        storage.url.assert_not_called()
        if storage.exists.return_value:
            storage.delete.assert_called_once_with(output_path)
        else:
            storage.delete.assert_not_called()

    if isinstance(storage, Mock):
        assert url == f'{settings.LMS_ROOT_URL}/media/{output_path}'
    else:
        assert url == f'/{output_path}'

    # Check the calls to credential.encrypt
    credential.encrypt.assert_called_once_with(
        '',
        mock_token_hex(),
        permissions_flag=expected_pdf_permissions,
        algorithm='AES-256',
    )

    # Allow specifying a custom domain for credentials.
    with override_settings(LEARNING_CREDENTIALS_CUSTOM_DOMAIN='https://example2.com'):
        url = _save_credential(credential, credential_uuid)
        assert url == f'https://example2.com/{credential_uuid}.pdf'


@pytest.mark.parametrize(
    ("context_name", "options", "expected_template_slug", "expected_context_name"),
    [
        # Default.
        ('Test Course', {'template': 'default', 'template_multiline': 'multiline'}, 'default', 'Test Course'),
        # Specify a different template for multiline course names and replace \n with newline.
        ('Test\nCourse', {'template': 'default', 'template_multiline': 'multiline'}, 'multiline', 'Test\nCourse'),
        # Ensure that the default template is used when no multiline template is specified.
        ('Test\nCourse', {'template': 'default'}, 'default', 'Test\nCourse'),
        # Custom context text with newlines uses multiline template.
        (
            'Single Line',
            {'template_multiline': 'multiline', 'text_elements': {'context': {'text': 'Line 1\nLine 2'}}},
            'multiline',
            'Single Line',
        ),
        # Custom context text without newlines still uses multiline template if the original context name has newlines.
        # This allows using the `context_name` placeholder in the `context` text element.
        (
            'Multi\nLine',
            {'template_multiline': 'multiline', 'text_elements': {'context': {'text': 'Single Line'}}},
            'multiline',
            'Multi\nLine',
        ),
        # Disabled context element falls back to learning context name for template selection.
        (
            'Multi\nLine',
            {'template_multiline': 'multiline', 'text_elements': {'context': False}},
            'multiline',
            'Multi\nLine',
        ),
    ],
)
@patch(
    'learning_credentials.generators.CredentialAsset.get_asset_by_slug',
    return_value=Mock(
        open=Mock(
            return_value=Mock(
                __enter__=Mock(return_value=Mock(read=Mock(return_value=b'pdf_data'))),
                __exit__=Mock(return_value=None),
            ),
        ),
    ),
)
@patch('learning_credentials.generators.get_localized_credential_date', return_value='April 1, 2021')
@patch('learning_credentials.generators.PdfReader')
@patch('learning_credentials.generators.PdfWriter')
@patch(
    'learning_credentials.generators._write_text_on_template',
    return_value=Mock(getpdfdata=Mock(return_value=b'pdf_data')),
)
@patch('learning_credentials.generators._save_credential', return_value='credential_url')
def test_generate_pdf_credential(
    mock_save_credential: Mock,
    mock_write_text_on_template: Mock,
    mock_pdf_writer: Mock,
    mock_pdf_reader: Mock,
    mock_get_date: Mock,
    mock_get_asset_by_slug: Mock,
    context_name: str,
    options: dict[str, str],
    expected_template_slug: str,
    expected_context_name: str,
):
    """Test the generate_pdf_credential function."""
    verify_uuid = uuid4()
    credential = Mock(
        user_full_name='Test User',
        learning_context_name=context_name,
        verify_uuid=verify_uuid,
    )

    result = generate_pdf_credential(credential, options)

    assert result == 'credential_url'
    mock_get_asset_by_slug.assert_called_with(expected_template_slug)
    assert mock_pdf_reader.call_count == 2
    mock_pdf_writer.assert_called_once_with()

    mock_write_text_on_template.assert_called_once()
    _, args, _kwargs = mock_write_text_on_template.mock_calls[0]
    assert args[1] == 'Test User'
    assert args[2] == expected_context_name
    assert args[3] == mock_get_date.return_value
    assert args[4] == str(verify_uuid)
    assert args[5] == options

    mock_save_credential.assert_called_once()


def test_generate_pdf_credential_no_template():
    """Test that generate_pdf_credential raises ValueError when no template is specified."""
    credential = Mock(learning_context_name='Test Course')
    options = {}  # No template specified.

    with pytest.raises(ValueError, match=r"Template path must be specified in options."):
        generate_pdf_credential(credential, options)


@patch('learning_credentials.generators._invalidate_credential')
def test_generate_pdf_credential_invalidate(mock_invalidate: Mock):
    """Test that generate_pdf_credential calls _invalidate_credential when invalidate=True."""
    credential_uuid = uuid4()
    credential = Mock(uuid=credential_uuid, user=Mock(id=1))

    result = generate_pdf_credential(credential, {}, invalidate=True)

    assert result == ''
    mock_invalidate.assert_called_once_with(credential_uuid)


def test_get_credential_paths():
    """Test that _get_credential_paths returns correct paths."""
    credential_uuid = uuid4()

    original_path, archive_path = _get_credential_paths(credential_uuid)

    assert original_path == f'learning_credentials/{credential_uuid}.pdf'
    assert archive_path == f'learning_credentials_invalidated/{credential_uuid}.pdf'


@override_settings(LEARNING_CREDENTIALS_OUTPUT_DIR='custom_dir')
def test_get_credential_paths_custom_dir():
    """Test that _get_credential_paths respects custom output directory."""
    credential_uuid = uuid4()

    original_path, archive_path = _get_credential_paths(credential_uuid)

    assert original_path == f'custom_dir/{credential_uuid}.pdf'
    assert archive_path == f'custom_dir_invalidated/{credential_uuid}.pdf'


@pytest.mark.parametrize(
    "storage",
    [
        (InMemoryStorage()),  # Test a real storage, without mocking.
        (Mock(spec=FileSystemStorage, exists=Mock(return_value=True), open=Mock(), save=Mock(), delete=Mock())),
    ],
)
def test_invalidate_credential(storage: DefaultStorage | Mock, temp_media: str):  # noqa: ARG001
    """Test the _invalidate_credential function."""
    credential_uuid = uuid4()
    original_path = f'learning_credentials/{credential_uuid}.pdf'
    archive_path = f'learning_credentials_invalidated/{credential_uuid}.pdf'
    pdf_content = b'test pdf content'

    # For InMemoryStorage, we need to create the file first.
    if isinstance(storage, InMemoryStorage):
        storage.save(original_path, ContentFile(pdf_content))

    # For mocked storage, set up the open mock to return the content.
    if isinstance(storage, Mock):
        mock_file = Mock()
        mock_file.read.return_value = pdf_content
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        storage.open.return_value = mock_file

    with patch('learning_credentials.generators.default_storage', storage):
        result = _invalidate_credential(credential_uuid)

    assert result == archive_path

    if isinstance(storage, Mock):
        storage.exists.assert_called_once_with(original_path)
        storage.open.assert_called_once_with(original_path, 'rb')
        storage.delete.assert_called_once_with(original_path)

        save_call_args = storage.save.call_args
        assert save_call_args[0][0] == archive_path


def test_invalidate_credential_file_not_exists():
    """Test that _invalidate_credential returns None when file doesn't exist."""
    credential_uuid = uuid4()
    storage = Mock(spec=FileSystemStorage, exists=Mock(return_value=False))

    with patch('learning_credentials.generators.default_storage', storage):
        result = _invalidate_credential(credential_uuid)

    assert result is None
    storage.exists.assert_called_once()
    storage.open.assert_not_called()
    storage.delete.assert_not_called()


def test_invalidate_credential_sets_acl_on_s3():
    """Test that _invalidate_credential sets ACL to private on S3 storage."""
    credential_uuid = uuid4()
    archive_path = f'learning_credentials_invalidated/{credential_uuid}.pdf'
    pdf_content = b'test pdf content'

    # Create a mock S3 storage with bucket attribute.
    mock_acl = Mock()
    mock_object = Mock(Acl=Mock(return_value=mock_acl))
    mock_bucket = Mock(Object=Mock(return_value=mock_object))

    mock_file = Mock()
    mock_file.read.return_value = pdf_content
    mock_file.__enter__ = Mock(return_value=mock_file)
    mock_file.__exit__ = Mock(return_value=None)

    storage = Mock(
        exists=Mock(return_value=True),
        open=Mock(return_value=mock_file),
        save=Mock(),
        delete=Mock(),
        bucket=mock_bucket,
    )

    with patch('learning_credentials.generators.default_storage', storage):
        result = _invalidate_credential(credential_uuid)

    assert result == archive_path
    mock_bucket.Object.assert_called_once_with(archive_path)
    mock_acl.put.assert_called_once_with(ACL='private')


def test_invalidate_credential_s3_acl_failure_continues():
    """Test that _invalidate_credential continues even if setting ACL fails."""
    credential_uuid = uuid4()
    original_path = f'learning_credentials/{credential_uuid}.pdf'
    archive_path = f'learning_credentials_invalidated/{credential_uuid}.pdf'
    pdf_content = b'test pdf content'

    mock_acl = Mock(put=Mock(side_effect=Exception("ACL error")))
    mock_object = Mock(Acl=Mock(return_value=mock_acl))
    mock_bucket = Mock(Object=Mock(return_value=mock_object))

    mock_file = Mock()
    mock_file.read.return_value = pdf_content
    mock_file.__enter__ = Mock(return_value=mock_file)
    mock_file.__exit__ = Mock(return_value=None)

    storage = Mock(
        exists=Mock(return_value=True),
        open=Mock(return_value=mock_file),
        save=Mock(),
        delete=Mock(),
        bucket=mock_bucket,
    )

    with patch('learning_credentials.generators.default_storage', storage):
        result = _invalidate_credential(credential_uuid)

    assert result == archive_path
    storage.delete.assert_called_once_with(original_path)
