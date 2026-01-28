"""Tests for the data migrations."""

from __future__ import annotations

import copy
import importlib
from typing import Any

import pytest

# Import the migration module using importlib since it starts with a number.
migration_0007 = importlib.import_module('learning_credentials.migrations.0007_migrate_to_text_elements_format')
_convert_to_text_elements = migration_0007._convert_to_text_elements
_convert_to_flat_format = migration_0007._convert_to_flat_format

# Type alias for options dictionary.
OptionsDict = dict[str, Any] | None


class TestMigration0007:
    """Tests for migration 0007: migrate_to_text_elements_format."""

    @pytest.mark.parametrize(
        ("options", "expected"),
        [
            # Empty options.
            ({}, {}),
            (None, None),
            # Template only.
            ({'template': 'cert.pdf'}, {'template': 'cert.pdf'}),
            # Template with multiline.
            (
                {'template': 'cert.pdf', 'template_two_lines': 'cert2.pdf'},
                {'template': 'cert.pdf', 'template_multiline': 'cert2.pdf'},
            ),
            # Global font.
            (
                {'template': 'cert.pdf', 'font': 'Arial'},
                {'template': 'cert.pdf', 'defaults': {'font': 'Arial'}},
            ),
            # Name options.
            (
                {'template': 'cert.pdf', 'name_y': 300, 'name_color': '#333', 'name_size': 24, 'name_uppercase': True},
                {
                    'template': 'cert.pdf',
                    'text_elements': {
                        'name': {'y': 300, 'color': '#333', 'size': 24, 'uppercase': True},
                    },
                },
            ),
            # Context name options.
            (
                {'template': 'cert.pdf', 'context_name_y': 200, 'context_name_color': '#666', 'context_name_size': 20},
                {
                    'template': 'cert.pdf',
                    'text_elements': {
                        'context': {'y': 200, 'color': '#666', 'size': 20},
                    },
                },
            ),
            # Issue date options.
            (
                {
                    'template': 'cert.pdf',
                    'issue_date_y': 100,
                    'issue_date_color': '#999',
                    'issue_date_char_space': 2,
                },
                {
                    'template': 'cert.pdf',
                    'text_elements': {
                        'date': {'y': 100, 'color': '#999', 'char_space': 2},
                    },
                },
            ),
            # context_name option.
            (
                {'template': 'cert.pdf', 'context_name': 'Custom Course Name'},
                {
                    'template': 'cert.pdf',
                    'text_elements': {
                        'context': {'text': 'Custom Course Name'},
                    },
                },
            ),
            # Mixed options.
            (
                {
                    'template': 'cert.pdf',
                    'font': 'Arial',
                    'name_y': 300,
                    'context_name_y': 200,
                    'issue_date_y': 100,
                    'context_name': 'Custom Course Name',
                },
                {
                    'template': 'cert.pdf',
                    'defaults': {'font': 'Arial'},
                    'text_elements': {
                        'name': {'y': 300},
                        'context': {'text': 'Custom Course Name', 'y': 200},
                        'date': {'y': 100},
                    },
                },
            ),
            # Processor options should be preserved.
            (
                {
                    'template': 'cert.pdf',
                    'name_y': 300,
                    'required_grades': {'exam': 0.8},
                    'required_completion': 0.9,
                    'steps': {'step1': {'required_completion': 1.0}},
                },
                {
                    'template': 'cert.pdf',
                    'required_grades': {'exam': 0.8},
                    'required_completion': 0.9,
                    'steps': {'step1': {'required_completion': 1.0}},
                    'text_elements': {
                        'name': {'y': 300},
                    },
                },
            ),
            # Already in new format (should not be converted).
            (
                {
                    'template': 'cert.pdf',
                    'text_elements': {'name': {'y': 300}},
                },
                {
                    'template': 'cert.pdf',
                    'text_elements': {'name': {'y': 300}},
                },
            ),
            # template_multiline should not be overridden if it already exists.
            (
                {
                    'template': 'cert.pdf',
                    'template_two_lines': 'old.pdf',
                    'template_multiline': 'new.pdf',
                },
                {
                    'template': 'cert.pdf',
                    'template_multiline': 'new.pdf',
                },
            ),
        ],
    )
    def test_convert_to_text_elements(self, options: OptionsDict, expected: OptionsDict):
        """Test conversion from old flat format to new text_elements format."""
        _convert_to_text_elements(options)
        assert options == expected

    @pytest.mark.parametrize(
        ("options", "expected"),
        [
            # Empty options.
            ({}, {}),
            (None, None),
            # Template only (no new format markers, returned as-is).
            ({'template': 'cert.pdf'}, {'template': 'cert.pdf'}),
            # Template with multiline and text_elements (triggers conversion).
            (
                {'template': 'cert.pdf', 'template_multiline': 'cert2.pdf', 'text_elements': {}},
                {'template': 'cert.pdf', 'template_two_lines': 'cert2.pdf'},
            ),
            # Global font.
            (
                {'template': 'cert.pdf', 'defaults': {'font': 'Arial'}},
                {'template': 'cert.pdf', 'font': 'Arial'},
            ),
            # Name options.
            (
                {
                    'template': 'cert.pdf',
                    'text_elements': {
                        'name': {'y': 300, 'color': '#333', 'size': 24, 'uppercase': True},
                    },
                },
                {'template': 'cert.pdf', 'name_y': 300, 'name_color': '#333', 'name_size': 24, 'name_uppercase': True},
            ),
            # context.text option.
            (
                {
                    'template': 'cert.pdf',
                    'text_elements': {
                        'context': {'text': 'Custom Course Name'},
                    },
                },
                {'template': 'cert.pdf', 'context_name': 'Custom Course Name'},
            ),
            # Processor options should be preserved.
            (
                {
                    'template': 'cert.pdf',
                    'required_grades': {'exam': 0.8},
                    'required_completion': 0.9,
                    'steps': {'step1': {'required_completion': 1.0}},
                    'text_elements': {
                        'name': {'y': 300},
                    },
                },
                {
                    'template': 'cert.pdf',
                    'required_grades': {'exam': 0.8},
                    'required_completion': 0.9,
                    'steps': {'step1': {'required_completion': 1.0}},
                    'name_y': 300,
                },
            ),
            # Already in old format (should not be converted).
            (
                {'template': 'cert.pdf', 'name_y': 300},
                {'template': 'cert.pdf', 'name_y': 300},
            ),
        ],
    )
    def test_convert_to_flat_format(self, options: OptionsDict, expected: OptionsDict):
        """Test conversion from new text_elements format back to old flat format."""
        _convert_to_flat_format(options)
        assert options == expected

    def test_round_trip_conversion(self):
        """Test that converting to new format and back preserves the data."""
        original = {
            'template': 'cert.pdf',
            'font': 'Arial',
            'name_y': 300,
            'name_color': '#333',
            'context_name_y': 200,
            'context_name': 'Custom Course Name',
            'issue_date_y': 100,
            'issue_date_char_space': 2,
            'required_grades': {'exam': 0.8, 'quiz': 0.7},
            'required_completion': 0.9,
            'steps': {'step1': {'required_completion': 1.0}},
        }
        expected = copy.deepcopy(original)

        _convert_to_text_elements(original)

        # Verify processor options are intact after forward conversion.
        assert original['required_grades'] == expected['required_grades']
        assert original['required_completion'] == expected['required_completion']
        assert original['steps'] == expected['steps']

        _convert_to_flat_format(original)

        assert original == expected
