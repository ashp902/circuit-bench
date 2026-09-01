# Implementation Phases

This is the execution plan for a coding agent.

The agent should complete one phase at a time and run its acceptance tests before continuing.

---

## Global rule

Do not build the UI first.

The critical technical risk is:

```text
Circuit JSON
  → SPICE netlist
  → ngspice
  → parsed structured output
  → measurements
```

Prove that loop before spending time on polish.

---

## Phase 0: Project bootstrap
**Target:** 1 to 2 hours

### Tasks

- Create monorepo structure.
- Bootstrap Next.js frontend.
- Bootstrap FastAPI backend.
- Add `/health` endpoint.
- Add frontend page that confirms backend connectivity.
- Add `.env.example`.
- Add lint/test scripts.
- Add basic CI.
- Add Docker support only if ngspice installation requires it.

### Required commands

Backend:

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run lint
npm run test
npm run dev
```

### Acceptance criteria

- frontend loads,
- backend `/health` returns 200,
- frontend can call backend,
- tests run in one command,
- README contains exact local setup commands.

Do not continue until this works.

---

## Phase 1: Prove ngspice integration
**Target:** 2 to 3 hours

### Goal

From Python, run one hardcoded circuit and obtain one known measurement.

### Tasks

1. Install/locate ngspice.
2. Create `scripts/verify_ngspice.py`.
3. Generate the 5 V divider netlist.
4. Run ngspice batch mode.
5. Parse `V(out)`.
6. Assert approximately 2.5 V.
7. Add timeout and failure handling.

### Acceptance test

```bash
python scripts/verify_ngspice.py
```

Expected:

```text
ngspice: OK
divider output: 2.500 V
PASS
```

If this phase fails, do not build any agent functionality.

---

## Phase 2: Canonical circuit model
**Target:** 2 hours

### Tasks

Implement Pydantic models for:

- Circuit,
- Node,
- Component,
- Challenge,
- Constraint,
- SimulationResult,
- Experiment.

Implement component validators.

Implement:
- add component,
- remove component,
- create node,
- connect,
- disconnect,
- set parameter.

Add revision checking.

### Tests

- add resistor,
- invalid resistance rejected,
- connect pin,
- duplicate ID rejected,
- stale revision rejected,
- component limit rejected,
- missing ground detected,
- floating pin detected.

### Acceptance criteria

```bash
pytest backend/tests/test_circuit_model.py
```

All green.

---

## Phase 3: Netlist generator and simulator service
**Target:** 3 to 4 hours

### Tasks

Implement:

```text
Circuit JSON
  ↓
NetlistBuilder
  ↓
NgspiceSimulator
  ↓
