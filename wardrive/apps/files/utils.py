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
from django.utils.timezone import make_aware, now, is_naive
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
# ESP32 Marauder parsers (Flipper/Classic)
# -----------------------------

LINE_RE_FLIPPER_WIFI = re.compile(
    r"^(?:>?\s*)?\d+\s*\|\s*"  # "1 |" with optional leading ">"
    r"([0-9A-Fa-f:]+),\s*"  # MAC/BSSID
    r"([^,]*),\s*"  # SSID
    r"\[([^\]]*)\],\s*"  # auth_mode
    r"(\d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}:\d{2}),\s*"  # timestamp
    r"(\d+),\s*"  # channel
    r"(-?\d+),\s*"  # rssi
    r"(-?\d+(?:\.\d+)?),\s*"  # lat
    r"(-?\d+(?:\.\d+)?),\s*"  # lon
    r"(-?\d+(?:\.\d+)?),\s*"  # alt
    r"(-?\d+(?:\.\d+)?),\s*"  # acc
    r"(WIFI)$"  # Technology
)
# New support in > 1.9.1_version hell yeah!!!
LINE_RE_FLIPPER_BLE = re.compile(
    r"^(?:>?\s*)?(?:Device:\s*)?"  # optional prefixes: ">" and/or "Device:"
    r"(?:(.*?)(?=(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}))?"  # device_name (optional) right before MAC
    r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})"  # MAC
    r"(?:(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})?"  # duplicated MAC glued back-to-back (optional)
    r",\s*"
    r"([^,]*),\s*"  # extra field (often empty in your sample)
    r"\[([^\]]*)\],\s*"  # auth_mode (e.g., BLE)
    r"(\d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}:\d{2}),\s*"  # timestamp
    r"(\d+),\s*"  # channel (usually 0 for BLE)
    r"(-?\d+),\s*"  # rssi
    r"(-?\d+(?:\.\d+)?),\s*"  # lat
    r"(-?\d+(?:\.\d+)?),\s*"  # lon
    r"(-?\d+(?:\.\d+)?),\s*"  # alt
    r"(-?\d+(?:\.\d+)?),\s*"  # acc
    r"(BLE)$"  # Technology
)

# -----------------------------
# Helpers
# -----------------------------

_SKIP_CONTAINS = (
    "stopscan",
    "Starting Wardrive",
    "Starting Continuous BT Wardrive",
    "Started BLE Scan",
    "wifi:can not get wifi protocol",
)


def _should_skip_marauder_line(line: str) -> bool:
    """Return True if the line is metadata/noise and should not be parsed."""
    if not line:
        return True
    s = line.strip()
    if not s or s.startswith("#"):
        return True
    return any(x in s for x in _SKIP_CONTAINS)


