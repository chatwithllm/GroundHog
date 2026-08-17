# RTK GPS Bridge (Autonomy Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ArduRover on the F405 sees centimeter RTK position (injected from the Pi as `GPS_INPUT`) and a healthy calibrated compass heading (HGLRC M100-5883), with the EKF happy — verified in Mission Planner over WiFi.

**Architecture:** A MAVLink router on the Pi owns the F405 USB link and fans it to UDP endpoints. A Python bridge tails the existing RTK NMEA log (never opening the serial the relay owns), parses it, and streams `GPS_INPUT` to the F405 through the router. The M100-5883 wired to the F405 supplies compass heading + a backup GPS.

**Tech Stack:** Python 3 (pymavlink), mavlink-router (C), systemd, ArduPilot Rover 4.7, Raspberry Pi 4 / Debian 13 (aarch64). Deploy target: `npalakurla@rtk`.

## Global Constraints

- **Never open `/dev/serial0`** — the RTK relay is its sole owner; the bridge is **read-only via `/var/log/rtk/live-nmea.log`**. (Opening the port drops the LC29H out of RTK.)
- **`mavlink-router` is the sole owner of `/dev/ttyACM0`** — no other process opens the F405 serial directly.
- Services run under **systemd** (`Restart=always`); Python uses the existing venv `/home/npalakurla/rsvenv` (has pymavlink) or system python3 (also has pymavlink).
- **Bench-safe:** phase A is sensors only — no autonomous motion, no arming required.
- Repo source lives under `pi/`; deployment copies to Pi paths (`/usr/local/bin`, `/etc/systemd/system`, `/etc/mavlink-router`).
- Pure-logic functions must be importable + unit-tested with **no hardware and no pymavlink** dependency (parsing + field-mapping return plain values/dicts).

---

## File Structure

- `pi/rtk_gps_bridge.py` — the bridge. Pure functions `parse_nmea_line()`, `merge_fix()`, `fix_type_from_quality()`, `build_gps_input_kwargs()` (no deps) + `main()` loop (tails log, sends via pymavlink).
- `pi/test_rtk_gps_bridge.py` — pytest for the pure functions.
- `pi/mavlink-router.conf` — router config (UART master + 3 UDP endpoints).
- `pi/systemd/mavlink-router.service` — router unit.
- `pi/systemd/rtk-gps-bridge.service` — bridge unit.
- `pi/set_ardupilot_gps.py` — one-shot param setter (idempotent) for GPS/EKF/compass params, run through the router.
- `pi/README.md` — deploy + verify steps.

---

### Task 1: MAVLink router — install, configure, share the F405 link

**Files:**
- Create: `pi/mavlink-router.conf`
- Create: `pi/systemd/mavlink-router.service`
- Test: manual verification (heartbeat on a UDP endpoint)

**Interfaces:**
- Produces: F405 MAVLink reachable at `udp:127.0.0.1:14551` (bridge), `udp:127.0.0.1:14552` (future), `udp:0.0.0.0:14550` (GCS/WiFi).

- [ ] **Step 1: Write the router config**

`pi/mavlink-router.conf`:
```ini
[General]
TcpServerPort=0
ReportStats=false

[UartEndpoint f405]
Device=/dev/ttyACM0
Baud=115200

[UdpEndpoint gcs]
Mode=Server
Address=0.0.0.0
Port=14550

[UdpEndpoint bridge]
Mode=Server
Address=127.0.0.1
Port=14551

[UdpEndpoint spare]
Mode=Server
Address=127.0.0.1
Port=14552
```

- [ ] **Step 2: Install mavlink-router on the Pi**

Try apt first, else build from source:
```bash
ssh npalakurla@rtk 'sudo apt-get install -y mavlink-router 2>/dev/null || echo "not in apt — build from source"'
```
If not in apt, build:
```bash
ssh npalakurla@rtk 'sudo apt-get install -y git meson ninja-build pkg-config g++ libsystemd-dev &&
  git clone --recurse-submodules https://github.com/mavlink-router/mavlink-router.git ~/mavlink-router-src &&
  cd ~/mavlink-router-src && meson setup build . && ninja -C build && sudo ninja -C build install'
```

