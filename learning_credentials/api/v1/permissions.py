"""Django REST framework permissions."""

from typing import TYPE_CHECKING

from learning_paths.models import LearningPathEnrollment
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import LearningContextKey
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.permissions import BasePermission

from learning_credentials.compat import get_course_enrollments

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class IsAdminOrSelf(BasePermission):
    """
    Permission to allow only admins or the user themselves to access the API.

    Non-staff users cannot pass "username" that is not their own.
    """

    def has_permission(self, request: "Request", view: "APIView") -> bool:  # noqa: ARG002
        """Check if the user is admin or accessing their own data."""
        if request.user.is_staff:
            return True

        username = request.query_params.get("username") if request.method == "GET" else request.data.get("username")

        # For learners, the username passed should match the logged in user.
        if username:
            return request.user.username == username
        return True


class CanAccessLearningContext(BasePermission):
    """Permission to allow access to learning context if the user is enrolled."""

    def has_permission(self, request: "Request", view: "APIView") -> bool:
        """Check if the user is enrolled in the learning context."""
        try:
            key = view.kwargs.get("learning_context_key") or request.query_params.get("learning_context_key")
            learning_context_key = LearningContextKey.from_string(key)
        except InvalidKeyError as e:
            msg = "Invalid learning context key."
            raise ParseError(msg) from e

        if request.user.is_staff:
            return True

        if learning_context_key.is_course:
            if bool(get_course_enrollments(learning_context_key, request.user.id)):
                return True
            msg = "Course not found or user does not have access."
            raise NotFound(msg)

        if LearningPathEnrollment.objects.filter(learning_path__key=learning_context_key, user=request.user).exists():
            return True

        msg = "Learning path not found or user does not have access."
        raise NotFound(msg)
