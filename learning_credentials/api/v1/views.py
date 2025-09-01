"""API views for Learning Credentials."""

import logging
from typing import TYPE_CHECKING

import edx_api_doc_tools as apidocs
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from edx_api_doc_tools import ParameterLocation
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from learning_credentials.models import Credential, CredentialConfiguration
from learning_credentials.tasks import generate_credential_for_user_task

from .permissions import CanAccessLearningContext, IsAdminOrSelf
from .serializers import (
    CredentialEligibilityResponseSerializer,
    CredentialListResponseSerializer,
    CredentialModelSerializer,
)

if TYPE_CHECKING:
    from rest_framework.request import Request

logger = logging.getLogger(__name__)


class CredentialConfigurationCheckView(APIView):
    """API view to check if any credentials are configured for a specific learning context."""

    permission_classes = (IsAuthenticated, IsAdminOrSelf, CanAccessLearningContext)

    @apidocs.schema(
        parameters=[
            apidocs.string_parameter(
                "learning_context_key",
                ParameterLocation.PATH,
                description=(
                    "Learning context identifier. Can be a course key (course-v1:OpenedX+DemoX+DemoCourse) "
                    "or learning path key (path-v1:OpenedX+DemoX+DemoPath+Demo)"
                ),
            ),
        ],
        responses={
            200: "Boolean indicating if credentials are configured.",
            400: "Invalid context key format.",
            404: "Learning context not found or user does not have access.",
        },
    )
    def get(self, _request: "Request", learning_context_key: str) -> Response:
        """
        Check if any credentials are configured for the given learning context.

        **Example Request**

            GET /api/learning_credentials/v1/configured/course-v1:OpenedX+DemoX+DemoCourse/

        **Response Values**

        If the request is successful, an HTTP 200 "OK" response is returned.

        **Example Response**

        ```json
        {
          "has_credentials": true,
          "credential_count": 2
        }
        ```

        **Response Fields**
        - `has_credentials`: Boolean indicating if any credentials are configured
        - `credential_count`: Number of credential configurations available

        **Note**
        This endpoint does not perform learning context existence validation, so it will not return 404 for staff users.
        """
        credential_count = CredentialConfiguration.objects.filter(learning_context_key=learning_context_key).count()

        response_data = {
            'has_credentials': credential_count > 0,
            'credential_count': credential_count,
        }

        return Response(response_data, status=status.HTTP_200_OK)


