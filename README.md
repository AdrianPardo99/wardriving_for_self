# About application

This app is develop by d3vnullv01d for a simple self hostage wardriving conquest application

# About technologies

For a quick overview:

* Containers for a simple self hostage deploy (Docker, Podman you can choose what you prefer)
* Python + Django + Django-Rest-Framework (DRF)
* Celery, Celery-Beat for paralallel files processing
* For a quick deploy you can choose your compose technology that you prefer (Docker-Compose, Podman-Compose)

# Initial deploy

For a well deploy of the application you need to create the `.env` file for work 

This file may need to contains the next variables:

```bash
SECRET_KEY=""                   # Your own secret for manage in admin
DEBUG=""                        # True if you want to contribute or get all trace related to app
CORS_ORIGIN_ALLOW_ALL=True      # For admit a integration from WebApp or MobileApp
SWAGGER_USE_SESSION_AUTH=True   # For login using your credentials in Swagger url
ENVIRONMENT=local               # For a better develop and separate the envs
DB_HOST=wardrive_db             # You think this is a bad implementation but you can configure change configs in compose file
DB_PORT=5432                    # Port
DB_NAME=postgres                # Name
DB_USER=postgres                # User
DB_PASSWORD=postgres            # Password Note: You can change if you add .env file in compose and use the related information to config
DB_ENGINE="django.db.backends.postgresql"   # Engine that use the app
SWAGGER_EMAIL=""                            # If you want reach someone in swagger you can ommit
SWAGGER_AUTHOR="d3vnullv01d"                # If you want to change my auth of the project, pls don't do bad things
SWAGGER_CONTACT_URL=""                      # For your own website 
# Redis Configuration
REDIS_HOST=redis                            # Default config for Redis image
REDIS_PORT=6379                             # Default
REDIS_DB=0                                  # Select and change as you wish your cache Redis DB
# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0      # Same for above config is this for default
CELERY_RESULT_BACKEND=redis://redis:6379/0  # Just same
```

With this you only need to execute

```bash
# I use Podman (Long live the open source)
podman-compose up --build -d
```

You need to create a superuser for access the admin panel

```bash
podman-compose exec wardrive python wardrive/manage.py createsuperuser
# This part has a interactive shell so add the related information about the admin user 
```

The last part and the most important you need to create a single instance that allow to process the files:

```bash
podman-compose exec wardrive python wardrive/manage.py shell
```

In the interactive shell:

```python
from apps.files.models import AllowToLoadData
AllowToLoadData.objects.create()
```

And you can upload your logs using DRF API

The expected body is:

```
$BASE_URL/api/v1/files-uploaded/
```

```json
{
    "device_source": "",
    "uploaded_by": "your nickname here remember this app is develop for a conquest or kind of CTF",
    "files": ["enumerated files for process (max 100 files) per request"]
}
```

# Special thanks

* B3ts0b3ts4
* RF Village MX
* And the Mexico Cibersecurity Comunity that want to use the idea

# TODO 

* Add Metabase and first configuration for add a scoreboard and for BI Analysis
* Fix Swagger output for access to that endpoint
* Add more mechanism for the conquest