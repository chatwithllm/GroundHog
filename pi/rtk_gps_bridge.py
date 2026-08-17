def _dm_to_deg(dm, hemi):
    if not dm:
        return None
    dot = dm.find(".")
    deg = int(dm[:dot - 2]); minutes = float(dm[dot - 2:])
    val = deg + minutes / 60.0
    return -val if hemi in ("S", "W") else val


def parse_nmea_line(line):
    line = line.strip()
    if not line.startswith("$") or "," not in line:
        return None
    body = line.split("*")[0]; f = body.split(",")
    typ = f[0][3:] if len(f[0]) >= 6 else ""
    try:
        if typ == "GGA":
            return {"kind": "GGA", "lat": _dm_to_deg(f[2], f[3]), "lon": _dm_to_deg(f[4], f[5]),
                    "quality": int(f[6] or 0), "sats": int(f[7] or 0),
                    "hdop": float(f[8] or 0), "alt": float(f[9] or 0)}
        if typ == "RMC":
            return {"kind": "RMC", "sog_mps": float(f[7] or 0) * 0.514444, "cog_deg": float(f[8] or 0)}
        if typ == "GST":
            return {"kind": "GST", "lat_acc": float(f[6] or 0), "lon_acc": float(f[7] or 0), "alt_acc": float(f[8] or 0)}
    except (ValueError, IndexError):
        return None
    return None


def fix_type_from_quality(q):
    return {0: 0, 1: 3, 2: 4, 4: 6, 5: 5, 6: 6}.get(int(q), 3)


# GPS_INPUT_IGNORE_FLAGS bits
_IGN = {"alt": 1, "hdop": 2, "vdop": 4, "vel_horiz": 8, "vel_vert": 16, "speed_accuracy": 32,
        "horizontal_accuracy": 64, "vertical_accuracy": 128}


def build_gps_input_kwargs(fix):
    ign = 0

    def have(k):
        return fix.get(k) is not None
    for key, bit in (("vn", "vel_horiz"), ("vd", "vel_vert"), ("s_acc", "speed_accuracy"),
                     ("h_acc", "horizontal_accuracy"), ("v_acc", "vertical_accuracy"),
                     ("vdop", "vdop")):
        if not have(key):
            ign |= _IGN[bit]
    return dict(
        time_usec=0, gps_id=0, ignore_flags=ign, time_week_ms=0, time_week=0,
        fix_type=fix_type_from_quality(fix.get("quality", 0)),
        lat=int(round(fix["lat"] * 1e7)), lon=int(round(fix["lon"] * 1e7)),
        alt=float(fix.get("alt", 0.0)),
        hdop=float(fix.get("hdop", 0.0)), vdop=float(fix.get("vdop", 0.0)),
        vn=float(fix.get("vn", 0.0)), ve=float(fix.get("ve", 0.0)), vd=float(fix.get("vd", 0.0)),
        speed_accuracy=float(fix.get("s_acc", 0.0)),
        horiz_accuracy=float(fix.get("h_acc", 0.0)), vert_accuracy=float(fix.get("v_acc", 0.0)),
        satellites_visible=int(fix.get("sats", 0)))
