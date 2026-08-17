#!/usr/bin/env python3
# Idempotent ArduPilot param setter for the MAVLink-injected RTK GPS + EKF source.
# Connects through the mavlink-router spare endpoint (Server on :14552 -> connect via udpout).
import sys, time
from pymavlink import mavutil

WANT = {"GPS1_TYPE": 14,         # GPS1 = MAVLink (the injected RTK). Rover 4.7 renamed GPS_TYPE -> GPS1_TYPE.
        "GPS_AUTO_SWITCH": 1,
        "EK3_SRC1_POSXY": 3,     # 3 = GPS
        "EK3_SRC1_VELXY": 3,
        "EK3_SRC1_POSZ": 3}

m = mavutil.mavlink_connection("udpout:127.0.0.1:14552")
m.mav.heartbeat_send(6, 8, 0, 0, 0)   # announce so the router learns our address
m.wait_heartbeat(timeout=10)


def rd(name):
    m.mav.param_request_read_send(m.target_system, m.target_component, name.encode(), -1)
    t = time.time()
    while time.time() - t < 4:
        r = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=2)
        if r and r.param_id.strip(chr(0)) == name:
            return round(r.param_value, 3)
    return None


ok = True
for name, val in WANT.items():
    m.mav.param_set_send(m.target_system, m.target_component, name.encode(),
                         float(val), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    time.sleep(0.5)
    got = rd(name)
    good = (got == val)
    print(name, "=", got, "OK" if good else "MISMATCH")
    ok = ok and good

sys.exit(0 if ok else 1)
