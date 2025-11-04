from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import FilesUploaded
from .tasks import process_file


@receiver(post_save, sender=FilesUploaded)
def send_form_evaluate(sender, instance, created, **kwargs):
    if not created:
        return
    uploaded_by_id = getattr(instance, "uploaded_by", None)
    device_source = instance.device_source

    def _enqueue():
        process_file.apply_async(
            args=(instance.pk,),
            kwargs={"_uploaded_by_id": uploaded_by_id, "_device_source": device_source},
        )

    transaction.on_commit(_enqueue)
