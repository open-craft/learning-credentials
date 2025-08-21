"""
This module contains processors for credential criteria.

The functions prefixed with `retrieve_` are automatically detected by the admin page and are used to retrieve the
IDs of the users that meet the criteria for the credential type.

We will move this module to an external repository (a plugin).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from completion_aggregator.api.v1.views import CompletionDetailView
from django.contrib.auth import get_user_model
from learning_paths.models import LearningPath
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from learning_credentials.compat import (
    get_course_enrollments,
    get_course_grade,
    get_course_grading_policy,
    prefetch_course_grades,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from django.contrib.auth.models import User
    from opaque_keys.edx.keys import CourseKey, LearningContextKey
    from rest_framework.views import APIView


log = logging.getLogger(__name__)


def _process_learning_context(
    learning_context_key: LearningContextKey,
    course_processor: Callable[[CourseKey, dict[str, Any], int | None], dict[int, dict[str, Any]]],
    options: dict[str, Any],
    user_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    """
    Process a learning context (course or learning path) using the given course processor function.

    For courses, runs the processor directly. For learning paths, runs the processor on each
    course in the path with step-specific options (if available), and returns detailed results
    with step breakdown.

    Args:
        learning_context_key: A course key or learning path key to process
        course_processor: A function that processes a single course and returns detailed progress for all users
        options: Options to pass to the processor. For learning paths, may contain a "steps" key
                with step-specific options in the format: {"steps": {"<course_key>": {...}}}
        user_id: Optional. If provided, will filter to the specific user.

    Returns:
        A dict mapping user_id to detailed progress, with step breakdown for learning paths
    """
    if learning_context_key.is_course:
        return course_processor(learning_context_key, options, user_id)  # type: ignore[invalid-argument-type]

    learning_path = LearningPath.objects.get(key=learning_context_key)

    step_results_by_course = {}
    all_user_ids = set()

    # TODO: Use a single Completion Aggregator request when retrieving step results for a single user.
    for step in learning_path.steps.all():
        course_options = options.get("steps", {}).get(str(step.course_key), options)
        step_results = course_processor(step.course_key, course_options, user_id)

        step_results_by_course[str(step.course_key)] = step_results
        all_user_ids.update(step_results.keys())

    # Filter out users who are not enrolled in the Learning Path.
    all_user_ids &= set(
        learning_path.enrolled_users.filter(learningpathenrollment__is_active=True).values_list('id', flat=True)
    )

    final_results = {}
    for uid in all_user_ids:
        overall_eligible = True
        user_step_results = {}

        for course_key, step_results in step_results_by_course.items():
            if uid in step_results:
                user_step_results[course_key] = step_results[uid]
                overall_eligible = overall_eligible and step_results[uid].get('is_eligible', False)
            else:
                overall_eligible = False

        final_results[uid] = {'is_eligible': overall_eligible, 'steps': user_step_results}

    return final_results


def _get_category_weights(course_id: CourseKey) -> dict[str, float]:
    """
    Retrieve the course grading policy and return the weight of each category.

    :param course_id: The course ID to get the grading policy for.
    :returns: A dictionary with the weight of each category.
    """
    log.debug('Getting the course grading policy.')
    grading_policy = get_course_grading_policy(course_id)
    log.debug('Finished getting the course grading policy.')

    # Calculate the total weight of the non-exam categories
    log.debug(grading_policy)

    category_weight_ratios = {category['type'].lower(): category['weight'] for category in grading_policy}

    log.debug(category_weight_ratios)
    return category_weight_ratios


def _get_grades_by_format(course_id: CourseKey, users: list[User]) -> dict[int, dict[str, float]]:
    """
    Get the grades for each user, categorized by assignment types.

    :param course_id: The course ID.
    :param users: The users to get the grades for.
    :returns: A dictionary with the grades for each user, categorized by assignment types.
    """
    log.debug('Getting the grades for each user.')

    grades = {}

    with prefetch_course_grades(course_id, users):
        for user in users:
            grades[user.id] = {}
            course_grade = get_course_grade(user, course_id)
            for assignment_type, subsections in course_grade.graded_subsections_by_format().items():
                assignment_earned = 0
                assignment_possible = 0
                log.debug(subsections)
                for subsection in subsections.values():
                    assignment_earned += subsection.graded_total.earned
                    assignment_possible += subsection.graded_total.possible
                grade = (assignment_earned / assignment_possible) * 100 if assignment_possible > 0 else 0
                grades[user.id][assignment_type.lower()] = grade

    log.debug('Finished getting the grades for each user.')
    return grades


def _are_grades_passing_criteria(
    user_grades: dict[str, float],
    required_grades: dict[str, float],
    category_weights: dict[str, float],
) -> bool:
    """
    Determine whether the user received passing grades in all required categories.

    :param user_grades: The grades of the user, divided by category.
    :param required_grades: The required grades for each category.
    :param category_weights: The weight of each category.
    :returns: Whether the user received passing grades in all required categories.
    :raises ValueError: If a category weight is not found.
    """
    # If user does not have a grade for a category (except for the "total" category), it means that they did not
    # attempt it. Therefore, they should not be eligible for the credential.
    if not all(category in user_grades for category in required_grades if category != 'total'):
        return False

    total_score = 0
    for category, score in user_grades.items():
        if score < required_grades.get(category, 0):
            return False

        if category not in category_weights:
            msg = "Category weight '%s' was not found in the course grading policy."
            raise ValueError(msg, category)
        total_score += score * category_weights[category]

    return total_score >= required_grades.get('total', 0)


def _calculate_grades_progress(
    user_grades: dict[str, float],
    required_grades: dict[str, float],
    category_weights: dict[str, float],
) -> dict[str, Any]:
    """
    Calculate detailed progress information for grade-based criteria.

    :param user_grades: The grades of the user, divided by category.
    :param required_grades: The required grades for each category.
    :param category_weights: The weight of each category.
    :returns: Dict with is_eligible, current_grades, and required_grades.
    """
    # Calculate total score
    total_score = 0
    for category, score in user_grades.items():
        if category in category_weights:
            total_score += score * category_weights[category]

    # Add total to user grades
    user_grades_with_total = {**user_grades, 'total': total_score}

    is_eligible = _are_grades_passing_criteria(user_grades, required_grades, category_weights)

    return {
        'is_eligible': is_eligible,
        'current_grades': user_grades_with_total,
        'required_grades': required_grades,
    }


def _retrieve_course_subsection_grades(
    course_id: CourseKey, options: dict[str, Any], user_id: int | None = None
) -> dict[int, dict[str, Any]]:
    """Implementation for retrieving course grades. Always returns detailed progress for all users."""
    required_grades: dict[str, int] = options['required_grades']
    required_grades = {key.lower(): value * 100 for key, value in required_grades.items()}

    users = get_course_enrollments(course_id, user_id)
    grades = _get_grades_by_format(course_id, users)
    log.debug(grades)
    weights = _get_category_weights(course_id)

    results = {}
    for uid, user_grades in grades.items():
        results[uid] = _calculate_grades_progress(user_grades, required_grades, weights)

    return results


def retrieve_subsection_grades(
    learning_context_key: LearningContextKey, options: dict[str, Any], user_id: int | None = None
) -> list[int] | dict[str, Any]:
    """
    Retrieve the users that have passing grades in all required categories.

    :param learning_context_key: The learning context key (course or learning path).
    :param options: The custom options for the credential.
    :param user_id: Optional. If provided, will check eligibility for the specific user.
    :returns: The IDs of the users that have passing grades in all required categories.

    Options:
      - required_grades: A dictionary of required grades for each category, where the keys are the category names and
        the values are the minimum required grades. The grades are percentages, so they should be in the range [0, 1].
        See the following example::

          {
            "required_grades": {
              "Homework": 0.4,
              "Exam": 0.9,
              "Total": 0.8
            }
          }

        It means that the user must receive at least 40% in the Homework category and 90% in the Exam category.
        The "Total" key is a special value used to specify the minimum required grade for all categories in the course.
        Let's assume that we have the following grading policy (the percentages are the weights of each category):
        1. Homework: 20%
        2. Lab: 10%
        3. Exam: 70%
        The grades for the Total category will be calculated as follows:
        total_grade = (homework_grade * 0.2) + (lab_grade * 0.1) + (exam_grade * 0.7)
      - steps: For learning paths only. A dictionary with step-specific options in the format
        {"&lt;course_key&gt;": {...}}. If provided, each course in the learning path will use its specific
        options instead of the global options. Example::

          {
            "required_grades": {
              "Total": 0.8
            },
            "steps": {
              "course-v1:edX+DemoX+Demo_Course": {
                "required_grades": {
                  "Total": 0.9
                }
              },
              "course-v1:edX+CS101+2023": {
                "required_grades": {
                  "Homework": 0.5,
                  "Total": 0.7
                }
              }
            }
          }
    """
    detailed_results = _process_learning_context(
        learning_context_key, _retrieve_course_subsection_grades, options, user_id
    )

    if user_id is not None:
        if user_id in detailed_results:
            return detailed_results[user_id]
        return {'is_eligible': False, 'current_grades': {}, 'required_grades': {}}

    return [uid for uid, result in detailed_results.items() if result.get('is_eligible', False)]


def _prepare_request_to_completion_aggregator(course_id: CourseKey, query_params: dict, url: str) -> APIView:
    """
    Prepare a request to the Completion Aggregator API.

    :param course_id: The course ID.
    :param query_params: The query parameters to use in the request.
    :param url: The URL to use in the request.
    :returns: The view with the prepared request.
    """
    log.debug('Preparing the request for retrieving the completion.')

    # The URL does not matter, as we do not retrieve any data from the path.
    django_request = APIRequestFactory().get(url, query_params)
    django_request.course_id = course_id
    drf_request = Request(django_request)  # convert django.core.handlers.wsgi.WSGIRequest to DRF request

    view = CompletionDetailView()
    view.request = drf_request  # type: ignore[invalid-assignment]

    # HACK: Bypass the API permissions.
    staff_user = get_user_model().objects.filter(is_staff=True).first()
    view._effective_user = staff_user  # noqa: SLF001

    log.debug('Finished preparing the request for retrieving the completion.')
    return view


def _retrieve_course_completions(
    course_id: CourseKey, options: dict[str, Any], user_id: int | None = None
) -> dict[int, dict[str, Any]]:
    """Implementation for retrieving course completions. Always returns detailed progress for all users."""
    # If it turns out to be too slow, we can:
    # 1. Modify the Completion Aggregator to emit a signal/event when a user achieves a certain completion threshold.
    # 2. Get this data from the `Aggregator` model. Filter by `aggregation name == 'course'`, `course_key`, `percent`.

    required_completion = options.get('required_completion', 0.9)

    url = f'/completion-aggregator/v1/course/{course_id}/'
    # The API supports up to 10k results per page, but we limit it to 1k to avoid performance issues.
    query_params = {'page_size': 1000, 'page': 1}

    # TODO: Extract the logic of this view into an API. The current approach is very hacky.
    view = _prepare_request_to_completion_aggregator(course_id, query_params.copy(), url)
    completions = {}

    while True:
        # noinspection PyUnresolvedReferences
        response = view.get(view.request, str(course_id))
        log.debug(response.data)
        for res in response.data['results']:
            completions[res['username']] = res['completion']['percent']
        if not response.data['pagination']['next']:
            break
        query_params['page'] += 1
        view = _prepare_request_to_completion_aggregator(course_id, query_params.copy(), url)

    # Get all enrolled users and map usernames to user IDs
    users = get_course_enrollments(course_id, user_id)
    username_to_id = {user.username: user.id for user in users}  # type: ignore[unresolved-attribute]

    # Always return detailed progress for all users as dict
    detailed_results = {}
    for username, current_completion in completions.items():
        if username in username_to_id:
            user_id_for_result = username_to_id[username]
            progress = {
                'is_eligible': current_completion >= required_completion,
                'current_completion': current_completion,
                'required_completion': required_completion,
            }
            detailed_results[user_id_for_result] = progress

    return detailed_results


def retrieve_completions(
    learning_context_key: LearningContextKey, options: dict[str, Any], user_id: int | None = None
) -> list[int] | dict[str, Any]:
    """
    Retrieve the course completions for all users through the Completion Aggregator API.

    :param learning_context_key: The learning context key (course or learning path).
    :param options: The custom options for the credential.
    :param user_id: Optional. If provided, will check eligibility for the specific user.
    :returns: The IDs of the users that have achieved the required completion percentage.

    Options:
      - required_completion: The minimum required completion percentage. The default value is 0.9.
      - steps: For learning paths only. A dictionary with step-specific options in the format
        {"&lt;course_key&gt;": {...}}. If provided, each course in the learning path will use its specific
        options instead of the global options. Example::

          {
            "required_completion": 0.8,
            "steps": {
              "course-v1:edX+DemoX+Demo_Course": {
                "required_completion": 0.9
              },
              "course-v1:edX+CS101+2023": {
                "required_completion": 0.7
              }
            }
          }
    """
    detailed_results = _process_learning_context(learning_context_key, _retrieve_course_completions, options, user_id)

    if user_id is not None:
        if user_id in detailed_results:
            return detailed_results[user_id]
        return {'is_eligible': False, 'current_completion': 0.0, 'required_completion': 0.9}

    return [uid for uid, result in detailed_results.items() if result.get('is_eligible', False)]


def retrieve_completions_and_grades(
    learning_context_key: LearningContextKey, options: dict[str, Any], user_id: int | None = None
) -> list[int] | dict[str, Any]:
    """
    Retrieve the users that meet both completion and grade criteria.

    This processor combines the functionality of retrieve_course_completions and retrieve_subsection_grades.
    To be eligible, learners must satisfy both sets of criteria.

    :param learning_context_key: The learning context key (course or learning path).
    :param options: The custom options for the credential.
    :param user_id: Optional. If provided, will check eligibility for the specific user.
    :returns: The IDs of the users that meet both sets of criteria.

    Options:
      - required_completion: The minimum required completion percentage (default: 0.9)
      - required_grades: A dictionary of required grades for each category, where the keys are the category names and
        the values are the minimum required grades. The grades are percentages in the range [0, 1]. Example::

          {
            "required_grades": {
              "Homework": 0.4,
              "Exam": 0.9,
              "Total": 0.8
            }
          }

      - steps: For learning paths only. A dictionary with step-specific options in the format
        {"&lt;course_key&gt;": {...}}. If provided, each course in the learning path will use its specific
        options instead of the global options. Example::

          {
            "required_completion": 0.8,
            "required_grades": {
              "Total": 0.7
            },
            "steps": {
              "course-v1:edX+DemoX+Demo_Course": {
                "required_completion": 0.9,
                "required_grades": {
                  "Total": 0.8
                }
              },
              "course-v1:edX+CS101+2023": {
                "required_completion": 0.7,
                "required_grades": {
                  "Homework": 0.5,
                  "Total": 0.6
                }
              }
            }
          }
    """
    if user_id is not None:
        completion_result = retrieve_completions(learning_context_key, options, user_id)
        grades_result = retrieve_subsection_grades(learning_context_key, options, user_id)

        if type(grades_result) is not dict or type(completion_result) is not dict:
            msg = 'Both results must be dictionaries when user_id is provided.'
            raise ValueError(msg)

        completion_eligible = completion_result.get('is_eligible', False)
        grades_eligible = grades_result.get('is_eligible', False)

        return {
            **completion_result,
            **grades_result,
            'is_eligible': completion_eligible and grades_eligible,
        }

    completion_eligible_users = set(retrieve_completions(learning_context_key, options))
    grades_eligible_users = set(retrieve_subsection_grades(learning_context_key, options))

    return list(completion_eligible_users & grades_eligible_users)
