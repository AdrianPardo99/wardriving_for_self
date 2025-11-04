#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

QUEUE=${QUEUE:-proc_0}
echo "Start Celery Service ${QUEUE}"
cd /code/wardrive 
watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- \
    celery -A wardrive worker -Q "$QUEUE" -n "w.${QUEUE}@%h" -c 1 -O fair --prefetch-multiplier=1 --loglevel=info