class CredentialEligibilityView(APIView):
    """
    API view for credential eligibility and generation.

    This endpoint manages credential eligibility checking and generation for users in specific learning contexts.

    Supported Learning Contexts:
    - Course keys: `course-v1:org+course+run`
    - Learning path keys: `path-v1:org+path+run+group`

    **Staff Features**:
    - Staff users can view eligibility for any user by providing `username` parameter
    - Non-staff users can only view their own eligibility
    """

    permission_classes = (IsAuthenticated, IsAdminOrSelf, CanAccessLearningContext)

    def _get_eligibility_data(self, user: User, config: CredentialConfiguration) -> dict:
        """Calculate eligibility data for a credential configuration."""
        progress_data = config.get_user_eligibility_details(user_id=user.id)  # ty: ignore[unresolved-attribute]

        existing_credential = (
            Credential.objects.filter(
                user_id=user.id,  # ty: ignore[unresolved-attribute]
                learning_context_key=config.learning_context_key,
                credential_type=config.credential_type.name,
            )
            .exclude(status=Credential.Status.ERROR)
            .first()
        )

        return {
            'credential_type_id': config.credential_type.pk,
            'name': config.credential_type.name,
            'is_eligible': progress_data.get('is_eligible', False),
            'existing_credential': existing_credential.uuid if existing_credential else None,
            'existing_credential_url': existing_credential.download_url if existing_credential else None,
            **progress_data,
        }

    @apidocs.schema(
        parameters=[
            apidocs.string_parameter(
                "learning_context_key",
                ParameterLocation.PATH,
                description=(
                    "Learning context identifier. Can be a course key (course-v1:OpenedX+DemoX+DemoCourse) "
                    "or learning path key (path-v1:OpenedX+DemoX+DemoPath+Demo)"
                ),
            ),
        ],
        responses={
            200: CredentialEligibilityResponseSerializer,
            400: "Invalid context key format.",
            403: "User is not authenticated.",
            404: "Learning context not found or user does not have access.",
        },
    )
    def get(self, request: "Request", learning_context_key: str) -> Response:
        """
        Get credential eligibility for a learning context.

        Retrieve detailed eligibility information for all available credentials in a learning context.
        This endpoint returns comprehensive progress data including:
        - Current grades and requirements for grade-based credentials
        - Completion percentages for completion-based credentials
        - Step-by-step progress for learning paths
        - Eligibility status for each credential type

        **Query Parameters:**
        - `username` (staff only): View eligibility for a specific user

        **Example Request**

            GET /api/learning_credentials/v1/eligibility/course-v1:OpenedX+DemoX+DemoCourse/

        **Response Values**

        If the request is successful, an HTTP 200 "OK" response is returned.

        The response structure adapts based on credential types:
        - Grade-based credentials include `current_grades` and `required_grades`
        - Completion-based credentials include `current_completion` and `required_completion`
        - Learning paths include detailed `steps` breakdown

        **Example Response for Grade-based Credential**

        ```json
        {
          "context_key": "course-v1:OpenedX+DemoX+DemoCourse",
          "credentials": [
            {
              "credential_type_id": 1,
              "name": "Certificate of Achievement",
              "description": "",
              "is_eligible": true,
              "existing_credential": null,
              "current_grades": {
                "Final Exam": 86,
                "Overall Grade": 82
              },
              "required_grades": {
                "Final Exam": 65,
                "Overall Grade": 80
              }
            }
          ]
        }
        ```

        **Example Response for Completion-based Credential**

        ```json
        {
          "context_key": "course-v1:OpenedX+DemoX+DemoCourse",
          "credentials": [
            {
              "credential_type_id": 2,
              "name": "Certificate of Completion",
              "description": "",
              "is_eligible": false,
              "existing_credential": null,
              "current_completion": 74.0,
              "required_completion": 100.0
            }
          ]
        }
        ```
        """
        username = request.query_params.get('username')
        user = get_object_or_404(User, username=username) if username else request.user

        configurations = CredentialConfiguration.objects.filter(
            learning_context_key=learning_context_key
        ).select_related('credential_type')

        eligibility_data = [self._get_eligibility_data(user, config) for config in configurations]

        response_data = {
            'context_key': learning_context_key,
            'credentials': eligibility_data,
        }

        serializer = CredentialEligibilityResponseSerializer(data=response_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    @apidocs.schema(
        parameters=[
            apidocs.string_parameter(
                "learning_context_key",
                ParameterLocation.PATH,
                description="Learning context identifier (e.g. course-v1:OpenedX+DemoX+DemoCourse)",
            ),
            apidocs.parameter(
                "credential_type_id",
                ParameterLocation.PATH,
                int,
                description="ID of the credential type to generate",
            ),
        ],
        responses={
            201: "Credential generation started.",
            400: "User is not eligible for this credential or validation error.",
            403: "User is not authenticated.",
            404: "Learning context or credential type not found, or user does not have access.",
            409: "User already has a valid credential of this type.",
            500: "Internal server error during credential generation.",
        },
    )
    def post(self, request: "Request", learning_context_key: str, credential_type_id: int) -> Response:
        """
        Trigger credential generation for an eligible user.

        This endpoint initiates the credential generation process for a specific credential type.
        The user must be eligible for the credential based on the configured requirements.

        **Prerequisites:**
        - User must be authenticated
        - User must be enrolled in the course or have access to the learning path
        - User must meet the eligibility criteria for the specific credential type
        - User must not already have an existing valid credential of this type

        **Process:**
        1. Validates user eligibility using the configured processor function
        2. Checks for existing credentials to prevent duplicates
        3. Initiates asynchronous credential generation
        4. Returns credential status and tracking information

        **Notification:**
        Users will receive an email notification when credential generation completes.

        **Query Parameters:**
        - `username` (staff only): Trigger credential generation for a specific user

        **Example Request**

            POST /api/learning_credentials/v1/eligibility/course-v1:OpenedX+DemoX+DemoCourse/1/

        **Response Values**

        If the request is successful, an HTTP 201 "Created" response is returned.

        **Example Response**

        ```json
        {
          "status": "generating",
          "credential_id": "123e4567-e89b-12d3-a456-426614174000",
          "message": "Credential generation started. You will receive an email when ready."
        }
        ```
        """
        username = request.query_params.get('username')
        user = get_object_or_404(User, username=username) if username else request.user

        config = get_object_or_404(
            CredentialConfiguration.objects.select_related('credential_type'),
            learning_context_key=learning_context_key,
            credential_type_id=credential_type_id,
        )

        existing_credential = (
            Credential.objects.filter(
                user_id=user.id,
                learning_context_key=learning_context_key,
                credential_type=config.credential_type.name,
            )
            .exclude(status=Credential.Status.ERROR)
            .first()
        )

        if existing_credential:
            return Response({"detail": "User already has a credential of this type."}, status=status.HTTP_409_CONFLICT)

        if not config.get_eligible_user_ids(user_id=user.id):
            return Response({"detail": "User is not eligible for this credential."}, status=status.HTTP_400_BAD_REQUEST)

        generate_credential_for_user_task.delay(config.id, user.id)
        return Response({"detail": "Credential generation started."}, status=status.HTTP_201_CREATED)


class CredentialListView(APIView):
    """
    API view to list user credentials with staff override capability.

    This endpoint provides access to user credential records with optional filtering
    by learning context and staff oversight capabilities.

    **Authentication Required**: Yes

    **Staff Features**:
    - Staff users can view credentials for any user by providing `username` parameter
    - Non-staff users can only view their own credentials
    """

    def get_permissions(self) -> list:
        """Instantiate and return the list of permissions required for this view."""
        permission_classes = [IsAuthenticated, IsAdminOrSelf]

        if self.request.query_params.get('learning_context_key'):
            permission_classes.append(CanAccessLearningContext)

        return [permission() for permission in permission_classes]

    @apidocs.schema(
        parameters=[
            apidocs.string_parameter(
                "learning_context_key",
                ParameterLocation.QUERY,
                description="Optional learning context to filter credentials (e.g. course-v1:OpenedX+DemoX+DemoCourse)",
            ),
            apidocs.string_parameter(
                "username",
                ParameterLocation.QUERY,
                description="Username to view credentials for (staff only)",
            ),
        ],
        responses={
            200: CredentialListResponseSerializer,
            403: "User is not authenticated or lacks permission to view specified user's credentials.",
            404: "Specified user not found or learning context not found/accessible.",
        },
    )
    def get(self, request: "Request") -> Response:
        """
        Retrieve a list of credentials for the authenticated user or a specified user.

        This endpoint returns credential records with filtering options:
        - Filter by learning context (course or learning path)
        - Staff users can view credentials for any user
        - Regular users can only view their own credentials

        **Query Parameters:**
        - `username` (staff only): View credentials for a specific user
        - `learning_context_key` (optional): Filter credentials by learning context

        **Response includes:**
        - Credential ID and type
        - Learning context information
        - Creation date and status
        - Download URL for completed credentials

        **Example Request**

            GET /api/learning_credentials/v1/credentials/
            GET /api/learning_credentials/v1/credentials/course-v1:OpenedX+DemoX+DemoCourse/
            GET /api/learning_credentials/v1/credentials/?username=student123  # staff only

        **Response Values**

        If the request is successful, an HTTP 200 "OK" response is returned.

        **Example Response**

        ```json
        {
          "credentials": [
            {
              "credential_id": "123e4567-e89b-12d3-a456-426614174000",
              "credential_type": "Certificate of Achievement",
              "context_key": "course-v1:OpenedX+DemoX+DemoCourse",
              "status": "available",
              "created_date": "2024-08-20T10:30:00Z",
              "download_url": "https://example.com/credentials/123e4567.pdf"
            }
          ]
        }
        ```
        """
        learning_context_key = request.query_params.get('learning_context_key')
        username = request.query_params.get('username')
        user = get_object_or_404(User, username=username) if username else request.user

        credentials_queryset = Credential.objects.filter(user_id=user.pk)

        if learning_context_key:
            credentials_queryset = credentials_queryset.filter(learning_context_key=learning_context_key)

        credentials_data = CredentialModelSerializer(credentials_queryset, many=True).data
        return Response({'credentials': credentials_data})
