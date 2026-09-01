# Domain and Simulation Specification

This document defines the minimum electronics model needed for the hackathon implementation.

The application should feel like a small electronics lab, but it must remain intentionally constrained.

---

## 1. Supported component set

### Required

| Component | Internal type | Parameters | Pins |
|---|---|---|---|
| Ground | `ground` | none | `gnd` |
| Resistor | `resistor` | `resistance_ohm` | `a`, `b` |
| Capacitor | `capacitor` | `capacitance_f` | `a`, `b` |
| Inductor | `inductor` | `inductance_h` | `a`, `b` |
| Voltage source | `voltage_source` | mode-specific | `positive`, `negative` |
| Diode | `diode` | `model` | `anode`, `cathode` |
| Ideal op-amp | `ideal_opamp` | `gain`, optional rails | `plus`, `minus`, `out`, optional rails |

### Optional

- NPN BJT
- NMOS

Do not add optional components until every required component has end-to-end tests.

---

## 2. Value conventions

The API stores values in SI base units.

Examples:

```json
{
  "resistance_ohm": 10000,
  "capacitance_f": 1e-7,
  "frequency_hz": 1000,
  "voltage_v": 3.3
}
```

The UI may display engineering notation such as `10 kΩ` or `100 nF`.

Do not store `"10k"` as canonical data.

---

## 3. Node model

A node is an electrical connection shared by one or more component pins.

Examples:

```text
R1.a -> vin
R1.b -> out
C1.a -> out
C1.b -> gnd
```

All ground connections map to SPICE node `0`.

All other nodes are sanitized to alphanumeric names.

---

## 4. Circuit validation

Run validation before every simulation.

Required checks:

### Graph checks
- at least one ground node exists,
- every non-ground component pin is connected,
- duplicate component IDs are impossible,
- component values are valid and finite,
- voltage source positive and negative pins are not identical,
- no unknown component types,
- component count is within challenge limit.

### Domain checks
- resistance > 0,
- capacitance > 0,
- inductance > 0,
- source frequencies >= 0,
- no NaN or infinity,
- safe upper and lower bounds to prevent pathological simulator input.

Suggested limits:

```text
Resistance: 1e-3 Ω to 1e12 Ω
Capacitance: 1e-15 F to 10 F
Inductance: 1e-12 H to 1e3 H
Voltage magnitude: <= 1e4 V
Frequency: <= 1e10 Hz
```

These are software safety limits, not educational claims.

---

## 5. Netlist generation

### Deterministic naming

Generate SPICE names from component IDs.

```text
resistor R1 -> R1
capacitor C3 -> C3
voltage source V1 -> V1
```

Reject IDs that cannot be safely normalized.

---

## 6. Minimal resistor divider example

Circuit:

```text
V1 5V
 |
 R1 1k
 |
 +---- out
 |
 R2 1k
 |
GND
```

Generated netlist:

```spice
* generated circuit
V1 vin 0 DC 5
R1 vin out 1000
R2 out 0 1000

.op
.end
```

Expected output voltage:

```text
V(out) ≈ 2.5 V
```

This circuit is the first backend smoke test.

---

## 7. RC low-pass example

```spice
* RC low pass
V1 in 0 AC 1
R1 in out 1000
C1 out 0 1e-7

.ac dec 50 10 100000
.end
```

Expected behavior:

```text
cutoff ≈ 1591.5 Hz
gain near 10 Hz ≈ 0 dB
gain far above cutoff becomes increasingly negative
```

Do not require exact floating-point matches in tests.

---

## 8. Transient example

```spice
V1 in 0 PULSE(0 1 0 1u 1u 10m 20m)
R1 in out 1000
C1 out 0 1e-6

.tran 10u 50m
.end
```

Expected behavior:
- output rises exponentially,
- output does not instantly jump to input,
- measured rise time is positive.

---

## 9. Supported analyses

### Operating point

Use for:
- node DC voltages,
- branch currents,
- checking bias,
- diagnosing saturation-like conditions.

API concept:

```json
{
  "analysis": "operating_point"
}
```

Output:

```json
{
  "node_voltages_v": {
    "vin": 0.1,
    "out": 1.2
  }
}
```

---

### AC analysis

Use for:
- frequency response,
- gain,
- cutoff frequency,
- bandwidth,
- attenuation.

Input:

```json
{
  "start_hz": 10,
  "stop_hz": 100000,
  "points_per_decade": 50,
  "input_node": "vin",
  "output_node": "out"
}
```

Output:
- frequency vector,
- output magnitude,
- gain in dB,
- optional phase.

---

### Transient analysis

Use for:
- clipping,
- response time,
- rise time,
- overshoot,
- settling,
- max/min voltage.

Input:

```json
{
  "duration_s": 0.05,
  "time_step_s": 0.00001,
  "output_nodes": ["out"]
}
```

---

### Parameter sweep

Optional after MVP.

Use for:
- varying one component value,
- testing sensitivity,
- helping agent gather evidence.

Example:

```json
{
  "component_id": "R1",
  "parameter": "resistance_ohm",
  "values": [1000, 2200, 4700, 10000],
  "analysis": {
    "type": "ac",
    "start_hz": 10,
    "stop_hz": 100000
  }
}
```

---

## 10. ngspice execution

Recommended MVP integration:

```text
Circuit JSON
   ↓
netlist_service.py
   ↓
temporary .cir file
   ↓
ngspice batch subprocess
   ↓
machine-readable output file
   ↓
parser
   ↓
structured SimulationResult
```

Do not begin with the ngspice shared library.

A subprocess is easier to debug and isolate.

