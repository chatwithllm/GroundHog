# Full handoff — Pool-cleaner → RTK rover: motor power stage blocked

You are an expert embedded-systems / power-electronics reverse engineer taking over an in-progress hardware bring-up. You have live SSH access to the rig (see below) and should be able to start debugging immediately. Read this whole document first — it contains everything done so far, every relevant address/command, what's solved, and the exact open problem. Challenge our conclusions; don't just agree.

---

## 0. Goal
Convert a salvaged cordless **pool-cleaner robot** into an autonomous **RTK-GPS rover** (later maybe a mower). It will NOT run in water. Phase 1: drive a differential chassis (two brushed DC gear-motors with Hall encoders, left + right) under a Raspberry Pi 4 running an RTK nav stack. Reuse the robot's main board, H-bridges, battery pack, motors, and encoders if possible.

## 1. Access & environment
- **SSH:** `ssh npalakurla@rtk` (key auth, no password). Run all hardware commands on the Pi.
- **Programmer:** ST-Link/V2 on the board's SWD port (silk "URT1"). Tools on Pi: `st-flash`, `st-info` (stlink 1.8.0), `openocd` 0.12, `arm-none-eabi-gcc` 14.2, `python3-serial`.
- **Console:** USB-TTL (CP210x) at `/dev/ttyUSB0` = the board's debug UART (silk "CON1" = MCU USART2), **115200 8N1**.
- **Firmware project on Pi:** `~/sp5fw/` — files: `main.c` (~776 lines), `smbus.c`, `smbus.h`, `startup.c`, `linker.ld`, `Makefile`. Build: `cd ~/sp5fw && make`. Flash: `st-flash --reset write sp5fw.bin 0x08000000`. (Mac mirror of source: `~/dev/active/Pool Robo RTK/firmware/sp5fw/`.)
- **Helper scripts on Pi** (`~/uartcap/`):
  - `python3 ~/uartcap/cmd.py "<cmd>" <secs>` — send one console command, print reply for <secs>.
  - `python3 ~/uartcap/seq.py <arg> <arg> ...` — send many commands; `@0.5` = sleep 0.5s; `==label==` = print label; prints each reply (minus heartbeats).
  - `python3 ~/uartcap/cap.py <baud> <secs>` — raw capture.

### ⚠️ Hard-won operational rules
- **NEVER use openocd for live register pokes.** Its reset/halt drops the firmware's GPIO "power-hold" and the board powers OFF. Use `st-flash` (for flashing) and the UART console only. openocd is fine ONLY for flashing/one-shot reads when you accept it may power-cycle the board.
- **`st-flash` connect is flaky** — it intermittently returns "Failed to connect to target". Just retry 2–3×; it then succeeds ("jolly good!").
- The board is battery-powered; ST-Link SWD is wired signals-only (SWCLK/SWDIO/GND, **no 3.3V**), so the target is self-powered.
- When probing/experimenting, keep motors' chassis **wheels off the ground** and PWM duty ≤15%.

