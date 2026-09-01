# WebMCP and Agent Specification

This document defines the semantic tool surface exposed to AI agents.

The purpose of WebMCP in this product is to let an agent operate the same laboratory a human sees.

---

## 1. Core rule

Expose **engineering actions**, not UI gestures.

Bad:

```text
click_add_button()
drag_node()
open_simulation_modal()
press_run()
```

Good:

```text
add_component()
connect()
run_ac_analysis()
measure_gain()
```

---

## 2. What the agent should decide

The agent owns:

- interpreting the user's goal,
- deciding what circuit topology to try,
- selecting component values,
- deciding which experiment to run,
- choosing what measurement matters,
- diagnosing failures,
- deciding what to change next,
- deciding when evidence is sufficient.

---

## 3. What backend code should decide

Backend owns:

- circuit validity,
- electrical simulation,
- measurements,
- constraint pass/fail,
- component limits,
- experiment budget,
- persistence,
- concurrency/version control.

---

## 4. Tools that must NOT exist

Do not create:

```text
design_filter()
design_sensor_interface()
optimize_circuit()
solve_challenge()
fix_circuit()
choose_best_topology()
choose_next_experiment()
auto_tune()
```

If such a function exists, too much reasoning has moved out of the agent.

---

## 5. Tool surface

### Inspection

#### `get_lab_state`

Purpose:
Return challenge, circuit, remaining budget, and latest experiment summary.

Input:

```json
{}
```

Output:

```json
{
  "challenge": {},
  "circuit": {},
  "remaining_experiments": 9,
  "latest_experiment": {}
}
```

---

#### `get_circuit`

Input:

```json
{}
```

Output:

```json
{
  "id": "ckt_123",
  "revision": 7,
  "components": [],
  "nodes": []
}
```

---

#### `get_component`

Input:

```json
{
  "component_id": "R1"
}
```

Errors:
- `COMPONENT_NOT_FOUND`

---

#### `get_constraints`

Returns exact machine-readable challenge requirements.

---

#### `list_experiments`

Input:

```json
{
  "limit": 20
}
```

Return compact summaries, not full waveform data.

---

## 6. Circuit mutation tools

All mutation tools accept `expected_revision`.

This prevents agent edits from overwriting a human edit that occurred after the agent last inspected the lab.

### `add_component`

Input:

```json
{
  "type": "resistor",
  "params": {
    "resistance_ohm": 10000
  },
  "expected_revision": 7
}
```

Output:

```json
{
  "component": {
    "id": "R3",
    "type": "resistor"
  },
  "new_revision": 8
}
```

Errors:
- `INVALID_PARAMETER`
- `UNSUPPORTED_COMPONENT`
- `COMPONENT_LIMIT_EXCEEDED`
- `STALE_REVISION`

---

### `remove_component`

Input:

```json
{
  "component_id": "R3",
  "expected_revision": 8
}
```

---

### `set_component_value`

Input:

```json
{
  "component_id": "R1",
  "parameter": "resistance_ohm",
  "value": 4700,
  "expected_revision": 9
}
```

Only allow parameters defined for that component type.

Never allow arbitrary SPICE strings.

---

### `connect`

Input:

```json
{
  "component_id": "R1",
  "pin": "b",
  "node_id": "out",
  "expected_revision": 10
}
```

If node does not exist, support either:
- explicit `create_node`, or
- `connect` with `new_node_label`.

Preferred MVP: provide `create_node`.

---

### `create_node`

Input:

```json
{
  "label": "filter_out",
  "expected_revision": 10
}
```

---

### `disconnect`

Input:

```json
{
  "component_id": "R1",
  "pin": "b",
  "expected_revision": 11
}
```

---

## 7. Circuit validation

### `validate_circuit`

Input:

```json
{}
```

Output:

```json
{
  "valid": false,
  "issues": [
    {
      "code": "FLOATING_PIN",
      "severity": "error",
      "component_id": "C2",
      "pin": "b",
      "message": "C2.b is not connected."
    }
  ]
}
```

This tool does not consume experiment budget.

---

## 8. Simulation tools

A completed simulation consumes one experiment only when saved or, alternatively, every run may consume budget.

For hackathon clarity, use this rule:

> Every successful simulator execution consumes one experiment.

Validation failures do not consume budget.

---

### `run_operating_point`

Input:

```json
{
  "output_nodes": ["out"]
}
```

Output:

```json
{
  "simulation_id": "sim_1",
  "remaining_experiments": 9,
  "node_voltages_v": {
    "out": 1.52
  }
}
```

---

### `run_ac_analysis`

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

```json
{
  "simulation_id": "sim_2",
  "remaining_experiments": 8,
  "summary": {
    "low_frequency_gain_db": 19.8,
    "peak_gain_db": 20.1
  }
}
```

The default tool response should omit full waveform arrays unless explicitly requested through a dedicated visualization/data endpoint.

---

### `run_transient`

Input:

```json
{
  "duration_s": 0.05,
  "time_step_s": 0.00001,
  "output_nodes": ["out"]
}
```

---

### `run_parameter_sweep`

Optional.

Do not implement until core demos are stable.

---

## 9. Measurement tools

Measurement tools operate on an existing simulation and do not consume budget.

### `measure_voltage`

```json
{
  "simulation_id": "sim_3",
  "node": "out",
  "mode": "max"
}
```

Modes:
- `dc`
- `max`
- `min`
- `final`

---

### `measure_gain`

