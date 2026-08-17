from rtk_gps_bridge import parse_nmea_line, fix_type_from_quality, build_gps_input_kwargs


def test_gga_rtk_fixed():
    r = parse_nmea_line("$GNGGA,143735.000,3942.306636,N,08559.601851,W,4,19,0.77,271.763,M,-33.633,M,,*47")
    assert r["kind"] == "GGA"
    assert abs(r["lat"] - 39.705111) < 1e-5
    assert abs(r["lon"] - (-85.993364)) < 1e-5
    assert r["quality"] == 4 and r["sats"] == 19
    assert abs(r["hdop"] - 0.77) < 1e-6 and abs(r["alt"] - 271.763) < 1e-3


def test_rmc_velocity():
    r = parse_nmea_line("$GNRMC,143735.000,A,3942.306636,N,08559.601851,W,1.20,90.0,170826,,,A*XX")
    assert r["kind"] == "RMC"
    assert abs(r["sog_mps"] - 1.20 * 0.514444) < 1e-3 and abs(r["cog_deg"] - 90.0) < 1e-6


def test_garbage_returns_none():
    assert parse_nmea_line("not a sentence") is None
    assert parse_nmea_line("$GNGSV,3,1,11,...") is None


def test_fix_mapping():
    assert fix_type_from_quality(0) == 0
    assert fix_type_from_quality(1) == 3
    assert fix_type_from_quality(2) == 4
    assert fix_type_from_quality(5) == 5
    assert fix_type_from_quality(4) == 6


def test_gps_input_kwargs():
    fix = {"lat": 39.705111, "lon": -85.993364, "alt": 271.763, "quality": 4, "sats": 19, "hdop": 0.77,
           "vdop": 1.1, "vn": 1.0, "ve": 0.0, "vd": 0.0, "h_acc": 0.02, "v_acc": 0.03, "s_acc": 0.1}
    k = build_gps_input_kwargs(fix)
    assert k["lat"] == int(39.705111 * 1e7) and k["lon"] == int(-85.993364 * 1e7)
    assert k["fix_type"] == 6 and k["satellites_visible"] == 19
    assert abs(k["alt"] - 271.763) < 1e-3
    IGN_VEL_HORIZ = 8
    assert (k["ignore_flags"] & IGN_VEL_HORIZ) == 0
