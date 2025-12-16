from django.contrib import admin
from .models import Vendors


@admin.register(Vendors)
class VendorsAdmin(admin.ModelAdmin):
    pass
