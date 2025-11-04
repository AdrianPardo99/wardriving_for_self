from celery import shared_task


from .models import FilesUploaded, AllowToLoadData
from .utils import CHOICES_FUNCTION_PROCESS


@shared_task(
    bind=True,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    reject_on_worker_lost=True,
)
def process_file(self, file_pk, _uploaded_by_id=None, _device_source=None):
    if not AllowToLoadData.objects.filter(active=True).exists():
        return "Data loading is currently disabled."
    try:
        file_obj = FilesUploaded.objects.get(pk=file_pk, is_procesed=False)
    except FilesUploaded.DoesNotExist:
        return f"File with pk={file_pk} does not exist or is already processed."
    device_source = file_obj.device_source
    class_process_function = CHOICES_FUNCTION_PROCESS.get(device_source, None)

    if not class_process_function:
        return f"No processing function found for source: {device_source}"
    try:
        file_path = file_obj.source.path
        new_added, updated, ignored = class_process_function(
            file_path=file_path,
            device_source=device_source,
            uploaded_by=file_obj.uploaded_by,
        )
        total = new_added + updated + ignored
        file_obj.is_procesed = True
        file_obj.save()
        return f"File {file_pk} - {file_obj} processed successfully. Total of records in file {total}, Total new records {new_added}, Total updated found records {updated}, Total ignored {ignored}"
    except Exception as e:
        return f"Error while processing file {file_pk}: {str(e)}"
