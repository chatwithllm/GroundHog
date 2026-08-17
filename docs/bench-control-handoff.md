# Pool-Robo RTK — Bench Control Handoff (2026-08-12)

Status snapshot after getting the salvaged BLDC motors under live control.

## TL;DR
- Motors are **BLDC5520 24V with integrated drivers** (5-wire), **not brushed**. No external motor driver (MDDS30 dropped).
- The driver runs **5V logic** — that quietly **killed 3 microcontrollers** before we caught it. FG and CW/CCW idle at ~5V; blue/PWM at ~1.2V.
- **Working now:** NodeMCU **ESP8266** running ESPHome, Wi-Fi dashboard, **2 drive motors** with speed + direction + one FG feedback. First controlled spin achieved.
- **Blade (motor 3) deliberately NOT on the bench ESP** — needs failsafe + e-stop; belongs on the F405.

## The motor (confirmed)
- Label: **BLDC5520 DC 24V** (tkcdmotor / Wenzhou Tuoke), integrated driver on the green PCB.
- 5 wires, same gauge. Datasheet pad order VCC·FG·CW/CCW·GND·PWM, supply 8-24V.
- **Confirmed wire map:** 🔴 red=VCC(+24V) · ⚫ black=GND · 🔵 blue=PWM(speed) · 🟡 yellow=CW/CCW(direction) · 🟢 green=FG(tacho out).
- Speed = PWM duty (inverted: 0%=stop). Direction = CW/CCW level. FG = pulses ∝ speed (540 pulses/min at full — pulses-per-rev not yet calibrated).

## The gotcha that cost 3 boards
- Driver signals are **5V**; ESP GPIOs are **3.3V, not 5V-tolerant**. Wiring FG/CW-CCW straight to a pin fed 5V in → dead board (2× XIAO ESP32-C3, 1× NodeMCU ESP32). One XIAO also died earlier from 5V on its B+/B− LiPo pads.
- **Measured (driver on 24V, no MCU):** FG ≈ 5V, CW/CCW ≈ 5V, PWM ≈ 1.2V.

## The proven per-motor interface (ESP8266, 3.3V-safe)
- 🔵 **PWM (blue) → pin, direct** — it's 1.2V, safe. (3.3V PWM does drive the 5V driver.)
- 🟡 **CW/CCW (yellow) → 1kΩ series → pin** — current-limits the 5V pull-up so the pin's clamp survives boot.
- 🟢 **FG (green) → divider 10kΩ(top)+22kΩ(bottom) = 3.4V → pin** — real voltage drop (needs the leg to GND). Measure across the 22k (tap↔GND).
- All grounds common: pack − · motor black · ESP GND · divider bottom.
- Diagram: `media/diagrams/esp8266_wiring.png`. Pinout: `media/diagrams/pinout.png`.

## Working bench setup
- **Board:** NodeMCU ESP8266, ESPHome. Reflashes reliably via esptool auto-reset (the ESP32 boards needed manual BOOT and kept dying).
- **Config:** `firmware/esphome/bldc-esp8266.yaml` (Wi-Fi in `secrets.yaml` = Blair_AC). OTA works.
- **Dashboard:** http://192.168.20.119 (DHCP; find by `bldc-esp8266.local` if it moves). Controls: Left Speed, Right Speed, Left/Right Direction, STOP ALL, Left FG.
- **Pins:** LEFT — PWM=D5(GPIO14), CW/CCW=D6(GPIO12, via 1k), FG=D7(GPIO13, via 10k/22k). RIGHT — PWM=D1(GPIO5), CW/CCW=D2(GPIO4, via 1k), no FG (out of clean pins).
- ESP8266 limit: ~5 clean GPIOs + heavy software-PWM load → **2 motors max** on this board. 3 motors want the F405 or ESP32.
- USB-serial diagnostic (no Wi-Fi) also available: `firmware/arduino/bldc_diag_8266/` and merged bins in `firmware/arduino/`.

## Next steps
1. Finish the **2-motor skid-steer** bench test (wire right motor, confirm turn/straight, STOP ALL).
2. **Blade (motor 3):** on the **F405** (ArduRover) driven by a spare PWM + relay, with **failsafe-on-signal-loss + hardware e-stop**, or a relay + physical switch. Blade removed for all bench testing. Never on a Wi-Fi board with no failsafe.
3. **F405 / ArduRover** becomes the real brain: 3 motors (2 drive skid-mix + blade), fuse the blade 24V, add heading source (compass or moving-baseline GPS).
4. **RTK:** Pi + LC29H HAT (NTRIP→RTCM), forward fix to F405 over MAVLink (GPS_TYPE=MAV).
5. Calibrate FG → RPM (count revs vs pulses) once needed.

## Power / board reuse
- Keep the salvaged board WHOLE: it's the **24V source + motor mounts + charge path** (charging is passive, works with the stock MCU dead).
- UBEC (5.5-26V in → 5V/3A out) for F405; Pi wants its own 5V/5A. Common ground everywhere. Never 24V/5V on a 3.3V pin or the ESP B+/B− pads.
