from django.urls import include, path

from .files.routers import router as files_router

urlpatterns = [
    path("", include(files_router.urls)),
]
