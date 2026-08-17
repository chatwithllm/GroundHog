# F405 / ArduRover Integration — Design

**Date:** 2026-08-15
**Status:** Approved (architecture), pending spec review
**Scope of this spec:** Bench milestone only — F405 + ArduRover + FlySky drives the two bench BLDC motors through the ESP32-C6, wheels up. RTK and autonomy are later phases (roadmap at bottom).

## Goal

Make the Radiolink F405 (running ArduPilot Rover) the rover's brain, driving the existing integrated-driver BLDC wheel motors **through the ESP32-C6** as a motor interface. Bench success = FlySky stick drives both wheels correctly (direction + proportional speed) with RC failsafe stopping the motors.

## Why the C6 stays in the loop

The BLDC5520/3830 motors have **integrated drivers** needing an **inverted PWM** (0% duty = full speed) plus a **direction** line and expose an **FG** tacho. ArduRover cannot emit inverted-duty PWM natively, and the C6 firmware already solves all of this (inverted LEDC PWM, DIR via BSS138 shifter, FG pulse counting, deadman). So the C6 remains the motor driver; the F405 does nav/RC/RTK. Clean split, minimal new risk.

## Hardware

In hand: Radiolink F405 FC, LC29H RTK GPS (+antenna), FlySky RX+TX, ESP32-C6 rig (BSS138 shifter, 2 BLDC motors), 24V pack.
**To buy:** one **BEC, 24V→5V, ≥3A** to power the F405 + C6 + shifter HV off the pack.
Not needed for bench: telemetry radio (ground station over USB); LC29H (RTK is a later phase).

## Architecture (bench)

```
FlySky TX --RF--> FlySky RX --SBUS--> F405 (ArduRover, skid-steer)
                                        | mixes stick -> 2 per-wheel outputs
                                        v
     SERVO1 = ThrottleLeft, SERVO3 = ThrottleRight   (1000-2000us PWM, 3.3V logic)
                                        v
                          ESP32-C6 (motor interface)
              reads 2 RC-PWM inputs -> per-wheel throttle (1500us = stop,
              >1500 fwd, <1500 rev, deflection = speed); drives each BLDC
              with proven inverted-PWM + DIR-via-shifter; FG + deadman kept
                                        v
                 BLDC-L driver + BLDC-R driver -> wheels
```

## Division of labor

- **F405 / ArduRover:** read FlySky (SBUS), skid-steer mixing, arming, RC failsafe. Outputs two per-wheel PWM channels. (Later: LC29H RTK, GUIDED/AUTO waypoints, heading hold.)
- **C6:** maps each RC-PWM channel straight to one wheel — no mixing (ArduRover already mixed). 1500us = stop, offset = signed speed → inverted-PWM + DIR. Keeps the deadman: invalid/lost pulse → stop. BLE joystick retained as a bench backup control path.

Rationale for **ThrottleLeft/Right** (not Throttle+Steering): ArduRover owns the mix, so turning ties to nav/heading in later phases; the C6 stays a dumb per-wheel actuator.

## Data flow

FlySky stick → F405 mixes → 2 PWM (per wheel) → C6 measures pulse width per channel → maps to pwm level + dir per wheel → BLDC drivers → wheels. Single common ground: pack−, BEC, F405, C6, shifter GND, both driver grounds.

## Comms link — primary and fallback

- **Primary: RC-PWM.** C6 reads two servo-PWM channels from the F405 via interrupt-timed pulse-width capture. ESPHome has no native servo-input, so this is a custom interrupt reader (well-trodden on ESP32). Both sides are 3.3V logic → direct wire, no shifter.
- **Fallback (if PWM capture is flaky): serial.** F405 UART → C6 UART, simple line protocol (e.g. `L<val> R<val>`), driven from an ArduPilot Lua script or a spare serial output. Chosen only if the PWM reader proves unreliable.

This single link is the **first thing to prototype** — everything else depends on it.

## C6 firmware changes

- Add two RC-PWM input readers (GPIO interrupt, measure HIGH pulse 1000–2000µs at ~50Hz).
- Map each channel → wheel: `mid=1500`, `speed=(pulse-1500)/500` (−1..+1), sign→DIR, magnitude→inverted-PWM level.
- Failsafe: if a channel gives no valid pulse within the deadman window, or reads center, force that wheel to 0. (Reuse existing `last_cmd`/interval deadman, fed by valid RC pulses.)
- RC input takes priority when present; BLE joystick remains available when no RC signal (bench backup). Keep it simple — no blending.

## ArduRover config (bench)

- Frame: skid-steer (`FRAME_CLASS`/rover skid config).
- `SERVO1_FUNCTION = 73` (ThrottleLeft), `SERVO3_FUNCTION = 74` (ThrottleRight).
- `MOT_PWM_TYPE` = normal (standard 1000–2000µs; the C6 handles inversion — the F405 must NOT output brushed/inverted).
- FlySky bound via SBUS; set RC map, arming, and RC failsafe (throttle-cut on signal loss).
- Manual mode only for bench.

