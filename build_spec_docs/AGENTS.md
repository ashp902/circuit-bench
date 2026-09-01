# AGENTS.md
## Coding Agent Execution Instructions

You are implementing the Autonomous Virtual Electronics Lab described in the specification files in this repository.

Read these files in order before writing code:

```text
00_MASTER_SPEC.md
01_DOMAIN_AND_SIMULATION.md
02_WEBMCP_AND_AGENT.md
03_IMPLEMENTATION_PHASES.md
04_UI_UX_SPEC.md
05_TEST_AND_DEMO.md
```

---

## 1. Primary objective

Deliver a working hackathon MVP where:

```text
Human or AI agent
      ↓
edits shared circuit
      ↓
real ngspice simulation
      ↓
structured measurements
      ↓
constraint evaluation
      ↓
experiment history
```

The flagship demo is Sensor Interface.

---

## 2. Implementation priority

Follow `03_IMPLEMENTATION_PHASES.md`.

Do not reorder the work unless a dependency makes the documented order impossible.

Highest technical priority:

```text
Circuit JSON → ngspice → measurements
```

Highest product priority:

```text
Agent edit → visible canvas update → simulation → failed constraint → agent adapts
```

---

## 3. Non-negotiable rules

### Rule A: Do not fake physics

Simulation results must come from ngspice.

Do not hardcode challenge outputs.

### Rule B: Do not create solver shortcuts

Do not implement:
- `solve_challenge`,
- `design_filter`,
- `optimize_circuit`,
- `fix_circuit`,
- equivalent hidden logic.

The AI agent must reason using primitive domain tools.

### Rule C: Backend is canonical state

Frontend and WebMCP both call the same backend state layer.

### Rule D: Protect against stale writes

Every mutation must use circuit revisions.

### Rule E: Validate before simulation

Invalid circuits should produce structured validation errors.

### Rule F: Keep the scope narrow

Do not add PCB editing, large component libraries, or advanced semiconductor models unless the documented MVP is complete and tested.

---

## 4. Development protocol

For each phase:

1. Read the phase.
2. Implement only required scope.
3. Add tests.
4. Run tests.
5. Fix all failures.
6. Record completion.
7. Proceed.

At phase completion, report:

```text
PHASE N COMPLETE

Implemented:
- ...

Tests run:
- ...

Result:
- ...

Known limitations:
- ...

Files changed:
- ...
```

Do not report completion if required tests fail.

---

## 5. Code quality rules

### Python

- use type hints,
- use Pydantic models,
- avoid untyped dictionaries inside core domain logic,
- isolate subprocess logic,
- no `shell=True`,
- structured exceptions.

### TypeScript

- strict TypeScript,
- shared API types,
- no `any` except temporary integration boundaries,
- component state should not duplicate backend canonical state unnecessarily.

### General

- small modules,
- deterministic IDs in tests,
- clear error codes,
- no giant utility files,
- no premature abstraction.

---

## 6. Required backend service boundaries

Implement approximately:

```text
CircuitService
NetlistService
SimulationService
MeasurementService
ConstraintService
ExperimentService
```

WebMCP handlers should call these services.

REST handlers should call these services.

Do not duplicate logic.

---

## 7. Required domain errors

Use stable codes:

```text
STALE_REVISION
COMPONENT_NOT_FOUND
NODE_NOT_FOUND
INVALID_PARAMETER
UNSUPPORTED_COMPONENT
COMPONENT_LIMIT_EXCEEDED
EXPERIMENT_BUDGET_EXHAUSTED
INVALID_CIRCUIT
NO_GROUND
FLOATING_PIN
SIMULATION_FAILED
SIMULATION_TIMEOUT
MEASUREMENT_UNAVAILABLE
```

Every error response includes:
- code,
- short message,
- recovery hint when useful.

---

## 8. Required test commands

Create scripts so these commands work from repo root:

```bash
make test
make lint
make dev
```

If Make is not desired, provide equivalent documented scripts.

Minimum backend:

```bash
pytest
```

Minimum frontend:

```bash
npm run lint
npm run test
```

---

## 9. Do not block on perfect UI wiring

If professional schematic connection editing becomes expensive, use explicit electrical node hubs.

Example:

```text
R1.b → node "out"
C1.a → node "out"
```

Correct electrical state is more important than perfect visual wires.

---

## 10. ngspice spike is mandatory

Before building UI or WebMCP, prove:

```text
Python
→ generated divider netlist
→ ngspice
→ parsed V(out)
→ assertion near 2.5 V
```

If ngspice is unavailable in deployment environment:
1. document the issue,
2. containerize backend if possible,
3. do not replace it with hardcoded simulation.

---

## 11. WebMCP implementation

Expose semantic tools defined in `02_WEBMCP_AND_AGENT.md`.

Tool handlers should be thin.

Example:

```text
WebMCP add_component
   ↓
CircuitService.add_component
   ↓
persist
   ↓
return DTO
```

Do not include chart geometry or frontend coordinates in the semantic tool response.

---

## 12. Agent context discipline

Agent should receive:
- objective,
- constraints,
- component list,
- circuit structure,
- measurements,
- concise experiment summaries.

Agent should not receive:
- giant waveform arrays,
- raw ngspice logs,
- frontend layout state.

---

## 13. Demo data

Create seed fixtures for:

```text
filter_design
sensor_interface
debug_amplifier
```

Each must have:
- challenge JSON,
- starting circuit JSON,
- documented known valid solution,
- tests confirming a valid solution exists.

The agent is not given the known solution.

It exists only to ensure challenge solvability.

---

## 14. Known solution policy

Known solutions may exist in test fixtures.

They must never be returned by production API or WebMCP tools.

Their purpose is regression testing only.

---

## 15. Experiment budget

Every successful ngspice simulation decrements challenge budget by one.

Validation does not.

Measurements on an existing simulation do not.

Restoring an experiment does not.

When budget reaches zero:
- simulation tools return `EXPERIMENT_BUDGET_EXHAUSTED`,
- inspection and history remain available.

---

## 16. Concurrency policy

Every mutation request includes:

```json
{
  "expected_revision": 14
}
```

If current revision is 15:

```text
STALE_REVISION
```

Do not automatically merge.

This is required for human-agent collaboration.

---

## 17. UI synchronization

Preferred:
- WebSocket or SSE.

Acceptable hackathon fallback:
- polling every 750 ms.

Requirement:
agent WebMCP edit must become visible without manual page refresh.

---

## 18. Definition of implementation success

Before stopping, demonstrate through automated tests or a reproducible script:

```text
1. load Sensor Interface
2. inspect lab
3. mutate circuit
4. validate
5. run simulation
6. calculate measurements
7. evaluate constraints
8. save experiment
9. make another change
10. restore previous experiment
```

Then demonstrate the same state visually in the UI.

---

## 19. If time is running out

Cut features using the order in `03_IMPLEMENTATION_PHASES.md`.

Do not cut the simulator-backed agent loop.

A smaller complete system is preferable to a large partial one.

---

## 20. Final delivery requirements

Before declaring the project done:

```text
[ ] local setup documented
[ ] ngspice dependency documented
[ ] all required tests pass
[ ] frontend build passes
[ ] backend starts cleanly
[ ] challenge seed data works
[ ] WebMCP tools documented
[ ] Sensor demo rehearsed
[ ] Filter fallback rehearsed
[ ] no hardcoded simulation results
[ ] no hidden solve endpoint
```

Produce a final `README.md` for judges containing:

```text
What it is
Why WebMCP matters
How it works
Architecture
How to run
Demo prompts
Known limitations
```
