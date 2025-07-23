#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

echo "Start Celery Beat Service"
cd /code/wardrive
watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- celery -A wardrive beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler