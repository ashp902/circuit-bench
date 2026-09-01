# Virtual Electronics Laboratory — Project Source of Truth

**Status:** Current implementation reference  
**Last reviewed:** 2026-09-01

**Audience:** product, design, engineering, QA, and WebMCP integrators

This document defines what the application is, what it currently does, the boundaries it deliberately keeps, and the facts future work must preserve. It describes the running implementation—not a wish list. When a conflict exists, the precedence order is:

1. Runtime behavior and passing tests.
2. Backend models, services, and API contracts.
3. This document.
4. Historical build prompts and design documents in `build_spec_docs/`.

## 1. Product definition

Virtual Electronics Laboratory is a **human-first virtual laboratory for small analog circuits**. It lets an engineer build or inspect a circuit, use real ngspice analyses, record measured evidence, run repeatable parameter-sweep experiments, and produce a traceable technical record.

It is engineering software, not a generic dashboard, circuit calculator, PCB editor, or AI chat application. The interface is intentionally built around three workspaces:

| Workspace | Primary job |
| --- | --- |
| **Workbench** | Build, inspect, validate, simulate, and measure a circuit. |
| **Experiments** | Define a repeatable parameter sweep, execute its run matrix, and inspect results. |
| **Reports** | Open the reproducible report generated from an executed experiment. |

The system also exposes an optional WebMCP tool surface so a compatible external agent can use the same laboratory state. WebMCP is an integration capability; it is **not** an AI/chat feature in the human product UI.

## 2. Product principles

- **Physics is measured, not guessed.** ngspice performs the circuit analysis; the application stores the resulting measurements and evidence.
- **Humans remain in control.** The visual workbench is fully usable without WebMCP.
- **One canonical circuit per anonymous Lab.** The backend owns each browser session's circuit state and increments a revision after every accepted mutation.
- **Evidence is preserved.** An executed experiment is read-only so its circuit snapshot, run matrix, conditions, timestamps, and results remain reproducible.
- **Technical clarity over decoration.** The visual language favors compact panels, structured property rows, engineering units, subtle borders, and dense readable data.

### Anonymous session ownership

Circuit Bench has no login or account system. On first use, the backend creates an isolated Lab and associates it with a cryptographically random, opaque browser cookie. The cookie is HttpOnly, uses SameSite=Lax, is Secure in production, and has a sliding 30-day lifetime. Only a SHA-256 digest of the bearer token is persisted.

Every Workbench circuit, saved circuit, simulation, experiment, report, and WebMCP invocation resolves through that request's Lab. Two browsers may therefore use the same local IDs such as `circuit_001` or `exp_001` without sharing data. Session identity is intentionally absent from public REST payloads and WebMCP tool schemas. Clearing the cookie starts a new blank Lab; there is no account recovery mechanism.

## 3. Supported laboratory domain

### Components

The circuit model supports the following primitive components:

- Ground
- Resistor
- Capacitor
- Inductor
- Independent voltage source: DC, sine, or pulse modes
- Diode using a built-in SPICE model
- Ideal op-amp / simplified high-gain controlled source

Component availability is constrained by the active challenge. Each component has explicit supported pins and parameters; the backend rejects unsupported values, pins, or component types.

The application opens to an unsaved **blank Workbench** with only the Ground reference, no components, the full supported component library, no acceptance criteria, and the same validation and simulation tools as a challenge circuit. Selecting **New Circuit** immediately creates and saves `New Circuit`; later circuits use `New Circuit 1`, `New Circuit 2`, and so on only when that name is already taken. A circuit name is edited directly in the Workbench toolbar. All accepted edits are persisted automatically; an edited challenge template becomes a saved circuit on its first change. There is no human-facing Save action. The project switcher lists saved circuits with a delete control. Deleting the open circuit returns the Workbench to the unsaved blank state without deleting other saved circuits or experiment history.

