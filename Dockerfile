FROM python:3.13


RUN mkdir /code
WORKDIR /code

# Installing apps
RUN apt-get update && apt-get install -y postgresql netcat-traditional gettext

# Copy all sources for deploy code and that stuff
COPY . .

RUN sed -i 's/\r$//g' start.sh
RUN sed -i 's/\r$//g' wait.sh
RUN sed -i 's/\r$//g' start_celery.sh
RUN sed -i 's/\r$//g' start_celery_beat.sh
RUN chmod +x /code/start.sh /code/wait.sh /code/start_celery.sh /code/start_celery_beat.sh

# Install Py dependencies
RUN pip install -r /code/requirements.txt
