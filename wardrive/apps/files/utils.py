import re
from decimal import Decimal
from datetime import datetime
from functools import reduce
from operator import or_ as OR
from contextlib import contextmanager

from pandas import read_csv, to_datetime, isna, notna, to_numeric, DataFrame
from redis import Redis

from django.db import transaction
from django.db.models import Q
from django.utils.timezone import make_aware, now
from django.conf import settings

from apps.wardriving.models import Wardriving, SourceDevice, LTEWardriving


# -----------------------------
# Redis singleton (locks opcionales)
# -----------------------------
redis_client = Redis.from_url(settings.REDIS_URL)


@contextmanager
def record_lock(mac, channel, uploaded_by, timeout=10, wait=60, **kwargs):
    key = get_lock_key(mac, channel, uploaded_by)
    lock = redis_client.lock(key, timeout=timeout, blocking_timeout=wait)
    try:
        lock.acquire()
        yield
    finally:
        lock.release()


@contextmanager
def record_lte_lock(mcc, mnc, lac, cell_id, timeout=10, wait=60, **kwargs):
    key = get_lock_lte_key(mcc, mnc, lac, cell_id)
    lock = redis_client.lock(key, timeout=timeout, blocking_timeout=wait)
    try:
        lock.acquire()
        yield
    finally:
        lock.release()


def get_lock_key(mac, channel, uploaded_by):
    return f"lock:wardriving:{mac}:{channel}:{uploaded_by}"


def get_lock_lte_key(mcc, mnc, lac, cell_id):
    return f"lock:lte-wardriving:{mcc}:{mnc}:{lac}:{cell_id}"


# -----------------------------
# Helpers of upsert
# -----------------------------


def _build_q(keys, key_fields):
    ors = []
    for tup in keys:
        q = Q(**{f: v for f, v in zip(key_fields, tup)})
        ors.append(q)
    # Si no hay keys, previene reduce([])
    if not ors:
        return Q(pk=None)
    return reduce(lambda a, b: a | b, ors)


def _dedupe_keep_best(rows, key_fields, better_row_fn):
    """
    rows: list[dict] (incluyen las key_fields)
    better_row_fn(new_row, cur_row) -> bool
    """
    by_key = {}
    for r in rows:
        k = tuple(r.get(f) for f in key_fields)
        cur = by_key.get(k)
        if cur is None or better_row_fn(r, cur):
            by_key[k] = r
    return by_key


def default_better_row_fn(new_row, cur_row):
    nr = new_row.get("rssi")
    cr = cur_row.get("rssi")
    if cr is None:
        return True
    if nr is None:
        return False
    return nr > cr


def wardriving_better_obj_fn(new_row, old_obj):
    # If have "default" values (without valid data), always perform
    is_default = False
    if hasattr(old_obj, "is_default_data"):
        try:
            is_default = bool(old_obj.is_default_data())
        except Exception:
            is_default = False
    if is_default:
        return True

    nrssi = new_row.get("rssi")
    orssi = getattr(old_obj, "rssi", None)

    # Check RSSI, if New RSSI don't change
    if nrssi is None:
        return False

    # If RSSI is better (less value)
    return (orssi is None) or (nrssi > orssi)


@transaction.atomic
def bulk_upsert_by_keys(
    *,
    model,
    key_fields,  # e.g. ['uploaded_by','mac','channel']
    rows,  # list[dict]
    better_obj_fn,  # (new_row:dict, old_obj:model)->bool
    better_row_fn=default_better_row_fn,
    update_fields=None,  # list[str]
    only_fields=None,  # list[str]
    base_filter=None,  # dict
    chunk_size=1000,
):
    if not rows:
        return 0, 0, 0

    update_fields = update_fields or []

    # 1) Deduplicación en memoria: mejor candidato por clave
    best_by_key = _dedupe_keep_best(rows, key_fields, better_row_fn)
    keys = list(best_by_key.keys())

    # 2) Leer existentes en 1..N queries
    existing = {}
    for i in range(0, len(keys), chunk_size):
        batch = keys[i : i + chunk_size]
        cond = _build_q(batch, key_fields)
        qs = model.objects.filter(cond)
        if base_filter:
            qs = qs.filter(**base_filter)
        if only_fields:
            qs = qs.only(*only_fields)
        for obj in qs:
            k = tuple(getattr(obj, f) for f in key_fields)
            existing[k] = obj

    # 3) Clasificar para create/update
    to_create = []
    to_update = []

    for k, row in best_by_key.items():
        obj = existing.get(k)
        if obj is None:
            to_create.append(model(**row))
        else:
            if better_obj_fn(row, obj):
                for f in update_fields:
                    if f in row and row[f] is not None:
                        setattr(obj, f, row[f])
                to_update.append(obj)

    # 4) Ejecutar en bulk
    created = updated = 0
    if to_create:
        model.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=1000)
        created = len(to_create)
    if to_update:
        model.objects.bulk_update(to_update, update_fields, batch_size=1000)
        updated = len(to_update)

    ignored = max(0, len(best_by_key) - (created + updated))
    return created, updated, ignored


