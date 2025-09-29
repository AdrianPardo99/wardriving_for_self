from django.utils.translation import pgettext_lazy

from rest_framework import viewsets, permissions, status
from rest_framework.parsers import MultiPartParser
from rest_framework.decorators import parser_classes, action
from rest_framework.response import Response

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from django_filters import rest_framework as filters

from .serializers import (
    FileUploadedListSerializer,
    MultipleFileUploadedCreateSerializer,
)


from apps.files.models import FilesUploaded
from api.utils import is_swagger_fake_view
from api.pagination import CustomPagination

upload_params = [
    openapi.Parameter(
        name="files",
        in_=openapi.IN_FORM,
        type=openapi.TYPE_FILE,
        description="Multiple files",
        required=True,
        collectionFormat="multi",
    ),
    openapi.Parameter(
        name="device_source",
        in_=openapi.IN_FORM,
        type=openapi.TYPE_STRING,
        required=True,
        description="Source device",
    ),
    openapi.Parameter(
        name="uploaded_by",
        in_=openapi.IN_FORM,
        type=openapi.TYPE_STRING,
        required=False,
        description="Uploader identifier",
    ),
]


@parser_classes([MultiPartParser])
class FilesUploadedViewSet(viewsets.ModelViewSet):
    lookup_field = "pk"
    queryset = FilesUploaded.objects.all()
    permission_classes = [
        permissions.AllowAny,
    ]
    actions_serializers = {
        "list": FileUploadedListSerializer,
        "create": MultipleFileUploadedCreateSerializer,
    }
    pagination_class = CustomPagination
    filter_backends = [
        filters.DjangoFilterBackend,
    ]
    http_method_names = [
        "post",
    ]

    def get_serializer_class(self):
        return self.actions_serializers.get(self.action, FileUploadedListSerializer)

    @swagger_auto_schema(
        manual_parameters=upload_params, responses={201: "Files uploaded successfully"}
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instances = serializer.save()
        data = FileUploadedListSerializer(instances, many=True).data
        return Response(data, status=status.HTTP_201_CREATED)
