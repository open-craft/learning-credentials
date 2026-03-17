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

from .permissions import CanAccessLearningContext, IsAdminOrSelf
from .serializers import CredentialEligibilityResponseSerializer, CredentialSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request

logger = logging.getLogger(__name__)


class CredentialConfigurationCheckView(APIView):
    """API view to check if any credentials are configured for a specific learning context."""

    permission_classes = (IsAuthenticated, CanAccessLearningContext)

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
            403: "User is not authenticated or does not have permission to access the learning context.",
            404: "Learning context not found or user does not have access.",
        },
    )
    def get(self, _request: "Request", learning_context_key: str) -> Response:
        """
        Check if any credentials are configured for the given learning context.

        **Example Request**

        ``GET /api/learning_credentials/v1/configured/course-v1:OpenedX+DemoX+DemoCourse/``

        **Response Values**

        - **200 OK**: Request successful, returns credential configuration status.
        - **400 Bad Request**: Invalid learning context key format.
        - **403 Forbidden**: User is not authenticated or does not have permission to access the learning context.
        - **404 Not Found**: Learning context not found or user does not have access.

        **Example Response**

        .. code-block:: json

            {
              "has_credentials": true,
              "credential_count": 2
            }

        **Response Fields**

        - ``has_credentials``: Boolean indicating if any credentials are configured
        - ``credential_count``: Number of credential configurations available

        **Note**

        This endpoint does not perform learning context existence validation, so it will not return 404 for staff users.
        """
        credential_count = CredentialConfiguration.objects.filter(learning_context_key=learning_context_key).count()

        response_data = {
            'has_credentials': credential_count > 0,
            'credential_count': credential_count,
        }

        return Response(response_data, status=status.HTTP_200_OK)


class CredentialMetadataView(APIView):
    """API view to retrieve credential metadata by UUID."""

    @apidocs.schema(
        parameters=[
            apidocs.string_parameter(
                "uuid",
                ParameterLocation.PATH,
                description="The UUID of the credential to retrieve.",
            ),
        ],
        responses={
            200: "Successfully retrieved the credential metadata.",
            404: "Credential not found or not valid.",
        },
    )
    def get(self, _request: "Request", uuid: str) -> Response:
        """
        Retrieve credential metadata by its UUID.

        **Example Request**

        ``GET /api/learning_credentials/v1/metadata/123e4567-e89b-12d3-a456-426614174000/``

        **Response Values**

        - **200 OK**: Successfully retrieved the credential metadata.
        - **404 Not Found**: Credential not found or not valid.

        **Example Response**

        .. code-block:: json

            {
                "user_full_name": "John Doe",
                "created": "2023-01-01",
                "learning_context_name": "Demo Course",
                "status": "available",
                "invalidation_reason": ""
            }


            {
                "user_full_name": "John Doe",
                "created": "2023-01-01",
                "learning_context_name": "Demo Course",
                "status": "invalidated",
                "invalidation_reason": "Reissued due to name change."
            }
        """
        try:
            credential = Credential.objects.get(verify_uuid=uuid)
        except Credential.DoesNotExist:
            return Response({'error': 'Credential not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = CredentialSerializer(credential)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CredentialEligibilityView(APIView):
    """
    API view for credential eligibility checking and generation.

    **GET**: Returns detailed eligibility info for all configured credentials in a learning context.
    **POST**: Triggers credential generation for an eligible user.

    Staff users can operate on behalf of other users via the ``username`` parameter.
    """

    permission_classes = (IsAuthenticated, IsAdminOrSelf, CanAccessLearningContext)

    def _get_eligibility_data(self, user: User, config: "CredentialConfiguration", credentials: list) -> dict:
        """Calculate eligibility data for a credential configuration."""
        progress_data = config.get_user_eligibility_details(user_id=user.id)
        existing_credential = next((cred for cred in credentials if cred.configuration_id == config.id), None)

        return {
            'credential_type_id': config.credential_type.pk,
            'name': config.credential_type.name,
            'is_generation_enabled': config.periodic_task.enabled,
            **progress_data,
            'existing_credential': existing_credential.uuid if existing_credential else None,
            'existing_credential_url': existing_credential.download_url if existing_credential else None,
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
            apidocs.string_parameter(
                "retrieval_func",
                ParameterLocation.QUERY,
                description=(
                    "Filter by credential type retrieval function "
                    "(e.g. learning_credentials.processors.retrieve_subsection_grades)."
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

        Returns detailed eligibility information for all configured credentials, including:

        - Current grades and requirements for grade-based credentials
        - Completion percentages for completion-based credentials
        - Step-by-step progress for learning paths
        - Existing credential info if already generated

        **Query Parameters**

        - ``username`` (staff only): View eligibility for a specific user.
        - ``retrieval_func``: Filter by credential type retrieval function
          (e.g. ``learning_credentials.processors.retrieve_subsection_grades``).

        **Example Request**

        ``GET /api/learning_credentials/v1/eligibility/course-v1:OpenedX+DemoX+DemoCourse/``

        **Example Response**

        .. code-block:: json

            {
              "context_key": "course-v1:OpenedX+DemoX+DemoCourse",
              "credentials": [
                {
                  "credential_type_id": 1,
                  "name": "Certificate of Achievement",
                  "is_eligible": true,
                  "existing_credential": null,
                  "current_grades": {"final exam": 86, "total": 82},
                  "required_grades": {"final exam": 65, "total": 80}
                }
              ]
            }
        """
        username = request.query_params.get('username')
        user = get_object_or_404(User, username=username) if username else request.user

        configurations = CredentialConfiguration.objects.filter(
            learning_context_key=learning_context_key
        ).select_related('credential_type')

        retrieval_func = request.query_params.get('retrieval_func')
        if retrieval_func:
            configurations = configurations.filter(credential_type__retrieval_func=retrieval_func)

        # Pre-fetch all credentials for this user and learning context to avoid N+1 queries in the loop below.
        credentials = Credential.objects.filter(user_id=user.id, configuration__in=configurations).exclude(
            status__in=[Credential.Status.ERROR, Credential.Status.INVALIDATED]
        )

        eligibility_data = [self._get_eligibility_data(user, config, credentials) for config in configurations]

        response_data = {
            'context_key': learning_context_key,
            'credentials': eligibility_data,
        }

        serializer = CredentialEligibilityResponseSerializer(data=response_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
