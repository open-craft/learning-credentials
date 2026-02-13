"""API views for Learning Credentials."""

from typing import TYPE_CHECKING

import edx_api_doc_tools as apidocs
from edx_api_doc_tools import ParameterLocation
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from learning_credentials.models import Credential, CredentialConfiguration

from .permissions import CanAccessLearningContext
from .serializers import CredentialSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request


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
