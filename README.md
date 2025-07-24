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
## Metabase set up

I have to say sorry but in this moment I cannot add a quick setup for deploy all the integration with metabase, maybe in next updates 

You need to do the first set up the application with your own data and set the variables related to your conection with the data base so you need to access to your url: `$BASE_METABASE_URL/admin/databases` and configure with the data related to your `.env` file if you know about the configuration related and how Podman or Containers work internal with the dns and naming of service you can go into your conection and creation of your dashboard using the query or modify as you wish in directory `sql_bi_sources/`, but if you follow the instruction you need to add the server host using the variable of `$DB_HOST` value for your database conection.

Finally when you configure and explore about the configuration from database, you need to add a Question or SQL Query in the button `+ New > SQL` and you can add all the query information related to the database and have fun and do your activity with wardriving

## How to finish the conquest don't ammit more processing of the files

You can enter to your admin panel and change the value of `AllowToLoadData` instance and with that everyone can upload them files and logs into the API, but it will not process anymore til' you enable it again, or if you has the physical access to your terminal or where you host the application, you only need to enter in the interactive shell and write

```python
from apps.files.models import AllowToLoadData
AllowToLoadData.objects.all().update(active=False)
```

And with that you disable the processing of the files and nobody can get more SSID points.

# Special thanks

I have to thank to some people and groups that make me develop this application

* B3ts0b3ts4
* [Ekoparty (Ekogroup Mx)](https://www.instagram.com/ekogroup_mx/)
* [misskernel](https://www.instagram.com/misskernel/)
* [samo_harakiri_2600/@Dr0xharakiri](https://github.com/Dr0xharakiri) 
* [RF Village MX](https://www.instagram.com/rf_village_mx/)
* And the Mexico Cibersecurity Comunity that want to use the idea

# TODO 

* Add Metabase and first configuration for add a scoreboard (BI Analysis)
* Fix Swagger output for access to that endpoint
* Add more mechanism for the conquest