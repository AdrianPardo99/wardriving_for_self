import re
from decimal import Decimal
from datetime import datetime
from pandas import read_csv, to_datetime, notnull, isna, notna, to_numeric, DataFrame
from redis import Redis
from contextlib import contextmanager

from django.utils.timezone import make_aware, now
from django.conf import settings


from apps.wardriving.models import Wardriving, SourceDevice, LTEWardriving

# Singlenton redis instance
redis_client = Redis.from_url(settings.REDIS_URL)


# Decorator for handle the parallel update/create record
@contextmanager
def record_lock(mac, channel, uploaded_by, timeout=10, wait=5, **kwargs):
    key = get_lock_key(mac, channel, uploaded_by)
    lock = redis_client.lock(key, timeout=timeout, blocking_timeout=wait)
    try:
        lock.acquire()
        yield
    finally:
        lock.release()


@contextmanager
def record_lte_lock(mcc, mnc, lac, cell_id, timeout=10, wait=5, **kwargs):
    key = get_lock_lte_key(mcc, mnc, lac, cell_id)
    lock = redis_client.lock(key, timeout=timeout, blocking_timeout=wait)
    try:
        lock.acquire()
        yield
    finally:
        lock.release()


# Generate a dynamic lock key for redis and parallel processing
def get_lock_key(mac, channel, uploaded_by):
    return f"lock:wardriving:{mac}:{channel}:{uploaded_by}"


def get_lock_lte_key(mcc, mnc, lac, cell_id):
    return f"lock:lte-wardriving:{mcc}:{mnc}:{lac}:{cell_id}"


