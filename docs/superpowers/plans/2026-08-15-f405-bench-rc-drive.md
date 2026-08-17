# F405 Bench RC-Drive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Note:** This is a hardware/firmware/config plan, not a software-test plan. "Verify" steps are bench measurements, Mission Planner readings, ESPHome log checks, and motor-test observations — not pytest. Many steps need the human at the bench (wiring, meter, powering the pack). The agent's job is the firmware/config edits + telling the human exactly what to wire and what reading confirms success.

**Goal:** FlySky stick, through the F405 (ArduRover) and the ESP32-C6 motor interface, drives both bench BLDC wheel motors correctly (direction + proportional) with RC-loss failsafe stopping them — wheels up.

**Architecture:** F405/ArduRover reads FlySky over SBUS, does skid-steer mixing, and emits two per-wheel servo-PWM channels (ThrottleLeft/ThrottleRight, 1000–2000µs). The ESP32-C6 reads those two PWM channels and maps each straight to one wheel, reusing its proven inverted-PWM + DIR-via-BSS138 + FG + deadman. No mixing on the C6.

**Tech Stack:** ArduPilot Rover (RadiolinkF405 target) via Mission Planner; FlySky SBUS; ESPHome (esp-idf) on XIAO ESP32-C6; BSS138 level shifter; BLDC5520/3830 integrated-driver motors; 24V pack; 24V→5V BEC.

## Global Constraints

- **Wheels up / off the ground for every powered motor test.** No exceptions.
- **Blade motor NOT part of this milestone** — leave it disconnected; no blade config touched.
- **Never put 5V or 24V on the C6 LiPo pads (B+/B−).** Killed a XIAO before.
- **FG and CW/CCW idle at ~5V — never wire straight to a 3.3V C6 pin.** Use the existing BSS138 shifter (DIR) / divider (FG). PWM (blue) is 3.3V-direct, proven.
- **Single common ground:** pack−, BEC−, F405 GND, C6 GND, shifter GND, both driver grounds.
- **C6 free pins for RC-PWM in:** D6=GPIO16, D7=GPIO17 (all other GPIOs already used: L=0/1/2, R=21/22/23, blade=19/20/18). Avoid strapping pins GPIO4/5/8/9/15.
- **ArduRover MOT_PWM_TYPE = 0 (normal servo PWM).** The C6 does the inversion — the F405 must NOT output brushed/inverted PWM.
- Firmware file: `firmware/esphome/bldc-c6.yaml`. Flash via `esphome run bldc-c6.yaml --device 192.168.20.119` (OTA) — retry on transient 408.

---

### Task 1: Bench power (Pi 5V) + verify F405 servo-output logic voltage

**Files:** none (hardware setup + measurement).

**Bench power decision (2026-08-15):** the **Raspberry Pi's 5V (USB)** powers the logic rail for the bench — F405 5V-in, C6, shifter HV. **No BEC for the bench.** A BEC (24V→5V ≥3A) is deferred to the field/deploy phase when there's no Pi/USB. Motors stay on the separate 24V; never 24V on the 5V rail or the C6 LiPo pads. Common ground: Pi GND + F405 + C6 + shifter + pack− + both drivers.

**Ground-station note:** flash + configure ArduRover with **QGroundControl** (Pi/Linux or Mac — no Windows needed) or **MAVProxy** on the Pi, over the F405 USB. Same Pi later becomes the RTK companion (NTRIP → GPS_INPUT).

**Interfaces:**
- Produces: a powered F405 + C6 logic rail off the Pi, and a known FC servo-output voltage (expected 3.3V) that Task 6 relies on when wiring F405→C6 direct.

- [ ] **Step 1:** Confirm the Pi 5V can feed F405 5V-in + C6 + shifter HV. Logic draw is small (<0.5A). Wire common ground across Pi, F405, C6, shifter, pack−, drivers.
- [ ] **Step 2:** With the F405 powered (USB), in QGroundControl/MAVProxy arm in Manual (or run servo test) and **meter the SERVO1 signal pin to GND** while it pulses.
- [ ] **Step 3: Verify** the servo signal high level. Expected **~3.3V** (STM32 logic). Record it.
  - If 3.3V → F405→C6 is a direct wire (Task 6).
  - If ~5V → route the 2 RC lines through 2 spare BSS138 channels into the C6 (adjust Task 6 wiring).
- [ ] **Step 4:** No commit (hardware). Record the measured voltage in the handoff doc. (BEC purchase moved to the field-deploy phase.)

---

### Task 2: Flash ArduPilot Rover to the F405 and confirm boot

