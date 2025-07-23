import re
from decimal import Decimal
from datetime import datetime
from pandas import read_csv, to_datetime, notnull, isna, notna
from redis import Redis
from contextlib import contextmanager

from django.utils.timezone import make_aware
from django.conf import settings


from apps.wardriving.models import Wardriving, SourceDevice

# Singlenton redis instance
redis_client = Redis.from_url(settings.REDIS_URL)


# Decorator for handle the parallel update/create record
@contextmanager
def record_lock(mac, channel, uploaded_by, timeout=10, wait=5):
    key = get_lock_key(mac, channel, uploaded_by)
    lock = redis_client.lock(key, timeout=timeout, blocking_timeout=wait)
    try:
        lock.acquire()
        yield
    finally:
        lock.release()


# Generate a dynamic lock key for redis and parallel processing
def get_lock_key(mac, channel, uploaded_by):
    return f"lock:wardriving:{mac}:{channel}:{uploaded_by}"


# Process some files with structure from project Marauder ESP32
# Source to project firmware: https://github.com/justcallmekoko/ESP32Marauder/
# Header example of file
# mac,ssid,auth_mode,first_seen,channel,rssi,lat,lon,alt,acc,scan_device_type
def process_file_marauder_esp32(
    file_path="",
    device_source=SourceDevice.FLIPPER_DEV_BOARD,
    uploaded_by="Without Owner",
):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as file:
            lines = file.readlines()

    total_new = 0
    total_old = 0

    for line in lines:
        # Ignore headers and special lines
        if line.startswith("#") or "stopscan" in line or "Starting Wardrive" in line:
            continue

        # Extract data using regular expressions
        match = re.match(
            r"\d+ \| ([\dA-Fa-f:]+),(.*?),\[(.*?)\],(.*?),(.*?),(-?\d+),(.*?),(.*?),(.*?),(.*?),(WIFI)",
            line.strip(),
        )
        if match:
            # Extract values from the line
            (
                mac,
                ssid,
                auth_mode,
                first_seen,
                channel,
                rssi,
                lat,
                lon,
                alt,
                acc,
                data_type,
            ) = match.groups()

            # Parse values
            ssid = ssid if ssid else None
            if first_seen:
                try:
                    first_seen = make_aware(
                        datetime.strptime(first_seen, "%Y-%m-%d %H:%M:%S")
                    )
                except Exception:
                    pass
            if isinstance(first_seen, str):
                first_seen = None
            channel = int(channel) if channel.isdigit() else None
            rssi = int(rssi)
            lat = Decimal(lat) if lat else None
            lon = Decimal(lon) if lon else None
            alt = Decimal(alt) if alt else None
            acc = Decimal(acc) if acc else None
            # Create or update a record
            with record_lock(mac, channel, uploaded_by):
                created = True
                try:
                    obj = Wardriving.objects.get(
                        mac=mac,
                        channel=channel,
                        uploaded_by=uploaded_by,
                    )
                    created = False
                except Wardriving.DoesNotExist:
                    obj = Wardriving(
                        mac=mac,
                        channel=channel,
                        uploaded_by=uploaded_by,
                    )
                data = {
                    "ssid": ssid,
                    "auth_mode": auth_mode,
                    "first_seen": first_seen,
                    "current_latitude": lat,
                    "current_longitude": lon,
                    "altitude_meters": alt,
                    "accuracy_meters": acc,
                    "type": data_type,
                    "rssi": rssi,
                    "device_source": device_source,
                }
                # Clean empty fields
                data = {k: v for k, v in data.items() if v is not None}
                if created:
                    for field, value in data.items():
                        setattr(obj, field, value)
                    if not obj.is_default_data():
                        total_new += 1
                else:
                    if obj.rssi < rssi or obj.is_default_data():
                        for field, value in data.items():
                            setattr(obj, field, value)
                    total_old += 1
                obj.save()
    return total_new, total_old


