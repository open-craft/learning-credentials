"""API serializers for learning credentials."""

from typing import Any

from rest_framework import serializers

from learning_credentials.models import Credential


class CredentialSerializer(serializers.ModelSerializer):
    """Serializer that returns credential metadata (for the public verification endpoint)."""

    class Meta:
        """Serializer metadata."""

        model = Credential
        fields = ('user_full_name', 'created', 'learning_context_name', 'status', 'invalidation_reason')


class CredentialEligibilitySerializer(serializers.Serializer):
    """Serializer for credential eligibility information with dynamic fields."""

    credential_type_id = serializers.IntegerField()
    name = serializers.CharField()
    is_generation_enabled = serializers.BooleanField()
    is_eligible = serializers.BooleanField()
    existing_credential = serializers.UUIDField(required=False, allow_null=True)
    existing_credential_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)

    current_grades = serializers.DictField(required=False)
    required_grades = serializers.DictField(required=False)

    current_completion = serializers.FloatField(required=False, allow_null=True)
    required_completion = serializers.FloatField(required=False, allow_null=True)

    steps = serializers.DictField(required=False)

    def to_representation(self, instance: dict) -> dict[str, Any]:
        """Remove null/empty fields from representation."""
        data = super().to_representation(instance)
        return {key: value for key, value in data.items() if value is not None and value not in ({}, [])}


class CredentialEligibilityResponseSerializer(serializers.Serializer):
    """Serializer for the complete credential eligibility response."""

    context_key = serializers.CharField()
    credentials = CredentialEligibilitySerializer(many=True)
