# Second-opinion request: repurposing a pool-cleaner robot's control board — stuck on a BMS-gated motor rail

You are an expert in embedded systems, ARM Cortex-M bring-up, battery-management systems (SMBus/Smart Battery), and motor-driver hardware. I've spent a long session reverse-engineering a salvaged pool-cleaner control board and I'm stuck at one specific wall. Below is the complete context and everything I've already tried and ruled out. **Please poke holes in my conclusions and suggest anything — software or minimal-hardware — I might have missed to get the drive motors running. Be skeptical and concrete.**

---

## 1. What I'm trying to build
Repurpose a cordless **pool-cleaner robot** into an autonomous **RTK-GPS-guided ground rover** (later possibly a robot lawnmower). It will NOT operate in water. Phase 1 goal: drive a differential-drive chassis (two brushed DC gear-motors, left + right) under control of a Raspberry Pi 4 running an RTK navigation stack. I want to reuse the robot's existing main board, its H-bridges, its Li-ion battery pack, and its motors if at all possible.

## 2. Hardware on the bench
- Raspberry Pi 4 (the brain; I run everything over SSH from it).
- ST-Link/V2 (SWD programmer/debugger) wired to the board's SWD port.
- USB-TTL serial adapter (CP210x) wired to the board's debug UART.
- The donor board, fully torn down. Three motors currently connected (Left, Right, Pump), wheels off the ground for testing.
- A multimeter (I've been trying to avoid using it, but it's available).

## 3. The donor board & MCU
- Board silkscreen: **"SP5-MAIN VER:1.2"**, dated 2023.11.14, UL E224772.
- Center MCU is a 48-pin LQFP. Probing identified it as a **GigaDevice GD32F103CB** (a clone of the STM32F103; ARM Cortex-M3 r2p1, reports device id 0x410, rev 0x1303, runs a GD32-specific 108 MHz clock tree in stock firmware). 64–128 KB flash, 20 KB SRAM.
- Connectors (from silkscreen, Chinese labels translated):
  - **URT1** = SWD port (VDD·CLK·GND·DIO) — labeled "Download port"
  - **CON1** = UART console (5V·RX·TX·GND) — labeled "Debug port" — this is USART2 on the MCU
  - **CON2** = secondary UART (VDD·TX·RX·GND) — "light/BT board" — this is USART3
  - **CON3** = power button + status-LED daughterboard (KEY·DAT·CLK)
  - **BATTERY** = smart battery pack: **GND·SCL·SDA·PWR·VDD** (note: **VDD and PWR are separate pins**)
  - **MT-L / MT-R / MT-P** = Left drive motor / Right drive motor / Pump motor
- Power stage: big D-PAK MOSFETs (T1–T4…) + R020/R050 shunt resistors = brushed-DC H-bridges with current sensing. Several SOT-23 transistors (Q1–Q9) as gate level-shifters. Two SOIC-8 ICs (U5/U6) that appear to be current-sense amplifiers (they sit in the analog section next to the ADC pins, with paired gain resistors), not gate drivers. Piezo buzzer on-board.
- **Battery pack:** 6S2P Li-ion smart pack, **22.2 V nominal / 25.2 V full charge, 5.2 Ah, 115 Wh**, with an internal BMS. The pack talks I²C/SMBus to the board over the BATTERY connector's SCL/SDA pins.

