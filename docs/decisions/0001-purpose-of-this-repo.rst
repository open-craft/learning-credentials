0001 Purpose of This Repo
#########################

Status
******

**Accepted**

.. Standard statuses

    - **Draft** if the decision is newly proposed and in active discussion
    - **Provisional** if the decision is still preliminary and in experimental phase
    - **Accepted** *(date)* once it is agreed upon
    - **Superseded** *(date)* with a reference to its replacement if a later ADR changes or reverses the decision

    If an ADR has Draft status and the PR is under review, you can either use the intended final status
    (e.g. Provisional, Accepted, etc.), or you can clarify both the current and intended status using something like the
    following: "Draft (=> Provisional)". Either of these options is especially useful if the merged status is not
    intended to be Accepted.

Context
*******

We want to issue the credentials and badges for students participating in the courses.

The present workflow used by one of our clients is quite complex because they generate the credentials based on the
data pulled from the Open edX databases (MySQL and MongoDB). The purpose of this repository is to implement a service
closely connected with Open edX.

We want to support the following credential types:

#. Certificate of achievement
    We grant it when a student receives a passing grade in both of the following:

    #. Course assignments (excluding the final exam).
    #. The final exam.

#. Certificate of completion
    We grant it when a student receives the required percentage of the completion checkmarks in the course.

#. Badge of achievement/completion (temporary name)
    Almost identical to the credentials of achievement/completion. The only difference is that we award them for
    completing :ref:`Lessons <lesson>`.

#. Pathway credential
    We grant it when a student receives a passing grade in all courses/lessons in the :ref:`Pathway <pathway>`.

#. Achievement (temporary name)
    Similar to the `Badges`_, recently removed from Open edX. Example criteria:

    #. A student received a passing grade on the course assignments (excluding the final exam).
    #. A student received a passing grade on the final exam.
    #. A student received all completion checkmarks in the course.
    #. A student has posted a comment in the forum.


Other notes:

#. We do not need to pull data in real time. This service can retrieve data periodically, but the frequency should be
   configurable per course.
#. We need to design an interface for configuring these credentials per course. The goal is to make it as simple as
   possible for the course authors. It will be designed in a future iteration.

.. _Badges: https://edx.readthedocs.io/projects/edx-installing-configuring-and-running/en/latest/configuration/enable_badging.html

.. This section describes the forces at play, including technological, political, social, and project local.
   These forces are probably in tension, and should be called out as such. The language in this section is
   value-neutral. It is simply describing facts.

Decision
********

#. We will implement the credentials mechanism as a Django app plugin.
#. This plugin will be installed on the same server as the Open edX instance. It will use the same database as the
   Open edX instance to optimize the performance. This decision is made to minimize the latency that would be
   introduced by querying web APIs.
#. The goal is to rely only on the public Python APIs and avoid direct access to the database or models. This is to
   minimize breaking changes in the next Open edX releases.
#. The details of this plugin's architecture are described in the :doc:`0002-architecture` document.

.. This section describes our response to these forces. It is stated in full sentences, with active voice. "We will …"

Consequences
************

We will stop using the built-in credentials mechanism. The goal of this repository is to have as little dependencies
from the core ``edx-platform`` as possible to make it easier to maintain and upgrade.

.. This section describes the resulting context, after applying the decision. All consequences should be listed here,
   not just the "positive" ones. A particular decision may have positive, negative, and neutral consequences, but all of
   them affect the team and project in the future.

Rejected Alternatives
*********************

We considered:

#. Using the certificates built into Open edX.
    However, we need to rework them significantly to meet the described requirements. Given the plans to migrate
    the course certificates to the `credentials`_ service, maintaining this approach could take a lot of work.
#. Using the `credentials`_ service.
    Currently, this service supports only Programs. It means that it is tightly coupled to the `course-discovery`_ IDA.
    We will use :ref:`Pathway <pathway>` instead of Programs to remove this dependency and gain more flexibility.
    Therefore, the `credentials`_ service would also require significant reworks to support the necessary features.
#. Using the existing implementation of the `Badges`_.
    This code was not maintained for a long time and was recently removed from Open edX.

.. _credentials: https://github.com/openedx/credentials
.. _course-discovery: https://github.com/openedx/course-discovery

.. This section lists alternate options considered, described briefly, with pros and cons.

Definitions
***********

#. **Course**

   .. _course:

   A standard Open edX course.

#. **Lesson**

   .. _lesson:

   A course that consists of a single section. The `section-to-course`_ extension extracts this section from a "full"
   course.

#. **Pathway**

   .. _pathway:

   A similar concept to Open edX Programs but handled by an Open edX plugin. Once we complete the Pathway planning
   phase, we will update this definition and add a link.

.. _section-to-course: https://github.com/open-craft/section-to-course/