## 2. Hardware
- **Board:** silk "SP5-MAIN VER:1.2", 2023.11.14, UL E224772.
- **MCU (U3):** **GigaDevice GD32F103CB** (STM32F103 clone). ARM Cortex-M3 r2p1, dev id 0x410, rev 0x1303. 128KB flash (st-info misreports; linker set to 128K but chip may be 64K — irrelevant, fw is ~10KB), 20KB SRAM. Runs HSE 8MHz (crystal Y1) → PLL → **72 MHz** in our firmware.
- **Battery:** 6S2P Li-ion smart pack, **22.2V nominal / 25.2V full**, 5.2Ah, 115Wh, internal BMS (Shenzhen BetterPower). BATTERY connector silk order (left→right): **VDD · PWR · SDA · SCL · GND** (VDD = logic ~3-5V; PWR = switched high-current motor rail; SDA/SCL = SMBus).
- **Connectors:** URT1 (SWD: VDD/CLK/GND/DIO), CON1 (console UART = USART2: 5V/RX/TX/GND), CON2 (USART3: VDD/TX/RX/GND, "light/BT board"), CON3 (power button + status-LED board: KEY/DAT/CLK), BATTERY (above), **MT-L / MT-R / MT-P** = Left drive / Right drive / Pump motors.
- **Motors:** 5 wires each = **2 motor-power** + **3 Hall encoder** (encoder Vcc ≈ 5V, GND, signal ≈ 3V toggling). Confirmed by probing MT-R (5V + 3V present).
- **Power stage:** H-bridges from D-PAK MOSFETs (silk T1–T4) + SOT-23 transistors (Q1–Q9, gate level-shifters) + R020/R050 current-sense shunts. Bulk caps: "25V 330 AM" (330µF) near each motor connector; "100 25V UE" (100µF) near the input/buck. Buck converter: inductor **L2 (4R7)** + chip **U2** → makes the 3.3/5V logic from 24V. SOIC-8 **U5/U6** = current-sense amplifiers (NOT gate drivers). A MOSFET silk **Q2 ("SOP03")** near the 24V cap = suspected motor-rail load switch. Piezo buzzer onboard.

## 3. MCU pin / peripheral map (verified via SWD capture of stock running state + live probing)
- **Motor PWM:** TIM1, ~20 kHz in our fw (15.4 kHz stock), single-ended, on **PA8=CH1, PA9=CH2, PA10=CH3** (AF-PP; MOE set; PWM verified to physically reach the pins). TIM1 complementary pins CH1N/CH2N/CH3N = **PB13/PB14/PB15**.
- **Current sense (ADC1):** 7-ch scan. The **3 motor shunts = PA6, PA7, PB0** (bidirectional, idle-biased ~1075 counts = zero current). **PA5 ≈ 1770** = battery-voltage divider. Others: PA1 (a latching voltage node), PA4, PB1.
- **UARTs:** USART2 = PA2(TX)/PA3(RX) = CON1 console @115200. USART3 = PB10(TX)/PB11(RX) — stock ran a real device @19200 8N1 (likely CON2 light/button board).
- **Stock idle GPIO ("power-hold") state** — the board powers itself off if these aren't held: driven **LOW**: PA0, PA11, PA12, PA15, PB3, PB4. driven **HIGH**: PB5, PB13, PB14. Inputs: PB8, PB9, PB12 (EXTI/Hall), PB15 (pull-up). **PB3 driven HIGH reliably powers the board OFF** (power/enable-critical — do not drive it high).
- **I2C-ish:** PB6/PB7 have a real pull-up bus but only a non-battery sensor at addr **0x6A** lives there (regs mostly 0). The pack's SMBus is NOT on any bit-bang-reachable MCU pin we could find.
- **SWD:** PA13 (SWDIO) / PA14 (SWCLK). Our fw sets **AFIO_MAPR = 0x02000000** (SWJ_CFG=010: JTAG off, SWD on) — required, else PA15/PB3/PB4 are JTAG-locked and don't respond to GPIO writes.

### Register cheat-sheet
- TIM1 @ 0x40012C00: CR1 +0x00, CR2 +0x04, SR +0x10, CCMR1 +0x18, CCMR2 +0x1C, CCER +0x20, CNT +0x24, PSC +0x28, ARR +0x2C, CCR1 +0x34, CCR2 +0x38, CCR3 +0x3C, BDTR +0x44. Live baseline: CCMR1=0x6868, CCMR2=0x0068, CCER=0x0111, BDTR=0x8000 (MOE, no dead-time), ARR=3599 (20kHz), PSC=0.
- GPIOA @ 0x40010800, GPIOB @ 0x40010C00: CRL +0x00, CRH +0x04, IDR +0x08, ODR +0x0C, BSRR +0x10, BRR +0x14. AFIO_MAPR @ 0x40010004. RCC @ 0x40021000. ADC1 @ 0x40012400.

