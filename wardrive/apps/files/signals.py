from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import FilesUploaded
from .services import run_process_file


@receiver(post_save, sender=FilesUploaded)
def send_form_evaluate(sender, instance, created, **kwargs):
    if not created:
        return
    run_process_file(instance=instance)