**Files:** none (firmware flash via Mission Planner).

**Interfaces:**
- Produces: an F405 running ArduRover, connectable in Mission Planner over USB.

- [ ] **Step 1:** Install Mission Planner (Windows) or use it via the user's machine. Connect the F405 by USB.
- [ ] **Step 2:** Setup → Install Firmware → select **Rover**, target board **RadiolinkF405** (confirmed official hwdef). Flash.
- [ ] **Step 3: Verify** Mission Planner connects (MAVLink heartbeat), firmware shows ArduRover version, and the HUD shows attitude moving when you tilt the board.
- [ ] **Step 4:** No commit (FC firmware lives on the board). Note the ArduRover version in the handoff doc.

---

### Task 3: Bind FlySky over SBUS and verify RC input

**Files:** none (FC config in Mission Planner).

**Interfaces:**
- Consumes: F405 running ArduRover (Task 2).
- Produces: live RC channels in Mission Planner; a known throttle + steering channel mapping.

- [ ] **Step 1:** Wire FlySky RX **SBUS out → F405 SBUS/RCIN** pad. Power RX from F405 5V. Bind RX↔TX.
- [ ] **Step 2:** Set `SERIALn_PROTOCOL`/`BRD_ALT_CONFIG` as needed so RCIN reads SBUS (RadiolinkF405 usually has a dedicated SBUS/RCIN pad — no serial port needed).
- [ ] **Step 3: Verify** in Mission Planner → Setup → Radio Calibration: moving the FlySky sticks moves the green bars. Calibrate. Identify **throttle** channel and **steering** channel.
- [ ] **Step 4:** Set `RC_MAP` / confirm channel roles. Set **RC failsafe**: `FS_THR_ENABLE` + throttle-failsafe so signal loss = neutral/hold. `THR_FAILSAFE` behavior = motors to neutral.
- [ ] **Step 5:** No commit. Record channel map + failsafe params in the handoff doc.

---

### Task 4: Configure skid-steer + per-wheel PWM outputs, verify pulses (motors disconnected)

**Files:** none (FC params).

**Interfaces:**
- Consumes: RC input (Task 3).
- Produces: two servo outputs SERVO1 (ThrottleLeft) + SERVO3 (ThrottleRight), 1000–2000µs, 1500=stop, that move with the sticks — the signals the C6 will read.

- [ ] **Step 1:** Set frame/skid params: `FRAME_CLASS=1` (Rover), enable skid-steering (`SERVO1_FUNCTION=73` ThrottleLeft, `SERVO3_FUNCTION=74` ThrottleRight). Set `SERVO1_MIN/TRIM/MAX = 1000/1500/2000`, same for SERVO3.
- [ ] **Step 2:** Set **`MOT_PWM_TYPE=0`** (normal servo PWM — NOT brushed). Set servo output rate to a fixed **`SERVO_RATE`/`RC_SPEED` = 50 Hz** (so the C6 duty read has a known frame period; see Task 5).
- [ ] **Step 3:** **C6 and motors disconnected from the F405 for this task.**
- [ ] **Step 4: Verify** with a meter/logic probe on SERVO1 & SERVO3 signal pins (or Mission Planner → Setup → Servo Output live values): center sticks → both ~1500µs; throttle forward → both rise toward 2000; reverse → toward 1000; steer → the two split opposite. Arm first if outputs are zero when disarmed.
- [ ] **Step 5:** No commit. Record final params in the handoff doc.

---

### Task 5: C6 reads ONE RC-PWM channel (prove the link — the main risk)

**Files:**
- Modify: `firmware/esphome/bldc-c6.yaml` (add a duty_cycle sensor on D6/GPIO16)

**Interfaces:**
- Consumes: SERVO1 pulse from F405 (Task 4), 50 Hz, 1000–2000µs.
- Produces: a live pulse-width reading on the C6, exposed as a sensor, that Task 6 converts to a wheel command. Pulse width `us = duty_percent * 200` at 50 Hz (20 ms period).

- [ ] **Step 1:** Wire **F405 SERVO1 signal → C6 D6 (GPIO16)**, and **F405 GND → C6 GND** (common ground). (If Task 1 found 5V servo logic, route via a spare BSS138 channel instead.)
- [ ] **Step 2:** Add to `bldc-c6.yaml` a duty-cycle reader + derived pulse width:

```yaml
sensor:
  # ... existing FG sensors stay ...
  - platform: duty_cycle
    pin: GPIO16          # D6 <- F405 SERVO1 (ThrottleLeft)
    id: rc_l_duty
    update_interval: 100ms
    name: "RC L duty"
  - platform: template
    name: "RC L us"
    id: rc_l_us
    lambda: "return id(rc_l_duty).state * 200.0;"   # 50Hz: 20000us * duty% / 100
    update_interval: 100ms
    unit_of_measurement: "us"
```

- [ ] **Step 3:** Flash: `esphome run bldc-c6.yaml --device 192.168.20.119` (retry on 408).
- [ ] **Step 4: Verify** on the ESPHome dashboard / logs (or `curl -s http://192.168.20.119/sensor/RC%20L%20us`): center stick → **~1500**, throttle up → toward **2000**, down → toward **1000**. Values track the stick.
- [ ] **Step 5: Decision gate.** If the reading is stable and responsive → continue. **If laggy/jittery** (duty_cycle averaging too slow for control), switch to the serial fallback (F405 UART → C6 D7/D6 UART, simple `L<us> R<us>` line protocol) — stop and re-plan Tasks 5–7 around serial. Record which path.
- [ ] **Step 6: Commit:**

```bash
git add firmware/esphome/bldc-c6.yaml
git commit -m "feat(c6): read one RC-PWM channel from F405 via duty_cycle"
```
(If not a git repo, skip commit — save the file.)

---

### Task 6: Map RC channel → LEFT wheel, bench-drive one wheel from FlySky

**Files:**
- Modify: `firmware/esphome/bldc-c6.yaml` (interval that converts rc_l_us → pwm_l/dir_l + feeds deadman)

**Interfaces:**
- Consumes: `rc_l_us` (Task 5), existing `pwm_l`, `dir_l`, `last_cmd`, deadman interval.
- Produces: LEFT wheel driven by the FlySky throttle; center = stop; forward/reverse correct.

- [ ] **Step 1:** Add a control interval to `bldc-c6.yaml` that converts the pulse to a signed wheel command and drives the existing left channel:

```yaml
interval:
  # ... existing deadman interval stays ...
  - interval: 50ms
    then:
      - lambda: |-
          float us = id(rc_l_us).state;
          if (us < 900 || us > 2100 || isnan(us)) return;   // invalid frame -> let deadman stop it
          int cmd = (int)((us - 1500) / 5.0);                // -100..+100  (500us span -> +-100)
          if (cmd > 100) cmd = 100; if (cmd < -100) cmd = -100;
          if (cmd > -6 && cmd < 6) cmd = 0;                  // center deadband
          if (cmd >= 0) id(dir_l).turn_on(); else id(dir_l).turn_off();   // left fwd = dir_l ON (flipped, matches bench)
          id(pwm_l).set_level((cmd < 0 ? -cmd : cmd) / 100.0f);
          id(last_cmd) = millis();                            // feed deadman
```

- [ ] **Step 2:** Wire LEFT motor to the C6 as today (blue/PWM→D0 direct, yellow/DIR→shifter, green/FG→shifter/divider, red→24V, black→GND). **Wheels up.** BEC powering C6 + F405 + shifter HV; pack 24V to motor.
- [ ] **Step 3:** Flash the firmware (OTA, retry on 408).
- [ ] **Step 4: Verify (wheels up):** FlySky throttle forward → LEFT wheel spins forward, proportional to stick; center → stops; reverse → spins reverse. Direction matches "forward = forward"; if reversed, flip the `dir_l` on/off in Step 1 and reflash.
- [ ] **Step 5: Commit:**

```bash
git add firmware/esphome/bldc-c6.yaml
git commit -m "feat(c6): drive left wheel from RC-PWM channel"
```

---

### Task 7: Add RIGHT channel + wheel, verify skid-steer both wheels

**Files:**
- Modify: `firmware/esphome/bldc-c6.yaml` (second duty_cycle on D7/GPIO17 + right wheel in the control interval)

**Interfaces:**
- Consumes: SERVO3 pulse (Task 4) on D7/GPIO17; existing `pwm_r`, `dir_r`.
- Produces: both wheels driven per-channel = full skid-steer from FlySky.

- [ ] **Step 1:** Wire **F405 SERVO3 → C6 D7 (GPIO17)**. Add the right duty reader:

```yaml
  - platform: duty_cycle
    pin: GPIO17          # D7 <- F405 SERVO3 (ThrottleRight)
    id: rc_r_duty
    update_interval: 100ms
    name: "RC R duty"
  - platform: template
    name: "RC R us"
    id: rc_r_us
    lambda: "return id(rc_r_duty).state * 200.0;"
    update_interval: 100ms
    unit_of_measurement: "us"
```