# Process some files with structure from project Marauder ESP32 in flippler format (has a index for follow the wardrive)
# Source to project firmware: https://github.com/justcallmekoko/ESP32Marauder/
def process_format_flipper_marauder(
    lines=list(),
    device_source=SourceDevice.FLIPPER_DEV_BOARD,
    uploaded_by="Without Owner",
):
    total_new = 0
    total_old = 0
    total_ignored = 0
    for line in lines:
        # Ignore headers and special lines
        if line.startswith("#") or "stopscan" in line or "Starting Wardrive" in line:
            continue

        # Extract data using regular expressions
        match = re.match(
            r"\d+ \| ([\dA-Fa-f:]+),(.*?),\[(.*?)\],(.*?),(.*?),(-?\d+),(.*?),(.*?),(.*?),(.*?),(WIFI|BLE)$",
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
                save = False
                if created:
                    for field, value in data.items():
                        setattr(obj, field, value)
                else:
                    if obj.rssi < rssi or obj.is_default_data():
                        for field, value in data.items():
                            setattr(obj, field, value)
                if not obj.is_default_data():
                    save = True
                    total_new += 1 if created else 0
                    total_old += 1 if not created else 0

                if save:
                    obj.save()
                    continue
                total_ignored += 1

    return total_new, total_old, total_ignored


# Process some files with structure from project Marauder ESP32 in format classic (without index and can process as CSV)
# Source to project firmware: https://github.com/justcallmekoko/ESP32Marauder/
def process_format_classic_marauder(
    lines=list(),
    device_source=SourceDevice.MARAUDER_V6,
    uploaded_by="Without Owner",
):
    total_new = 0
    total_old = 0
    total_ignored = 0
    for line in lines:
        # Ignore headers and special lines
        if line.startswith("#") or "stopscan" in line or "Starting Wardrive" in line:
            continue
        # Extract data using regular expressions
        match = re.match(
            r"^([0-9A-Fa-f:]+),\s*"  # MAC
            r"([^,]*),\s*"  # SSID
            r"\[([^\]]*)\],\s*"  # auth_mode
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\s*"  # timestamp
            r"(\d+),\s*"  # channel
            r"(-?\d+),\s*"  # rssi
            r"(-?\d+(?:\.\d+)?),\s*"  # lat
            r"(-?\d+(?:\.\d+)?),\s*"  # lon
            r"(-?\d+(?:\.\d+)?),\s*"  # alt
            r"(-?\d+(?:\.\d+)?),\s*"  # acc
            r"(WIFI|BLE)$",  # Technology
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
                save = False
                if created:
                    for field, value in data.items():
                        setattr(obj, field, value)
                else:
                    if obj.rssi < rssi or obj.is_default_data():
                        for field, value in data.items():
                            setattr(obj, field, value)
                if not obj.is_default_data():
                    save = True
                    total_new += 1 if created else 0
                    total_old += 1 if not created else 0

                if save:
                    obj.save()
                    continue
                total_ignored += 1
    return total_new, total_old, total_ignored


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
    total_ignored = 0
    esp32_classess_process = {
        SourceDevice.FLIPPER_DEV_BOARD: process_format_flipper_marauder,
        SourceDevice.FLIPPER_DEV_BOARD_PRO: process_format_flipper_marauder,
    }
    cls_process = esp32_classess_process.get(
        device_source, process_format_classic_marauder
    )
    if cls_process:
        total_new, total_old, total_ignored = cls_process(
            device_source=device_source,
            uploaded_by=uploaded_by,
            lines=lines,
        )
    return total_new, total_old, total_ignored


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
    total_ignored = 0

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
            save = False
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
            else:
                if (
                    obj.rssi is None
                    or (rssi and obj.rssi < rssi)
                    or obj.is_default_data()
                ):
                    for field, value in data.items():
                        setattr(obj, field, value)
            if not obj.is_default_data():
                save = True
                total_new += 1 if created else 0
                total_old += 1 if not created else 0
            if save:
                obj.save()
                continue
            total_ignored += 1

    return total_new, total_old, total_ignored


# Process some files with structure from custom firmware from hardware Lilygo T-SIM7000G
# This part is for LTE Wardriving
# Header example of file
# Timestamp,Tecnología,Estado,MCC,MNC,LAC,CellID,Banda,RSSI,RSRP,RSRQ,SINR,Operador,Longitud,Latitud
def process_lte_wardriving(
    device_source=SourceDevice.RF_CUSTOM_FIRMWARE_LTE,
    uploaded_by="Without Owner",
    dataframe=DataFrame(),
):
    pop_keys = ["Timestamp", "Estado"]
    renamed_keys = {
        "CellID": "cell_id",
        "Banda": "band",
        "Operador": "provider",
        "Longitud": "current_longitud",
        "Latitud": "current_latitude",
        "Tecnología": "tech",
    }
    downcase_keys = ["MCC", "MNC", "LAC", "RSSI", "RSRP", "RSRQ", "SINR"]
    unique_keys = [
        "mcc",
        "mnc",
        "lac",
        "cell_id",
        "uploaded_by",
        "device_source",
        "tech",
    ]
    constant_payload = {
        "first_seen": now(),
        "uploaded_by": uploaded_by,
        "device_source": SourceDevice.RF_CUSTOM_FIRMWARE_LTE,
    }
    for key in pop_keys:
        if key in dataframe:
            dataframe.pop(key)
    dataframe.rename(columns=renamed_keys, inplace=True)
    for key in downcase_keys:
        if key in dataframe:
            dataframe[key.lower()] = dataframe.pop(key)
    # Pass string with dBm part to integer for process
    dataframe["rssi"] = (
        dataframe["rssi"].astype(str).str.replace(" dBm", "", regex=False).str.strip()
    )
    dataframe["rssi"] = to_numeric(dataframe["rssi"], errors="coerce")
    dataframe = dataframe.dropna(subset=["rssi"]).reset_index(drop=True)
    dataframe["rssi"] = dataframe["rssi"].astype(int)
    # Fill provider None/NaN missing information
    dataframe["provider"] = dataframe["provider"].fillna("Not Provided")
    # Start to process
    total_new = 0
    total_old = 0
    total_ignored = 0
    content_data = dataframe.to_dict(orient="records")
    for instance_data in content_data:
        data = instance_data | constant_payload
        new_payload = {key: data.pop(key, None) for key in unique_keys}
        with record_lte_lock(**new_payload):
            created = True
            save = False
            cell_id = new_payload.get("cell_id")
            if cell_id in ["0 dBm"]:
                continue
            try:
                obj = LTEWardriving.objects.get(**new_payload)
                created = False
            except LTEWardriving.DoesNotExist:
                obj = LTEWardriving(**new_payload)

            if created:
                for field, value in data.items():
                    setattr(obj, field, value)
            else:
                rssi = data.get("rssi")
                if (
                    obj.rssi is None
                    or (rssi and obj.rssi < rssi)
                    or obj.is_default_data()
                ):
                    for field, value in data.items():
                        setattr(obj, field, value)
            if not obj.is_default_data():
                save = True
                total_new += 1 if created else 0
                total_old += 1 if not created else 0
            if save:
                obj.save()
                continue
            total_ignored += 1
    return total_new, total_old, total_ignored


# Process some files with structure from custom firmware from hardware Lilygo T-SIM7000G
# This part is for WIFI Wardriving
# Header example of file
# Timestamp,Lat,Long,SSID,BSSID,Canal,Señal,Seguridad
def process_wifi_rf_wardriving(
    device_source=SourceDevice.RF_CUSTOM_FIRMWARE_WIFI,
    uploaded_by="Without Owner",
    dataframe=DataFrame(),
):
    pop_keys = [
        "Timestamp",
    ]
    renamed_keys = {
        "Lat": "current_latitude",
        "Long": "current_longitude",
        "SSID": "ssid",
        "BSSID": "mac",
        "Canal": "channel",
        "Señal": "rssi",
        "Seguridad": "auth_mode",
    }
    unique_keys = [
        "mac",
        "uploaded_by",
        "channel",
    ]
    constant_payload = {
        "first_seen": now(),
        "uploaded_by": uploaded_by,
        "device_source": SourceDevice.RF_CUSTOM_FIRMWARE_WIFI,
    }
    dataframe.rename(columns=renamed_keys, inplace=True)
    # Pass string with dBm part to integer for process
    dataframe["rssi"] = dataframe["rssi"].astype(str).str.strip()
    dataframe["rssi"] = to_numeric(dataframe["rssi"], errors="coerce")
    dataframe = dataframe.dropna(subset=["rssi"]).reset_index(drop=True)
    dataframe["rssi"] = dataframe["rssi"].astype(int)
    # Start to process
    total_new = 0
    total_old = 0
    total_ignored = 0
    content_data = dataframe.to_dict(orient="records")
    for instance_data in content_data:
        data = instance_data | constant_payload
        new_payload = {key: data.pop(key, None) for key in unique_keys}
        with record_lock(**new_payload):
            created = True
            save = False
            cell_id = new_payload.get("cell_id")
            if cell_id in ["0 dBm"]:
                continue
            try:
                obj = Wardriving.objects.get(**new_payload)
                created = False
            except Wardriving.DoesNotExist:
                obj = Wardriving(**new_payload)

            if created:
                for field, value in data.items():
                    setattr(obj, field, value)
            else:
                rssi = data.get("rssi")
                if (
                    obj.rssi is None
                    or (rssi and obj.rssi < rssi)
                    or obj.is_default_data()
                ):
                    for field, value in data.items():
                        setattr(obj, field, value)
            if not obj.is_default_data():
                save = True
                total_new += 1 if created else 0
                total_old += 1 if not created else 0
            if save:
                obj.save()
                continue
            total_ignored += 1
    return total_new, total_old, total_ignored


# Process some files with structure from custom firmware from hardware Lilygo T-SIM7000G
# This part is enable for process LTE or WIFI Wardriving check above for more detail of processing
def process_file_rf(
    file_path="",
    device_source=SourceDevice.RF_CUSTOM_FIRMWARE_WIFI,
    uploaded_by="Without Owner",
):
    try:
        df = read_csv(file_path, encoding="utf-8", sep=",")
    except UnicodeDecodeError:
        df = read_csv(file_path, encoding="latin-1", sep=",")
    rf_classess_process = {
        SourceDevice.RF_CUSTOM_FIRMWARE_LTE: process_lte_wardriving,
        SourceDevice.RF_CUSTOM_FIRMWARE_WIFI: process_wifi_rf_wardriving,
    }
    total_new = 0
    total_old = 0
    total_ignored = 0
    cls_process = rf_classess_process.get(device_source, None)
    if cls_process:
        total_new, total_old, total_ignored = cls_process(
            device_source=device_source,
            uploaded_by=uploaded_by,
            dataframe=df,
        )
    return total_new, total_old, total_ignored


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
    SourceDevice.RF_CUSTOM_FIRMWARE_WIFI: process_file_rf,
    SourceDevice.RF_CUSTOM_FIRMWARE_LTE: process_file_rf,
    SourceDevice.OTHER: None,
}
