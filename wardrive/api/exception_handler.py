from django.core.exceptions import ValidationError, PermissionDenied
from django.http import Http404

from rest_framework.views import exception_handler
from rest_framework.serializers import as_serializer_error
from rest_framework import exceptions


def custom_exception_handler(exc, ctx):
    if isinstance(exc, ValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    if isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    response = exception_handler(exc, ctx)
    if response is None:
        return response
    if isinstance(exc.detail, dict) and "__all__" in exc.detail:
        response.data = {"message": response.data["__all__"]}

    return response