## 4. Firmware console command reference (current build)
- `p <ch> <pct>` — PWM ch=1/2/3 (PA8/9/10), duty 0–100. `s` — all PWM 0. `?` — print CCR values.
- `o <P><pin> <v>` — drive GPIO push-pull, e.g. `o A11 1`, `o B13 0` (P = A/B, pin 0–15).
- `i <P><pin>` — set pin input, print its level.
- `a` — read the 7 ADC channels: PA1 PA4 PA5 PA6 PA7 PB0 PB1.
- `mr <hexaddr>` — read any 32-bit register. `mw <hexaddr> <hexval>` — write any register (this is the key live-poke tool).
- `treg` — dump TIM1 CR1/CR2/SR/CCMR1/CCMR2/CCER/BDTR/CCR/ARR + AFIO_MAPR + GPIOA/B CRH.
- SMBus (bit-bang PB6/PB7): `bscan bpu ba<addr> br<cmd> brb<cmd> bblk<cmd> bw<cmd><val> bdump bdumpx bstat bka<0|1> bhb<0|1>`.
- Arbitrary-pin bit-bang I2C: `xpu <P1> <P2>` (idle levels), `xscan <P1> <P2>`, `xrd <P1> <P2> <cmd>`, `xall`. (v with `xrestore()` that re-asserts stock GPIO after each op.)

## 5. What is SOLVED
1. **RDP (flash read-protect) removed** via `openocd ... "stm32f1x unlock 0"` (mass-erase; irreversible; stock firmware gone — acceptable). Flash now writable; a debug reset reloaded option bytes (no physical power-cycle needed). Option bytes went 0xBB→0xA5.
2. **Our own bare-metal firmware runs** (register-level C, 72 MHz), reflashable at will over SWD.
3. **Full low-level control:** PWM (PA8/9/10), any GPIO, 7-ch ADC, UART console, bit-bang I2C, live register read/write (`mr`/`mw`).
4. **Power stability solved.** Earlier the board powered off after a variable 30–180 s; root cause was scan/poke commands leaving pins FLOATING, which released the power-hold latch. Firmware now re-asserts the full stock GPIO hold-state → board stays powered indefinitely (verified for many minutes). (Also: openocd resets were causing power-offs — banned from live use.)
5. **Verified pin/peripheral map** (section 3).

## 6. The debugging journey — what's been RULED OUT (firmware-only, exhaustively)
Motors never draw current. The 3 shunts (PA6/PA7/PB0) never leave ~1075 in ANY configuration. Tested live via `mr`/`mw`/`treg`:
- **MOE / break:** BDTR stays 0x8000 (MOE set) under drive; SR bit7 (break flag) = 0. Outputs enabled, no break event. ELIMINATED.
- **PWM polarity / mode:** CC1P inverted (CCER 0x0111→0x0113), OC1M=PWM2 (CCMR1→0x6878). No current. ELIMINATED.
- **Forced-DC:** OC1M/OC2M/OC3M forced-active (0b101 → constant 100% high) on each channel individually AND all three at once. No current. ELIMINATED. (This is decisive: forcing all high-sides hard-on with motors attached draws zero current.)
- **Complementary:** PB13 → TIM1_CH1N (AF), dead-time in BDTR (0x8048), CC1NE set (CCER 0x0115), drive ch1. No current. ELIMINATED.
- **Direction/enable GPIO sweep:** toggled A0/A11/A12/A15/B4 high and B13/B14/B15 low, individually, while driving and (later) while watching the rail voltage. No current, rail never rose. ELIMINATED.
- **BMS SMBus hunt:** the pack's SMBus is not on any bit-bang-reachable MCU pin (only dual-pull-up pair B15/B9 scanned empty; PB6/PB7 has only a non-pack 0x6A sensor). Concluded the pack link is not MCU-mastered.

