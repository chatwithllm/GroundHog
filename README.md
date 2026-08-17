# 🦫 Groundhog

**An all-season autonomous ground robot — RTK-precise, tracked base, swappable implements (mow · edge · snow).**

Groundhog is a tracked, centimeter-accurate robot platform built around a modular, user-replaceable component stack. One base carries whatever you strap on — a mower deck, an edger, a snow blower — and drives itself by RTK GPS, or under manual BLE / WiFi / RC control.

> Origin: reincarnated from a salvaged cordless pool cleaner. That's the backstory, not the mission.

## Architecture

Three layers, cleanly split:

| Layer | Hardware | Role |
|-------|----------|------|
| **Brain** | Radiolink F405 (ArduPilot Rover) | RC, skid-steer mixing, arming, failsafe, autonomy (GUIDED/AUTO waypoints) |
| **Motor interface** | ESP32 (C6 now → Lonely Binary S3) | Per-wheel actuator: inverted-PWM + DIR (via BSS138 shifter) + FG tacho + deadman |
| **Companion** | Raspberry Pi + LC29H RTK HAT | NTRIP→RTCM corrections, MAVLink, coverage planning, camera |

Control modes (BLE / WiFi / RC / autonomous) are all just **input sources to ArduRover modes** — one brain, many inputs. RTK corrections are source-agnostic: NTRIP now, own base station later.

The drivetrain uses the salvaged board's **integrated-driver BLDC motors** (5-wire: VCC/GND/PWM/DIR/FG, 5V-logic, inverted PWM where 0% duty = full speed).

## Repository layout

```
firmware/esphome/     ESP32 motor-interface firmware (ESPHome) + web/BLE control pages
firmware/arduino/     Arduino diagnostic sketches
docs/                 Design specs, plans, handoff notes
media/diagrams/       Wiring planner (interactive), diagrams, pinouts
media/probe/          Bench probe/scope captures
```

## Setup

ESPHome firmware needs a local `secrets.yaml` (gitignored):

```bash
cp firmware/esphome/secrets.yaml.example firmware/esphome/secrets.yaml
# edit in your Wi-Fi + a freshly generated API encryption key
```

## Status

- ✅ Bench motor control (tank / joystick / BLE) on ESP32-C6
- ✅ F405 + ArduRover flashed, FlySky RC drive working (skid-steer)
- ✅ RTK NTRIP pipeline deployed on the Pi (cm-fixed under open sky)
- 🔜 Modular attachment port (CAN), coverage autonomy, own base station

## Roadmap

Bench RC drive → chassis mount + field drive → RTK autonomy (waypoint rows) → attachment platform (mower / edger / snow blower).
