# SP5 motor bring-up — diagnostic firmware v8 results

Date: 2026-08-08

## Deployed firmware

- Source: `firmware/sp5fw/main.c`, `startup.c`, `smbus.c`
- Pi build directory: `~/sp5fw/`
- Current flashed binary SHA-256: `4454d5144930078cd11ed022ecb1a3ebf500ee775a43898c7131734f0857f906`
- Previous v6/v7 sources and binaries are preserved under `~/sp5fw/backup-v6/`
  and `~/sp5fw/backup-v7/`.

The hash above includes the corrected PA5/PA6/PA7 shunt map, in-probe PA4/PB0
telemetry, 200 ms rail precharge, rail-on shunt re-baselining, and one-sided
control isolation using index `9`.

## Important ADC correction

The old `read_adc()` did not explicitly clear EOC before starting a new
conversion. Back-to-back reads therefore returned the preceding channel's
result on this GD32. The earlier ADC labels were shifted by one channel.

After clearing EOC before every conversion, repeated stable readings are:

| MCU input | Idle count | Revised interpretation |
| --- | ---: | --- |
| PA1 / ADC1 | 0 | low/unused sense node |
| PA4 / ADC4 | 938–939 | voltage-divider or rail-sense node |
| PA5 / ADC5 | 1084–1085 | motor current sense 1 |
| PA6 / ADC6 | 1070–1072 | motor current sense 2 |
| PA7 / ADC7 | 1077–1079 | motor current sense 3 |
| PB0 / ADC8 | 8–9 | low/unused sense node |
| PB1 / ADC9 | 8 | low/unused sense node |

Consequences:

- The old statement that PA5 is the battery divider is wrong; PA4 is the
  voltage-like channel.
- The old PA6/PA7/PB0 shunt map is wrong; the three biased shunts are
  PA5/PA6/PA7.
- Historical ADC readings taken before the EOC fix must be reinterpreted with
  caution.

## v8 safeguards

- Complete captured GPIO idle state is asserted at every boot.
- PB3-high and PB5-low are rejected.
- Hold pins cannot be left floating through the normal `i` command.
- Normal PWM is capped at 15% and automatically stops after 750 ms.
- `dt` probes last at most 120 ms, monitor all three shunts, and always restore
  zero PWM plus the captured GPIO state.
- TIM1 is fully canonicalized and read back before a probe: CR1/CR2/SMCR,
  PSC/ARR/RCR/CNT, CCMR1/2, CCR1/2/3, CCER, BDTR, and PA8–PA10 AF modes.
- ADC timeout, shunt-baseline validation, UART abort, and fault-time motor
  shutdown are implemented.

## Approved stock-state tests

Commands executed:

```text
dt 9 9 1 1
dt 9 9 2 1
dt 9 9 3 1
```

Results:

| PWM channel | Duration | PA5 range | PA6 range | PA7 range | Result |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 120 ms | 1084–1085 | 1070–1072 | 1077–1079 | no measurable current |
| 2 | 120 ms | 1084–1085 | 1070–1072 | 1077–1079 | no measurable current |
| 3 | 120 ms | 1084–1085 | 1070–1072 | 1077–1079 | no measurable current |

After every test, CCR1/2/3 read `0/0/0` and TIM1 returned to the canonical
PWM1 configuration. No trip, ADC error, timer error, or persistent state change
occurred.

### Staged 2% and 5% results

All three PWM channels were subsequently tested at 2% and 5%, using isolated
UART captures so the next command could not overlap the probe's abort polling.

| Duty | PWM channel | Duration | Maximum shunt span | Result |
| ---: | ---: | ---: | ---: | --- |
| 2% | 1 | 120 ms | 2 counts | no measurable current |
| 2% | 2 | 123 ms | 2 counts | no measurable current |
| 2% | 3 | 120 ms | 2 counts | no measurable current |
| 5% | 1 | 120 ms | 2 counts | no measurable current |
| 5% | 2 | 120 ms | 2 counts | no measurable current |
| 5% | 3 | 120 ms | 2 counts | no measurable current |