Blank circuits do not assume Input or Output nets. Direct terminal-to-terminal wiring automatically creates or reuses electrical nets named `N001`, `N002`, and so on. A non-ground net can be renamed in the inspector (for example, `N002` to `VOUT`). Ground remains the special ngspice electrical reference. Challenge templates may still provide semantic input/output nodes in their metadata.

### Analyses and measurements

The workbench and WebMCP backend support:

- DC operating-point analysis
- AC frequency sweep analysis
- Transient analysis
- Voltage measurements: DC, maximum, minimum, and final value
- Actual ngspice component/branch current: DC, maximum, minimum, and final value
- AC gain measurement at a requested frequency
- First descending -3 dB cutoff-frequency measurement
- 10–90% rise-time measurement
- Deterministic evaluation of challenge constraints from existing simulation evidence

Simulation is unlimited for both the human workbench and WebMCP. Validation and post-processing measurements are likewise unrestricted.

### Current challenge templates

| Challenge | Intended work | Component limit |
| --- | --- | ---: |
| Sensor Interface | Make a weak/noisy 10 Hz sensor signal useful and safe for a 3.3 V ADC. | 10 |
| Filter Design | Preserve the useful 500 Hz band and reject 10 kHz noise. | 6 |
| Debug Amplifier | Diagnose and correct excessive non-inverting amplifier gain. | 7 |

Challenge constraints, allowed components, and the starting circuit are loaded from the backend catalog. Loading a challenge replaces the active lab with that template.

## 4. Human application capabilities

### 4.1 Workbench

The Workbench is the primary circuit editor. It currently provides:

- A component library filtered by the active challenge.
- A pan-able, zoomable schematic canvas with fit-to-circuit control.
- Add, select, move, rotate, duplicate, and delete component interactions.
- Canonical component position and rotation persisted with the circuit and experiment snapshot; reopening or restoring preserves the recorded schematic layout.
- Schematic routing that follows terminal geometry, avoids component bodies where possible, and displays non-junction wire crossings as bridge bumps.
- Selectable, renameable electrical nets and component terminals; drag terminals to wire another terminal directly or attach to an existing named net.
- Visible terminal hit targets of at least 18×18 px, full component-body selection, inspector disconnect controls, junction dots, crossing bridge bumps, and floating-pin validation.
- A properties inspector with editable component values and engineering numeric/unit inputs.
- A selected-net voltage probe and selected-component branch-current probe for quick simulation measurements.
- Circuit validation, visible wiring issues, and error notices.
- Undo/redo for backend circuit mutations using revision-safe circuit snapshots (`Ctrl/⌘ Z`, `Ctrl/⌘ Shift Z`, and toolbar controls).
- Quick operating-point, AC-sweep, and transient controls in the instruments area and the matching primary Run action in the toolbar. These initiate the same selected analysis, not different kinds of run.
- A collapsible results/instruments panel for measurements, waveforms, console output, and acceptance criteria.

### 4.2 Experiments

An experiment is a named, circuit-revision-bound test definition. The builder supports:

- Name, purpose/description, type, operator (`Run by`), free-form notes/comments, and optional named collection.
- Up to **two** swept numeric component parameters.
- Linear, logarithmic, and explicit-value sweeps.
- A generated Cartesian run matrix with individual enabled/disabled runs.
- A maximum of **5,000 planned runs**.
- Per-run measurements: Output Voltage, AC Gain, and/or actual component branch current.
- Optional requirements using minimum, maximum, between, or target ± tolerance conditions.
- Draft/save and Save-and-Run workflows.
- Pause, resume, and stop controls while an experiment is active.
- Experiment list grouping by `collection_name`; a collection is currently a name-based grouping, not an independently managed entity.
- Duplicate and delete actions. A duplicate is a new experiment definition and is the supported way to repeat a completed experiment.

### 4.3 Traceability and execution history

Traceability is part of the experiment record. An execution records:

- The saved circuit snapshot and circuit revision under test.
- Experiment creation time.
- Execution start and completion times.
- The manual `Run by` value and experiment notes/comments.
- Every generated run’s index, enabled configuration, parameter values, status, start time, end time, copied operator and notes, measurements, requirements, and first simulation error when applicable.

