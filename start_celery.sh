#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

echo "Start Celery Service"
cd /code/wardrive 
watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- celery -A wardrive worker --loglevel=info