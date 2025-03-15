Quick Start
###########

Diagram
=======

See the following diagram for a quick overview of the credential generation process:

.. graphviz::

    digraph G {
        CredentialType [shape=box, color="black", label="Credential Type\n\nProvides reusable configuration by storing the:\n- retrieval function\n- generation function\n- custom options"]
        CredentialCourseConfiguration [shape=box, color="black", label="Credential Course Configuration\n\n1. Stores option overrides.\n2.Defines custom schedules for credential generations."]
        RetrievalFunc [shape=ellipse, color="blue", label="retrieval_func\n\nA function that retrieves information\n about learners eligible for the credential.\nIt defines the criteria for getting a credential."]
        GenerationFunc [shape=ellipse, color="blue", label="generation_func\n\nA function that defines how the credential\ngeneration process looks like\n(e.g., it creates a PDF file)."]
        Credential [shape=box, color="black", label="Credential\n\nThe generated credential."]

        CredentialCourseConfiguration -> RetrievalFunc [label="runs"]
        RetrievalFunc -> GenerationFunc [label="sends data to"]
        CredentialType -> CredentialCourseConfiguration [label="provides default options"]
        GenerationFunc -> Credential [label="generates"]
    }

Preparations
============

1. Go to ``Django admin -> learning_credentials``.
2. Go to the ``External credential assets`` section and add your credential template.
   You should also add all the assets that are used in the template (images, fonts, etc.).

   .. image:: ./images/assets.png

3. Create a new credential type in the ``External credential types`` section.
   Credential types are reusable and can be used for multiple courses.
   Example of creating a credential type.

   a. To create a credential of completion, use the ``retrieve_course_completions``
      retrieval function. Ignore the "Custom options" for now. Click the
      "Save and continue editing" button instead. You will see the description of all
      optional parameters here.

         .. image:: ./images/type_completion.png

      You can add a custom option to specify the minimum completion required to
      receive the credential. For example, if you want to issue a credential only
      to students who achieved a completion of 80% or higher, you can add a custom
      option with the name ``required_completion`` and the value ``0.8``.
   b. To create a credential of achievement, use the ``retrieve_subsection_grades``.
      The process is similar to the one described above. The customization options
      for minimum grade are a bit more complex, so make sure to read the description
      of the retrieval function. The generation function options are identical to
      the ones for the credential of completion.

         .. image:: ./images/type_achievement.png

4. Configure the credential type for a course in the ``External credentials course
   configurations`` section. You can also specify the custom options here to override
   the ones specified in the credential type. For example, you can specify a different
   minimum completion for a specific course. Or, you can use a different credential
   template for a specific course.

    .. image:: ./images/course_config.png

5. Once you press the "Save and continue editing" button, you will see the "Generate
   credentials" button. Press it to generate credentials for all students who meet
   the requirements.
6. You can also create a scheduled task to generate credentials automatically.
   On the course configuration page, you will see the "Associated periodic tasks"
   section. Here, you can set a custom schedule for generating credentials.

    .. image:: ./images/course_schedule.png
