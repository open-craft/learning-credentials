"""Tests for the credential processors."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, call, patch

import pytest
from django.http import QueryDict
from learning_paths.models import LearningPath
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
from test_utils.factories import UserFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.contrib.auth.models import User


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
    expected: bool,  # noqa: FBT001
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
@patch('learning_credentials.processors._are_grades_passing_criteria')
def test_retrieve_subsection_grades(
    mock_are_grades_passing_criteria: Mock,
    mock_get_category_weights: Mock,
    mock_get_grades_by_format: Mock,
    mock_get_course_enrollments: Mock,
):
    """Test that the function returns the eligible users."""
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
        101: {'homework': 0.5, 'exam': 0.9},
        102: {'homework': 0.3, 'exam': 0.95},
    }
    required_grades = {'homework': 40.0, 'exam': 90.0, 'total': 80.0}
    weights = {'homework': 0.2, 'exam': 0.7, 'lab': 0.1}

    mock_get_course_enrollments.return_value = users
    mock_get_grades_by_format.return_value = grades
    mock_get_category_weights.return_value = weights
    mock_are_grades_passing_criteria.side_effect = [True, False]

    result = retrieve_subsection_grades(course_id, options)

    assert result == [101]
    mock_get_course_enrollments.assert_called_once_with(course_id, None)
    mock_get_grades_by_format.assert_called_once_with(course_id, users)
    mock_get_category_weights.assert_called_once_with(course_id)
    mock_are_grades_passing_criteria.assert_has_calls(
        [
            call(grades[101], required_grades, weights),
            call(grades[102], required_grades, weights),
        ],
    )


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


@patch('learning_credentials.processors.get_course_enrollments')
@patch('learning_credentials.processors._prepare_request_to_completion_aggregator')
def test_retrieve_course_completions(
    mock_prepare_request_to_completion_aggregator: Mock,
    mock_get_course_enrollments: Mock,
):
    """Test that we retrieve the course completions for all users and return IDs of users who meet the criteria."""
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
        ],
    }

    mock_view_page1 = Mock()
    mock_view_page1.get.return_value.data = completions_page1
    mock_view_page2 = Mock()
    mock_view_page2.get.return_value.data = completions_page2
    mock_prepare_request_to_completion_aggregator.side_effect = [mock_view_page1, mock_view_page2]

    users = [Mock(username="user1", id=1), Mock(username="user2", id=2), Mock(username="user3", id=3)]
    mock_get_course_enrollments.return_value = users

    result = retrieve_completions(course_id, options)

    assert result == [1, 3]
    mock_prepare_request_to_completion_aggregator.assert_has_calls(
        [
            call(course_id, {'page_size': 1000, 'page': 1}, f'/completion-aggregator/v1/course/{course_id}/'),
            call(course_id, {'page_size': 1000, 'page': 2}, f'/completion-aggregator/v1/course/{course_id}/'),
        ],
    )
    mock_view_page1.get.assert_called_once_with(mock_view_page1.request, str(course_id))
    mock_view_page2.get.assert_called_once_with(mock_view_page2.request, str(course_id))
    mock_get_course_enrollments.assert_called_once_with(course_id, None)


@pytest.mark.parametrize(
    ('completion_users', 'grades_users', 'expected_result'),
    [
        ([101, 102, 103], [102, 103, 104], [102, 103]),
        ([101, 102], [103, 104], []),
        ([101, 102], [101, 102], [101, 102]),
        ([101, 102], [], []),
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
    completion_users: list[int],
    grades_users: list[int],
    expected_result: list[int],
):
    """Test that the function returns the intersection of eligible users from both criteria."""
    course_id = Mock(spec=CourseKey)
    options = Mock()

    mock_retrieve_completions.return_value = completion_users
    mock_retrieve_subsection_grades.return_value = grades_users

    result = retrieve_completions_and_grades(course_id, options)

    assert result == expected_result
    mock_retrieve_completions.assert_called_once_with(course_id, options)
    mock_retrieve_subsection_grades.assert_called_once_with(course_id, options)


@pytest.fixture
def users() -> list[User]:
    """Create a list of users."""
    return UserFactory.create_batch(6)


@pytest.fixture
def learning_path_with_courses(users: list[User]) -> LearningPath:
    """Create a LearningPath with multiple course steps."""
    learning_path = LearningPath.objects.create(key='path-v1:test+number+run+group')

    for i in range(3):
        learning_path.steps.create(course_key=f"course-v1:TestX+Test101+2023_{i}", order=i)

    # Enroll all users except the last one.
    for i in range(len(users) - 1):
        learning_path.enrolled_users.add(users[i])

    # Mark the second last user's enrollment as inactive.
    learning_path.learningpathenrollment_set.filter(user=users[-2]).update(is_active=False)

    return learning_path


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
    function_to_test: Callable[[str, dict], list[int]],
    learning_path_with_courses: LearningPath,
    users: list[User],
):
    """Test retrieving data for a learning path."""
    with patch(patch_target) as mock_retrieve:
        options = {}
        mock_retrieve.side_effect = (
            ({users[i].id: {'is_eligible': True} for i in (0, 1, 2, 4, 5)}),  # Users passing/completing course0
            ({users[i].id: {'is_eligible': True} for i in (0, 1, 2, 3, 4, 5)}),  # Users passing/completing course1
            ({users[i].id: {'is_eligible': True} for i in (0, 2, 3, 4, 5)}),  # Users passing/completing course2
        )

        result = function_to_test(learning_path_with_courses.key, options)

        assert sorted(result) == [users[0].id, users[2].id]

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


@pytest.mark.parametrize(
    ('patch_target', 'function_to_test'),
    [
        ("learning_credentials.processors._retrieve_course_subsection_grades", retrieve_subsection_grades),
        ("learning_credentials.processors._retrieve_course_completions", retrieve_completions),
    ],
    ids=['subsection_grades', 'completions'],
)
def test_retrieve_data_for_individual_user_course(patch_target: str, function_to_test: Callable):
    """Test retrieving progress data for an individual user in a course."""
    course_key = CourseKey.from_string("course-v1:TestX+CS101+2024")
    user_id = 123
    options = {}

    # Mock the internal function to return detailed progress for all users
    with patch(patch_target) as mock_retrieve:
        mock_retrieve.return_value = {
            user_id: {
                'is_eligible': True,
                'current_grades' if 'grades' in patch_target else 'current_completion': 85.5
                if 'grades' in patch_target
                else 0.95,
                'required_grades' if 'grades' in patch_target else 'required_completion': {'total': 80.0}
                if 'grades' in patch_target
                else 0.9,
            },
            456: {
                'is_eligible': False,
                'current_grades' if 'grades' in patch_target else 'current_completion': 75.0
                if 'grades' in patch_target
                else 0.85,
                'required_grades' if 'grades' in patch_target else 'required_completion': {'total': 80.0}
                if 'grades' in patch_target
                else 0.9,
            },
        }

        result = function_to_test(course_key, options, user_id=user_id)

        # Should return detailed progress for the specific user
        assert isinstance(result, dict)
        assert result['is_eligible'] is True
        if 'grades' in patch_target:
            assert result['current_grades'] == 85.5
            assert result['required_grades'] == {'total': 80.0}
        else:
            assert result['current_completion'] == 0.95
            assert result['required_completion'] == 0.9

        mock_retrieve.assert_called_once_with(course_key, options, user_id)


@pytest.mark.parametrize(
    ('patch_target', 'function_to_test'),
    [
        ("learning_credentials.processors._retrieve_course_subsection_grades", retrieve_subsection_grades),
        ("learning_credentials.processors._retrieve_course_completions", retrieve_completions),
    ],
    ids=['subsection_grades', 'completions'],
)
def test_retrieve_data_for_individual_user_not_found(patch_target: str, function_to_test: Callable):
    """Test retrieving progress data for a user not found in course."""
    course_id = Mock(spec=CourseKey)
    user_id = 999  # User not in results
    options = {}

    # Mock the internal function to return detailed progress without the requested user
    with patch(patch_target) as mock_retrieve:
        mock_retrieve.return_value = {
            123: {
                'is_eligible': True,
                'current_grades' if 'grades' in patch_target else 'current_completion': 85.5
                if 'grades' in patch_target
                else 0.95,
                'required_grades' if 'grades' in patch_target else 'required_completion': {'total': 80.0}
                if 'grades' in patch_target
                else 0.9,
            }
        }

        result = function_to_test(course_id, options, user_id=user_id)

        # Should return not eligible for user not found
        assert isinstance(result, dict)
        assert result['is_eligible'] is False
        if 'grades' in patch_target:
            assert result['current_grades'] == {}
            assert result['required_grades'] == {}
        else:
            assert result['current_completion'] == 0.0
            assert result['required_completion'] == 0.9

        mock_retrieve.assert_called_once_with(course_id, options, user_id)


@pytest.mark.parametrize(
    ('patch_target', 'function_to_test'),
    [
        ("learning_credentials.processors._retrieve_course_subsection_grades", retrieve_subsection_grades),
        ("learning_credentials.processors._retrieve_course_completions", retrieve_completions),
    ],
    ids=['subsection_grades', 'completions'],
)
@pytest.mark.django_db
def test_retrieve_data_for_individual_user_learning_path(
    patch_target: str,
    function_to_test: Callable,
    learning_path_with_courses: LearningPath,
    users: list[User],
):
    """Test retrieving progress data for an individual user in a learning path with steps breakdown."""
    user_id = users[0].id
    options = {}

    # Mock the internal function to return detailed progress for each course step
    with patch(patch_target) as mock_retrieve:
        mock_retrieve.side_effect = [
            {  # Course 1 results
                user_id: {
                    'is_eligible': True,
                    'current_grades' if 'grades' in patch_target else 'current_completion': {
                        'homework': 85.0,
                        'total': 82.0,
                    }
                    if 'grades' in patch_target
                    else 0.95,
                    'required_grades' if 'grades' in patch_target else 'required_completion': {
                        'homework': 50.0,
                        'total': 80.0,
                    }
                    if 'grades' in patch_target
                    else 0.9,
                }
            },
            {  # Course 2 results
                user_id: {
                    'is_eligible': True,
                    'current_grades' if 'grades' in patch_target else 'current_completion': {
                        'exam': 90.0,
                        'total': 85.0,
                    }
                    if 'grades' in patch_target
                    else 0.88,
                    'required_grades' if 'grades' in patch_target else 'required_completion': {
                        'exam': 85.0,
                        'total': 80.0,
                    }
                    if 'grades' in patch_target
                    else 0.8,
                }
            },
            {  # Course 3 results
                user_id: {
                    'is_eligible': True,
                    'current_grades' if 'grades' in patch_target else 'current_completion': {'total': 83.0}
                    if 'grades' in patch_target
                    else 0.92,
                    'required_grades' if 'grades' in patch_target else 'required_completion': {'total': 80.0}
                    if 'grades' in patch_target
                    else 0.9,
                }
            },
        ]

        result = function_to_test(learning_path_with_courses.key, options, user_id=user_id)

        # Should return detailed progress with steps breakdown
        assert isinstance(result, dict)
        assert result['is_eligible'] is True
        assert 'steps' in result
        assert len(result['steps']) == 3

        # Check that each step has the expected structure
        for step_result in result['steps'].values():
            assert isinstance(step_result, dict)
            assert step_result['is_eligible'] is True
            if 'grades' in patch_target:
                assert 'current_grades' in step_result
                assert 'required_grades' in step_result
            else:
                assert 'current_completion' in step_result
                assert 'required_completion' in step_result

        # Verify internal function was called for each course step
        assert mock_retrieve.call_count == 3


@pytest.mark.django_db
def test_retrieve_completions_and_grades_for_individual_user():
    """Test the combined processor for individual user progress."""
    course_id = Mock(spec=CourseKey)
    user_id = 123
    options = {}

    # Mock both individual processors
    with (
        patch('learning_credentials.processors.retrieve_completions') as mock_completions,
        patch('learning_credentials.processors.retrieve_subsection_grades') as mock_grades,
    ):
        mock_completions.return_value = {
            'is_eligible': True,
            'current_completion': 0.95,
            'required_completion': 0.9,
        }

        mock_grades.return_value = {
            'is_eligible': True,
            'current_grades': {'homework': 85.0, 'exam': 90.0, 'total': 87.0},
            'required_grades': {'homework': 40.0, 'exam': 80.0, 'total': 75.0},
        }

        result = retrieve_completions_and_grades(course_id, options, user_id=user_id)

        # Should return combined progress information
        assert isinstance(result, dict)
        assert result['is_eligible'] is True

        # Should include both completion and grades information
        assert result['current_completion'] == 0.95
        assert result['required_completion'] == 0.9
        assert result['current_grades'] == {'homework': 85.0, 'exam': 90.0, 'total': 87.0}
        assert result['required_grades'] == {'homework': 40.0, 'exam': 80.0, 'total': 75.0}

        # Verify both processors were called
        mock_completions.assert_called_once_with(course_id, options, user_id)
        mock_grades.assert_called_once_with(course_id, options, user_id)


@pytest.mark.django_db
def test_retrieve_completions_and_grades_for_individual_user_mixed_eligibility():
    """Test combined processor when user meets one criteria but not the other."""
    course_id = Mock(spec=CourseKey)
    user_id = 123
    options = {}

    with (
        patch('learning_credentials.processors.retrieve_completions') as mock_completions,
        patch('learning_credentials.processors.retrieve_subsection_grades') as mock_grades,
    ):
        # User meets completion but not grade requirements
        mock_completions.return_value = {
            'is_eligible': True,
            'current_completion': 0.95,
            'required_completion': 0.9,
        }

        mock_grades.return_value = {
            'is_eligible': False,
            'current_grades': {'homework': 65.0, 'exam': 70.0, 'total': 67.0},
            'required_grades': {'homework': 40.0, 'exam': 80.0, 'total': 75.0},
        }

        result = retrieve_completions_and_grades(course_id, options, user_id=user_id)

        # Should be not eligible overall despite meeting completion requirement
        assert isinstance(result, dict)
        assert result['is_eligible'] is False

        # Should still include all progress information
        assert result['current_completion'] == 0.95
        assert result['required_completion'] == 0.9
        assert result['current_grades'] == {'homework': 65.0, 'exam': 70.0, 'total': 67.0}
        assert result['required_grades'] == {'homework': 40.0, 'exam': 80.0, 'total': 75.0}
