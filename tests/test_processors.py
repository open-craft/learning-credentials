"""Tests for the credential processors."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, call, patch

import pytest
from django.http import QueryDict
from opaque_keys.edx.keys import CourseKey

# noinspection PyProtectedMember
from learning_credentials.processors import (
    _are_grades_passing_criteria,
    _get_category_weights,
    _get_grades_by_format,
    _prepare_request_to_completion_aggregator,
    retrieve_completions,
    retrieve_completions_and_grades,
    retrieve_subsection_grades,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.contrib.auth.models import User
    from learning_paths.models import LearningPath


@patch(
    'learning_credentials.processors.get_course_grading_policy',
    return_value=[{'type': 'Homework', 'weight': 0.15}, {'type': 'Exam', 'weight': 0.85}],
)
def test_get_category_weights(mock_get_course_grading_policy: Mock):
    """Check that the course grading policy is retrieved and the category weights are calculated correctly."""
    course_id = Mock(spec=CourseKey)
    assert _get_category_weights(course_id) == {'homework': 0.15, 'exam': 0.85}
    mock_get_course_grading_policy.assert_called_once_with(course_id)


@patch('learning_credentials.processors.prefetch_course_grades')
@patch('learning_credentials.processors.get_course_grade')
def test_get_grades_by_format(mock_get_course_grade: Mock, mock_prefetch_course_grades: Mock):
    """Test that grades are retrieved for each user and categorized by assignment types."""
    course_id = Mock(spec=CourseKey)
    users = [Mock(name="User1", id=101), Mock(name="User2", id=102)]

    mock_get_course_grade.return_value.graded_subsections_by_format.return_value = {
        'Homework': {'subsection1': Mock(graded_total=Mock(earned=50.0, possible=100.0))},
        'Exam': {'subsection2': Mock(graded_total=Mock(earned=90.0, possible=100.0))},
    }

    result = _get_grades_by_format(course_id, users)

    assert result == {101: {'homework': 50.0, 'exam': 90.0}, 102: {'homework': 50.0, 'exam': 90.0}}
    mock_prefetch_course_grades.assert_called_once_with(course_id, users)

    mock_get_course_grade.assert_has_calls(
        [
            call(users[0], course_id),
            call().graded_subsections_by_format(),
            call(users[1], course_id),
            call().graded_subsections_by_format(),
        ],
    )


_are_grades_passing_criteria_test_data = [
    (
        "All grades are passing",
        {"homework": 90, "lab": 90, "exam": 90},
        {"homework": 85, "lab": 80, "exam": 60, "total": 50},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        True,
    ),
    (
        "The homework grade is failing",
        {"homework": 80, "lab": 90, "exam": 70},
        {"homework": 85, "lab": 80, "exam": 60, "total": 50},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        False,
    ),
    (
        "The total grade is failing",
        {"homework": 90, "lab": 90, "exam": 70},
        {"homework": 85, "lab": 80, "exam": 60, "total": 300},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        False,
    ),
    (
        "Only the total grade is required",
        {"homework": 90, "lab": 90, "exam": 70},
        {"total": 50},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        True,
    ),
    (
        "Total grade is not required",
        {"homework": 90, "lab": 90, "exam": 70},
        {"homework": 85, "lab": 80},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        True,
    ),
    (
        "Required grades are not defined",
        {"homework": 80, "lab": 90, "exam": 70},
        {},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        True,
    ),
    (
        "User has no grades",
        {},
        {"homework": 85, "lab": 80, "exam": 60, "total": 240},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        False,
    ),
    ("User has no grades and the required grades are not defined", {}, {}, {}, True),
    (
        "User has no grades in a required category",
        {"homework": 90, "lab": 85},
        {"homework": 85, "lab": 80, "exam": 60},
        {"homework": 0.3, "lab": 0.3, "exam": 0.4},
        False,
    ),
]


@pytest.mark.parametrize(
    ('desc', 'user_grades', 'required_grades', 'category_weights', 'expected'),
    _are_grades_passing_criteria_test_data,
    ids=[i[0] for i in _are_grades_passing_criteria_test_data],
)
def test_are_grades_passing_criteria(
    desc: str,  # noqa: ARG001
    user_grades: dict[str, float],
    required_grades: dict[str, float],
    category_weights: dict[str, float],
    expected: bool,
):
    """Test that the user grades are compared to the required grades correctly."""
    assert _are_grades_passing_criteria(user_grades, required_grades, category_weights) == expected


def test_are_grades_passing_criteria_invalid_grade_category():
    """Test that an exception is raised if user grades contain a category that is not defined in the grading policy."""
    with pytest.raises(ValueError, match='unknown_category'):
        _are_grades_passing_criteria(
            {"homework": 90, "unknown_category": 90},
            {"total": 175},
            {"homework": 0.5, "lab": 0.5},
        )


@patch('learning_credentials.processors.get_course_enrollments')
@patch('learning_credentials.processors._get_grades_by_format')
@patch('learning_credentials.processors._get_category_weights')
def test_retrieve_subsection_grades(
    mock_get_category_weights: Mock,
    mock_get_grades_by_format: Mock,
    mock_get_course_enrollments: Mock,
):
    """Test that the function returns detailed eligibility results for users."""
    course_id = Mock(spec=CourseKey)
    options = {
        'required_grades': {
            'homework': 0.4,
            'exam': 0.9,
            'total': 0.8,
        },
    }
    users = [Mock(name="User1", id=101), Mock(name="User2", id=102)]
    grades = {
        101: {'homework': 80.0, 'exam': 95.0},
        102: {'homework': 30.0, 'exam': 95.0},
    }
    weights = {'homework': 0.2, 'exam': 0.7, 'lab': 0.1}

    mock_get_course_enrollments.return_value = users
    mock_get_grades_by_format.return_value = grades
    mock_get_category_weights.return_value = weights

    result = retrieve_subsection_grades(course_id, options)

    assert 101 in result
    assert 102 in result
    assert result[101]['is_eligible'] is True
    assert result[102]['is_eligible'] is False
    assert 'current_grades' in result[101]
    assert 'required_grades' in result[101]
    mock_get_course_enrollments.assert_called_once_with(course_id, None)
    mock_get_grades_by_format.assert_called_once_with(course_id, users)
    mock_get_category_weights.assert_called_once_with(course_id)


@patch('learning_credentials.processors.get_course_enrollments')
@patch('learning_credentials.processors._get_grades_by_format')
@patch('learning_credentials.processors._get_category_weights')
def test_retrieve_subsection_grades_unknown_grade_category(
    mock_get_category_weights: Mock,
    mock_get_grades_by_format: Mock,
    mock_get_course_enrollments: Mock,
):
    """Test that grade categories not in the grading policy are skipped in total calculation."""
    course_id = Mock(spec=CourseKey)

    options = {'required_grades': {'exam': 0.9}}
    users = [Mock(name="User1", id=101)]
    grades = {101: {'homework': 80.0, 'lab': 100.0}}
    weights = {'homework': 0.5, 'exam': 0.5}

    mock_get_course_enrollments.return_value = users
    mock_get_grades_by_format.return_value = grades
    mock_get_category_weights.return_value = weights

    result = retrieve_subsection_grades(course_id, options)

    assert result[101]['is_eligible'] is False
    assert result[101]['current_grades']['total'] == 80.0 * 0.5


def test_prepare_request_to_completion_aggregator():
    """Test that the request to the completion aggregator API is prepared correctly."""
    course_id = Mock(spec=CourseKey)
    query_params = {'param1': 'value1', 'param2': 'value2'}
    url = '/test_url/'

    with (
        patch('learning_credentials.processors.get_user_model') as mock_get_user_model,
        patch(
            'learning_credentials.processors.CompletionDetailView',
        ) as mock_view_class,
    ):
        staff_user = Mock(is_staff=True)
        mock_get_user_model().objects.filter().first.return_value = staff_user

        view = _prepare_request_to_completion_aggregator(course_id, query_params, url)

        mock_view_class.assert_called_once()
        assert view.request.course_id == course_id
        # noinspection PyUnresolvedReferences
        assert view._effective_user is staff_user
        assert isinstance(view, mock_view_class.return_value.__class__)

        # Create a QueryDict from the query_params dictionary.
        query_params_qdict = QueryDict('', mutable=True)
        query_params_qdict.update(query_params)
        assert view.request.query_params.urlencode() == query_params_qdict.urlencode()


@patch('learning_credentials.processors._prepare_request_to_completion_aggregator')
@patch('learning_credentials.processors.get_course_enrollments')
def test_retrieve_course_completions(
    mock_get_course_enrollments: Mock, mock_prepare_request_to_completion_aggregator: Mock
):
    """Test that we retrieve the course completions for all users and return detailed results."""
    course_id = Mock(spec=CourseKey)
    options = {'required_completion': 0.8}
    completions_page1 = {
        'pagination': {'next': '/completion-aggregator/v1/course/{course_id}/?page=2&page_size=1000'},
        'results': [
            {'username': 'user1', 'completion': {'percent': 0.9}},
        ],
    }
    completions_page2 = {
        'pagination': {'next': None},
        'results': [
            {'username': 'user2', 'completion': {'percent': 0.7}},
            {'username': 'user3', 'completion': {'percent': 0.8}},
            {'username': 'unenrolled_user', 'completion': {'percent': 0.95}},
        ],
    }

    mock_view_page1 = Mock()
    mock_view_page1.get.return_value.data = completions_page1
    mock_view_page2 = Mock()
    mock_view_page2.get.return_value.data = completions_page2
    mock_prepare_request_to_completion_aggregator.side_effect = [mock_view_page1, mock_view_page2]

    # Mock enrolled users to map usernames to IDs.
    mock_get_course_enrollments.return_value = [
        Mock(username='user1', id=1),
        Mock(username='user2', id=2),
        Mock(username='user3', id=3),
    ]

    result = retrieve_completions(course_id, options)

    assert result[1] == {'is_eligible': True, 'current_completion': 0.9, 'required_completion': 0.8}
    assert result[2] == {'is_eligible': False, 'current_completion': 0.7, 'required_completion': 0.8}
    assert result[3] == {'is_eligible': True, 'current_completion': 0.8, 'required_completion': 0.8}
    mock_prepare_request_to_completion_aggregator.assert_has_calls(
        [
            call(course_id, {'page_size': 1000, 'page': 1}, f'/completion-aggregator/v1/course/{course_id}/'),
            call(course_id, {'page_size': 1000, 'page': 2}, f'/completion-aggregator/v1/course/{course_id}/'),
        ],
    )
    mock_view_page1.get.assert_called_once_with(mock_view_page1.request, str(course_id))
    mock_view_page2.get.assert_called_once_with(mock_view_page2.request, str(course_id))


@pytest.mark.parametrize(
    ('completion_results', 'grade_results', 'expected_eligible_ids'),
    [
        (
            {101: {'is_eligible': True}, 102: {'is_eligible': True}, 103: {'is_eligible': True}},
            {102: {'is_eligible': True}, 103: {'is_eligible': True}, 104: {'is_eligible': True}},
            {102, 103},
        ),
        (
            {101: {'is_eligible': True}, 102: {'is_eligible': True}},
            {103: {'is_eligible': True}, 104: {'is_eligible': True}},
            set(),
        ),
        (
            {101: {'is_eligible': True}, 102: {'is_eligible': True}},
            {101: {'is_eligible': True}, 102: {'is_eligible': True}},
            {101, 102},
        ),
        (
            {101: {'is_eligible': True}, 102: {'is_eligible': True}},
            {},
            set(),
        ),
    ],
    ids=[
        "Some users pass both criteria",
        "No overlap between eligible users",
        "All users pass both criteria",
        "One criteria returns no users",
    ],
)
@patch("learning_credentials.processors.retrieve_subsection_grades")
@patch("learning_credentials.processors.retrieve_completions")
def test_retrieve_course_completions_and_grades(
    mock_retrieve_completions: Mock,
    mock_retrieve_subsection_grades: Mock,
    completion_results: dict,
    grade_results: dict,
    expected_eligible_ids: set[int],
):
    """Test that the function merges results for users present in both criteria."""
    course_id = Mock(spec=CourseKey)
    options = Mock()

    mock_retrieve_completions.return_value = completion_results
    mock_retrieve_subsection_grades.return_value = grade_results

    result = retrieve_completions_and_grades(course_id, options)

    assert set(result.keys()) == expected_eligible_ids
    for uid in expected_eligible_ids:
        assert result[uid]['is_eligible'] is True
    mock_retrieve_completions.assert_called_once_with(course_id, options, None)
    mock_retrieve_subsection_grades.assert_called_once_with(course_id, options, None)


@pytest.mark.parametrize(
    ('patch_target', 'function_to_test'),
    [
        ("learning_credentials.processors._retrieve_course_subsection_grades", retrieve_subsection_grades),
        ("learning_credentials.processors._retrieve_course_completions", retrieve_completions),
    ],
    ids=['subsection_grades', 'completions'],
)
@pytest.mark.django_db
def test_retrieve_data_for_learning_path(
    patch_target: str,
    function_to_test: Callable,
    learning_path_with_courses: LearningPath,
    users: list[User],
):
    """Test retrieving data for a learning path returns eligible users with step breakdown."""
    with patch(patch_target) as mock_retrieve:
        options = {}

        def make_results(user_indices: tuple) -> dict[int, dict]:
            return {users[i].id: {'is_eligible': True} for i in user_indices}

        mock_retrieve.side_effect = [
            make_results((0, 1, 2, 4, 5)),  # Users passing/completing course0
            make_results((0, 1, 2, 3, 4, 5)),  # Users passing/completing course1
            make_results((0, 2, 3, 4, 5)),  # Users passing/completing course2
        ]

        result = function_to_test(learning_path_with_courses.key, options)

        # users[0] and users[2] pass all 3 courses AND are enrolled+active in the learning path.
        # users[4] passes all 3 but enrollment is inactive. users[5] is not enrolled at all.
        eligible_ids = sorted(uid for uid, details in result.items() if details['is_eligible'])
        assert eligible_ids == [users[0].id, users[2].id]

        assert mock_retrieve.call_count == 3
        course_keys = [step.course_key for step in learning_path_with_courses.steps.all()]
        for i, course_key in enumerate(course_keys):
            call_args = mock_retrieve.call_args_list[i]
            assert call_args[0] == (course_key, options, None)


@patch("learning_credentials.processors._retrieve_course_completions")
@pytest.mark.django_db
def test_retrieve_data_for_learning_path_with_step_options(
    mock_retrieve: Mock,
    learning_path_with_courses: LearningPath,
):
    """Test retrieving data for a learning path with step-specific options."""
    mock_retrieve.return_value = {}
    course_keys = [step.course_key for step in learning_path_with_courses.steps.all()]

    options = {
        "required_completion": 0.7,
        "steps": {
            str(course_keys[0]): {"required_completion": 0.8},
            str(course_keys[1]): {"required_completion": 0.9},
            # course_keys[2] will use base options
        },
    }

    retrieve_completions(learning_path_with_courses.key, options)

    assert mock_retrieve.call_count == 3
    assert mock_retrieve.call_args_list[0][0] == (course_keys[0], options["steps"][str(course_keys[0])], None)
    assert mock_retrieve.call_args_list[1][0] == (course_keys[1], options["steps"][str(course_keys[1])], None)
    assert mock_retrieve.call_args_list[2][0] == (course_keys[2], options, None)