- [ ] **Step 2:** Extend the 50ms control interval with the right wheel (append inside the same lambda, after the left block):

```cpp
          float ur = id(rc_r_us).state;
          if (ur < 900 || ur > 2100 || isnan(ur)) return;
          int cr = (int)((ur - 1500) / 5.0);
          if (cr > 100) cr = 100; if (cr < -100) cr = -100;
          if (cr > -6 && cr < 6) cr = 0;
          if (cr >= 0) id(dir_r).turn_off(); else id(dir_r).turn_on();    // right fwd = dir_r OFF (flipped)
          id(pwm_r).set_level((cr < 0 ? -cr : cr) / 100.0f);
```

- [ ] **Step 3:** Wire the RIGHT motor to the C6 as today. **Wheels up.** Flash (OTA).
- [ ] **Step 4: Verify (wheels up):** throttle forward → both wheels forward, equal at center steer; steer right → left wheel faster / right slower (arc), full steer → spin; reverse works. If a wheel's direction is wrong, flip its `dir_*` on/off and reflash.
- [ ] **Step 5: Commit:**

```bash
git add firmware/esphome/bldc-c6.yaml
git commit -m "feat(c6): drive both wheels from RC-PWM (skid-steer)"
```

---

### Task 8: RC-loss failsafe — verify wheels stop

**Files:** none (verification of existing deadman + FC failsafe).

**Interfaces:**
- Consumes: the deadman interval (fed by `last_cmd` in Tasks 6–7) + F405 RC failsafe (Task 3).

- [ ] **Step 1:** Confirm the deadman interval still zeroes `pwm_l`/`pwm_r` when `last_cmd` is stale (>1000ms). The control interval only updates `last_cmd` on a **valid** pulse — so a lost/invalid RC frame stops feeding it.
- [ ] **Step 2: Verify (wheels up):** drive forward, then **turn the FlySky TX off**. Expected: F405 failsafe drives SERVO1/3 to neutral (~1500) AND/OR the pulse stops → C6 sees center/invalid → **both wheels stop within ~1s**.
- [ ] **Step 3: Verify** the reverse: TX back on → control resumes.
- [ ] **Step 4:** No commit. Record failsafe behavior in the handoff doc.

---

### Task 9: Full bench acceptance + handoff doc

**Files:**
- Create/Modify: `docs/bench-f405-handoff.md` (bench results, params, wiring, next phase)

- [ ] **Step 1: Verify all success criteria (wheels up):**
  1. Throttle forward → both wheels forward, proportional.
  2. Steering → correct differential.
  3. Reverse works.
  4. TX off → wheels stop within ~1s.
- [ ] **Step 2:** Write `docs/bench-f405-handoff.md`: final ArduRover params (frame, SERVO1/3 functions, MOT_PWM_TYPE, servo rate, RC map, failsafe), C6 pins (D6/D7 RC in), the duty→us→cmd math, per-wheel DIR polarity as tuned, and the measured F405 servo voltage.
- [ ] **Step 3:** Update memory `bench-esp-control-status.md` + `rover-architecture.md` with "bench RC drive DONE" and any deviations (e.g. serial fallback used).
- [ ] **Step 4: Commit:**

```bash
git add docs/bench-f405-handoff.md
git commit -m "docs: F405 bench RC-drive results + handoff"
```

---

## Self-Review

**Spec coverage:** hardware/BEC (T1), ArduRover flash (T2), FlySky/SBUS + failsafe (T3), skid-steer + per-wheel PWM out (T4), C6 RC read w/ serial fallback gate (T5), left wheel (T6), right wheel + skid (T7), failsafe verify (T8), acceptance + handoff (T9). All spec success criteria mapped (T9 Step 1). Out-of-scope items (RTK, autonomy, blade) correctly excluded.

**Placeholder scan:** no TBD/TODO; each firmware step has real YAML/C++; each config step has exact param names; each verify step has an expected reading.

**Type/name consistency:** `rc_l_us`/`rc_r_us` (template sensors) consumed by the control interval; `pwm_l`/`pwm_r`/`dir_l`/`dir_r`/`last_cmd` reuse the existing IDs from the working joystick firmware; DIR polarity (left ON=fwd, right OFF=fwd) matches the current flipped-forward convention. Deadman fed by `last_cmd` in both the control interval and honored by the existing deadman interval.

**Known adaptation:** if T5 Step 5 gate fails (duty_cycle too laggy), Tasks 5–7 re-plan around a serial link — this is the one branch, flagged explicitly rather than hidden.