The final stopped baseline was PA5=1085, PA6=1072, PA7=1079 with canonical
TIM1 state and CCR1/2/3=`0/0/0`.

One initial 2% invocation used `seq.py`, whose 300 ms per-command window raced
with `dt`'s UART abort polling and lost the result text. The controller did not
reset, its timer remained stopped, and the test was repeated successfully with
an isolated two-second `cmd.py` capture. This was a serial orchestration issue,
not an electrical trip.

## Interpretation and next gate

At 1%, 2%, and 5% duty, all three channels are electrically quiet. This rules
out stock-idle GPIO plus main-channel PWM as a working drive state. It remains
consistent with either an unpowered bridge or a missing direction/enable state.

The next staged options are:

1. Test the guarded direction-pair matrix at 1%:
   three A-side candidates (PA0/PA11/PA12) x two B-side candidates
   (PB13/PB14) x three PWM channels = 18 cases.

Both remain battery-direct tests on an incompletely traced bridge. Software ADC
monitoring is not a substitute for a fuse or hardware current limit.

## Motor-rail enable identified

The approved direction-pair work found the missing rail control. Zero-duty
classification was added so each candidate could be isolated without PWM.

| Asserted control for 200 ms | PA4 maximum | PB0 maximum | Conclusion |
| --- | ---: | ---: | --- |
| PA0 high only | 1903 | 3791 | motor rail/control supply enabled |
| PA11 high only | 943 | 91 | no rail enable |
| PA12 high only | 942 | 83 | no rail enable |
| PB13 low only | 941 | 163 | no rail enable |
| PB14 low only | 943 | 58 | no rail enable |
| PA0 high + PB13 low | 1919 | 3823 | enabled by PA0; PB13 not required |
| PA0 high + PB14 low | 1903 | 3792 | enabled by PA0; PB14 not required |

Baseline PA4 is about 938–942. PA0-high raises PA4 into the old 1770–1930
range associated with the approximately 24 V rail and raises PB0 close to full
ADC scale. When PA0 returns low, PA4 collapses quickly and PB0 decays more
slowly. This establishes PA0 as a common board-side motor-rail enable.

The three shunt amplifiers transiently shift together while the rail starts but
settle close to their original biases after a 200 ms precharge. `dt` now takes a
second, rail-on shunt baseline before applying PWM so motor current is not
confused with this startup transient.

The next highest-value drive tests were PA0-high with PB13/PB14 left at stock:

```text
dt 0 9 1 1
dt 0 9 2 1
dt 0 9 3 1
```

The operator explicitly approved these three battery-direct states and accepted
the risk of shoot-through and permanent motor-driver/board damage. All three
were then executed individually with an isolated UART capture and a separate
stopped-state check after each test.

| PWM channel | Duration | PA5 base/drive/min/max | PA6 base/drive/min/max | PA7 base/drive/min/max | PA4 base/min/max | PB0 base/min/max | Result |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| 1 | 122 ms | 1085/1087/1063/1097 | 1072/1073/1070/1105 | 1079/1078/1069/1091 | 942/2/1887 | 12/12/3761 | ok |
| 2 | 122 ms | 1085/1086/1069/1095 | 1071/1072/1070/1098 | 1079/1078/1068/1091 | 942/5/1887 | 132/132/3761 | ok |
| 3 | 121 ms | 1085/1086/1069/1094 | 1072/1072/1070/1099 | 1078/1078/1067/1090 | 942/5/1887 | 122/122/3760 | ok |

No test tripped the 120-count current guard. The largest drive-baseline to
shunt extreme was 34 ADC counts on channel 1, 27 counts on channel 2, and 27
counts on channel 3. These small excursions were similar across all three
shunts rather than being specific to the selected PWM channel. The PA4/PB0
rail signature appeared in every case, confirming PA0 rail enable, but there
was no convincing motor-current signature.

