from rest_framework.routers import DefaultRouter

from .views import FilesUploadedViewSet

router = DefaultRouter()

router.register(
    prefix="files-uploaded",
    viewset=FilesUploadedViewSet,
    basename="files-uploaded",
)