---

## 11. Subprocess safety

Every simulation:

1. creates an isolated temporary directory,
2. writes only generated netlist files,
3. runs an allowlisted executable,
4. uses no shell expansion,
5. applies a strict timeout,
6. limits request sizes,
7. kills runaway processes,
8. deletes temporary files,
9. never accepts arbitrary SPICE text from the agent.

Pseudo-code:

```python
subprocess.run(
    ["ngspice", "-b", "-o", "stdout.log", "circuit.cir"],
    cwd=temp_dir,
    timeout=5,
    check=False,
    capture_output=True,
    text=True,
)
```

Do not call with `shell=True`.

---

## 12. Parsing strategy

Prefer generating `.control` blocks that write selected vectors to files in a predictable format.

Example concept:

```spice
.control
run
wrdata ac.csv frequency vdb(out)
quit
.endc
```

The exact ngspice syntax should be verified during implementation with a local smoke test.

The application parser should output normalized arrays.

---

## 13. Measurement engine

The simulator returns raw vectors.

The measurement engine turns those into facts useful to the agent.

### `measure_voltage`

Input:
- node,
- simulation.

Return:
- DC voltage or transient min/max.

### `measure_gain`

For AC analysis:

```text
gain_db = 20 * log10(|Vout / Vin|)
```

At requested frequency, interpolate between adjacent points.

Return:

```json
{
  "frequency_hz": 1000,
  "gain_db": -0.92
}
```

### `measure_cutoff_frequency`

Definition for MVP:

1. determine low-frequency reference gain,
2. target = reference gain - 3 dB,
3. find first descending crossing,
4. linearly interpolate around crossing.

Return null if no crossing exists.

### `measure_bandwidth`

MVP:
- use -3 dB points,
- return upper bandwidth for low-pass style circuits.

### `measure_rise_time`

MVP definition:
- calculate time from 10% to 90% of final transition.

### `measure_max_voltage`

Return maximum simulated output voltage.

### `measure_min_voltage`

Return minimum simulated output voltage.

### `measure_overshoot`

```text
overshoot_percent =
(max_value - final_value) / abs(final_value - initial_value) * 100
```

Only calculate when denominator is meaningful.

---

## 14. Constraint engine

Supported operators:

```text
<
<=
>
>=
between
approximately
```

Example:

```json
{
  "id": "output_safe",
  "metric": "max_output_voltage_v",
  "operator": "<=",
  "target": 3.3
}
```

Evaluation:

```json
{
  "constraint_id": "output_safe",
  "status": "PASS",
  "actual": 3.12,
  "target": 3.3,
  "message": "Maximum output voltage is within the 3.3 V limit."
}
```

All challenge evaluation must be deterministic backend logic.

The agent should not decide whether a numeric requirement passed.

---

## 15. Experiment record

```json
{
  "id": "exp_009",
  "sequence": 9,
  "created_at": "2026-08-29T20:00:00Z",
  "hypothesis": "The previous stage filters too aggressively. Raise the cutoff while preserving gain.",
  "circuit_revision": 14,
  "circuit_snapshot": {},
  "simulation_ids": ["sim_91", "sim_92"],
  "measurements": {},
  "constraint_results": [],
  "agent_conclusion": "Response time improved, but high-frequency attenuation is now insufficient."
}
```

`hypothesis` and `agent_conclusion` are optional text provided by the agent.

Physics and measurements remain simulator-derived.

---

## 16. Ideal op-amp implementation

Use a deliberately simplified model for the MVP.

Option A:
- voltage-controlled voltage source with large gain,
- optional clamp behavior implemented with rails if easy.

Option B:
- small subcircuit with high gain and output limits.

The goal is not professional op-amp accuracy.

The UI must label it:

> Idealized Op-Amp

This prevents implying manufacturer-level fidelity.

---

## 17. Diode implementation

Use either:
- a simple built-in diode model,
- or one fixed app-owned model.

Do not let users upload arbitrary SPICE models during the hackathon.

---

## 18. Golden simulation tests

The backend must include these golden tests.

### Test A: divider

Input:
- 5 V,
- two equal resistors.

Expected:
- out close to 2.5 V.

### Test B: RC cutoff

Input:
- R = 1 kΩ,
- C = 100 nF.

Expected:
- cutoff close to 1591 Hz.

### Test C: RC step

Input:
- R = 1 kΩ,
- C = 1 µF,
- step 0 to 1 V.

Expected:
- rise time roughly consistent with RC behavior,
- no instantaneous output jump.

### Test D: invalid circuit

Input:
- resistor with missing connection.

Expected:
- validation error before ngspice runs.

### Test E: no ground

Expected:
- validation error before ngspice runs.

---

## 19. Simulator abstraction

Define an interface so ngspice can be replaced later.

```python
class Simulator:
    def operating_point(self, circuit): ...
    def ac(self, circuit, config): ...
    def transient(self, circuit, config): ...
```

Implementation:

```python
class NgspiceSimulator(Simulator):
    ...
```

Do not let route handlers directly invoke subprocesses.

---

## 20. Failure handling

Expected failures are product features.

Return machine-readable errors:

```text
INVALID_CIRCUIT
NO_GROUND
FLOATING_PIN
UNSUPPORTED_COMPONENT
SIMULATION_TIMEOUT
SIMULATION_FAILED
NO_CONVERGENCE
MEASUREMENT_UNAVAILABLE
EXPERIMENT_BUDGET_EXHAUSTED
COMPONENT_LIMIT_EXCEEDED
STALE_REVISION
```

The agent must be able to react to these failures without scraping logs.
