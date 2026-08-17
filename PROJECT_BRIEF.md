# Project: RTK-guided rover / robot-mower from a hacked pool cleaner

## Role & access
You have SSH access to a Raspberry Pi 4 on my bench. I've physically wired an
ST-Link (SWD) and a serial/USB-TTL adapter to a salvaged controller board (details
below). Your job: run diagnostics over SSH, interpret output, and drive the build
forward. I'm the hands for anything physical; you run everything on the Pi.

## Goal
Repurpose a cordless pool-cleaner robot into an autonomous, RTK-GPS-guided ground
vehicle. Two phases:
1. Mobile RTK rover: cm-accurate path logging (differential-drive chassis + Pi 4 + LC29H RTK).
2. Stretch goal: add a rear cutting deck to make it a robot lawn mower.
NOTE: it will NOT operate in water. GNSS is blocked by water; antenna needs open sky.

## Hardware I have
- Raspberry Pi 4 (the brain; runs NTRIP client, logging, high-level nav).
- Quectel LC29H RTK GNSS: a BASE board + a ROVER board, each with antenna (dual-band L1/L5, cm-level RTK).
- ST-Link (SWD programmer/debugger).
- USB-TTL serial adapter.
- The donor pool robot, fully torn down.

## Donor board: "SP5-MAIN VER:1.2" (dated 2023.11.14, UL E224772)
Main controller from a cordless pool robot. Center MCU (U3) is a ~48-pin LQFP,
ARM Cortex-M (has crystal Y1). Big D-PAK MOSFETs (T1-T4) + shunt resistors
(R020/R050) = motor H-bridges with current sensing. Piezo buzzer onboard.

### Full connector map (from silkscreen; Chinese labels translated)
| Silk    | Pins                    | Purpose                                             |
|---------|-------------------------|-----------------------------------------------------|
| URT1    | VDD·CLK·GND·DIO         | SWD port. Silk = 下载接口 "Download port" (factory flash) |
| CON1    | 5V·RX·TX·GND            | UART console. Silk = 调试接口 "Debug port"            |
| CON3    | KEY·DAT·CLK             | Power button + status LED board (开关板口)            |
| CON2    | VDD·TX·RX·GND           | Secondary UART (BT/light board)                     |
| BATTERY | GND·SCL·SDA·PWR·VDD     | SMART battery: power + I2C to BMS/fuel gauge        |
| MT-L    | multi-pin               | Motor - LEFT drive                                  |
| MT-R    | multi-pin               | Motor - RIGHT drive                                 |
| MT-P    | multi-pin               | Motor - PUMP (candidate cutter motor later)         |

Drivetrain confirmed: MT-L + MT-R = differential drive; MT-P = pump.
Drive motors are brushed DC with Hall-effect quadrature encoders (green daughterboards).
Salvage value: Li-ion pack + BMS (power), waterproof enclosure. Pump/drive motors reusable.

## Key decisions & findings
- The board is unusually hackable: URT1 is the LABELED factory flash (SWD) port and
  CON1 is the LABELED debug UART. Doors left open.
- Two candidate strategies for motor control:
  - Strategy A (Bypass): cut motor wires, drive motors with our own driver
    (Cytron MDD10A or 2x BTS7960) from Pi/ESP32. Guaranteed, no reversing.
  - Strategy B (Reuse power stage): reflash the SP5 MCU via URT1 with custom firmware
    that takes commands from Pi over CON1 UART and drives the existing H-bridges.
    Viable ONLY if flash is not read-protected. Preferred if unlocked.
- DECISION GATE: read the MCU IDCODE + flash-lock status first → picks A vs B.

## ⚠️ Smart-battery gotcha
The pack talks I2C (SCL/SDA) to a BMS. Its discharge FET may be held OFF until a
power-button press (CON3 KEY line) or MCU I2C handshake — so the pack can read 0V
"dead" at rest. If we keep the SP5 MCU, handshake is free. If we bypass, we may need
to latch the button line or emulate the wake. Test: measure VDD→GND at rest, then
press power button and watch for voltage.

## RTK architecture (already decided)
- Corrections via NTRIP over Wi-Fi/LTE.
- Base board at a fixed sky-view spot → RTCM3 → pushed to a caster (e.g. rtk2go).
- Rover board + Pi on the robot → NTRIP client pulls RTCM, injects to rover UART,
  reads NMEA. Watch GGA quality: 4 = RTK fixed (cm), 5 = float, 1 = plain GPS.
- LC29H computes the fix internally; Pi just relays RTCM in + reads NMEA out (one UART).

## Safety constraints (mower phase — enforce these)
- Use pivoting razor blades or trimmer line, NEVER fixed rigid metal blades.
- 3D-printed guard is geometry only, NOT blade containment; keep blade recessed under
  a wide deck so nothing can reach it from the side.
- Cutter must fail-OFF: only spins when tilt-OK AND on-ground AND no e-stop AND commanded.
  Add tilt/lift cutoff, bump stop, physical e-stop, lift kill-switch.
- Reference projects: OpenMower, ArduMower.
- Pump motor may be too low-RPM to cut; verify no-load RPM at pack voltage before committing.

## IMMEDIATE NEXT STEPS (do these first)
1. Install tools on the Pi:
   sudo apt update && sudo apt install -y stlink-tools openocd python3-serial
2. Identify MCU + check flash protection (ST-Link on URT1):
   st-info --probe
   st-flash read /tmp/dump.bin 0x08000000 0x1000 ; echo "exit=$?"
   - exit=0 & file created  -> flash UNLOCKED -> Strategy B viable
   - error/"protected"      -> read-protected -> fall back to Strategy A
   - If st-info mislabels a clone (GD32/APM32/AT32), note the raw chipid.
3. Capture UART boot log (USB-TTL on CON1: RX·TX·GND, do NOT feed its 5V):
   - Find the port (likely /dev/ttyUSB0), baud-scan from 115200.
   - Use picocom/screen or a pyserial script; power-cycle the board and capture output.
4. Report chipid, flash-lock result, and any UART boot text back to me, then recommend
   Strategy A vs B and the next action.

## Working style
- Explain what each command does before/while running it.
- One decision gate at a time; don't buy/commit hardware before the IDCODE + lock check.
- Be honest about uncertainty (e.g. clone MCUs, H-bridge vs half-bridge — still need to
  confirm MT-L/MT-R are full H-bridges since drive must reverse).
