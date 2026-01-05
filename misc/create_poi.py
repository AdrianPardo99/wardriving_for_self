import re
import simplekml
from xml.sax.saxutils import escape


# KML uses AABBGGRR
NAMED_KML_COLORS = {
    "red": "ff0000ff",
    "green": "ff00ff00",
    "blue": "ffff0000",
    "yellow": "ff00ffff",
    "cyan": "ffffff00",
    "magenta": "ffff00ff",
    "white": "ffffffff",
    "black": "ff000000",
    "orange": "ff00a5ff",
    "purple": "ff800080",
}


def to_kml_color(color: str) -> str:
    c = (color or "").strip().lower()
    if not c:
        return NAMED_KML_COLORS["red"]

    if c in NAMED_KML_COLORS:
        return NAMED_KML_COLORS[c]

    # Already KML AABBGGRR
    if re.fullmatch(r"[0-9a-f]{8}", c):
        return c

    # RGB #RRGGBB or RRGGBB -> convert to AABBGGRR with alpha ff
    m = re.fullmatch(r"#?([0-9a-f]{6})", c)
    if m:
        rrggbb = m.group(1)
        rr, gg, bb = rrggbb[0:2], rrggbb[2:4], rrggbb[4:6]
        return f"ff{bb}{gg}{rr}"

    raise ValueError(
        f"Unsupported color '{color}'. Use name (red/green/...), RGB hex (#RRGGBB) or KML hex (AABBGGRR)."
    )


def parse_extra_data_from_description(description: str) -> dict:
    """
    Tries to extract structured info from your description format.

    Example formats supported:
      (Belkin International Inc.) - C4:41:1E:E7:A2:10
      WIFI / 2 / -91 / Weak
      WPA_WPA2_PSK / 20/10/2025

    Or template-like:
      (vendor) - bssid
      type / accuracy_meters / rssi / signal_streng
      auth_mode / first_seen
    """
    extra = {}
    if not description:
        return extra

    lines = [ln.strip() for ln in description.splitlines() if ln.strip()]
    if not lines:
        return extra

    # Line 1: "(Vendor Name) - BSSID"
    # Also accept "(vendor) - bssid" template
    m = re.match(r"^\((?P<vendor>.*)\)\s*-\s*(?P<bssid>.*)$", lines[0])
    if m:
        vendor = m.group("vendor").strip()
        bssid = m.group("bssid").strip()
        if vendor and vendor.lower() != "vendor":
            extra["vendor"] = vendor
        if bssid and bssid.lower() != "bssid":
            extra["bssid"] = bssid
        lines = lines[1:]

    # Remaining lines: either data rows or templates "a / b / c"
    # We'll map known patterns by position:
    #   line like: "WIFI / 2 / -91 / Weak" -> type, accuracy_meters, rssi, signal_strength
    #   line like: "WPA_WPA2_PSK / 20/10/2025" -> auth_mode, first_seen
    # If it's template text (words like 'type', 'rssi', etc.), we ignore values but keep nothing.
    for ln in lines:
        parts = [p.strip() for p in ln.split("/")]

        # Skip if it's clearly a header/template row (contains non-value markers)
        # (Heuristic: if all parts are alphabetic-ish or contain underscores and no digits)
        if all(not re.search(r"\d", p) for p in parts) and any(
            p.lower()
            in {
                "type",
                "accuracy_meters",
                "rssi",
                "signal_streng",
                "signal_strength",
                "auth_mode",
                "first_seen",
            }
            for p in parts
        ):
            continue

        if len(parts) == 4:
            # type / accuracy_meters / rssi / signal_strength
            extra.setdefault("type", parts[0])
            extra.setdefault("accuracy_meters", parts[1])
            extra.setdefault("rssi", parts[2])
            # keep your original label too
            extra.setdefault("signal_strength", parts[3])
        elif len(parts) == 2:
            # auth_mode / first_seen
            extra.setdefault("auth_mode", parts[0])
            extra.setdefault("first_seen", parts[1])
        else:
            # Fallback: store the raw line
            extra.setdefault("notes", [])
            extra["notes"].append(ln)

    # Normalize notes list into a string if present
    if "notes" in extra and isinstance(extra["notes"], list):
        extra["notes"] = " | ".join(extra["notes"])

    return extra


