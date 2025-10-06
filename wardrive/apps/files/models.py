from django.db import models

from apps.wardriving import SourceDevice


class FilesUploaded(models.Model):
    source = models.FileField(upload_to="wardrive_sources/")
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.TextField(verbose_name="Uploaded by", default="")
    device_source = models.CharField(
        max_length=50,
        verbose_name="Source",
        choices=SourceDevice.CHOICES,
        default=SourceDevice.UNKNOWN,
    )
    is_procesed = models.BooleanField(default=False)

    class Meta:
        db_table = "file_upload"
        verbose_name = "File Upload"
        verbose_name_plural = "Files Upload"

    def __str__(self):
        return f"{self.source}"


class AllowToLoadData(models.Model):
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "allow_to_load_data"
