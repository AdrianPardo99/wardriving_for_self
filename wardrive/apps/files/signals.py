from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import FilesUploaded
from .tasks import process_file


@receiver(post_save, sender=FilesUploaded)
def send_form_evaluate(sender, instance, created, **kwargs):
    if created:
        process_file.delay(instance.pk)
