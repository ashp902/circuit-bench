# Passive anti-aliasing filter — verified result

## Final circuit

`V1 (1 V AC) -> R1 (1 kΩ) -> N002 -> R2 (100 kΩ) -> VOUT`.

`C1 = 68 nF` connects from `N002` to ground and `C2 = 1 nF` connects from `VOUT` to ground.  V1 negative is grounded.  The named source/output nets are `VIN` and `VOUT`.

## Nominal simulator evidence

Real ngspice AC simulation at the required frequencies gave:

| Metric | Result | Requirement | Status |
|---|---:|---:|---|
| Gain at 500 Hz | -0.615141 dB | >= -0.75 dB | PASS |
| Gain at 10 kHz | -28.925000 dB | <= -25 dB | PASS |
| First -3 dB cutoff | 1.20 kHz | report-only | measured in laboratory |

## Capacitor tolerance experiment

The preserved laboratory experiment **Final passive anti-aliasing filter tolerance sweep** uses 25 ngspice-backed runs: C1 = 61.2, 64.6, 68.0, 71.4, 74.8 nF and C2 = 0.90, 0.95, 1.00, 1.05, 1.10 nF.

The independently reproducible exact-frequency sweep (`python3 scripts/verify_passive_filter.py`) found:

| Worst-case metric across all 25 combinations | Result | Requirement | Status |
|---|---:|---:|---|
| Lowest 500 Hz gain | -0.738144 dB | >= -0.75 dB | PASS |
| Highest 10 kHz gain | -27.174000 dB | <= -25 dB | PASS |

All 25 laboratory runs completed with zero simulator errors. The script prints every recorded tolerance combination and its two frequency gains.

## Revision history

An initial wiring attempt placed C1 in series with the signal path. Its AC response did not provide adequate 10 kHz attenuation and it was retained only as a failed, earlier experiment. The final revision moves C1 to the first-stage shunt position and was re-simulated and re-swept.
