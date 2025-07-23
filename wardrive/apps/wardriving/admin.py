from django.contrib import admin
from .models import Wardriving


@admin.register(Wardriving)
class WardrivingAdmin(admin.ModelAdmin):
    pass
