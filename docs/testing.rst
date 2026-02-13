.. _chapter-testing:

Testing
#######

learning-credentials has an assortment of test cases and code quality
checks to catch potential problems during development.  To run them all in the
version of Python you chose for your virtualenv:

.. code-block:: bash

    $ mise run validate

To run just the unit tests:

.. code-block:: bash

    $ mise run test

To run just the unit tests and check diff coverage:

.. code-block:: bash

    $ mise run diff-cover

To run just the code quality checks:

.. code-block:: bash

    $ mise run quality

To run the unit tests under every supported Python version and the code
quality checks:

.. code-block:: bash

    $ mise run test-all

To generate and open an HTML report of how much of the code is covered by
test cases:

.. code-block:: bash

    $ mise run coverage
