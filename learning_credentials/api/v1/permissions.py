"""Django REST framework permissions."""

from typing import TYPE_CHECKING

from django.db.models import Q
from learning_paths.models import LearningPath
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import LearningContextKey
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.permissions import BasePermission

from learning_credentials.compat import get_course_enrollments

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from learning_paths.keys import LearningPathKey
    from opaque_keys.edx.keys import CourseKey
    from rest_framework.request import Request
    from rest_framework.views import APIView


class CanAccessLearningContext(BasePermission):
    """Permission to allow access to learning context if the user is enrolled."""

    def has_permission(self, request: "Request", view: "APIView") -> bool:
        """Check if the user can access the learning context."""
        try:
            key = view.kwargs.get("learning_context_key") or request.query_params.get("learning_context_key")
            learning_context_key = LearningContextKey.from_string(key)
        except InvalidKeyError as e:
            msg = "Invalid learning context key."
            raise ParseError(msg) from e

        if request.user.is_staff:
            return True

        if learning_context_key.is_course:
            if self._can_access_course(learning_context_key, request.user):
                return True

            msg = "Course not found or user does not have access."
            raise NotFound(msg)

        # For learning paths, check enrollment or if it's not invite-only.
        if self._can_access_learning_path(learning_context_key, request.user):
            return True

        msg = "Learning path not found or user does not have access."
        raise NotFound(msg)

    def _can_access_course(self, course_key: "CourseKey", user: "User") -> bool:
        """Check if user can access a course."""
        # Check if user is enrolled in the course.
        if get_course_enrollments(course_key, user.id):  # ty: ignore[unresolved-attribute]
            return True

        # Check if the course is a part of a learning path the user can access.
        return self._can_access_course_via_learning_path(course_key, user)

    def _get_accessible_learning_paths_filter(self, user: "User") -> Q:
        """Get Q filter for learning paths that the user can access."""
        return Q(invite_only=False) | Q(learningpathenrollment__user=user, learningpathenrollment__is_active=True)

    def _can_access_course_via_learning_path(self, course_key: "CourseKey", user: "User") -> bool:
        """Check if user can access a course through learning path membership."""
        accessible_paths = (
            LearningPath.objects.filter(steps__course_key=course_key)
            .filter(self._get_accessible_learning_paths_filter(user))
            .distinct()
        )

        return accessible_paths.exists()

    def _can_access_learning_path(self, learning_path_key: "LearningPathKey", user: "User") -> bool:
        """Check if user can access a learning path."""
        # Single query to check if learning path exists and user can access it
        accessible_path = LearningPath.objects.filter(key=learning_path_key).filter(
            self._get_accessible_learning_paths_filter(user)
        )

        return accessible_path.exists()
