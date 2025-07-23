from django.apps import AppConfig


class FilesUploadedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.files"

    def ready(self):
        import apps.files.signals
