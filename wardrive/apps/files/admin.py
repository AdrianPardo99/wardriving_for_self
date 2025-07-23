from django.contrib import admin
from .models import FilesUploaded


@admin.register(FilesUploaded)
class FilesUploadedAdmin(admin.ModelAdmin):
    pass