# -----------------------------
# Procesadores ESP32 Marauder (Flipper/Classic)
# -----------------------------
LINE_RE_FLIPPER = re.compile(
    r"\d+ \| ([\dA-Fa-f:]+),(.*?),\[(.*?)\],(.*?),(.*?),(-?\d+),(.*?),(.*?),(.*?),(.*?),(WIFI|BLE)$"
)


def _parse_marauder_line(line):
    if line.startswith("#") or "stopscan" in line or "Starting Wardrive" in line:
        return None
    m = LINE_RE_FLIPPER.match(line.strip())
    if not m:
        return None
    return m.groups()


# Process some files with structure from project Marauder ESP32 in flipper format (has an index for follow the wardrive)
# Source to project firmware: https://github.com/justcallmekoko/ESP32Marauder/
def process_format_flipper_marauder(
    lines=list(),
    device_source=SourceDevice.FLIPPER_DEV_BOARD,
    uploaded_by="Without Owner",
):
    rows = []
    for line in lines:
        g = _parse_marauder_line(line)
        if not g:
            continue
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
        ) = g

        ssid = ssid or None
        if first_seen:
            try:
                first_seen = make_aware(
                    datetime.strptime(first_seen, "%Y-%m-%d %H:%M:%S")
                )
            except Exception:
                first_seen = None
        if isinstance(first_seen, str):
            first_seen = None

        try:
            channel = int(channel) if channel and channel.isdigit() else None
            rssi = int(rssi) if rssi not in (None, "") else None
            lat = Decimal(lat) if lat else None
            lon = Decimal(lon) if lon else None
            alt = Decimal(alt) if alt else None
            acc = Decimal(acc) if acc else None
        except Exception:
            continue

        if channel is None:
            continue
        if lat == 0 and lon == 0:
            continue

        row = {
            "uploaded_by": uploaded_by,
            "mac": mac,
            "channel": channel,
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
        # Limpia None si no deseas sobreescribir con nulos
        row = {k: v for k, v in row.items() if v is not None}
        rows.append(row)

    return bulk_upsert_by_keys(
        model=Wardriving,
        key_fields=["uploaded_by", "mac", "channel"],
        rows=rows,
        better_obj_fn=wardriving_better_obj_fn,
        update_fields=[
            "ssid",
            "auth_mode",
            "first_seen",
            "current_latitude",
            "current_longitude",
            "altitude_meters",
            "accuracy_meters",
            "type",
            "rssi",
            "device_source",
        ],
        only_fields=["id", "uploaded_by", "mac", "channel", "rssi"],
        # base_filter={'device_source': device_source},  # opcional
        chunk_size=1000,
    )


# Process some files with structure from project Marauder ESP32 in classic format (without index and can process as CSV)
# Source to project firmware: https://github.com/justcallmekoko/ESP32Marauder/
def process_format_classic_marauder(
    lines=list(),
    device_source=SourceDevice.MARAUDER_V6,
    uploaded_by="Without Owner",
):
    rows = []
    for line in lines:
        if line.startswith("#") or "stopscan" in line or "Starting Wardrive" in line:
            continue
        m = re.match(
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
        if not m:
            continue
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
        ) = m.groups()

        ssid = ssid or None
        if first_seen:
            try:
                first_seen = make_aware(
                    datetime.strptime(first_seen, "%Y-%m-%d %H:%M:%S")
                )
            except Exception:
                first_seen = None
        if isinstance(first_seen, str):
            first_seen = None

        try:
            channel = int(channel) if channel and channel.isdigit() else None
            rssi = int(rssi) if rssi not in (None, "") else None
            lat = Decimal(lat) if lat else None
            lon = Decimal(lon) if lon else None
            alt = Decimal(alt) if alt else None
            acc = Decimal(acc) if acc else None
        except Exception:
            continue

        if channel is None:
            continue
        if lat == 0 and lon == 0:
            continue

        row = {
            "uploaded_by": uploaded_by,
            "mac": mac,
            "channel": channel,
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
        row = {k: v for k, v in row.items() if v is not None}
        rows.append(row)

    return bulk_upsert_by_keys(
        model=Wardriving,
        key_fields=["uploaded_by", "mac", "channel"],
        rows=rows,
        better_obj_fn=wardriving_better_obj_fn,
        update_fields=[
            "ssid",
            "auth_mode",
            "first_seen",
            "current_latitude",
            "current_longitude",
            "altitude_meters",
            "accuracy_meters",
            "type",
            "rssi",
            "device_source",
        ],
        only_fields=["id", "uploaded_by", "mac", "channel", "rssi"],
        chunk_size=1000,
    )


# -----------------------------
# General function for Marauder/Flipper
# -----------------------------
# Entry point for processing Marauder ESP32 files
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

    esp32_classess_process = {
        SourceDevice.FLIPPER_DEV_BOARD: process_format_flipper_marauder,
        SourceDevice.FLIPPER_DEV_BOARD_PRO: process_format_flipper_marauder,
    }
    cls_process = esp32_classess_process.get(
        device_source, process_format_classic_marauder
    )
    return cls_process(
        device_source=device_source, uploaded_by=uploaded_by, lines=lines
    )


# -----------------------------
# Minino (Electronic Cats)
# -----------------------------
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

    # Normaliza first_seen
    if "first_seen" in df:
        fs = to_datetime(df["first_seen"], errors="coerce")
        # make_aware individual en loop por seguridad de tz
        df["first_seen"] = fs

    rows = []
    for _, row in df.iterrows():
        mac = row.get("mac")
        channel = row.get("channel")
        if isna(mac) or isna(channel):
            continue

        first_seen = row.get("first_seen")
        if isinstance(first_seen, datetime):
            first_seen = make_aware(first_seen)
        else:
            first_seen = None

        rssi_val = int(row["rssi"]) if "rssi" in row and notna(row["rssi"]) else None

        payload = {
            "uploaded_by": uploaded_by,
            "mac": mac,
            "channel": int(channel),
            "ssid": (row.get("ssid") or None),
            "auth_mode": (row.get("auth_mode") or None),
            "first_seen": first_seen,
            "current_latitude": Decimal(row["current_latitude"])
            if notna(row.get("current_latitude"))
            else None,
            "current_longitude": Decimal(row["current_longitude"])
            if notna(row.get("current_longitude"))
            else None,
            "altitude_meters": Decimal(row["altitude_meters"])
            if notna(row.get("altitude_meters"))
            else None,
            "accuracy_meters": Decimal(row["accuracy_meters"])
            if notna(row.get("accuracy_meters"))
            else None,
            "type": (row.get("type") or "WIFI"),
            "rssi": rssi_val,
            "device_source": device_source,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        rows.append(payload)

    return bulk_upsert_by_keys(
        model=Wardriving,
        key_fields=["uploaded_by", "mac", "channel"],
        rows=rows,
        better_obj_fn=wardriving_better_obj_fn,
        update_fields=[
            "ssid",
            "auth_mode",
            "first_seen",
            "current_latitude",
            "current_longitude",
            "altitude_meters",
            "accuracy_meters",
            "type",
            "rssi",
            "device_source",
        ],
        only_fields=["id", "uploaded_by", "mac", "channel", "rssi"],
        chunk_size=1000,
    )


# -----------------------------
# RF (LTE / WIFI) Lilygo T-SIM7000G
# -----------------------------
# Process LTE wardriving data from Lilygo T-SIM7000G
# Header example of LTE file
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
        "Longitud": "current_longitude",
        "Latitud": "current_latitude",
        "Tecnología": "tech",
    }
    downcase_keys = ["MCC", "MNC", "LAC", "RSSI", "RSRP", "RSRQ", "SINR"]

    for key in pop_keys:
        if key in dataframe:
            dataframe.pop(key)
    dataframe.rename(columns=renamed_keys, inplace=True)
    for key in downcase_keys:
        if key in dataframe:
            dataframe[key.lower()] = dataframe.pop(key)

    # RSSI a int
    dataframe["rssi"] = (
        dataframe["rssi"].astype(str).str.replace(" dBm", "", regex=False).str.strip()
    )
    dataframe["rssi"] = to_numeric(dataframe["rssi"], errors="coerce")
    dataframe = dataframe.dropna(subset=["rssi"]).reset_index(drop=True)
    dataframe["rssi"] = dataframe["rssi"].astype(int)

    dataframe["provider"] = dataframe["provider"].fillna("Not Provided")

    rows = []
    for instance_data in dataframe.to_dict(orient="records"):
        if not instance_data.get("cell_id"):
            continue
        row = {
            "uploaded_by": uploaded_by,
            "device_source": device_source,
            "tech": instance_data.get("tech"),
            "mcc": instance_data.get("mcc"),
            "mnc": instance_data.get("mnc"),
            "lac": instance_data.get("lac"),
            "cell_id": instance_data.get("cell_id"),
            "first_seen": now(),
            "rssi": instance_data.get("rssi"),
            "rsrp": instance_data.get("rsrp"),
            "rsrq": instance_data.get("rsrq"),
            "sinr": instance_data.get("sinr"),
            "band": instance_data.get("band"),
            "provider": instance_data.get("provider") or "Not Provided",
            "current_longitude": instance_data.get("current_longitude"),
            "current_latitude": instance_data.get("current_latitude"),
        }
        row = {k: v for k, v in row.items() if v is not None}
        rows.append(row)

    return bulk_upsert_by_keys(
        model=LTEWardriving,
        key_fields=[
            "uploaded_by",
            "device_source",
            "tech",
            "mcc",
            "mnc",
            "lac",
            "cell_id",
        ],
        rows=rows,
        better_obj_fn=wardriving_better_obj_fn,
        update_fields=[
            "first_seen",
            "rssi",
            "rsrp",
            "rsrq",
            "sinr",
            "band",
            "provider",
            "current_longitude",
            "current_latitude",
        ],
        only_fields=[
            "id",
            "uploaded_by",
            "device_source",
            "tech",
            "mcc",
            "mnc",
            "lac",
            "cell_id",
            "rssi",
        ],
        chunk_size=1000,
    )


# Process WIFI wardriving from Lilygo T-SIM7000G custom firmware
# Header example of WIFI file
# Timestamp,Lat,Long,SSID,BSSID,Canal,Señal,Seguridad
def process_wifi_rf_wardriving(
    device_source=SourceDevice.RF_CUSTOM_FIRMWARE_WIFI,
    uploaded_by="Without Owner",
    dataframe=DataFrame(),
):
    pop_keys = ["Timestamp"]
    for k in pop_keys:
        if k in dataframe:
            dataframe.pop(k)

    dataframe.rename(
        columns={
            "Lat": "current_latitude",
            "Long": "current_longitude",
            "SSID": "ssid",
            "BSSID": "mac",
            "Canal": "channel",
            "Señal": "rssi",
            "Seguridad": "auth_mode",
        },
        inplace=True,
    )

    dataframe["rssi"] = dataframe["rssi"].astype(str).str.strip()
    dataframe["rssi"] = to_numeric(dataframe["rssi"], errors="coerce")
    dataframe = dataframe.dropna(subset=["rssi"]).reset_index(drop=True)
    dataframe["rssi"] = dataframe["rssi"].astype(int)

    rows = []
    for rec in dataframe.to_dict(orient="records"):
        if rec.get("mac") is None or rec.get("channel") is None:
            continue
        row = {
            "uploaded_by": uploaded_by,
            "mac": rec["mac"],
            "channel": int(rec["channel"]),
            "ssid": rec.get("ssid"),
            "auth_mode": rec.get("auth_mode"),
            "first_seen": now(),
            "current_latitude": rec.get("current_latitude"),
            "current_longitude": rec.get("current_longitude"),
            "rssi": rec.get("rssi"),
            "device_source": device_source,
            "type": "WIFI",
        }
        row = {k: v for k, v in row.items() if v is not None}
        rows.append(row)

    return bulk_upsert_by_keys(
        model=Wardriving,
        key_fields=["uploaded_by", "mac", "channel"],
        rows=rows,
        better_obj_fn=wardriving_better_obj_fn,
        update_fields=[
            "ssid",
            "auth_mode",
            "first_seen",
            "current_latitude",
            "current_longitude",
            "rssi",
            "device_source",
            "type",
        ],
        only_fields=["id", "uploaded_by", "mac", "channel", "rssi"],
        chunk_size=1000,
    )


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
    cls_process = rf_classess_process.get(device_source, None)
    if cls_process:
        return cls_process(
            device_source=device_source, uploaded_by=uploaded_by, dataframe=df
        )
    return 0, 0, 0


# -----------------------------
# Map functions
# -----------------------------

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