```json
{
  "simulation_id": "sim_2",
  "input_node": "vin",
  "output_node": "out",
  "frequency_hz": 500
}
```

Return:

```json
{
  "frequency_hz": 500,
  "gain_db": -0.73
}
```

---

### `measure_cutoff_frequency`

```json
{
  "simulation_id": "sim_2",
  "input_node": "vin",
  "output_node": "out"
}
```

---

### `measure_rise_time`

```json
{
  "simulation_id": "sim_3",
  "node": "out"
}
```

---

### `measure_overshoot`

Same pattern.

---

## 10. Constraint tools

### `evaluate_constraints`

Input:

```json
{
  "simulation_ids": ["sim_2", "sim_3"]
}
```

Output:

```json
{
  "all_pass": false,
  "passed": 3,
  "failed": 1,
  "results": [
    {
      "constraint_id": "max_voltage",
      "status": "PASS",
      "actual": 3.1,
      "target": 3.3
    },
    {
      "constraint_id": "hf_rejection",
      "status": "FAIL",
      "actual": -16.7,
      "target": -20
    }
  ]
}
```

If a constraint cannot be evaluated because the necessary simulation is missing:

```json
{
  "status": "NOT_EVALUATED",
  "required_analysis": "ac"
}
```

This helps the agent decide what experiment it still needs.

---

## 11. Experiment tools

### `save_experiment`

Input:

```json
{
  "hypothesis": "Increasing the filter order should improve 10 kHz attenuation.",
  "simulation_ids": ["sim_8"],
  "conclusion": "High-frequency rejection improved, but passband loss is now too large."
}
```

Output:

```json
{
  "experiment_id": "exp_5"
}
```

---

### `restore_experiment`

Input:

```json
{
  "experiment_id": "exp_3",
  "expected_revision": 18
}
```

Restoring creates a new circuit revision.

Never erase future history.

---

### `compare_experiments`

Optional but useful.

Return:
- changed components,
- changed measurements,
- changed constraint status.

---

## 12. WebMCP naming rules

Names must:
- use verbs,
- describe domain actions,
- remain stable,
- avoid implementation details.

Descriptions should teach the agent when to call them.

Bad description:

> Runs AC.

Good description:

> Simulates the circuit over a frequency range. Use this when you need to understand gain, attenuation, cutoff frequency, or bandwidth.

---

## 13. Recommended agent system instruction

Use this as the base instruction for the demo agent:

```text
You are operating a virtual electronics laboratory.

Your job is to satisfy the user's engineering goal by conducting experiments.

Rules:
1. Inspect the current lab and constraints before editing.
2. Do not claim a circuit works until simulator measurements support the claim.
3. Treat failed experiments as evidence.
4. Prefer small, explainable changes between experiments.
5. Respect component and experiment limits.
6. If the user edits the circuit, re-read the current circuit before continuing.
7. Use validation before simulation after structural changes.
8. Use the appropriate analysis for the question:
   - operating point for DC bias,
   - AC analysis for frequency behavior,
   - transient analysis for time behavior and clipping.
9. Stop when all constraints pass or the experiment budget is exhausted.
10. When finished, explain the final circuit and the evidence supporting it.
```

---

## 14. Human-agent collaboration behavior

The UI must allow this sequence:

```text
Agent edits circuit
       ↓
Human sees edit live
       ↓
Human manually changes R2
       ↓
Circuit revision increments
       ↓
Agent's next stale edit is rejected
       ↓
Agent calls get_circuit
       ↓
Agent adapts to human change
```

This is important.

Do not silently auto-merge concurrent circuit changes.

---

## 15. Tool errors

Every tool error should have:

```json
{
  "error": {
    "code": "STALE_REVISION",
    "message": "Circuit changed since revision 14.",
    "recovery_hint": "Call get_circuit and retry using the latest revision."
  }
}
```

Useful codes:

```text
STALE_REVISION
COMPONENT_NOT_FOUND
NODE_NOT_FOUND
INVALID_PARAMETER
UNSUPPORTED_COMPONENT
COMPONENT_LIMIT_EXCEEDED
EXPERIMENT_BUDGET_EXHAUSTED
INVALID_CIRCUIT
SIMULATION_FAILED
SIMULATION_TIMEOUT
MEASUREMENT_UNAVAILABLE
```

---

## 16. Keep the agent context small

Do not send:
- giant waveform arrays,
- raw ngspice logs,
- full experiment snapshots,
- UI geometry.

Send:
- circuit graph,
- challenge constraints,
- summary measurements,
- concise failure messages.

The frontend can fetch full vectors separately for charts.

---

## 17. Agent-visible vs UI-only state

### Agent-visible

- components,
- electrical connections,
- values,
- constraints,
- experiment history,
- measurements,
- simulation summaries,
- remaining budget.

### UI-only

- x/y canvas coordinates,
- panel sizes,
- color theme,
- animation settings,
- chart zoom.

Do not pollute agent tools with presentation state.

---

## 18. WebMCP MVP priority

Implement in this order:

```text
1. get_lab_state
2. get_circuit
3. get_constraints
4. add_component
5. create_node
6. connect
7. set_component_value
8. remove_component
9. validate_circuit
10. run_operating_point
11. run_ac_analysis
12. run_transient
13. measure_voltage
14. measure_gain
15. measure_cutoff_frequency
16. measure_rise_time
17. evaluate_constraints
18. save_experiment
19. list_experiments
20. restore_experiment
```

If time is tight, `compare_experiments`, parameter sweeps, and Monte Carlo are cut first.
