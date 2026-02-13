References
##########

Django Settings
***************

The following Django settings can be used to configure the learning-credentials service:

.. list-table::
   :header-rows: 1
   :widths: 40 15 45

   * - Setting
     - Default
     - Description
   * - ``LEARNING_CREDENTIALS_OUTPUT_DIR``
     - ``learning_credentials``
     - Directory (prefix) in Django default storage where generated credential PDFs are saved. Invalidated credentials are stored in ``<dir>_invalidated/``.
   * - ``LEARNING_CREDENTIALS_CUSTOM_DOMAIN``
     - ``None``
     - If set, credential download URLs will use this domain instead of the storage backend's URL. Format: ``https://cdn.example.com/path``.
   * - ``LEARNING_CREDENTIALS_NAME_UPPERCASE``
     - ``False``
     - Convert the learner's name to uppercase by default on PDF credentials.
   * - ``LEARNING_CREDENTIALS_DATE_UPPERCASE``
     - ``False``
     - Convert the issue date to uppercase by default on PDF credentials.
   * - ``LEARNING_CREDENTIALS_DATE_CHAR_SPACE``
     - ``0``
     - Default character spacing (in points) for the date text element on PDF credentials.
   * - ``CERTIFICATE_DATE_FORMAT``
     - (from Open edX)
     - The date format string used for localizing the credential issue date.
   * - ``PLATFORM_NAME``
     - (from Open edX)
     - The platform name included in credential notification emails.

REST API Endpoints
******************

All endpoints are under ``/api/learning_credentials/v1/``.

Check Credential Configuration
==============================

``GET /api/learning_credentials/v1/configured/<learning_context_key>/``

Check whether credentials are configured for a given learning context (course or Learning Path).
Requires authentication and access to the learning context.

**Response (200 OK):**

.. code-block:: json

    {
        "is_configured": true,
        "credential_types": ["Certificate of Completion"]
    }

Credential Metadata (Verification)
===================================

``GET /api/learning_credentials/v1/metadata/<verify_uuid>/``

Retrieve credential metadata by its verification UUID. This is a **public endpoint** (no authentication required) intended for third-party verification.

**Response (200 OK):**

.. code-block:: json

    {
        "user_full_name": "John Doe",
        "created": "2026-01-15T10:30:00Z",
        "learning_context_name": "Introduction to Computer Science",
        "status": "available",
        "invalidation_reason": ""
    }

**Response (404 Not Found):**

.. code-block:: json

    {
        "error": "Credential not found."
    }

Development Commands
********************

This project uses `mise <https://mise.jdx.dev/>`_ for development task management.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Command
     - Description
   * - ``mise run requirements``
     - Install development dependencies using uv
   * - ``mise run test``
     - Run tests with pytest
   * - ``mise run quality``
     - Run code quality checks (ruff, yamllint)
   * - ``mise run validate``
     - Run tests, quality checks, and PII compliance checks
   * - ``mise run lint``
     - Format and lint files with ruff (auto-fix mode)
   * - ``mise run test-all``
     - Run tests across all tox environments (Python 3.11/3.12, Django 4.2/5.2)
   * - ``mise run coverage``
     - Generate HTML coverage report and open in browser
   * - ``mise run diff-cover``
     - Find diff lines needing test coverage
   * - ``mise run pii_check``
     - Check PII annotations on Django models
   * - ``mise run docs``
     - Generate Sphinx documentation and open in browser
   * - ``mise run clean``
     - Remove generated artifacts and coverage reports
   * - ``mise run upgrade``
     - Update uv.lock with latest package versions
   * - ``mise run extract_translations``
     - Extract translatable strings
   * - ``mise run compile_translations``
     - Compile translation files
   * - ``mise run pull_translations``
     - Pull translations from Transifex
   * - ``mise run push_translations``
     - Push source translation files to Transifex