## 7. THE KEY METER FINDINGS (this is where it stands)
Multimeter, black on GND (URT1 GND), board powered on:
- **The "100 25V UE" cap (100µF/25V, near U2/L2/buck) reads 24.1V.** → The pack DELIVERS ~24V (PWR). A buck (L2=4R7 + U2) makes the 3.3/5V logic from it (why the MCU runs). **No BMS handshake is needed to have 24V present.**
- **The motor-bridge bulk caps ("25V 330 AM" 330µF by MT-L and MT-R, e.g. silk C17) read only ~3V** (both legs ~3V; floating). Other motor-section points also ~3V.
- So **24V is present on the board but GATED before it reaches the H-bridges** — a **board-side gate**, NOT the BMS. Prime suspect: the P-channel load-switch MOSFET **Q2 ("SOP03")** near the 24V cap.
- **No GPIO opens this gate** (verified by watching the bridge-cap voltage while toggling every candidate pin — it never rose from ~3V toward 24V).

## 8. THE OPEN PROBLEM (what we need help with)
**24V is available on the board; the original H-bridges are starved because an on-board switch gates the 24V away from them, and we cannot open that switch from firmware.** We have NOT yet: (a) identified/traced the exact gate (is it Q2? what controls its gate?), (b) determined whether it can be enabled at all (GPIO combo we missed? hardware interlock? tied to a signal we haven't found?), or (c) confirmed whether the "25V 330" caps are the bridge SUPPLY node or the motor OUTPUT node (both legs reading ~3V is ambiguous — a supply bulk cap should show ~0V on its ground leg).

### Specific questions for you
1. How would you trace/identify the load switch (likely Q2/"SOP03") and what controls its gate, using: multimeter continuity (board OFF, zero risk), live voltage probing, and our `mr`/`mw` register pokes? What's the single highest-value measurement next?
2. Is there a plausible way the motor-rail switch is enabled that we haven't tried (e.g., a specific pin held while another pulses; the buck/power-good; a pin we classified as input like PB8/PB9/PB12; PB2/BOOT1; a combination)? Design concrete firmware experiments (exact `mw`/`o`/`a` sequences) and success criteria (bridge-cap voltage rising to 24V, or a shunt leaving ~1075).
3. Given "3V on both legs" of the "25V 330" caps — are these the bridge supply or the motor output? How do we tell definitively? Where is the true bridge +24V supply node (which component leg/MOSFET drain)?
4. If the gate genuinely can't be opened, what's the safest minimal-hardware way to feed the existing bridges 24V (which exact node to inject, avoiding back-feeding the pack or the 3.3/5V logic)? Risks?
5. Fallback we're leaning toward: **tap the confirmed 24V → external motor driver (L298N on hand / BTS7960 preferred) → the 2 motor-power wires; encoders (3 wires each) → Pi; common ground.** Sanity-check this plan and flag pitfalls (current limits, the L298N 78M05 5V-jumper at 24V, Pi 3.3V logic into the driver, encoder level 3V vs 5V, where to tap 24V for motor-level current without overloading a trace).

## 9. Constraints / safety
- UART + `st-flash` only for live work; NO openocd live (powers board off). Retry `st-flash` on connect failures.
- Do NOT drive PB3 high (powers board off). Keep the power-hold pins in their stock state or the board dies.
- Motors: wheels off ground; PWM ≤15% for tests.
- Board runs on the 22V pack; be careful probing the live 24V rail (single-point touches only; don't bridge two pads).
- The pack has a BMS but it delivers power fine (no handshake needed); the blocker is purely the on-board motor-rail gate.

Start by SSHing in, confirming the board is alive (`ssh npalakurla@rtk 'st-info --probe'` → chipid 0x410 means alive; if 0x000 the board is powered off and a human must long-press the power button), then `python3 ~/uartcap/cmd.py "?" 2` and `python3 ~/uartcap/cmd.py "treg" 2`. Report your plan before making destructive or irreversible changes.