- [ ] **Step 3: Deploy config + systemd unit**

`pi/systemd/mavlink-router.service`:
```ini
[Unit]
Description=MAVLink router (F405 <-> UDP)
After=network.target
[Service]
ExecStart=/usr/bin/mavlink-routerd -c /etc/mavlink-router/main.conf
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
```
```bash
ssh npalakurla@rtk 'sudo mkdir -p /etc/mavlink-router && sudo cp /tmp/mavlink-router.conf /etc/mavlink-router/main.conf &&
  sudo cp /tmp/mavlink-router.service /etc/systemd/system/ && sudo systemctl daemon-reload &&
  sudo systemctl enable --now mavlink-router'
```

- [ ] **Step 4: Verify the shared link (heartbeat on UDP)**

Run: on the Pi, connect a throwaway client to the bridge endpoint and confirm a heartbeat comes through the router.
```bash
ssh npalakurla@rtk '/home/npalakurla/rsvenv/bin/python -c "
from pymavlink import mavutil
m=mavutil.mavlink_connection(\"udpin:127.0.0.1:14552\")   # spare endpoint
hb=m.wait_heartbeat(timeout=10)
print(\"HEARTBEAT via router:\", hb.type if hb else \"NONE\")"'
```
Expected: `HEARTBEAT via router: 10` (rover). Confirms the router owns the serial and fans it out.

- [ ] **Step 5: Commit**
```bash
git add pi/mavlink-router.conf pi/systemd/mavlink-router.service
git commit -m "feat(nav): MAVLink router config + service (shares F405 link)"
```

---

### Task 2: NMEA parsing (pure logic, TDD)

**Files:**
- Create: `pi/rtk_gps_bridge.py` (parsing functions only this task)
- Test: `pi/test_rtk_gps_bridge.py`

**Interfaces:**
- Produces: `parse_nmea_line(line: str) -> dict | None` returning typed fields keyed by sentence (`{"kind":"GGA","lat":..,"lon":..,"quality":int,"sats":int,"hdop":float,"alt":float}`, or `RMC` with `sog_mps`,`cog_deg`, or `GST` with `lat_acc`,`lon_acc`,`alt_acc`). Returns `None` for non-matching/garbage lines.

- [ ] **Step 1: Write the failing test**

`pi/test_rtk_gps_bridge.py`:
```python
from rtk_gps_bridge import parse_nmea_line

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi && python3 -m pytest test_rtk_gps_bridge.py -q`
Expected: FAIL (`ImportError`/`parse_nmea_line` undefined).

- [ ] **Step 3: Implement the parser**

In `pi/rtk_gps_bridge.py`:
```python
def _dm_to_deg(dm, hemi):
    if not dm: return None
    dot = dm.find(".")
    deg = int(dm[:dot-2]); minutes = float(dm[dot-2:])
    val = deg + minutes/60.0
    return -val if hemi in ("S","W") else val

def parse_nmea_line(line):
    line = line.strip()
    if not line.startswith("$") or "," not in line: return None
    body = line.split("*")[0]; f = body.split(",")
    typ = f[0][3:] if len(f[0]) >= 6 else ""
    try:
        if typ == "GGA":
            return {"kind":"GGA","lat":_dm_to_deg(f[2],f[3]),"lon":_dm_to_deg(f[4],f[5]),
                    "quality":int(f[6] or 0),"sats":int(f[7] or 0),
                    "hdop":float(f[8] or 0),"alt":float(f[9] or 0)}
        if typ == "RMC":
            return {"kind":"RMC","sog_mps":float(f[7] or 0)*0.514444,"cog_deg":float(f[8] or 0)}
        if typ == "GST":
            return {"kind":"GST","lat_acc":float(f[6] or 0),"lon_acc":float(f[7] or 0),"alt_acc":float(f[8] or 0)}
    except (ValueError, IndexError):
        return None
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi && python3 -m pytest test_rtk_gps_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add pi/rtk_gps_bridge.py pi/test_rtk_gps_bridge.py
git commit -m "feat(nav): NMEA GGA/RMC/GST parser for RTK GPS bridge (TDD)"
```