An experiment with any recorded `run_results` is immutable. This prevents edits to a configuration after evidence is captured.

**Important current behavior:** an executed experiment cannot be run again. Running a past experiment does **not** append a new trace to it; the backend returns `EXPERIMENT_ALREADY_EXECUTED`. Use **Duplicate** to create a fresh definition and a new independent trace. Multi-execution history under one experiment definition is not implemented yet.

### 4.4 Reports and analysis

- Only experiments with recorded runs appear in Reports.
- A report is derived from the executed experiment and its stored circuit snapshot, run records, measurements, and requirement results.
- The application also provides an analysis view for an executed experiment before opening its report.
- Restoring an experiment or an individual run’s parameterized circuit creates the next circuit revision; it does not overwrite existing circuit history.

## 5. Terminology

| Term | Meaning |
| --- | --- |
| **Circuit** | The currently active electrical model: components, nodes, metadata, and revision. |
| **Revision** | Monotonically increasing circuit version used to prevent stale writes. |
| **Node / net** | A named electrical connection shared by one or more component pins. |
| **Probe** | A selected net for voltage or selected component for branch current in a Workbench simulation. |
| **Simulation** | One ngspice analysis result with an ID, series data, measurements, warnings, and errors. |
| **Challenge** | A constrained starting circuit, allowed component set, component limit, and acceptance criteria. |
| **Experiment definition** | Saved test plan bound to one circuit revision and snapshot. |
| **Generated run** | One parameter combination in an experiment’s planned matrix. |
| **Run result** | The immutable execution record for one generated run. |
| **Collection** | A user-entered name that visually groups experiments. It is not a separate persisted collection object. |
| **Report** | The reproducible technical view of an experiment with recorded runs. |

## 6. Canonical data and architecture

```text
Human Workbench UI ─┐
                    ├─> anonymous cookie ─> request-scoped LabService ─> SQLite Lab state
WebMCP integration ─┘                                      │
                                                           ├─> validation/revision checks
                                                           ├─> netlist generator + ngspice
                                                           └─> measurements + constraints
```

### Ownership rules

- **Backend / SQLite is canonical.** The frontend is a client and refreshes from API responses plus lightweight invalidation polling.
- Circuit-changing requests include `expected_revision`. A mismatched revision is rejected with `STALE_REVISION`; callers must refresh and retry deliberately.
- Anonymous session mappings, circuits, experiment definitions, simulation results, and snapshots are persisted in SQLite (`backend/lab.db` by default, configurable with `LAB_DB_PATH`).
- Component `position {x, y}` and `rotation` are part of the backend `Circuit` model, saved circuits, undo/redo snapshots, and experiment snapshots. Electrical topology depends only on nodes and pins, never visual position.
- The open UI polls canonical state every 2 seconds in Workbench, every 4 seconds in other idle workspaces, and every 750 ms while an experiment is active; focus and visibility changes also trigger refresh. This makes human and WebMCP changes visible without manual reload while avoiding high-frequency idle polling.
- ngspice is invoked by backend simulation services; the application does not use a custom electrical solver.

### Main implementation areas

| Area | Responsibility |
| --- | --- |
| `frontend/components/LabWorkbench.tsx` | Workspace state, backend operations, and navigation between workbench/experiments/reports. |
| `frontend/components/CircuitCanvas.tsx` | Interactive schematic layout, interaction, rotation, and display routing. |
| `frontend/components/ExperimentBuilder.tsx` | Experiment setup and run-matrix planning. |
| `backend/app/api/routes.py` | REST contract used by the browser. |
| `backend/app/services/` | Circuit mutation, netlist generation, simulation, measurement, constraints, challenges, and experiment execution. |
| `backend/app/db/repository.py` | SQLite persistence. |
| `backend/app/webmcp/tools.py` | WebMCP semantic tool registry. |

## 7. WebMCP tools and capabilities

### What WebMCP is in this project