## Success criteria (bench)

1. FlySky throttle forward → both wheels spin forward, proportional to stick.
2. Steering → wheels differential correctly (left/right as expected).
3. Reverse works.
4. **RC failsafe:** TX off (or out of range) → F405 failsafe → C6 deadman → wheels stop within ~1s.
5. Wheels-up throughout.

## Out of scope (later phases)

- LC29H RTK integration + RTCM injection.
- GUIDED/AUTO waypoint navigation, mowing row patterns, heading hold.
- Blade motor control (belongs on the F405 with a hardware e-stop, not bench).
- Chassis mounting, weatherproofing, field power.

## Risks

- **RC-PWM capture reliability on the C6** (primary risk) → serial fallback defined.
- **BEC current** under motor transients → size ≥3A, keep motor 24V rail separate from the 5V logic rail (only grounds common).
- **DIR logic level** 3.3V FC/C6 vs 5V driver — already handled by the BSS138 shifter as today.
- **Ground loops / noise** from 24V motor switching into FC → star-ground, keep FC away from motor leads.

## Roadmap after bench

1. Bench RC drive (this spec).
2. Mount in chassis, manual field drive + tune skid-steer.
3. LC29H RTK fix + inject corrections; verify cm-level position.
4. GUIDED/AUTO waypoints; straight-line rows for mowing.
5. Blade motor on F405 with hardware e-stop + failsafe.

## Open items

- Buy the BEC (24V→5V, ≥3A).
- Confirm F405 servo-output logic voltage (3.3V assumed; verify before wiring to C6).
- Pick the two C6 GPIOs for RC-PWM input (avoid strapping pins; must support interrupts).

---

# Future Wishlist — Modular Platform + Attachments

*Not scoped/committed — captured direction for later phases. The bench spec above stands unchanged.*

## Base is a tracked 2-motor skid-steer
Tracks give skid-steer with just **2 drive BLDCs** — confirmed sufficient. Any additional motor is an **attachment** (mower blade, edger, snow blower), never a drive wheel.

## Attachments = swappable kit on ONE standard port
Tractor **PTO + 3-point-hitch + ISOBUS**, done cheap. Define one interface every attachment plugs into:
- **Power:** 24V + GND, fused per attachment, current-sensed (board ADC shunts), low-volt cutoff.
- **Bus:** **CAN (ESP32 TWAI)** — 4 wires (24V/GND/CANH/CANL), multi-drop, noise-proof, DroneCAN-friendly. Even if attachment #1 (mower) only needs PWM, wire CANH/CANL now so the port is CAN-ready.
- **Identity:** attachment announces type on connect → base loads its profile (speed caps, UI, interlocks).
- **Safety:** blades are dangerous — e-stop, deadman, tilt/bump kill, tool-off unless in-bounds + mode-armed.
- **Connector:** one keyed, weatherproof connector (power + bus) for all attachments.
- Each attachment = its own tiny ESP32 node (takes "blade 60%", returns RPM/current/fault); base never knows its guts.

## Unified control modes (one brain, many inputs)
BLE / WiFi / RC / autonomous are **input sources to ArduRover modes**, not separate systems:
- BLE / WiFi joystick → MAVLink RC-override or GUIDED velocity (teleop).
- FlySky RC → F405 (bench-proven).
- Autonomous → AUTO waypoint mission; RTK corrections from **NTRIP _or_ own base** (rover stays source-agnostic — just wants RTCM on a port; pipeline already deployed).
- Build-once shared autonomy: **RTK boundary record** (drive perimeter, save polygon) + **coverage planner** (boustrophedon mow / perimeter edge / coverage+chute snow), reused by every attachment.

## Modular, user-replaceable component packages
Every major component is a **self-documenting, swap-in module** so a dead part is replaced + reflashed with zero tribal knowledge. Components: **Motherboard (SP5 salvage), ESP (C6→Lonely Binary S3), Flight Controller (Radiolink F405), Raspberry Pi, RC Controller (FlySky)**. Each package carries, at a glance:
- Photo + pinout image + key specs.
- Wiring (what connects where) + net colors.
- **Reprogram/recover procedure** (how to reflash: tool, port, command, firmware file).
- Replacement notes (exact part, config to restore, gotchas).
- Links to firmware/config in the repo.
→ Delivery vehicle: extend the living wiring planner (rich component cards) and/or a component knowledge-base page. *Format spec TBD — see separate brainstorm.*

## Controller choice
Move the base motor + attachment-bus master to the **Lonely Binary ESP32-S3 (WROOM-1)** — has CAN (TWAI) + ~30 GPIO + 8 LEDC channels. Reason to retire the C6 for the platform build.