After every test and at the final readback, CCR1/2/3 was `0/0/0`. Therefore
PA0 plus a single PA8/PA9/PA10 PWM output is not by itself a complete motor
drive state. The next topology hypothesis is that PA0 must remain asserted as
the common rail enable while PA11/PA12 and/or PB13/PB14 select bridge direction.
Those simultaneous-control states are electrically distinct from the tests
above and have not been executed.

## v9 guarded-combination firmware (deployed)

Firmware v9 adds one deliberately armed command for the next topology stage:

```text
d9 ARM <aopt 0-2> <bopt 0-2> <channel 1-3> <percent 0-5>
```

PA0 is always asserted as the common rail enable. `aopt=0` adds no A-side
control, `1` adds PA11 high, and `2` adds PA12 high. `bopt=0` leaves PB13 and
PB14 at stock high, `1` lowers PB13, and `2` lowers PB14. The literal uppercase
`ARM` token and exact six-token command prevent accidental invocation by the
old diagnostic scripts.

The implementation retains the 200 ms monitored rail settle and 120 ms PWM
window, 5% cap, PA5/PA6/PA7 delta guard, PA4/PB0 telemetry, UART abort, GPIO
readback, canonical TIM1 readback, immediate motor stop, and unconditional
stock-state cleanup. v9 additionally:

- rejects numeric overflow and trailing command tokens;
- clears and verifies TIM1 DIER/SR before generating an update event;
- checks PWM samples against both the original and rail-on shunt baselines;
- accepts UART abort during the precharge interval; and
- reports the real PWM-window duration even for a zero-duty probe.

The ARM cross-build completed with no warnings:

```text
text=13792 data=20 bss=48 total=13860 bytes
sp5fw.bin sha256=33ebdf07e23d1d067c1803e7bd068accfe5c53b19dc4199c60fe6b5784eebf9e
```

The final image was written and verified by `st-flash`, then mirrored into the
workspace. Two pre-test self-check issues were found and corrected before any
new state completed: an impossible `TIM1_SR==0` invariant rejected the first
command with `TIMERERR`, and an immediate post-BSRR IDR read rejected the next
attempt with `PINERR`. Both failures occurred before the GPIO test interval or
PWM. The final image keeps TIM1 interrupts disabled/canonicalized, allows the
free-running update flag, waits briefly for loaded GPIO pads before IDR
verification, and reports observed/expected masked GPIO values.

## Approved PA0-plus-direction results

The two static states were classified at zero duty before PWM:

| Command | Duration | Maximum shunt movement | PA4 max | PB0 max | GPIO readback | Result |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `d9 ARM 1 0 1 0` (PA0+PA11) | 122 ms | 24 counts | 1887 | 3761 | A=0801, B=6000 | ok |
| `d9 ARM 2 0 1 0` (PA0+PA12) | 121 ms | 21 counts | 1887 | 3761 | A=1001, B=6000 | ok |

Both asserted the PA0 motor rail without a static-current trip. Six 1% PWM
tests then completed:

| Added control | PWM channel | Duration | PA5 base/drive/min/max | PA6 base/drive/min/max | PA7 base/drive/min/max | Result |
| --- | ---: | ---: | --- | --- | --- | --- |
| PA11 high | 1 | 122 ms | 1085/1086/1085/1098 | 1072/1072/1071/1090 | 1079/1079/1069/1080 | ok |
| PA11 high | 2 | 122 ms | 1085/1086/1085/1098 | 1072/1072/1071/1091 | 1079/1078/1069/1079 | ok |
| PA11 high | 3 | 122 ms | 1085/1086/1085/1098 | 1072/1072/1071/1090 | 1079/1079/1069/1080 | ok |
| PA12 high | 1 | 121 ms | 1085/1086/1085/1097 | 1071/1071/1071/1090 | 1079/1078/1070/1079 | ok |
| PA12 high | 2 | 121 ms | 1085/1086/1085/1098 | 1072/1072/1071/1090 | 1079/1078/1069/1080 | ok |
| PA12 high | 3 | 121 ms | 1085/1086/1085/1098 | 1072/1072/1071/1091 | 1079/1079/1069/1079 | ok |

