from django.contrib import admin
from .models import Wardriving, LTEWardriving


@admin.register(Wardriving)
class WardrivingAdmin(admin.ModelAdmin):
    pass


@admin.register(LTEWardriving)
class LTEWardrivingAdmin(admin.ModelAdmin):
    pass
