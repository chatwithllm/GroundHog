# RTK GPS Bridge (Autonomy Phase A) — Design

**Date:** 2026-08-17
**Status:** Approved (design), pending spec review
**Scope of this spec:** Sub-project **A** only — inject the RTK LC29H fix into ArduRover on the F405 as `GPS_INPUT`, wire the HGLRC M100-5883 for a backup GPS + compass heading, and stand up a MAVLink router on the Pi so multiple clients share the F405 link. Autonomy phases B/C/D are context only (bottom).

## Goal
ArduRover on the F405 sees **centimeter RTK position** (from the Pi) and a **healthy calibrated compass heading** (from the M100-5883), with the EKF happy — verified in Mission Planner over WiFi and via the router. No GPS wire runs from the LC29H to the F405; position arrives over MAVLink.

## Why this is the foundation
Everything downstream (AUTO missions, avoidance, BLE control) needs the F405 to know **where it is** (cm) and **which way it faces**. It also needs **multiple processes to talk to the F405 at once** (GPS bridge now; avoidance + web UI + GCS later) — which one serial port can't do alone. This phase delivers both.

---

## Architecture context (framing — most of this is later phases)

**Layered brain:**
- **Pi** — autonomy: MAVLink router, RTK-GPS bridge, avoidance planner, web UI/GCS access
- **F405** — low-level: motor mixing, attitude/EKF, RC failsafe
- **C6** — motor interface (→ wheels), fed RC-PWM by the F405

**Sensors:**
- **GPS1 (primary, cm):** RTK LC29H (Pi HAT) → Pi → `GPS_INPUT` MAVLink → F405 (`GPS_TYPE=MAV`)
- **GPS2 + heading:** HGLRC **M100-5883** wired to the F405 → **QMC5883L** compass (yaw) + standard-GPS position backup

**Control = ArduPilot flight modes** (the arbitration is free):
| Priority | Mode | Source | Phase |
|---|---|---|---|
| 1 | `AUTO` | RTK waypoint mission + Pi avoidance overlay | B, C |
| 2 | `GUIDED` | Bluetooth (Pi relays BLE → velocity) | D |
| 3 | `MANUAL` | FlySky RC (last resort; RC failsafe always live) | done |