SimulationResult
```

Support:
- resistor,
- capacitor,
- inductor,
- voltage source,
- ground.

Add diode and op-amp only after core analyses work.

Implement:
- operating point,
- AC,
- transient.

### Tests

Golden circuits:

1. voltage divider,
2. RC low pass,
3. RC step response.

### Acceptance criteria

One Python test creates Circuit JSON, not raw SPICE, and obtains:

```text
divider output ≈ 2.5 V
RC cutoff ≈ 1.59 kHz
transient rise time > 0
```

---

## Phase 4: Measurement and constraint engine
**Target:** 2 to 3 hours

### Implement measurements

Required:
- DC voltage,
- maximum voltage,
- minimum voltage,
- gain at frequency,
- cutoff frequency,
- rise time.

Nice to have:
- bandwidth,
- overshoot,
- settling time.

### Implement constraint operators

```text
<
<=
>
>=
between
approximately
```

### Acceptance test

Given a known RC circuit:

```text
constraint: cutoff between 1400 and 1800 Hz
```

Expected:

```text
PASS
```

Given:

```text
constraint: cutoff <= 500 Hz
```

Expected:

```text
FAIL
```

The agent must never be responsible for this numeric decision.

---

## Phase 5: Backend API and experiment state
**Target:** 2 to 3 hours

### REST endpoints

Suggested:

```text
GET    /api/lab
GET    /api/circuit
POST   /api/components
PATCH  /api/components/{id}
DELETE /api/components/{id}
POST   /api/nodes
POST   /api/connections
DELETE /api/connections
POST   /api/validate
POST   /api/simulations/op
POST   /api/simulations/ac
POST   /api/simulations/transient
POST   /api/constraints/evaluate
GET    /api/experiments
POST   /api/experiments
POST   /api/experiments/{id}/restore
```

### Persistence

SQLite tables:

```text
labs
circuits
experiments
simulations
```

For speed, circuit snapshots may be stored as JSON.

### Acceptance criteria

A clean API-only integration test performs:

```text
create challenge
→ edit circuit
→ run AC simulation
→ evaluate constraints
→ save experiment
→ restore experiment
```

No frontend involved.

---

## Phase 6: WebMCP surface
**Target:** 2 to 3 hours

### Implement exact semantic tools

Start with:

```text
get_lab_state
get_circuit
get_constraints
add_component
create_node
connect
set_component_value
remove_component
validate_circuit
run_operating_point
run_ac_analysis
run_transient
measure_voltage
measure_gain
measure_cutoff_frequency
measure_rise_time
evaluate_constraints
save_experiment
list_experiments
restore_experiment
```

### Tool test

Use a mock agent or direct tool invocation.

Required scripted flow:

```text
get_circuit
add resistor
create node
connect
validate
run AC
measure gain
save experiment
```

### Acceptance criteria

The complete flow must work without clicking the human UI.

---

## Phase 7: Minimal shared UI
**Target:** 4 to 5 hours

### Build only these panels

```text
┌──────────────┬────────────────────────────┬──────────────┐
│ Goal         │ Circuit Canvas             │ Results      │
│ Constraints  │                            │ Measurements │
│ Budget       │                            │ Graph        │
├──────────────┴────────────────────────────┴──────────────┤
│ Experiment Timeline                                    │
└─────────────────────────────────────────────────────────┘
```

### Required UI functions

- component tray,
- add component,
- delete component,
- edit value,
- connect pins,
- run simulation manually,
- see graph,
- see constraints,
- see experiment count,
- see experiment history,
- restore experiment.

### Sync behavior

Use either:
- polling every 500 to 1000 ms,
- WebSocket,
- SSE.

For a hackathon, polling is acceptable if smooth enough.

### Acceptance criteria

When the agent changes a component through WebMCP, the human canvas reflects it automatically.

When the human changes a value, the agent's stale revision is rejected.

---

## Phase 8: Challenge templates
**Target:** 2 to 3 hours

Implement exactly three.

### Challenge A: Filter Design

Simplest demo.

Goal:
- pass low frequencies,
- attenuate high frequencies,
- component limit.

### Challenge B: Sensor Interface

Flagship.

Goal:
- amplify weak signal,
- reduce high-frequency noise,
- remain inside ADC voltage limits,
- meet response constraint,
- component limit.

### Challenge C: Debug Amplifier

Start from an intentionally bad circuit.

Goal:
- diagnose clipping or bad gain,
- fix without violating another requirement.

### Acceptance criteria

Each challenge has:
- starting state,
- human-readable prompt,
- machine-readable constraints,
- experiment budget,
- at least one known valid solution.

---

## Phase 9: Agent loop validation
**Target:** 2 to 4 hours

Run the real agent against each challenge.

Do not manually fix its circuit during testing unless evaluating collaboration.

Record:
- experiments used,
- invalid actions,
- simulator failures,
- whether constraints pass,
- time to completion.

### Required reliability target

At minimum:

```text
Filter challenge: 4/5 successful autonomous runs
Sensor challenge: 3/5 successful autonomous runs
Debug challenge: 3/5 successful autonomous runs
```

If reliability is lower:
- simplify starting circuit,
- clarify tool descriptions,
- improve error messages,
- reduce ambiguous component choices.

Do not add solver shortcuts.

---

## Phase 10: Demo polish
**Target:** remaining time

Priority order:

1. reliability,
2. visible agent actions,
3. graphs,
4. timeline,
5. visual polish,
6. optional features.

### Add visual activity feed

Example:

```text
Experiment 4
Hypothesis: output stage is clipping.
Changed R3: 10 kΩ → 4.7 kΩ
Ran transient analysis.
Max output: 3.71 V → 3.18 V
Constraint "ADC safe": FAIL → PASS
```

This is more valuable than fancy canvas styling.

---

# 2-day compressed schedule

## Day 1 morning

```text
Phase 0
Phase 1
Phase 2
```

## Day 1 afternoon/evening

```text
Phase 3
Phase 4
Phase 5
```

By end of Day 1:

> API-only autonomous circuit experiments must be technically possible.

---

## Day 2 morning

```text
Phase 6
Phase 7
```

## Day 2 afternoon

```text
Phase 8
Phase 9
```

## Day 2 evening

```text
Phase 10
record demo
deploy
```

---

# 3-day safer schedule

### Day 1
Simulation engine and backend.

### Day 2
WebMCP, UI, challenge templates.

### Day 3
Agent reliability, polish, deployment, recording.

---

# Cut list if behind schedule

Cut in this exact order:

```text
1. Monte Carlo
2. parameter sweep
3. transistor
4. experiment comparison
5. inductor
6. diode
7. manual connection dragging polish
8. Debug challenge
```

Do not cut:
- real ngspice,
- agent circuit mutation,
- AC simulation,
- transient simulation,
- measurement engine,
- constraint evaluation,
- experiment history,
- Sensor Interface flagship demo.

---

# Stop conditions for coding agent

At the end of every phase, output:

```text
PHASE N COMPLETE

Implemented:
- ...

Tests:
- command
- result

Known issues:
- ...

Next phase:
- ...
```

Do not claim a phase is complete with failing tests or placeholder TODOs in its required scope.