All six retained the PA0 rail signature (PA4 maximum 1887–1888; PB0 maximum
3760–3762), but none produced a selected-channel current signature. Maximum
shunt movement from the original baseline was about 20–21 counts and appeared
as the same common startup transient seen in the zero-duty controls. Therefore
PA0 plus PA11 or PA12 plus a main PWM output is still not a complete motor-drive
state while PB13/PB14 remain at stock high.

Every test was followed by an independent status query. The final controller
state is CCR1/2/3=`0/0/0`; no trip, ADC error, persistent GPIO state, or apparent
board damage occurred.

## Approved three-control matrix results

The remaining combinations of PA0 rail enable, one added A control, and one
lowered B control were first tested at zero duty:

| aopt,bopt | Asserted state | Duration | Maximum shunt movement | PA4 max | PB0 max | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1,1 | PA0+PA11 high, PB13 low | 122 ms | 24 counts | 1888 | 3763 | ok |
| 1,2 | PA0+PA11 high, PB14 low | 122 ms | 18 counts | 1893 | 3771 | ok |
| 2,1 | PA0+PA12 high, PB13 low | 122 ms | 17 counts | 1893 | 3772 | ok |
| 2,2 | PA0+PA12 high, PB14 low | 121 ms | 20 counts | 1904 | 3794 | ok |

All four static states passed. Each pair was then tested on all three TIM1 main
PWM channels at 1%:

| aopt,bopt | PWM ch1 max shunt movement | PWM ch2 | PWM ch3 | Result |
| --- | ---: | ---: | ---: | --- |
| 1,1 | 21 counts | 18 counts | 18 counts | all ok; no channel signature |
| 1,2 | 18 counts | 18 counts | 18 counts | all ok; no channel signature |
| 2,1 | 16 counts | 17 counts | 18 counts | all ok; no channel signature |
| 2,2 | 19 counts | 18 counts | 19 counts | all ok; no channel signature |

Every test ran for 121–122 ms with the commanded/observed GPIO masks matching.
PA4 peaked at 1871–1905 and PB0 at 3730–3794, confirming the PA0-controlled
rail remained active. The small shunt movement was common across PWM channels
and comparable to the zero-duty rail transient; none is evidence of motor
current.

This completes the guarded static-control matrix using PA0/PA11/PA12 and
PB13/PB14 around single-ended PA8/PA9/PA10 PWM. No combination drives a motor
at 1%. The strongest remaining firmware hypothesis is that PB13/PB14 must be
switched from GPIO direction levels into TIM1 complementary outputs CH1N/CH2N
with dead time, rather than treated as static controls. That is a different
power-stage mode and has not been executed.

All twelve PWM probes and four zero-duty probes were followed by independent
status queries. Final state: CCR1/2/3=`0/0/0`, no trip, no ADC/timer/pin error,
no reset, and no apparent board damage.

## v10 complementary-output probe

v10 added a separately armed complementary-output test for only the two known
TIM1 N-output pairs:

```text
c10 ARM <pair 1-2> N <pct 0-1>
```

- Pair 1: PA8/TIM1_CH1 and PB13/TIM1_CH1N.
- Pair 2: PA9/TIM1_CH2 and PB14/TIM1_CH2N.
- Diagnostic timer: 5 kHz, ARR=14399, CCR=144 at 1%.
- Hardware dead time: DTG=72, approximately 1 us at 72 MHz.
- PA0 is asserted only after the complementary idle state reads PA-low/PB-high.
- CH3N/PB15 and inverted/99%-reversed states remain unsupported.