# Process some files with structure from project Minino
# Source to project firmware: https://github.com/ElectronicCats/Minino
# Header example of file
# MAC,SSID,AuthMode,FirstSeen,Channel,Frequency,RSSI,CurrentLatitude,CurrentLongitude,AltitudeMeters,AccuracyMeters,RCOIs,MfgrId,Type
def process_file_minino(
    file_path="",
    device_source=SourceDevice.MININO,
    uploaded_by="Without Owner",
):
    try:
        df = read_csv(file_path, encoding="utf-8", skiprows=1)
    except UnicodeDecodeError:
        df = read_csv(file_path, encoding="latin-1", skiprows=1)

    # In next versions add support for feature of IoT and Sub wardriving minino features in model
    deleted_rows = ["Frequency", "RCOIs", "MfgrId"]
    renamed_headers = {
        "MAC": "mac",
        "SSID": "ssid",
        "AuthMode": "auth_mode",
        "FirstSeen": "first_seen",
        "Channel": "channel",
        "RSSI": "rssi",
        "CurrentLatitude": "current_latitude",
        "CurrentLongitude": "current_longitude",
        "AltitudeMeters": "altitude_meters",
        "AccuracyMeters": "accuracy_meters",
        "Type": "type",
    }

    df = df.drop(columns=[col for col in deleted_rows if col in df.columns])
    df.rename(columns=renamed_headers, inplace=True)

    total_new = 0
    total_old = 0

    for _, row in df.iterrows():
        mac = row["mac"] if "mac" in row else None
        channel = row["channel"] if "channel" in row else None
        if isna(mac) or isna(channel):
            continue

        # Convert types
        first_seen = (
            to_datetime(row["first_seen"], errors="coerce")
            if "first_seen" in row
            else None
        )
        if not isna(first_seen) and isinstance(first_seen, datetime):
            first_seen = make_aware(first_seen)
        else:
            first_seen = None
        with record_lock(mac, channel, uploaded_by):
            created = True
            try:
                obj = Wardriving.objects.get(
                    mac=mac,
                    channel=int(channel),
                    uploaded_by=uploaded_by,
                )
                created = False
            except Wardriving.DoesNotExist:
                obj = Wardriving(
                    mac=mac,
                    channel=int(channel),
                    uploaded_by=uploaded_by,
                )

            ssid = row["ssid"] if "ssid" in row else ""
            auth_mode = row["auth_mode"] if "auth_mode" in row else ""
            current_latitude = (
                row["current_latitude"] if "current_latitude" in row else None
            )
            current_longitude = (
                row["current_longitude"] if "current_longitude" in row else None
            )
            altitude_meters = (
                row["altitude_meters"] if "altitude_meters" in row else None
            )
            accuracy_meters = (
                row["accuracy_meters"] if "accuracy_meters" in row else None
            )
            rssi = int(row["rssi"]) if "rssi" in row and notna(row["rssi"]) else 0
            data_type = row["type"] if "type" in row else "WIFI"

            data = {
                "ssid": ssid or "",
                "auth_mode": auth_mode or "",
                "first_seen": first_seen,
                "rssi": int(row["rssi"])
                if "rssi" in row and notna(row["rssi"])
                else None,
                "current_latitude": Decimal(current_latitude)
                if current_latitude
                else None,
                "current_longitude": Decimal(current_longitude)
                if current_longitude
                else None,
                "altitude_meters": Decimal(altitude_meters)
                if altitude_meters
                else None,
                "accuracy_meters": Decimal(accuracy_meters)
                if accuracy_meters
                else None,
                "type": data_type,
                "device_source": device_source,
            }

            # Clean empty fields
            data = {k: v for k, v in data.items() if v is not None}

            if created:
                for field, value in data.items():
                    setattr(obj, field, value)
                if not obj.is_default_data():
                    total_new += 1
            else:
                if (
                    obj.rssi is None
                    or (rssi and obj.rssi < rssi)
                    or obj.is_default_data()
                ):
                    for field, value in data.items():
                        setattr(obj, field, value)
                total_old += 1
            obj.save()

    return total_new, total_old


# Singlenton of map related to processing functions files
CHOICES_FUNCTION_PROCESS = {
    SourceDevice.UNKNOWN: None,
    SourceDevice.MININO: process_file_minino,
    SourceDevice.FLIPPER_DEV_BOARD: process_file_marauder_esp32,
    SourceDevice.FLIPPER_DEV_BOARD_PRO: process_file_marauder_esp32,
    SourceDevice.MARAUDER_V4: process_file_marauder_esp32,
    SourceDevice.MARAUDER_V6: process_file_marauder_esp32,
    SourceDevice.FLIPPER_BFFB: process_file_marauder_esp32,
    SourceDevice.MARAUDER_ESP32: process_file_marauder_esp32,
    SourceDevice.OTHER: None,
}