The browser can register the backend tool definitions with a compatible `document.modelContext` implementation. The frontend obtains tool definitions from `GET /api/webmcp/tools`, registers them, and forwards invocations to `POST /api/webmcp/invoke`.

Every registered tool is a thin semantic wrapper around the **same request-scoped `LabService` and canonical Lab state** used by REST. The browser's HttpOnly cookie selects that Lab automatically; tool inputs never accept a session identifier. Therefore WebMCP-created circuit edits appear in that browser's human Workbench, and revision-safe mutations protect human changes from stale external writes without exposing another visitor's data.

WebMCP availability depends on the host browser’s experimental model-context implementation. The human application does not require it.

### Tool catalogue

| Tool | Access | Capability |
| --- | --- | --- |
| `get_lab_state` | Read | Get the active challenge, canonical circuit, and latest experiment. |
| `list_challenges` | Read | List the available challenge templates and engineering goals. |
| `load_challenge` | Write | Replace the active lab with a public challenge template. |
| `create_blank_circuit` | Write | Create a blank circuit with only Ground. Without a supplied name, it uses the human `New Circuit` naming sequence. |
| `list_saved_circuits` | Read | List named saved circuits available to open. |
| `rename_circuit` | Write | Rename the active circuit while retaining automatic persistence. |
| `open_saved_circuit` | Write | Open a saved circuit as the browser session's active workbench circuit. |
| `delete_saved_circuit` | Write | Delete a saved circuit; deleting the active one returns that session's workbench to the blank landing state. |
| `reset_lab` | Write | Replace the active challenge and circuit using the same reset service as the human UI. |
| `get_circuit` | Read | Get components, named nodes, pin connections, values, and current revision. |
| `get_constraints` | Read | Get machine-evaluated requirements for the active challenge. |
| `add_component` | Write | Add one allowed component with deterministic automatic placement; callers may optionally supply a position. |
| `create_node` | Write | Optionally create a named electrical net with `expected_revision`. |
| `rename_net` | Write | Rename an existing non-ground net without changing its stable identity or topology. |
| `connect` | Write | Attach a component pin to an existing node with `expected_revision`. |
| `connect_pins` | Write | Connect two component pins and automatically create, reuse, or merge their electrical net. |
| `disconnect` | Write | Detach a component pin from its node with `expected_revision`. |
| `set_component_value` | Write | Change one supported component parameter with `expected_revision`. |
| `remove_component` | Write | Remove one component with `expected_revision`. |
| `restore_circuit` | Write | Restore a supplied circuit snapshot as the next revision without rewinding history. |
| `validate_circuit` | Read | Validate ground, pins, values, limits, and graph integrity before simulation. |
| `run_operating_point` | Write | Run an ngspice DC operating-point analysis for requested nodes and component currents. |
| `run_ac_analysis` | Write | Run an ngspice AC analysis with requested input/output nodes and component currents. |
| `run_transient` | Write | Run an ngspice transient analysis with requested output nodes and component currents. |
| `measure_voltage` | Read | Derive DC/max/min/final voltage from a stored simulation. |
| `measure_current` | Read | Derive DC/max/min/final actual branch current from a stored simulation. |
| `measure_gain` | Read | Interpolate AC gain in dB at a requested frequency from a stored AC simulation. |
| `measure_cutoff_frequency` | Read | Find the first descending -3 dB cutoff from a stored AC simulation. |
| `measure_rise_time` | Read | Measure 10–90% rise time from a stored transient simulation. |
| `evaluate_constraints` | Read | Evaluate challenge constraints using one to twenty stored simulations. |
| `create_experiment` | Write | Create a circuit-revision-bound experiment definition and snapshot. |
| `get_experiment` | Read | Get one experiment definition and metadata without a full circuit snapshot or full generated-run matrix. |
| `list_experiments` | Read | Return concise saved experiment records, newest first (1–100). |
| `update_experiment` | Write | Update an unexecuted definition’s metadata, sweeps, measurements, requirements, and generated run enablement. |
| `get_experiment_plan` | Read | Preview sweep definitions, representative generated runs, readiness, and validation issues before execution. |
| `run_experiment` | Write | Start the exact same experiment execution path as the human UI. |
| `pause_experiment` / `resume_experiment` / `stop_experiment` | Write | Control an active experiment through the shared execution service. |
| `get_experiment_results` | Read | Get concise execution/range/error summaries and a paginated result slice. |
| `get_experiment_run` | Read | Get one run’s parameters, measurements, requirement outcomes, status, errors, and timestamps. |
| `get_experiment_analysis` | Read | Get deterministic tested ranges, pass/fail summary, measurement ranges, response data, and requirement analysis. |
| `get_report` | Read | Get structured report data derived from the recorded experiment, snapshot, setup, results, and reproducibility metadata. |
| `export_report` | Read | Return the executed experiment report as real JSON content. |
| `export_run_data` | Read | Return the executed experiment’s recorded runs as real CSV content. |
| `duplicate_experiment` | Write | Create a new independent definition for repeating a completed experiment. |
| `delete_experiment` | Write | Delete a non-active experiment definition and its recorded results. |
| `restore_experiment` | Write | Restore a saved experiment circuit snapshot as a new circuit revision. |
| `restore_experiment_run` | Write | Restore one run’s parameterized circuit as a new circuit revision. |