The final deployed image compiled without warnings:

```text
text=16448 data=20 bss=48 total=16516 bytes
sp5fw.bin sha256=421e1c68991898eac47b8b7ed5fb252a29b9e53ab3e9427bdeecdd47e3a8ea25
```

It canonicalizes and checks TIM1 remapping, moves nonselected main outputs to
defined GPIO-low levels during the diagnostic profile, verifies selected pin
AF modes and timer counting, transfers the preloaded CCR at a known update
boundary, monitors PA5/PA6/PA7 against both rail-off and rail-on baselines, and
restores the stock GPIO plus normal TIM1 profile on every path.

### Approved complementary results

| Command | Duration | PA5 off/on/min/max | PA6 off/on/min/max | PA7 off/on/min/max | PA4 off/min/max | PB0 off/min/max | Result |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `c10 ARM 1 N 0` | 122 ms | 1085/1086/1085/1101 | 1072/1073/1071/1097 | 1079/1078/1067/1080 | 945/4/1869 | 9/9/3725 | ok |
| `c10 ARM 2 N 0` | 122 ms | 1085/1086/1085/1098 | 1072/1072/1071/1091 | 1079/1078/1069/1080 | 944/4/1879 | 106/106/3744 | ok |
| `c10 ARM 1 N 1` | 122 ms | 1085/1086/1080/1100 | 1072/1073/1069/1093 | 1079/1078/1068/1080 | 943/4/1878 | 83/83/3741 | ok |
| `c10 ARM 2 N 1` | 121 ms | 1085/1087/1085/1098 | 1072/1073/1071/1090 | 1079/1079/1070/1080 | 946/4/1853 | 123/123/3692 | ok |

Both zero-duty complementary handoffs passed, proving the timer/pin handoff,
PA0 rail enable, current monitoring, and cleanup work. Both 1% complementary
pulses also passed, but their shunt excursions were small and comparable with
the zero-duty common rail transient. Neither pair produced a selected-current
signature or detectable motor drive.

This rules out normal-polarity CH1/CH1N and CH2/CH2N complementary pulses at
the conservative 1%/5 kHz setting. Every command was followed by an independent
status check; final CCR1/2/3=`0/0/0`, with no trip, reset, persistent GPIO state,
or apparent board damage.

## v10.1 staged 2% and 5% complementary results

v10.1 extended only the `c10` duty range and compare calculation. Values above
5% are rejected; CCR is `percent * 144` with ARR=14399. All other timer, rail,
current, abort, handoff, and cleanup guards remain unchanged.

Final deployed build:

```text
text=16440 data=20 bss=48 total=16508 bytes
sp5fw.bin sha256=08959430a2fd5ba03ab88863074f5a90baac616c9fba9bb1d6ed161a6a7fd473
```

The approved 2% probes completed before advancing to 5%:

| Command | Duration | PA5 off/on/min/max | PA6 off/on/min/max | PA7 off/on/min/max | PA4 off/min/max | PB0 off/min/max | Result |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `c10 ARM 1 N 2` | 122 ms | 1085/1087/1085/1101 | 1072/1074/1071/1096 | 1080/1079/1069/1080 | 947/5/1852 | 12/12/3692 | ok |
| `c10 ARM 2 N 2` | 122 ms | 1085/1087/1085/1098 | 1072/1073/1072/1091 | 1080/1079/1070/1080 | 947/5/1852 | 108/108/3690 | ok |
| `c10 ARM 1 N 5` | 122 ms | 1085/1086/1085/1097 | 1072/1072/1071/1089 | 1079/1079/1071/1080 | 946/3/1852 | 142/142/3690 | ok |
| `c10 ARM 2 N 5` | 122 ms | 1086/1086/1086/1096 | 1072/1072/1071/1089 | 1079/1079/1070/1080 | 947/4/1853 | 144/144/3691 | ok |