def _parse_dt_aware(s: str):
    """Parse 'YYYY-MM-DD HH:MM:SS' into a timezone-aware datetime; return None on failure."""
    if not s:
        return None
    try:
        return make_aware(datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return None


def _to_int(s: str):
    """Convert string to int; return None when empty/invalid."""
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    try:
        return int(s)
    except Exception:
        return None


def _to_dec(s: str):
    """Convert string to Decimal; return None when empty/invalid."""
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


# -----------------------------
# Parsers (always return the same 11-field tuple)
# (mac, ssid_or_name, auth_mode, first_seen, channel, rssi, lat, lon, alt, acc, data_type)
# -----------------------------


def _parse_marauder_wifi_line(line: str):
    """Parse a Marauder WiFi line; return tuple or None."""
    if _should_skip_marauder_line(line):
        return None
    m = LINE_RE_FLIPPER_WIFI.match(line.strip())
    if not m:
        return None
    return m.groups()


def _parse_marauder_ble_line(line: str):
    """Parse a Marauder BLE line; return normalized tuple or None."""
    if _should_skip_marauder_line(line):
        return None
    m = LINE_RE_FLIPPER_BLE.match(line.strip())
    if not m:
        return None
    # groups: (device_name, mac, extra, auth_mode, first_seen, channel, rssi, lat, lon, alt, acc, data_type)
    (
        device_name,
        mac,
        _extra,
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

    # Normalize to the common tuple (use device_name as "ssid" field downstream)
    ssid_or_name = (device_name or "").strip() or None
    return (
        mac,
        ssid_or_name,
        auth_mode,
        first_seen,
        channel,
        rssi,
        lat,
        lon,
        alt,
        acc,
        data_type,
    )


# -----------------------------
# Core processor (single source of truth)
# -----------------------------


def _process_format_flipper_marauder_core(
    lines,
    parser_fn,
    device_source,
    uploaded_by,
):
    """
    Core processing loop:
    - Parse each line via parser_fn
    - Normalize types (datetime/int/Decimal)
    - Apply minimal validation rules
    - Bulk upsert into Wardriving
    """
    rows = []

    for line in lines:
        g = parser_fn(line)
        if not g:
            continue

        (
            mac,
            ssid_or_name,
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

        mac = (mac or "").strip().lower() or None
        ssid_or_name = (ssid_or_name or "").strip() or None
        auth_mode = (auth_mode or "").strip() or None
        data_type = (data_type or "").strip() or None

        first_seen = _parse_dt_aware(first_seen)

        channel = _to_int(channel)
        rssi = _to_int(rssi)
        lat = _to_dec(lat)
        lon = _to_dec(lon)
        alt = _to_dec(alt)
        acc = _to_dec(acc)

        # Minimal validation rules (adjust if you want to accept edge cases)
        if mac is None:
            continue
        if channel is None:
            continue
        if lat is None or lon is None:
            continue
        if lat == 0 and lon == 0:
            continue

        row = {
            "uploaded_by": uploaded_by,
            "mac": mac,
            "channel": channel,
            "ssid": ssid_or_name,  # For BLE we store device_name here to reuse the same model
            "auth_mode": auth_mode,
            "first_seen": first_seen,
            "current_latitude": lat,
            "current_longitude": lon,
            "altitude_meters": alt,
            "accuracy_meters": acc,
            "type": data_type,  # WIFI or BLE
            "rssi": rssi,
            "device_source": device_source,
        }

        # Remove None values so we don't overwrite existing DB fields with nulls
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
# Public APIs by technology (thin wrappers pointing to the core)
# -----------------------------


def process_format_flipper_marauder_wifi(
    lines=list(),
    device_source=SourceDevice.FLIPPER_DEV_BOARD,
    uploaded_by="Without Owner",
):
    """Process Marauder Flipper-format WiFi lines."""
    return _process_format_flipper_marauder_core(
        lines=lines,
        parser_fn=_parse_marauder_wifi_line,
        device_source=device_source,
        uploaded_by=uploaded_by,
    )


def process_format_flipper_marauder_ble(
    lines=list(),
    device_source=SourceDevice.FLIPPER_DEV_BOARD,
    uploaded_by="Without Owner",
):
    """Process Marauder Flipper-format BLE lines."""
    return _process_format_flipper_marauder_core(
        lines=lines,
        parser_fn=_parse_marauder_ble_line,
        device_source=device_source,
        uploaded_by=uploaded_by,
    )


# Process some files with structure from project Marauder ESP32 in flipper format (has an index for follow the wardrive)
# Source to project firmware: https://github.com/justcallmekoko/ESP32Marauder/
def process_format_flipper_marauder(
    lines=list(),
    device_source=SourceDevice.FLIPPER_DEV_BOARD,
    uploaded_by="Without Owner",
):
    """
    Process mixed Marauder output (BLE + WiFi).
    Tries BLE first (many BLE lines do not have the numeric index), then WiFi.
    """

    def _auto_parser(line: str):
        return _parse_marauder_ble_line(line) or _parse_marauder_wifi_line(line)

    return _process_format_flipper_marauder_core(
        lines=lines,
        parser_fn=_auto_parser,
        device_source=device_source,
        uploaded_by=uploaded_by,
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
            r"(\d{4}-\d{1,2}-\d{1,2} \d{2}:\d{2}:\d{2}),\s*"  # timestamp
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
        df = read_csv(file_path, encoding="utf-8", skiprows=1, on_bad_lines="skip")
    except UnicodeDecodeError:
        df = read_csv(file_path, encoding="latin-1", skiprows=1, on_bad_lines="skip")

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
        if isna(first_seen):
            first_seen = None
        # pandas Timestamp -> datetime
        elif hasattr(first_seen, "to_pydatetime"):
            first_seen = first_seen.to_pydatetime()
            if is_naive(first_seen):
                first_seen = make_aware(first_seen)

        # datetime normal
        elif isinstance(first_seen, datetime):
            if is_naive(first_seen):
                first_seen = make_aware(first_seen)

        rssi_val = int(row["rssi"]) if "rssi" in row and notna(row["rssi"]) else None

        payload = {
            "uploaded_by": uploaded_by,
            "mac": mac,
            "channel": int(channel),
            "ssid": (row.get("ssid") or None),
            "auth_mode": (row.get("auth_mode") or None),
            "first_seen": first_seen,
            "current_latitude": (
                Decimal(row["current_latitude"])
                if notna(row.get("current_latitude"))
                else None
            ),
            "current_longitude": (
                Decimal(row["current_longitude"])
                if notna(row.get("current_longitude"))
                else None
            ),
            "altitude_meters": (
                Decimal(row["altitude_meters"])
                if notna(row.get("altitude_meters"))
                else None
            ),
            "accuracy_meters": (
                Decimal(row["accuracy_meters"])
                if notna(row.get("accuracy_meters"))
                else None
            ),
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
    SourceDevice.KISMET: process_file_marauder_esp32,
    SourceDevice.WARDRIVER_UK: process_file_marauder_esp32,
    SourceDevice.OTHER: None,
}
