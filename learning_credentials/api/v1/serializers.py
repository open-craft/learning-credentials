"""API serializers for learning credentials."""

from rest_framework import serializers

from learning_credentials.models import Credential


class CredentialSerializer(serializers.ModelSerializer):
    """Serializer that returns credential metadata."""

    class Meta:
        """Serializer metadata."""

        model = Credential
        fields = ('user_full_name', 'created', 'learning_context_name', 'status', 'invalidation_reason')