---

### Task 3: Fix-type mapping + GPS_INPUT kwargs (pure logic, TDD)

**Files:**
- Modify: `pi/rtk_gps_bridge.py`
- Test: `pi/test_rtk_gps_bridge.py`

**Interfaces:**
- Consumes: parsed dicts from Task 2.
- Produces: `fix_type_from_quality(q:int)->int` and `build_gps_input_kwargs(fix:dict)->dict` (field values for `gps_input_send`, including `ignore_flags` for absent fields). No pymavlink import.

- [ ] **Step 1: Write the failing test**

Append to `pi/test_rtk_gps_bridge.py`:
```python
from rtk_gps_bridge import fix_type_from_quality, build_gps_input_kwargs

def test_fix_mapping():
    # NMEA GGA quality -> MAVLink GPS_FIX_TYPE
    assert fix_type_from_quality(0) == 0   # no fix
    assert fix_type_from_quality(1) == 3   # 3D
    assert fix_type_from_quality(2) == 4   # DGPS
    assert fix_type_from_quality(5) == 5   # RTK float
    assert fix_type_from_quality(4) == 6   # RTK fixed

def test_gps_input_kwargs():
    fix = {"lat":39.705111,"lon":-85.993364,"alt":271.763,"quality":4,"sats":19,"hdop":0.77,
           "vdop":1.1,"vn":1.0,"ve":0.0,"vd":0.0,"h_acc":0.02,"v_acc":0.03,"s_acc":0.1}
    k = build_gps_input_kwargs(fix)
    assert k["lat"] == int(39.705111*1e7) and k["lon"] == int(-85.993364*1e7)
    assert k["fix_type"] == 6 and k["satellites_visible"] == 19
    assert abs(k["alt"] - 271.763) < 1e-3
    # velocity + accuracy provided -> those ignore bits are NOT set
    IGN_VEL_HORIZ = 8
    assert (k["ignore_flags"] & IGN_VEL_HORIZ) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd pi && python3 -m pytest test_rtk_gps_bridge.py -q`
Expected: FAIL (functions undefined).

- [ ] **Step 3: Implement mapping + builder**

In `pi/rtk_gps_bridge.py`:
```python
def fix_type_from_quality(q):
    return {0:0, 1:3, 2:4, 4:6, 5:5, 6:6}.get(int(q), 3)

# GPS_INPUT_IGNORE_FLAGS bits
_IGN = {"alt":1,"hdop":2,"vdop":4,"vel_horiz":8,"vel_vert":16,"speed_accuracy":32,
        "horizontal_accuracy":64,"vertical_accuracy":128}

def build_gps_input_kwargs(fix):
    ign = 0
    def have(k): return fix.get(k) is not None
    for key,bit in (("vn","vel_horiz"),("vd","vel_vert"),("s_acc","speed_accuracy"),
                    ("h_acc","horizontal_accuracy"),("v_acc","vertical_accuracy"),
                    ("vdop","vdop")):
        if not have(key): ign |= _IGN[bit]
    return dict(
        time_usec=0, gps_id=0, ignore_flags=ign, time_week_ms=0, time_week=0,
        fix_type=fix_type_from_quality(fix.get("quality",0)),
        lat=int(round(fix["lat"]*1e7)), lon=int(round(fix["lon"]*1e7)),
        alt=float(fix.get("alt",0.0)),
        hdop=float(fix.get("hdop",0.0)), vdop=float(fix.get("vdop",0.0)),
        vn=float(fix.get("vn",0.0)), ve=float(fix.get("ve",0.0)), vd=float(fix.get("vd",0.0)),
        speed_accuracy=float(fix.get("s_acc",0.0)),
        horiz_accuracy=float(fix.get("h_acc",0.0)), vert_accuracy=float(fix.get("v_acc",0.0)),
        satellites_visible=int(fix.get("sats",0)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd pi && python3 -m pytest test_rtk_gps_bridge.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add pi/rtk_gps_bridge.py pi/test_rtk_gps_bridge.py
git commit -m "feat(nav): fix-type mapping + GPS_INPUT builder (TDD)"
```