The 2% raw compare interval is 4 us (roughly 3 us effective after rising dead
time); the 5% interval is 10 us (roughly 9 us effective). Neither increase
produced a selected-channel current signature. At 5%, the largest shunt
movement was only 17 counts on pair 1 and 17 counts on pair 2, smaller than
some zero-duty rail-start transients.

This makes insufficient normal-polarity pulse width an unlikely explanation.
Normal CH1/CH1N and CH2/CH2N complementary drive through 5% has now been ruled
out under the observed PA0-enabled rail state. Final independent status:
CCR1/2/3=`0/0/0`; no trip, reset, persistent state, or apparent board damage.

## v10.2 staged 10% and 15% complementary results

v10.2 extended only the `c10` rejection limit to 15%. CCR remains
`percent * 144`, giving 1440 ticks at 10% and 2160 ticks at 15%, both against
ARR=14399. All protection and cleanup behavior is unchanged.

Final deployed build:

```text
text=16440 data=20 bss=48 total=16508 bytes
sp5fw.bin sha256=346f9004e238887184dfb2936c42cf1827bb1c093169b466dffa7cb5bac01c42
```

| Command | Duration | PA5 off/on/min/max | PA6 off/on/min/max | PA7 off/on/min/max | PA4 off/min/max | PB0 off/min/max | Result |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `c10 ARM 1 N 10` | 122 ms | 1086/1087/1086/1101 | 1072/1073/1071/1096 | 1079/1079/1068/1080 | 947/5/1852 | 14/14/3691 | ok |
| `c10 ARM 2 N 10` | 121 ms | 1086/1087/1086/1101 | 1072/1074/1072/1095 | 1079/1079/1069/1080 | 947/5/1852 | 23/23/3690 | ok |
| `c10 ARM 1 N 15` | 122 ms | 1085/1087/1085/1100 | 1072/1073/1072/1093 | 1079/1079/1070/1080 | 947/5/1853 | 82/82/3691 | ok |
| `c10 ARM 2 N 15` | 122 ms | 1085/1086/1085/1097 | 1072/1073/1071/1090 | 1079/1079/1071/1080 | 947/3/1853 | 126/126/3690 | ok |

The first pair-2 10% invocation returned only a heartbeat because the UART line
buffer desynchronized. Its following `?` parsed as `err`; an explicit `s`
returned `STOP all pwm=0`, and a fresh `?` confirmed CCR1/2/3=`0/0/0`. The exact
approved command was then retried and produced the valid result in the table.
No 15% test ran until that recovery and valid 10% result completed.

The raw compare intervals are 20 us at 10% and 30 us at 15%; after dead time,
the effective main pulses are approximately 19 us and 29 us. Neither pair
produced a motor-current signature. The maximum shunt changes remained in the
same approximately 17–24 count common rail-start range seen at zero duty.

Normal-polarity complementary output on PA8/PB13 and PA9/PB14 is now ruled out
through the project's 15% bench ceiling. Final independent status:
CCR1/2/3=`0/0/0`; no trip, reset, persistent state, or apparent board damage.

## Completion of the original 18-case direction-pair matrix

Review after the v10.2 tests found that the original approved direction-pair
matrix had been halted after the six PA0 cases. The remaining twelve PA11/PA12
x PB13/PB14 x PWM-channel cases were still covered by the operator's explicit
approval but had never executed. These were run at 1% using the current hardened
`dt` implementation.

