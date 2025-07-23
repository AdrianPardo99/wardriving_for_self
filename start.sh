#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

VAR_NAME="ENVIRONMENT"

if [ -z "${!VAR_NAME:-}" ]; then
    # If Env does not exist, then create it with the value 'container'
    export ENVIRONMENT="container"
fi

if [ "$ENVIRONMENT" == "local" ]; then
    echo "Install missing dependencies for local stage"
    apt update > /dev/null 2>&1 
    apt install -y netcat-openbsd > /dev/null 2>&1
    echo "Wait until database is already to use"
    bash /code/wait.sh $DB_HOST:$DB_PORT
fi

# Run Django migrations
python /code/wardrive/manage.py migrate


if [ "${ENVIRONMENT}" == "local" ]; then
    echo "Starting Django development server"
    python /code/wardrive/manage.py runserver 0.0.0.0:8000
else
    echo "Starting Gunicorn server"
    python /code/wardrive/manage.py collectstatic --noinput
    gunicorn --forwarded-allow-ips="*" --pythonpath /code/wardrive wardrive.wsgi:application --workers=4 --bind 0.0.0.0:8000
fi