def build_description_html(original_description: str, extra_data: dict) -> str:
    """
    Builds an HTML description that includes the original description plus a table of extra_data.
    This is useful because some viewers show description more reliably than ExtendedData.
    """
    original = escape(original_description or "").replace("\n", "<br/>")
    rows = ""
    for k, v in (extra_data or {}).items():
        rows += f"<tr><td><b>{escape(str(k))}</b></td><td>{escape(str(v))}</td></tr>"

    table = ""
    if rows:
        table = (
            "<br/><br/>"
            "<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;'>"
            f"{rows}"
            "</table>"
        )

    return f"<![CDATA[<div style='font-family:Arial;font-size:13px;'>{original}{table}</div>]]>"


def create_kml_with_pin(
    filename, pois=None, default_pin_color="red", include_html_table=True
):
    """
    Creates a KML file with placemarks (pins), color, description, and extra_data extracted from description.

    pois item format (dict):
      {
        "name": "...",
        "latitude": 19.48,
        "longitude": -99.08,
        "description": "...",
        "pin_color": "magenta" | "#RRGGBB" | "AABBGGRR",
        "extra_data": { ... }  # optional; will be merged with parsed extra
      }
    """
    pois = pois or []
    kml = simplekml.Kml()

    # Base icon (Google pin)
    icon_href = "https://raw.githubusercontent.com/AdrianPardo99/flipper_zero_anims_assets/refs/heads/hide/Ultra-hide-branch/misc_icons/kml_icon-v2_wo_back.png"

    for poi in pois:
        name = poi.get("name", "")
        longitude = float(poi.get("longitude", 0.0))
        latitude = float(poi.get("latitude", 0.0))
        description = poi.get("description", "")

        pin_color = poi.get("pin_color", default_pin_color)
        kml_color = to_kml_color(pin_color)

        # Parse extra from description, then merge with provided extra_data (provided wins)
        parsed_extra = parse_extra_data_from_description(description)
        provided_extra = poi.get("extra_data") or {}
        extra_data = {**parsed_extra, **provided_extra}

        pnt = kml.newpoint(name=name, coords=[(longitude, latitude)])

        # Put description (optionally with HTML table)
        if include_html_table:
            pnt.description = build_description_html(description, extra_data)
        else:
            pnt.description = description

        # Add ExtendedData
        # simplekml supports extendeddata via ExtendedData/Data objects.
        if extra_data:
            ext = simplekml.ExtendedData()
            for k, v in extra_data.items():
                ext.newdata(name=str(k), value=str(v))
            pnt.extendeddata = ext

        # Style: icon + color tint
        pnt.style.iconstyle.icon.href = icon_href
        pnt.style.iconstyle.color = kml_color
        pnt.style.iconstyle.scale = 1.1

    kml.save(filename)
    print(f"Created KML file: {filename}")


# Example Usage (your same input + optional pin_color)
create_kml_with_pin(
    "misc_create_poi.kml",
    [
        {
            "name": "ssid",
            "latitude": 19.489286,
            "longitude": -99.083252,
            "description": "(vendor) - bssid\ntype / accuracy_meters / rssi / signal_streng\nauth_mode / first_seen",
            "pin_color": "cyan",
        },
        {
            "name": "Test Estamos en Tepoz we",
            "latitude": 19.713787,
            "longitude": -99.200630,
            "description": "(Belkin International Inc.) - C4:41:1E:E7:A2:10\nWIFI / 2 / -91 / Weak\nWPA_WPA2_PSK / 20/10/2025",
            "pin_color": "red",  # RGB hex
            # You can also inject/override:
            "extra_data": {
                "uploaded_by": "example_user",
                "device_source": "Flipper Zero",
            },
        },
    ],
)
