import hashlib

from django.db import models

from apps.wardriving import SourceDevice


class SourcesWithCopy(models.Model):
    original_author = models.TextField(verbose_name="Original author", default="")
    fake_author = models.TextField(verbose_name="Fake author", default="")
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True, editable=False)

    class Meta:
        db_table = "sources_with_copy"


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
    hash_sha256 = models.CharField(max_length=64, blank=True, null=True, editable=False)

    class Meta:
        db_table = "file_upload"
        verbose_name = "File Upload"
        verbose_name_plural = "Files Upload"

    def __str__(self):
        return f"{self.source}"

    def _is_diff_author(self, first_instance):
        return self.uploaded_by != first_instance.uploaded_by

    def save(self, *args, **kwargs):
        if self.source and not self.hash_sha256:
            sha = hashlib.sha256()
            for chunk in self.source.chunks():
                sha.update(chunk)
            self.hash_sha256 = sha.hexdigest()
        qs = FilesUploaded.objects.filter(hash_sha256=self.hash_sha256)

        exists_instance = qs.exists()
        self.is_procesed = exists_instance
        old_instance = qs.first()
        if exists_instance and self._is_diff_author(old_instance):
            SourcesWithCopy.objects.create(
                original_author=old_instance.uploaded_by,
                fake_author=self.uploaded_by,
                hash_sha256=self.hash_sha256,
            )
        super().save(*args, **kwargs)


class AllowToLoadData(models.Model):
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "allow_to_load_data"
