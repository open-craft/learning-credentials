"""Serializers for the Learning Credentials API."""

from typing import Any, ClassVar

from rest_framework import serializers

from learning_credentials.models import Credential


class CredentialModelSerializer(serializers.ModelSerializer):
    """Model serializer for Credential instances."""

    credential_id = serializers.UUIDField(source='uuid', read_only=True)
    credential_type = serializers.CharField(read_only=True)
    context_key = serializers.CharField(source='learning_context_key', read_only=True)
    created_date = serializers.DateTimeField(source='created', read_only=True)
    download_url = serializers.URLField(read_only=True)

    class Meta:
        """Meta configuration for CredentialModelSerializer."""

        model = Credential
        fields: ClassVar[list[str]] = [
            'credential_id',
            'credential_type',
            'context_key',
            'status',
            'created_date',
            'download_url',
        ]
        read_only_fields: ClassVar[list[str]] = [
            'credential_id',
            'credential_type',
            'context_key',
            'status',
            'created_date',
            'download_url',
        ]


class CredentialEligibilitySerializer(serializers.Serializer):
    """Serializer for credential eligibility information with dynamic fields."""

    credential_type_id = serializers.IntegerField()
    name = serializers.CharField()
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


class CredentialListResponseSerializer(serializers.Serializer):
    """Serializer for credential list response."""

    credentials = CredentialModelSerializer(many=True)
