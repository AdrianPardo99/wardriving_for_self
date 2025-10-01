from django.db import models
from django.utils.timezone import now

from . import SourceDevice


class Wardriving(models.Model):
    mac = models.CharField(
        max_length=17, verbose_name="MAC Address"
    )  # Format: XX:XX:XX:XX:XX:XX
    ssid = models.CharField(max_length=255, verbose_name="SSID", default="")
    auth_mode = models.CharField(
        max_length=50, verbose_name="Authentication Mode", default=""
    )
    first_seen = models.DateTimeField(verbose_name="First Seen", default=now)
    channel = models.IntegerField(verbose_name="Channel")
    rssi = models.IntegerField(verbose_name="RSSI (Signal Strength)")
    current_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, verbose_name="Latitude", default=0
    )
    current_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, verbose_name="Longitude", default=0
    )
    altitude_meters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Altitude (Meters)",
        default=0,
    )
    accuracy_meters = models.DecimalField(
        max_digits=6, decimal_places=2, verbose_name="Accuracy (Meters)", default=0
    )
    type = models.CharField(max_length=50, verbose_name="Type", default="WIFI")
    device_source = models.CharField(
        max_length=50,
        verbose_name="Source",
        choices=SourceDevice.CHOICES,
        default=SourceDevice.UNKNOWN,
    )
    uploaded_by = models.TextField(verbose_name="Uploaded by", default="")

    class Meta:
        db_table = "wardriving"
        verbose_name = "Wardriving Data"
        verbose_name_plural = "Wardriving Data"

    def __str__(self):
        return (f"{(self.ssid or self.type) or "Unknown Device"} ({self.mac})")

    def is_default_data(self):
        return self.current_latitude == 0 and self.current_longitude == 0


class LTEWardriving(models.Model):
    # From csv device content file
    mcc = models.IntegerField(verbose_name="MCC (Mobile Country Code)")
    mnc = models.IntegerField(verbose_name="MNC (Mobile Network Code)")
    lac = models.IntegerField(verbose_name="LAC (Location Area Code)")
    cell_id = models.IntegerField(verbose_name="Cell ID (Cell Global Identity)")
    band = models.TextField(verbose_name="Band")
    rssi = models.IntegerField(verbose_name="RSSI (Signal Strength)")
    rsrp = models.IntegerField(verbose_name="RSRP (Reference Signal Received Power)")
    rsrq = models.IntegerField(verbose_name="RSRQ (Reference Signal Received Quality)")
    sinr = models.IntegerField(
        verbose_name="SINR (Signal-to-Interference-plus-Noise Ratio)"
    )
    provider = models.TextField(verbose_name="Provider", default="")
    current_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, verbose_name="Latitude", default=0
    )
    current_longitud = models.DecimalField(
        max_digits=9, decimal_places=6, verbose_name="Longitude", default=0
    )
    tech = models.TextField(verbose_name="Technology", default="LTE")
    # Custom config for conquest and identify origin of source and when its founded and by who
    first_seen = models.DateTimeField(verbose_name="First Seen", default=now)
    uploaded_by = models.TextField(verbose_name="Uploaded by", default="")
    device_source = models.CharField(
        max_length=50,
        verbose_name="Source",
        choices=SourceDevice.CHOICES,
        default=SourceDevice.UNKNOWN,
    )

    class Meta:
        db_table = "lte_wardriving"
        verbose_name = " LTE Wardriving Found"
        verbose_name_plural = " LTE Wardriving Founds"

    def __str__(self):
        return f"`{self.pk}`:{self.mcc}-{self.mnc}-{self.lac} : ({self.cell_id})"

    def is_default_data(self):
        return self.current_latitude == 0 and self.current_longitude == 0
