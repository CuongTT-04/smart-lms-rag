from rest_framework import serializers


class DocumentUploadRequest(serializers.Serializer):
    file = serializers.FileField()
    session_id = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=255, required=False)


class DocumentRetryRequest(serializers.Serializer):
    version_id = serializers.UUIDField()
