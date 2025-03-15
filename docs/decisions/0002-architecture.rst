0002 Architecture
#################

.. TODO: This document will be moved to a plugin repo once we have a plugin architecture.

Status
******

**Provisional**


Context
*******

#. This Django app generates and shows user certificates.
#. The models should store certificate configurations. The certificate types will vary between different course types.
   The available course types are:

   #. :ref:`Course <course>`.
   #. :ref:`Lesson <lesson>`.
   #. :ref:`Pathway <pathway>`.

#. This Django app uses `celerybeat`_ to periodically retrieve data from an API (either the platform's Python API or the
   HTTP one). Retrieving this data is pluggable - it means that other developers can develop a Python package and
   install it to have a custom ways to retrieve data from different APIs.
#. We decided not to use `openedx-events`_ because retrieving the eligible users can be a heavy operation. Doing it on
   every block completion or problem submission is likely to cause performance issues. We may consider this approach in
   the future, but now we want to avoid adding more complexity.
#. If a user matches the criteria, the certificates will be generated from a PDF template (stored in the assets model).
   The PDF will be uploaded to S3, and the link will be sent to the user. The generation process should also be
   pluggable - it means that other developers can develop a Python package and install it to have custom ways to
   generate certificates.

.. _celerybeat: https://django-celery-beat.readthedocs.io/en/latest/
.. _openedx-events: https://github.com/openedx/openedx-events


Decision
********

.. graphviz::

    digraph G {
        node [shape=box, style=filled, fillcolor=gray95]
        edge [fontcolor=black, color=black]

        subgraph cluster_0 {
            label = "Open edX";
            style=filled;
            color=lightgrey;

            // Resources
            LMS;
        }

        subgraph cluster_1 {
            label = "learning-credentials";
            style=filled;
            color=lightgrey;

            // Resources/models
            CertificateType [label="ExternalCertificateType"]
            CourseConfiguration [label="ExternalCertificateCourseConfiguration"]
            Certificate [label="ExternalCertificate"]
            Asset [label="ExternalCertificateAsset"]
            PeriodicTask
            Schedule

            // Processes
            Processing [shape=ellipse]
            Generation [shape=ellipse]

            // DB relations
            edge [fontcolor=black, color=gray50]
            CertificateType -> CourseConfiguration [dir=back, headlabel="0..*", taillabel="1   "]
            CourseConfiguration -> PeriodicTask [dir=both, headlabel="1   ", taillabel="1"]

            // Non-DB relations
            edge [fontcolor=black, color=blue]
            CourseConfiguration -> Generation
            Asset -> Generation
            PeriodicTask -> Schedule

            // Processes
            edge [fontcolor=black, color=red]
            Schedule -> Processing [label="trigger"]
            Processing -> Generation [label="provide eligible users"]
            Generation -> Certificate [label="generate certificates"]
        }


        // Processes involving external APIs.
        edge [fontcolor=black, color=red]
        Processing -> LMS [label="pull data", dir=forward]

    }


User stories
************

TODO: Move this to the docs.

As an Instructor, I want to enable certificate generation for a course.
=======================================================================

To do this, I should:

#. Visit course certificate admin page.
#. Create a new entry with a course ID, certificate type and an "Enabled" toggle.
#. Internally, each of these entries will be a cron task. This way, we can set individual certificate generation schedules.
   It means that an Instructor can schedule generating different certificates for the same course at different times.

Once done, the celery cron will be scheduled to run at the specified time. The celery task will:

#. Retrieve data from the external API.
#. Check which users are eligible for a certificate.
#. Generate certificates for the eligible users.


Questions:

#. Should we use course's start/end date to gate cert generation?
#. Maybe we could disable the cron task when the course is closed?