| A high | B low | PWM channel | Maximum shunt span | PA4 range | PB0 range | Result |
| --- | --- | ---: | ---: | --- | --- | --- |
| PA11 | PB13 | 1 | 2 counts | 945–948 | 24–27 | ok |
| PA11 | PB13 | 2 | 2 counts | 945–948 | 19–22 | ok |
| PA11 | PB13 | 3 | 2 counts | 945–948 | 15–18 | ok |
| PA11 | PB14 | 1 | 2 counts | 945–948 | 13–16 | ok |
| PA11 | PB14 | 2 | 2 counts | 945–948 | 12–16 | ok |
| PA11 | PB14 | 3 | 2 counts | 945–948 | 12–15 | ok |
| PA12 | PB13 | 1 | 3 counts | 944–947 | 11–14 | ok |
| PA12 | PB13 | 2 | 2 counts | 944–947 | 11–14 | ok |
| PA12 | PB13 | 3 | 2 counts | 944–948 | 11–14 | ok |
| PA12 | PB14 | 1 | 2 counts | 944–948 | 11–13 | ok |
| PA12 | PB14 | 2 | 3 counts | 944–947 | 10–13 | ok |
| PA12 | PB14 | 3 | 3 counts | 944–947 | 10–13 | ok |

Unlike every PA0-high case, none showed the PA4/PB0 rail signature. All three
shunts stayed at their idle biases to within 1–3 counts, regardless of selected
PWM channel. This rules out the alternative direct per-motor mappings
PA11/PB13/PA9 and PA12/PB14/PA10 at 1%.

Two status captures were delayed by UART line-buffer desynchronization. In both
cases the complete preceding `DT ... ok` result had already printed; output was
paused, explicit `s` was issued until `STOP all pwm=0` acknowledged, and a
`CCR 0/0/0` status was obtained before resuming. No electrical trip or reset
occurred.

The full original 18-case direction-pair matrix is now complete. Final status:
CCR1/2/3=`0/0/0`, no trip, no persistent GPIO state, and no apparent damage.

## v11 PA0/PB5 guarded-pair results

The final plausible static pair from the stock GPIO grouping was PA0/PB5.
PB5 had previously been excluded because lowering it might release the board's
power hold. v11 added an exact armed command:

```text
p5 ARM <channel 1-3> <pct 0-1>
```

The guarded transition lowers PB5 before raising PA0, enforces PB0<=500 before
entry, requires the known PA4/PB0 rail signature, requires a successful
zero-duty qualification before accepting 1%, monitors PA5/PA6/PA7 against both
baselines, and verifies PA0-low/PB5-high plus canonical TIM1 after cleanup.
Malformed `p5` text cannot fall through to the legacy `p` command.

Final deployed build:

```text
text=17004 data=20 bss=52 total=17076 bytes
sp5fw.bin sha256=b451b123ff310689226c172f71552923ec49a1177a6b2052d233e7a8bf11d5f6
```

| Command | Duration | PA5 base/drive/min/max | PA6 base/drive/min/max | PA7 base/drive/min/max | PA4 base/min/max | PB0 base/min/max | Result |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| `p5 ARM 1 0` | 121 ms | 1085/1086/1085/1101 | 1072/1073/1071/1096 | 1079/1079/1071/1080 | 947/5/1852 | 18/18/3690 | ok |
| `p5 ARM 1 1` | 122 ms | 1085/1086/1085/1101 | 1072/1073/1072/1096 | 1079/1079/1070/1080 | 947/5/1851 | 24/24/3690 | ok |
| `p5 ARM 2 1` | 122 ms | 1085/1087/1085/1100 | 1072/1074/1072/1094 | 1079/1079/1068/1080 | 947/4/1851 | 59/59/3689 | ok |
| `p5 ARM 3 1` | 122 ms | 1085/1087/1085/1101 | 1072/1073/1072/1095 | 1079/1079/1071/1080 | 947/3/1851 | 41/41/3689 | ok |

PB5-low did not remove controller power during any 321–322 ms guarded state.
All commands showed the same PA0-associated PA4/PB0 transition, but none showed
a PWM-channel-specific current signature. PA0/PB5 is therefore not a working
motor-control pair at 1%.

Final independent status: CCR1/2/3=`0/0/0`; PA0/PB5 cleanup verified; no trip,
reset, persistent state, or apparent board damage.
