Quick Start
###########

Diagram
=======

See the following diagram for a quick overview of the certificate generation process:

.. graphviz::

    digraph G {
        CertificateType [shape=box, color="black", label="Certificate Type\n\nProvides reusable configuration by storing the:\n- retrieval function\n- generation function\n- custom options"]
        CertificateCourseConfiguration [shape=box, color="black", label="Certificate Course Configuration\n\n1. Stores option overrides.\n2.Defines custom schedules for certificate generations."]
        RetrievalFunc [shape=ellipse, color="blue", label="retrieval_func\n\nA function that retrieves information\n about learners eligible for the certificate.\nIt defines the criteria for getting a certificate."]
        GenerationFunc [shape=ellipse, color="blue", label="generation_func\n\nA function that defines how the certificate\ngeneration process looks like\n(e.g., it creates a PDF file)."]
        Certificate [shape=box, color="black", label="Certificate\n\nThe generated certificate."]

        CertificateCourseConfiguration -> RetrievalFunc [label="runs"]
        RetrievalFunc -> GenerationFunc [label="sends data to"]
        CertificateType -> CertificateCourseConfiguration [label="provides default options"]
        GenerationFunc -> Certificate [label="generates"]
    }

Preparations
============

1. Go to ``Django admin -> learning_credentials``.
2. Go to the ``External certificate assets`` section and add your certificate template.
   You should also add all the assets that are used in the template (images, fonts, etc.).

   .. image:: ./images/assets.png

3. Create a new certificate type in the ``External certificate types`` section.
   Certificate types are reusable and can be used for multiple courses.
   Example of creating a certificate type.

   a. To create a certificate of completion, use the ``retrieve_course_completions``
      retrieval function. Ignore the "Custom options" for now. Click the
      "Save and continue editing" button instead. You will see the description of all
      optional parameters here.

         .. image:: ./images/type_completion.png

      You can add a custom option to specify the minimum completion required to
      receive the certificate. For example, if you want to issue a certificate only
      to students who achieved a completion of 80% or higher, you can add a custom
      option with the name ``required_completion`` and the value ``0.8``.
   b. To create a certificate of achievement, use the ``retrieve_subsection_grades``.
      The process is similar to the one described above. The customization options
      for minimum grade are a bit more complex, so make sure to read the description
      of the retrieval function. The generation function options are identical to
      the ones for the certificate of completion.

         .. image:: ./images/type_achievement.png

4. Configure the certificate type for a course in the ``External certificates course
   configurations`` section. You can also specify the custom options here to override
   the ones specified in the certificate type. For example, you can specify a different
   minimum completion for a specific course. Or, you can use a different certificate
   template for a specific course.

    .. image:: ./images/course_config.png

5. Once you press the "Save and continue editing" button, you will see the "Generate
   certificates" button. Press it to generate certificates for all students who meet
   the requirements.
6. You can also create a scheduled task to generate certificates automatically.
   On the course configuration page, you will see the "Associated periodic tasks"
   section. Here, you can set a custom schedule for generating certificates.

    .. image:: ./images/course_schedule.png