## 4. What I've accomplished (solved)
1. **Read protection defeated.** The MCU shipped with flash read-protection (RDP level 1) active. I cleared it via a mass-erase (`openocd ... stm32f1x unlock 0`), which is irreversible and wiped the stock firmware (acceptable — I don't need pool-cleaner behavior). Flash is now writable.
2. **I run my own bare-metal firmware** on the MCU (register-level C, GD32F103 = STM32F103 registers, Cortex-M3, HSE 8 MHz → PLL 72 MHz). I flash it via `st-flash --reset write ... 0x08000000`.
3. **Full low-level control**, exposed as an interactive command console over the CON1 UART (USART2 @115200 8N1):
   - Generate PWM on the three motor-drive pins (TIM1 CH1/CH2/CH3 = PA8/PA9/PA10), any duty.
   - Drive/read any GPIO.
   - Read the 7 ADC sense channels (PA1, PA4, PA5, PA6, PA7, PB0, PB1).
   - A bit-bang I²C/SMBus master on arbitrary pin pairs, with an address scanner and a robust ACK discriminator (rejects stuck-line false positives via pull-up gate, run-length gate, neighbor-NAK gate, and SDA-release gate).
4. **Power stability solved.** The board kept powering off after a variable 30–180 s. Root cause: my scan/poke commands left GPIO pins floating, which released the firmware "power-hold" latch. The stock idle state actively drives **PA0, PA11, PA12, PA15, PB3, PB4 push-pull LOW** and **PB5, PB13, PB14 HIGH**; releasing any of these lets the pack cut the rail. My firmware now re-asserts the complete stock GPIO hold-state after every operation → the board now stays powered indefinitely (verified stable for 2000+ seconds). (Also: never use openocd for live pokes — its reset halts the core and drops the hold, powering the board off. UART + st-flash only.)
5. **Verified peripheral/pin map** (from a capture of the stock firmware's running state before I erased it, plus live probing):
   - **Motor PWM:** TIM1, ~15–20 kHz, single-ended, on PA8/PA9/PA10 (one channel per motor; MOE set; verified the PWM physically reaches the pins by sampling GPIO IDR).
   - **Current sense:** ADC1 scans 7 channels; the **three motor-current shunts are PA6/PA7/PB0** (bidirectional sense amps, idle-biased to ~1075 counts = zero current). PA5 ≈ 1770 counts = a battery-voltage divider (reads the ~22 V pack, scaled).
   - **UARTs:** USART2 = PA2/PA3 (CON1 console). USART3 = PB10/PB11 (stock ran a real device here at 19200 8N1 — probably the CON2 light/button board).
   - **Sensors:** EXTI on PB8/PB9/PB12 (Hall/limit inputs).
   - Only GPIO ports A and B are used (complete pin map for a 48-pin part).

## 5. The hard blocker (where I'm stuck)
**The drive motors never draw any current, because the motor supply rail is switched off.**

- With my firmware replicating the **complete stock GPIO state** (every power-hold pin exactly as the stock firmware drove them) and PWM applied to any/all of the three channels at 12–15% duty, the three current-sense shunts (PA6/PA7/PB0) **never move from their ~1075 zero-current bias.** No current, no motion. (I confirmed there is no shoot-through or fault — the shunts are simply flat.)
- Because I reproduced the stock GPIO state exactly and still get zero current, the problem is **not** a missing GPIO enable line. The H-bridges have **no supply voltage** — the **PWR (motor) rail is switched off.**
- The BATTERY connector has separate **VDD** (logic rail — this is why the MCU runs) and **PWR** (high-current motor rail). The pack's BMS gates the PWR rail through its discharge FET. In the stock robot, the firmware presumably tells the BMS (over SMBus) to close the discharge FET so the motor rail comes alive. **I need to reproduce that handshake, but I cannot find the pack's SMBus on the MCU.**

### Why I can't reach the BMS (SMBus search — exhausted):
- The pack's SCL/SDA must connect to two MCU GPIOs that have external pull-ups (SMBus requires pull-ups on both lines).
- I did a pull-up survey of every candidate pin: **only PB15 and PB9 have stable pull-ups on both lines.** All other candidates (PA0, PA11, PA12, PA15, PB3, PB4, PB8) have no pull-ups → cannot be an I²C bus. PB12 was dynamic (a Hall input).
- I scanned **PB15/PB9** (both role orders) with the robust discriminator → **no device (empty).**
- The MCU's hardware-I²C1 default pins **PB6/PB7** *do* have a bus with pull-ups, but the only device there is at address **0x6A**, and it is **not the battery** — its registers read mostly zero (0x00=0x05, 0x01=0x7C, 0x02=0x20, 0x17=0x01; standard SBS registers like Voltage 0x09, RelativeStateOfCharge 0x0D, BatteryStatus 0x16 all read 0). Looks like a small sensor/config chip, not a 22 V smart pack.
- The standard Smart Battery address **0x0B NAKs 100%** of the time on the PB6/PB7 bus and everywhere else I can drive.
- Conclusion I've reached (and three separate AI models independently agreed): **the pack's SMBus SCL/SDA do not route to any MCU pin I can bit-bang.** They likely go to a different chip on the board, or the routing isn't where I expect. Determining this looks like it requires a multimeter continuity check (BATTERY SCL/SDA → wherever they actually land) and/or the board schematic.

## 6. Constraints / preferences
- I strongly prefer a solution that keeps reusing this board + pack (Strategy B). The fallback (Strategy A) is to give up on the smart pack and drive the two motors from the Pi with an external motor driver (e.g., BTS7960) powered by a separate plain battery — guaranteed to work but throws away the integrated pack/BMS.
- I can flash arbitrary firmware and bit-bang any protocol on any MCU pin. I have a multimeter (willing to use it now) but no schematic and the IC laser markings are unreadable in photos.
- Everything runs over SSH on the Pi; the MCU has SWD + a UART console.

## 7. My questions for you
1. **Is my conclusion that the motor rail is BMS-gated and requires an SMBus handshake correct**, or is there a more likely explanation for three brushed H-bridges showing zero shunt current despite correct PWM and a fully-replicated stock GPIO state? (E.g., an onboard load-switch / gate-driver supply I haven't considered, a charge-pump rail, a hardware interlock, high-side gate-drive bootstrap that never primes, etc.)
2. **Smart-battery packs of this class (6S, SMBus/SBS):** what's the usual mechanism that keeps the discharge FET closed and enables the high-current output? Is it typically (a) a continuous host SMBus poll/keepalive, (b) a specific ManufacturerAccess/OperationStatus command to close the FET, (c) just the physical button/PWR-enable line, or (d) simply current draw above a threshold? Any known BetterPower / generic Chinese 6S BMS behaviors?
3. **Given the pack SMBus isn't on the MCU pins I can find** — where would you expect SCL/SDA from the BATTERY connector to actually go on a board like this? Could a separate BMS-interface chip (or the CON2/light-board MCU) be the SMBus master, with my main MCU never talking to the pack directly? How would I confirm that quickly with a multimeter (which exact continuity checks)?
4. **Is there any way to bring up the motor rail without the pack's cooperation** — e.g., is the PWR rail likely just the pack's switched output (so nothing on my board can enable it), or could there be an on-board P-FET/enable I could drive? How would I tell them apart with a meter?
5. If you agree it's genuinely blocked at the pack, **what's the minimal-hardware path** to still reuse the motors + board (e.g., inject an external 22 V supply onto the H-bridge rail past the BMS gate; or which two nodes to bridge)? What are the risks?
6. Anything else you'd try, in the order you'd try it.

Please be concrete and challenge my assumptions. Thank you.
