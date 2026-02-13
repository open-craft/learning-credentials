Change Log
##########

..
   All enhancements and patches to learning_credentials will be documented
   in this file.  It adheres to the structure of https://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).

   This project adheres to Semantic Versioning (https://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Unreleased
**********

*

0.5.0 - 2026-01-29
******************

Added
=====

* Credential validation and invalidation system with ``INVALIDATED`` status.
* ``verify_uuid`` field on credentials — a separate UUID used for third-party verification, distinct from the primary key.
* ``invalidated_at`` timestamp and ``invalidation_reason`` fields on the ``Credential`` model.
* ``learning_context_name`` cached field on credentials for use in validation display.
* Public API endpoint (``/api/learning_credentials/v1/metadata/<uuid>/``) to retrieve credential metadata by verification UUID.
* "Reissue credential" admin action that invalidates the current credential and generates a new one.
* ``{verify_uuid}`` placeholder support in PDF text elements.
* Admin test suite (``test_admin.py``) and included it in test coverage.

Changed
=======

* Replaced ``user_id`` (IntegerField) with a ``user`` ForeignKey to the User model.
* Added ``configuration`` ForeignKey on ``Credential`` linking to ``CredentialConfiguration``, replacing ``credential_type`` and ``learning_context_key`` lookups.
* Simplified ``generate_pdf_credential()`` signature to accept a ``Credential`` object instead of separate parameters.
* Changed the PDF output directory from hardcoded ``external_certificates/`` to the configurable ``LEARNING_CREDENTIALS_OUTPUT_DIR`` setting.
* Credential issue date on PDFs now uses the credential's creation date instead of the current time.
* ``get_localized_credential_date()`` now accepts an explicit ``datetime`` parameter.
* Disabled add and delete permissions for credentials in the Django admin.

0.4.0 - 2026-01-28
******************

Added
=====

* New ``text_elements`` format for PDF credential generation with flexible text positioning and placeholder support.
* Support for custom text elements with ``{name}``, ``{context_name}``, and ``{issue_date}`` placeholders.
* Global ``defaults`` configuration for font, color, and character spacing.

Modified
========

* Migrated generator options from flat format (``name_y``, ``context_name_color``, etc.) to structured ``text_elements`` format.

0.3.1 - 2025-12-15
******************

Added
=====

* Support for defining the course name using the ``cert_name_long`` field (in Studio's Advanced Settings).
* Support for specifying individual fonts for PDF text elements.
* Support for \n in learning context names in PDF certificates.
* Options for uppercase name and issue date in PDF certificates.
* Option for defining character spacing for issue date in PDF certificates.
* Option for defining the horizontal offset of the issue date from its centered position (``issue_date_x``).

Modified
========

* Replaced ``template_two_lines`` with ``template_multiline``.

0.3.0 - 2025-09-17
******************

Added
=====

* REST API endpoint to check if credentials are configured for a learning context.

0.2.4 - 2025-09-07

Added
=====

* Option to customize the learner's name size on the PDF certificate.

0.2.3 - 2025-08-18

Modified
========

* Certificate email template wording.

0.2.2 - 2025-08-05

Added
=====

* Step-specific options support for Learning Path credentials.

Removed
=======

* Legacy `openedx_certificates` app.

0.2.1 – 2025-05-05
******************

Fixed
=====

* Check enrollment status before issuing Learning Path credentials.

0.2.0 – 2025-04-03
******************

Added
=====

* Learning Paths support.


0.1.0 – 2025-01-29
******************

Added
=====

* Initial implementation of the certificates app.
