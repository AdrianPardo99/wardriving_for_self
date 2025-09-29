from rest_framework import serializers
from drf_yasg import openapi
from drf_yasg.utils import swagger_serializer_method

from apps.files.models import FilesUploaded


class FileUploadedListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FilesUploaded
        fields = "__all__"
        read_only_fields = ["created_at"]


class MultipleFileUploadedCreateSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
    )
    device_source = serializers.ChoiceField(
        choices=FilesUploaded._meta.get_field("device_source").choices
    )
    uploaded_by = serializers.CharField()

    def create(self, validated_data):
        files = validated_data.pop("files")
        device_source = validated_data.get("device_source")
        uploaded_by = validated_data.get("uploaded_by", "")

        instances = [
            FilesUploaded.objects.create(
                source=f, device_source=device_source, uploaded_by=uploaded_by
            )
            for f in files
        ]

        return instances