---

### Task 4: Bridge main loop — tail log, assemble, send; deploy + verify injection

**Files:**
- Modify: `pi/rtk_gps_bridge.py` (add `main()`)
- Create: `pi/systemd/rtk-gps-bridge.service`

**Interfaces:**
- Consumes: Task 2/3 functions; the router at `udp:127.0.0.1:14551`.
- Produces: `GPS_INPUT` streamed to the F405. Verifiable via `GPS_RAW_INT` from the FC.

- [ ] **Step 1: Implement `main()` (tail + assemble + send)**

In `pi/rtk_gps_bridge.py`:
```python
def main():
    import time
    from pymavlink import mavutil
    LOG = "/var/log/rtk/live-nmea.log"
    m = mavutil.mavlink_connection("udpout:127.0.0.1:14551", source_system=1)
    fix = {}
    f = open(LOG, "r", errors="replace"); f.seek(0, 2)   # seek to end
    while True:
        line = f.readline()
        if not line:
            time.sleep(0.05); continue
        r = parse_nmea_line(line)
        if not r: continue
        if r["kind"] == "RMC":
            cog = r["cog_deg"] * 3.14159265/180.0
            fix["vn"] = r["sog_mps"]*__import__("math").cos(cog)
            fix["ve"] = r["sog_mps"]*__import__("math").sin(cog); fix["vd"] = 0.0
        elif r["kind"] == "GST":
            fix["h_acc"] = max(r["lat_acc"], r["lon_acc"]); fix["v_acc"] = r["alt_acc"]
        elif r["kind"] == "GGA":
            fix.update({k:r[k] for k in ("lat","lon","alt","quality","sats","hdop")})
            if fix.get("lat") is not None:
                m.mav.gps_input_send(**build_gps_input_kwargs(fix))

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Deploy the script + systemd unit**

`pi/systemd/rtk-gps-bridge.service`:
```ini
[Unit]
Description=RTK GPS bridge (NMEA log -> GPS_INPUT -> router)
After=rtk-port-relay.service mavlink-router.service
Wants=rtk-port-relay.service
[Service]
ExecStart=/home/npalakurla/rsvenv/bin/python /usr/local/bin/rtk_gps_bridge.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
```
```bash
scp pi/rtk_gps_bridge.py npalakurla@rtk:/tmp/ && scp pi/systemd/rtk-gps-bridge.service npalakurla@rtk:/tmp/
ssh npalakurla@rtk 'sudo cp /tmp/rtk_gps_bridge.py /usr/local/bin/ && sudo cp /tmp/rtk-gps-bridge.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload && sudo systemctl enable --now rtk-gps-bridge && sleep 3 && systemctl is-active rtk-gps-bridge'
```
Expected: `active`.

- [ ] **Step 3: Verify the F405 received the injected position**

Run: connect to the spare endpoint, read `GPS_RAW_INT`, confirm lat/lon match the LC29H log and `fix_type` maps.
```bash
ssh npalakurla@rtk '/home/npalakurla/rsvenv/bin/python -c "
from pymavlink import mavutil
m=mavutil.mavlink_connection(\"udpin:127.0.0.1:14552\"); m.wait_heartbeat(timeout=10)
g=m.recv_match(type=\"GPS_RAW_INT\",blocking=True,timeout=10)
print(\"fix_type\",g.fix_type,\"lat\",g.lat/1e7,\"lon\",g.lon/1e7,\"sats\",g.satellites_visible)"'
```
Expected: `fix_type` ≥ 3, lat/lon matching the current LC29H position (≈39.705, -85.993), sats > 0.

- [ ] **Step 4: Commit**
```bash
git add pi/rtk_gps_bridge.py pi/systemd/rtk-gps-bridge.service
git commit -m "feat(nav): bridge main loop + service; inject GPS_INPUT to F405"
```

---

### Task 5: ArduPilot params — accept the injected RTK as GPS1

**Files:**
- Create: `pi/set_ardupilot_gps.py`

**Interfaces:**
- Consumes: router endpoint (`udp:127.0.0.1:14552`).
- Produces: `GPS_TYPE=14`; EKF configured to use GPS position.

- [ ] **Step 1: Write the idempotent param setter (with readback)**

`pi/set_ardupilot_gps.py`:
```python
import sys, time
from pymavlink import mavutil
WANT = {"GPS_TYPE":14, "GPS_AUTO_SWITCH":1, "EK3_SRC1_POSXY":3, "EK3_SRC1_VELXY":3,
        "EK3_SRC1_POSZ":3}   # 3 = GPS
m = mavutil.mavlink_connection("udpin:127.0.0.1:14552"); m.wait_heartbeat(timeout=10)
def rd(n):
    m.mav.param_request_read_send(m.target_system,m.target_component,n.encode(),-1)
    t=time.time()
    while time.time()-t<4:
        r=m.recv_match(type="PARAM_VALUE",blocking=True,timeout=2)
        if r and r.param_id.strip(chr(0))==n: return r.param_value
    return None
ok=True
for n,v in WANT.items():
    m.mav.param_set_send(m.target_system,m.target_component,n.encode(),float(v),
                         mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    time.sleep(0.5); got=rd(n)
    print(n,"=",got,("OK" if got==v else "MISMATCH")); ok = ok and got==v
sys.exit(0 if ok else 1)
```

- [ ] **Step 2: Run it on the Pi**

Run:
```bash
scp pi/set_ardupilot_gps.py npalakurla@rtk:/tmp/ && ssh npalakurla@rtk '/home/npalakurla/rsvenv/bin/python /tmp/set_ardupilot_gps.py'
```
Expected: every param prints `OK`.

- [ ] **Step 3: Verify GPS1 shows the injected RTK data**

Run: read `GPS_RAW_INT` again (Task 4 Step 3). Now with `GPS_TYPE=14`, GPS1 is the MAV source; confirm `fix_type`/position still reflect the LC29H. (Outdoors this becomes fix_type 5/6.)

- [ ] **Step 4: Commit**
```bash
git add pi/set_ardupilot_gps.py
git commit -m "feat(nav): ArduPilot param setter for MAVLink RTK GPS + EKF source"
```

---

### Task 6: M100-5883 — backup GPS + compass heading

**Files:**
- Modify: `pi/set_ardupilot_gps.py` (add GPS2 + compass params) OR `pi/README.md` (wiring)

**Interfaces:**
- Consumes: a free F405 UART (confirm which) + I2C.
- Produces: GPS2 detected; compass healthy + calibrated; EKF yaw = compass.

- [ ] **Step 1: Wire the module (physical — operator)**

Document in `pi/README.md`: M100-5883 → F405 **GPS UART** (TX↔RX), **I2C** (SDA/SCL), **5V/GND**. Mount on a **mast**, elevated, away from motors + 24 V leads. Note the module's forward arrow for `COMPASS_ORIENT`.

- [ ] **Step 2: Set GPS2 + compass params**

Add to `pi/set_ardupilot_gps.py` `WANT` (confirm the free UART first — `SERIAL2` was set to -1 earlier for RCIN; pick the actual GPS UART):
```python
WANT.update({"SERIAL<N>_PROTOCOL":5, "GPS_TYPE2":1, "COMPASS_ENABLE":1, "COMPASS_USE":1})
```
Run it (Task 5 Step 2). Expected: all `OK`.

- [ ] **Step 3: Verify GPS2 detected + compass present**

Run: check for a second GPS + compass health.
```bash
ssh npalakurla@rtk '/home/npalakurla/rsvenv/bin/python -c "
from pymavlink import mavutil
m=mavutil.mavlink_connection(\"udpin:127.0.0.1:14552\"); m.wait_heartbeat(timeout=10)
g2=m.recv_match(type=\"GPS2_RAW\",blocking=True,timeout=8)
print(\"GPS2 fix\", g2.fix_type if g2 else \"none\")
s=m.recv_match(type=\"SYS_STATUS\",blocking=True,timeout=5)
MAG=1<<2
print(\"mag present\", bool(s.onboard_control_sensors_present & MAG), \"healthy\", bool(s.onboard_control_sensors_health & MAG))"'
```
Expected: GPS2 present, mag present + healthy.

- [ ] **Step 4: Compass calibration + CompassMot (operator, via Mission Planner over WiFi 14550)**

Document in `pi/README.md`: in Mission Planner (connect UDP to the Pi:14550) run **Compass calibration** (rotate the rover through all axes), then **CompassMot** (motor-current compensation). Verify offsets sane + no compass error.

- [ ] **Step 5: Verify heading tracks**

Run: read `ATTITUDE.yaw` while rotating the rover by hand; confirm yaw changes correctly and matches physical heading. (Command-line readback or the Mission Planner HUD.)

- [ ] **Step 6: Commit**
```bash
git add pi/set_ardupilot_gps.py pi/README.md
git commit -m "feat(nav): M100-5883 GPS2 + compass params + wiring/cal docs"
```

---

### Task 7: End-to-end acceptance (indoor bench, then outdoor)

**Files:**
- Modify: `pi/README.md` (verification checklist)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Indoor bench acceptance**

Confirm all of: bridge `active`; `GPS_RAW_INT` fix_type ≥ 3 with matching position; compass healthy, heading tracks on rotation; **EKF3 healthy** (`EKF_STATUS_REPORT` flags OK, no "GPS glitch"/"bad AHRS"); Mission Planner (WiFi 14550) shows live position + heading; a second client on 14552 runs simultaneously (no serial contention). Record results in `pi/README.md`.

- [ ] **Step 2: Outdoor acceptance (open sky) — the gate**

Take the rover outside; confirm `GPS_RAW_INT.fix_type` reaches **5 (float) then 6 (fixed)** with cm `h_acc`; heading holds while pushing/driving the rover; EKF stays healthy. This is the phase-A acceptance gate.

- [ ] **Step 3: Commit the verification record**
```bash
git add pi/README.md
git commit -m "docs(nav): phase-A acceptance checklist + results"
```

---

## Self-Review

**Spec coverage:** router (Task 1), GPS bridge + injection (Tasks 2–4), ArduPilot GPS/EKF params (Task 5), M100 GPS2 + compass (Task 6), success criteria/testing (Task 7). All spec components mapped. ✅

**Placeholder scan:** `SERIAL<N>` in Task 6 is an intentional confirm-the-free-UART step (flagged in the spec's open items), not a gap — it resolves during execution by reading the F405 serial assignments. No TBD/TODO in code steps; all test + implementation steps carry real content.

**Type consistency:** `parse_nmea_line` returns dicts consumed by `build_gps_input_kwargs`; `fix` keys (`lat/lon/alt/quality/sats/hdop/vn/ve/vd/h_acc/v_acc/vdop`) are consistent between Task 2 output, Task 3 builder, and Task 4 assembly. `fix_type_from_quality` mapping matches the spec. Router endpoints (14550/14551/14552) consistent across Tasks 1, 4, 5.

**Note on TDD:** the pure logic (parsing, mapping, builder) uses real TDD (Tasks 2–3). The hardware/MAVLink integration (Tasks 1, 4–7) uses observe-the-result verification steps — appropriate since the "assertion" is live FC/telemetry behavior, not a unit under test.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-17-rtk-gps-bridge.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