### WebMCP contract rules

- Inputs are validated by Pydantic schemas; unknown input fields are rejected.
- Write tools that mutate a circuit require `expected_revision`; callers should read the current circuit before applying a change.
- Simulation, measurement, and constraint tools have no quota or budget limit.
- `save_current_circuit` and the legacy `save_experiment` shortcut are intentionally not public WebMCP tools. Automatic circuit persistence and the explicit create/update/plan/run experiment lifecycle are unambiguous replacements.
- WebMCP has full semantic parity with the supported human experiment lifecycle: create/update/plan/run/control/inspect/duplicate/delete/restore. It calls the same experiment service and preserves the same experiment immutability and no-rerun behavior.
- `get_experiment_plan` and `get_experiment_results` are paginated (offset plus a bounded representative/run slice) so a large sweep does not force a massive default response. `get_experiment_run` provides the full detail for one recorded run.
- `get_experiment_analysis` and `get_report` return deterministic structured data based only on recorded evidence; neither produces speculative narrative conclusions.
- `export_report` and `export_run_data` return report JSON and run CSV content directly. They do not create fake download URLs.
- It does not contain a hidden `solve`, design, optimize, or repair tool. Any external agent must inspect, change, simulate, measure, and evaluate explicitly.

## 8. REST API capability map

The browser uses the `/api` endpoints as follows:

- **Lab and challenge:** inspect active lab, list templates, load a template, reset the lab.
- **Circuit:** inspect/restore circuit; add, change, move, rotate, and remove components; create/rename nets; connect/disconnect pins; validate.
- **Simulation:** operating point, AC, transient, voltage/current measurement, and constraint evaluation.
- **Experiments:** list/save legacy snapshots; create, update, execute, pause, resume, stop, duplicate, delete, and restore experiment definitions; restore a completed run’s parameterized circuit.
- **WebMCP:** list tool definitions and invoke a named tool.

The API uses structured `CircuitError` responses. `STALE_REVISION` maps to HTTP 409, not-found errors map to HTTP 404, and other domain validation errors map to HTTP 422.

### Human-to-WebMCP parity matrix

Presentation-only actions—panning/zooming the canvas, opening a tab, resizing a panel, and changing a chart view—remain UI concerns and intentionally have no WebMCP tool. Meaningful laboratory operations map as follows:

| Human capability | REST operation | WebMCP tool |
| --- | --- | --- |
| List/load/reset a challenge | `GET /challenges`, `POST /challenges/{id}/load`, `POST /lab` | `list_challenges`, `load_challenge`, `reset_lab` |
| Create a circuit from scratch | `POST /circuits/blank` | `create_blank_circuit` |
| Rename/list/open/delete named circuits | `POST /circuits`, `GET /circuits`, `POST /circuits/{id}/open`, `DELETE /circuits/{id}` | `rename_circuit`, `list_saved_circuits`, `open_saved_circuit`, `delete_saved_circuit` |
| Inspect the lab/circuit/criteria | `GET /lab`, `GET /circuit`, `POST /validate` | `get_lab_state`, `get_circuit`, `get_constraints`, `validate_circuit` |
| Add/edit/remove and wire components | component/node/connection endpoints | `add_component`, `create_node`, `rename_net`, `connect`, `connect_pins`, `disconnect`, `set_component_value`, `remove_component` |
| Restore a local circuit snapshot | `POST /circuit/restore` | `restore_circuit` |
| Run and measure direct analyses | simulation and evaluation endpoints | `run_operating_point`, `run_ac_analysis`, `run_transient`, measurement tools, `evaluate_constraints` |
| Create/configure/preview a sweep | experiment-definition create/update endpoints | `create_experiment`, `update_experiment`, `get_experiment_plan` |
| Execute or control a sweep | execute/pause/resume/stop endpoints | `run_experiment`, `pause_experiment`, `resume_experiment`, `stop_experiment` |
| Inspect runs, analysis, and report | experiment/report UI from canonical records | `get_experiment`, `get_experiment_results`, `get_experiment_run`, `get_experiment_analysis`, `get_report` |
| Export recorded report/data | client-side report JSON/CSV export | `export_report`, `export_run_data` |
| Repeat/delete/restore experiment evidence | duplicate/delete/restore endpoints | `duplicate_experiment`, `delete_experiment`, `restore_experiment`, `restore_experiment_run` |

## 9. Deliberate boundaries and current limitations

The following are not present or should not be assumed:

- No AI/chat UI, autonomous-run button, or hidden circuit-solving endpoint.
- No PCB layout, manufacturing files, autorouter, part marketplace, microcontroller firmware, RF, thermal, or switching-power simulation.
- No user accounts, identity verification, permissions, or collaboration model. `Run by` is manual provenance text.
- No standalone collection management: create/rename/delete collection objects, permissions, and collection metadata are not implemented.
- No multi-execution history within one experiment definition. Duplicate to repeat.
- There is no simulation quota or experiment-run budget for either the human or WebMCP interface.
- The op-amp is simplified and does not model rail clipping, slew rate, or noise. The diode is a built-in model, not a vendor device model.
- WebMCP host support is optional and experimental.

## 10. Product-change guardrails

Before changing the product, check this document and preserve these behaviors unless the change explicitly revises this source of truth:

1. Keep the Workbench usable by humans without an agent integration.
2. Keep backend state canonical and retain revision checks on circuit mutation.
3. Use ngspice-backed results for engineering claims.
4. Preserve experiment snapshotting and executed-record immutability.
5. Do not silently overwrite results when repeating work; create a new trace or implement an explicit execution-history model first.
6. Maintain compact technical UI patterns: structured panels, property rows, engineering units, readable tables, restrained visual emphasis.
7. Treat WebMCP tool definitions as a public integration contract. Changes require test and documentation updates.

## 11. Verification baseline

Run these before accepting changes that affect the documented behavior:

```bash
make test
make lint
backend/.venv/bin/python scripts/verify_ngspice.py
cd backend && .venv/bin/python scripts/validate_agent_loops.py
cd frontend && npm test
cd frontend && npm run build
```

Relevant automated coverage lives in `backend/tests/` and `frontend/tests/workbench.test.tsx`, including WebMCP registry coverage, circuit/simulation/constraint behavior, experiment history and traceability, challenge templates, and workbench interaction behavior.

## 12. Maintaining this document

Update this document in the same change set when any of the following changes:

- user-visible workspace behavior or terminology;
- supported components, simulations, measurements, or challenge limits;
- experiment record or rerun semantics;
- REST or WebMCP tools/contracts;
- canonical data ownership or persistence behavior;
- stated product boundaries.

Historical specifications remain useful design context, but this file is the concise current reference for deciding what the project does today.
