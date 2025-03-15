Getting Started
###############

Developing
**********

If you have not already done so, create/activate a `virtualenv`_. Unless otherwise stated, assume all terminal code
below is executed within the virtualenv.

.. _virtualenv: https://virtualenvwrapper.readthedocs.org/en/latest/

One Time Setup
==============
.. code-block:: bash

  # Clone the repository
  git clone git@github.com:open-craft/learning-credentials.git
  cd learning-credentials

  # Set up a virtualenv with the same name as the repo and activate it
  # Here's how you might do that if you have virtualenvwrapper setup.
  mkvirtualenv -p python3.11 learning-credentials

  # Install project dependencies
  make requirements


Every time you develop something in this repo
=============================================
.. code-block:: bash

  # Activate the virtualenv
  # Here's how you might do that if you're using virtualenvwrapper.
  workon learning-credentials

  # Grab the latest code
  git checkout main
  git pull

  # Install/update the dev requirements
  make requirements

  # Run the tests and quality checks (to verify the status before you make any changes)
  make validate

  # Make a new branch for your changes
  git checkout -b <your_github_username>/<short_description>

  # Using your favorite editor, edit the code to make your change.
  vim ...

  # Run your new tests
  pytest ./path/to/new/tests

  # Run all the tests and quality checks
  make validate

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