**Autonomy phases:** **A** (this spec) → **B** AUTO waypoint driving → **C** avoidance overlay (depth → GUIDED steer-around → resume AUTO; the FC's proximity/OA is stripped on 1 MB flash, so this lives on the Pi) → **D** mode arbitration + BLE→GUIDED.

---

## Sub-project A — detailed design

### Data flow
```
LC29H (RTK, /dev/serial0)
  → rtk-port-relay.py  →  /var/log/rtk/live-nmea.log   (existing; sole serial owner)
                                     │  (tail, read-only — never opens the port)
                                     ▼
                         rtk-gps-bridge  (new Pi service)
                            parse GGA + RMC + GST → GPS_INPUT (msg 232)
                                     │  UDP 127.0.0.1:14551
                                     ▼
                         mavlink-router  (new Pi service)
                            master = /dev/ttyACM0 (F405 USB)
                            ├─ UDP 0.0.0.0:14550  → GCS (Mission Planner over WiFi)
                            ├─ UDP 127.0.0.1:14551 → rtk-gps-bridge (in)
                            └─ UDP 127.0.0.1:14552 → future (avoidance / web UI)
                                     ▼
                              F405 / ArduRover
                        GPS1 = MAV (RTK cm) · GPS2 = M100 · compass = QMC5883L
```

### Component 1 — MAVLink router (`mavlink-router`)
- Single owner of `/dev/ttyACM0`; fans the F405 link out to UDP endpoints so the GPS bridge, a WiFi GCS, and later the avoidance/UI all share it. Solves the "one process per serial port" limit that blocked the earlier direct approach.
- Install: `mavlink-router` (build from source or apt if available on trixie); config file lists the UART master + the three UDP endpoints above. Run as a **systemd** service (`Restart=always`).
- Baud: match the F405 USB (CDC ACM ignores baud, but set 115200 for the config).

### Component 2 — RTK GPS bridge (`rtk-gps-bridge`, new)
- **Input:** tails `/var/log/rtk/live-nmea.log` (seek to end, follow new lines). **Read-only, non-invasive** — does NOT touch `/dev/serial0` (the relay is its sole owner; opening it drops the LC29H out of RTK). No change to the RTK-critical relay.
- **Parse:** `GxGGA` (lat, lon, alt, fix-quality, sats, HDOP), `GxRMC` (ground speed, course → NED velocity), `GxGST` (position accuracy h/v). Tolerate junk/partial lines.
- **Emit:** `GPS_INPUT` (MAVLink msg 232) to `udp:127.0.0.1:14551` (the router). Populate lat/lon/alt, `fix_type`, `satellites_visible`, `hdop`, `vdop`, `vn/ve/vd`, `horiz_accuracy`, `vert_accuracy`, `speed_accuracy`; set `ignore_flags` for any field the NMEA doesn't provide. Send at the LC29H's NMEA rate.
- **Fix-type mapping** (GGA quality → `GPS_INPUT.fix_type`): `0`→0 (no fix), `1/2`→3 (3D/DGPS), `5` float→5 (RTK_FLOAT), `4` fixed→6 (RTK_FIXED).
- Run as a **systemd** service (`Restart=always`, `After=rtk-port-relay.service`).

### Component 3 — ArduPilot configuration (params, over MAVLink)
- `GPS_TYPE = 14` (MAVLink) — GPS1 is the injected RTK.
- GPS2 = M100 u-blox on its SERIAL port: `SERIALx_PROTOCOL = 5` (GPS), `GPS_TYPE2 = 1/2` (auto/u-blox). (Confirm which UART is free — SERIAL2 was disabled earlier for RCIN; may reuse or pick another.)
- Compass: enable the external QMC5883L, set it primary, run **compass calibration + CompassMot** (motor-current compensation).
- EKF source set (`EK3_SRC1_*`): position/velocity = GPS, **yaw = compass**.
- `GPS_AUTO_SWITCH` so the EKF prefers the better fix; confirm blending vs primary behavior.

### Component 4 — M100-5883 hardware
- Wire to the F405: **GPS UART** (TX↔RX) + **I2C** (SDA/SCL for the compass) + **5V/GND**.
- **Mount on a mast**, elevated and away from the motors + the 24 V battery leads (magnetic interference is the #1 rover-compass problem).
- Orientation: note the module's arrow/forward and set `COMPASS_ORIENT` accordingly.

## Success criteria
1. **GPS1 = RTK** in ArduPilot: `GPS_RAW_INT.fix_type` = 5 (float) or 6 (fixed), cm-level `h_acc` — verified **outdoors** (open sky).
2. **Compass healthy + calibrated**: no compass errors; heading tracks correctly as the rover is rotated by hand.
3. **EKF3 healthy**: origin set, `GLOBAL_POSITION_INT` sane and stable, no "GPS glitch"/"bad AHRS" warnings.
4. **Router works**: Mission Planner connects over WiFi (UDP 14550) and shows the live RTK fix + heading; the GPS bridge and a second test client run simultaneously without serial contention.
5. **Bridge robustness**: survives an LC29H fix dropping to q=1 and recovering (fix_type follows), and a relay restart (`After=` + reconnect).

## Testing
- **Indoors (bench):** the whole pipeline is testable at standard fix (q=1 → fix_type 3). Confirm position flows, fix-type maps, compass calibrates + heading tracks, EKF accepts it, Mission Planner sees it. RTK-fixed accuracy is NOT provable indoors.
- **Outdoors (open sky):** final check — confirm fix_type 5/6 and cm `h_acc`, heading holds while driving. This is the acceptance gate.
- Bench-safe throughout (no autonomous motion in phase A; this is sensors only).

## Risks / open items
- **NMEA rate:** if the LC29H streams 1 Hz, GPS is low-rate for nav. May configure the LC29H to **5–10 Hz** (a receiver command injected via the relay's TCP path, as done for the PAIR reset). Note, not blocking.
- **Compass interference on a rover** — mitigated by mast mount + CompassMot; if still noisy, fall back to compassless GPS-yaw or (later) dual-GPS moving-baseline.
- **Free UART for GPS2** — confirm an F405 serial is available for the M100 GPS (SERIAL2 was set to -1 to stop RCIN hijack; may repurpose).
- **`mavlink-router` on trixie/aarch64** — confirm install path (apt vs source build).
- **`live-nmea.log` growth** (already 370 MB+) — the tail seeks to end so size is fine, but log rotation should be set up so it doesn't fill the disk (housekeeping, not blocking A).
- **Time fields in GPS_INPUT** — populate GPS week/ms if available from RMC/ZDA; else set ignore flags (ArduPilot tolerates).

## Out of scope (later phases — do NOT build here)
- **B:** AUTO waypoint missions, boundary/path definition, driving a route.
- **C:** depth → GUIDED steer-around avoidance overlay → resume AUTO.
- **D:** mode arbitration + BLE→GUIDED relay.
- Coverage-pattern planning, mowing logic, blade control.
