Configure PDF Credential Generation
####################################

This guide explains how to configure the PDF credential generator using the ``text_elements`` format.

Overview
********

The PDF credential generator renders text elements onto a PDF template. Three standard elements
are rendered by default:

- **name**: The learner's name
- **context**: The course or Learning Path name
- **date**: The issue date

Each element can be customized, hidden, or supplemented with custom text elements.

Basic Configuration
*******************

A minimal configuration only requires a template:

.. code-block:: json

    {
        "template": "certificate-template"
    }

This renders all three standard elements with default positioning.

Configuration Options
*********************

Top-Level Options
=================

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Option
     - Required
     - Description
   * - ``template``
     - Yes
     - The slug of the PDF template asset (from CredentialAsset).
   * - ``template_multiline``
     - No
     - Alternative template for multiline context names (when using ``\n``).
   * - ``defaults``
     - No
     - Global defaults for all text elements (see below).
   * - ``text_elements``
     - No
     - Configuration for individual text elements (see below).

Global Defaults
===============

The ``defaults`` object sets default values for all text elements:

.. code-block:: json

    {
        "defaults": {
            "font": "CustomFont",
            "color": "#333333",
            "size": 14,
            "char_space": 0.5,
            "uppercase": false,
            "line_height": 1.2
        }
    }

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Property
     - Default
     - Description
   * - ``font``
     - Helvetica
     - Font name (must be a CredentialAsset slug for custom fonts).
   * - ``color``
     - #000
     - Hex color code (3 or 6 characters, with or without ``#``).
   * - ``size``
     - 12
     - Font size in points.
   * - ``char_space``
     - 0
     - Character spacing in points.
   * - ``uppercase``
     - false
     - Convert text to uppercase.
   * - ``line_height``
     - 1.1
     - Line height multiplier for multiline text.

Text Elements
=============

The ``text_elements`` object configures individual elements. Standard elements (``name``,
``context``, ``date``) have defaults and can be partially overridden:

.. code-block:: json

    {
        "text_elements": {
            "name": {"y": 300, "uppercase": true},
            "context": {"size": 24},
            "date": {"color": "#666666"}
        }
    }

Element Properties
------------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Property
     - Default
     - Description
   * - ``text``
     - varies
     - Text content with placeholder substitution.
   * - ``y``
     - varies
     - Vertical position (PDF coordinates from bottom).
   * - ``size``
     - (inherited)
     - Font size in points (inherited from ``defaults.size``).
   * - ``font``
     - (inherited)
     - Font name (inherited from ``defaults.font``).
   * - ``color``
     - (inherited)
     - Hex color code (inherited from ``defaults.color``).
   * - ``char_space``
     - (inherited)
     - Character spacing (inherited from ``defaults.char_space``).
   * - ``uppercase``
     - (inherited)
     - Convert text to uppercase (inherited from ``defaults.uppercase``).
   * - ``line_height``
     - (inherited)
     - Line height multiplier for multiline text (inherited from ``defaults.line_height``).

Standard Element Defaults
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 15 25 10 10

   * - Element
     - Text
     - Y
     - Size
   * - ``name``
     - ``{name}``
     - 290
     - 32
   * - ``context``
     - ``{context_name}``
     - 220
     - 28
   * - ``date``
     - ``{issue_date}``
     - 120
     - 12

Django Settings
---------------

Some element defaults can be overridden globally via Django settings:

.. list-table::
   :header-rows: 1
   :widths: 45 15 40

   * - Setting
     - Default
     - Description
   * - ``LEARNING_CREDENTIALS_NAME_UPPERCASE``
     - ``False``
     - Convert name to uppercase by default.
   * - ``LEARNING_CREDENTIALS_DATE_UPPERCASE``
     - ``False``
     - Convert date to uppercase by default.
   * - ``LEARNING_CREDENTIALS_DATE_CHAR_SPACE``
     - ``0``
     - Default character spacing for date element.

These settings are applied before per-credential configuration, allowing you to set
organization-wide defaults while still permitting overrides in individual credentials.

Placeholders
============

Text content supports placeholder substitution using ``{placeholder}`` syntax:

- ``{name}`` - The learner's display name
- ``{context_name}`` - The course or Learning Path name
- ``{issue_date}`` - The localized issue date

To include literal braces, use ``{{`` and ``}}``:

.. code-block:: json

    {
        "text": "Score: {{95%}}"
    }

Hiding Elements
===============

Standard elements can be hidden by setting their configuration to ``false``:

.. code-block:: json

    {
        "text_elements": {
            "date": false
        }
    }

Custom Elements
===============

Add custom text elements by using any key other than ``name``, ``context``, or ``date``.
Custom elements require both ``text`` and ``y`` properties:

.. code-block:: json

    {
        "text_elements": {
            "award_line": {
                "text": "Awarded on {issue_date}",
                "y": 140,
                "size": 14
            },
            "institution": {
                "text": "Example University",
                "y": 80,
                "size": 10,
                "color": "#666666"
            }
        }
    }

Complete Example
****************

.. code-block:: json

    {
        "template": "certificate-template",
        "template_multiline": "certificate-multiline",
        "defaults": {
            "font": "OpenSans",
            "color": "#333333"
        },
        "text_elements": {
            "name": {
                "y": 300,
                "size": 36,
                "uppercase": true
            },
            "context": {
                "text": "Custom Course Name",
                "y": 230,
                "size": 24
            },
            "date": false,
            "award_line": {
                "text": "Awarded on {issue_date}",
                "y": 150,
                "size": 12,
                "color": "#666666"
            }
        }
    }

This configuration:

1. Uses ``OpenSans`` font and ``#333333`` color for all elements
2. Renders the name at y=300, size 36, in uppercase
3. Renders the context with custom text at y=230, size 24
4. Hides the default date element
5. Adds a custom "Awarded on [date]" line at y=150

Migration from Legacy Format
****************************

The legacy flat format (``name_y``, ``context_name_color``, etc.) has been migrated to the
new ``text_elements`` format. Existing configurations were automatically converted by
migration ``0007_migrate_to_text_elements_format``.

Legacy to New Format Mapping
============================

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Legacy Option
     - New Location
   * - ``font``
     - ``defaults.font``
   * - ``context_name``
     - ``text_elements.context.text``
   * - ``name_y``
     - ``text_elements.name.y``
   * - ``name_color``
     - ``text_elements.name.color``
   * - ``name_size``
     - ``text_elements.name.size``
   * - ``name_font``
     - ``text_elements.name.font``
   * - ``name_uppercase``
     - ``text_elements.name.uppercase``
   * - ``context_name_y``
     - ``text_elements.context.y``
   * - ``context_name_color``
     - ``text_elements.context.color``
   * - ``context_name_size``
     - ``text_elements.context.size``
   * - ``context_name_font``
     - ``text_elements.context.font``
   * - ``issue_date_y``
     - ``text_elements.date.y``
   * - ``issue_date_color``
     - ``text_elements.date.color``
   * - ``issue_date_size``
     - ``text_elements.date.size``
   * - ``issue_date_font``
     - ``text_elements.date.font``
   * - ``issue_date_char_space``
     - ``text_elements.date.char_space``
   * - ``issue_date_uppercase``
     - ``text_elements.date.uppercase``
   * - ``template_two_lines``
     - ``template_multiline``
