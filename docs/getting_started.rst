Getting Started
###############

Developing
**********

Prerequisites
=============

- Python (see the ``requires-python`` field in ``pyproject.toml`` for the supported versions)
- `mise <https://mise.jdx.dev/>`_ (Modern Infrastructure for Systems Engineering) for task management
- `uv <https://docs.astral.sh/uv/>`_ for Python package management

One Time Setup
==============
.. code-block:: bash

  # Clone the repository
  git clone git@github.com:open-craft/learning-credentials.git
  cd learning-credentials

  # Install development dependencies (creates a virtual environment automatically)
  mise run requirements


Every time you develop something in this repo
=============================================
.. code-block:: bash

  # Grab the latest code
  git checkout main
  git pull

  # Install/update the dev requirements
  mise run requirements

  # Activate the virtualenv
  . .venv/bin/activate

  # Run the tests and quality checks (to verify the status before you make any changes)
  mise run validate

  # Make a new branch for your changes
  git checkout -b <your_github_username>/<short_description>

  # Using your favorite editor, edit the code to make your change.
  vim ...

  # Run your new tests
  mise run test tests/path/to/the/test

  # Run all the tests and quality checks
  mise run test-all

  # Commit all your changes
  git commit ...
  git push

  # Open a PR and ask for review.


Deploying
*********

TODO: Document this.

Ansible Playbooks
=================

If you still use the `configuration`_ repository to deploy your Open edX instance, set
``EDXAPP_ENABLE_CELERY_BEAT: true`` to enable the Celery beat service. Without this, periodic tasks will not be run.

.. _configuration: https://github.com/openedx/configuration
