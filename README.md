# Circuit Bench

Circuit Bench is an open-source virtual electronics laboratory where people and WebMCP-capable agents work on the same circuit, in the same anonymous browser session. It is built for transparent engineering work: every edit, simulation, measurement, experiment run, and report is visible in the shared workbench and backed by real `ngspice` results.

## Why WebMCP matters

WebMCP is a particularly good fit for circuit work because it lets an agent act through the same meaningful lab operations a scientist uses instead of guessing from pixels or relying on hidden solver shortcuts. The browser registers a concise semantic tool surface to inspect the active lab, create and wire components, arrange a schematic, run real analyses, measure results, evaluate requirements, and preserve experiment evidence.

People and agents can now work together in a clear handoff loop:

- A person sets the engineering goal, draws or reviews a circuit, changes values, and sees every result in the workbench.
- An agent can construct candidate circuits from primitives, keep the schematic readable with automatic arrangement, run measurements and controlled sweeps, and record traceable evidence.
- Both operate the same revision-protected circuit state. Agent edits appear on the human canvas immediately; stale changes are rejected rather than overwriting newer human work.
- Every browser receives an isolated anonymous Lab, so a person and their agent collaborate within one session without exposing another visitor’s circuits, experiments, or reports.

The agent does not get a hidden `solve`, design, optimize, or fix endpoint. It must build, validate, simulate, measure, and iterate through the same laboratory capabilities available to a person.

## What is included

- Three selectable, simulator-backed challenges: **Sensor Interface** (flagship), **Filter Design**, and **Debug Amplifier**.
- A React Flow canvas with explicit electrical nodes, component inspector, component tray, run controls, response charts, constraint panel, and activity-oriented experiment timeline.
- FastAPI + SQLite canonical per-Lab state, anonymous secure-cookie isolation, real operating-point, AC, and transient simulation through `ngspice`, measurement and constraint services, snapshots, and restore.
- A browser WebMCP registration layer plus a backend semantic tool registry with revision-safe mutations.
- Topology-aware schematic arrangement that lays signal flow left-to-right, puts shunt parts below their nets, places feedback above the signal path, and respects manual placements during agent edits.

The implementation intentionally has no hidden `solve`, design, optimize, or fix endpoint. Known-good circuits exist only in test fixtures to keep the public challenges honest and regression-tested.

## Prerequisites

- Python 3.10 or newer
- Node.js 20 or newer
- `ngspice` (required from Phase 1 onward)

On macOS with Homebrew:

```bash
brew install ngspice
```

## Local setup

```bash
cp .env.example .env

cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ../frontend
npm install
```

## Run locally

In one terminal:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`. The bootstrap UI checks `GET /health` on the backend.

## Production deployment

The production image builds the Next.js application as a static export and serves it from the FastAPI process. This keeps the UI, API, and WebMCP site tools on one HTTPS origin. The image includes `ngspice`, listens on the platform-provided `PORT`, and stores SQLite at `LAB_DB_PATH`.

Railway is the primary target and Render is supported as a fallback. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for exact setup, volume configuration, environment variables, local production commands, and the smoke-test checklist.

## Demo prompts

**Sensor Interface**

> Make this sensor signal safe and useful for the 3.3 V ADC. Keep the useful slow signal, reduce high-frequency noise, and use no more than ten components.

**Filter Design**

> Design the simplest circuit you can that loses less than 1 dB at 500 Hz and attenuates 10 kHz by at least 30 dB.

**Debug Amplifier**

> This amplifier should produce about 1 V from a 100 mV input, but the output is over range. Find the cause and fix it without reducing gain below 8.

## Verification

```bash
make test
make lint
backend/.venv/bin/python scripts/verify_ngspice.py
cd backend && .venv/bin/python scripts/validate_agent_loops.py
```

The last command rehearses each template with only the public WebMCP primitive operations and prints simulator-backed records. The test suite repeats each workflow five times and checks the Phase 9 reliability targets.

## Known limitations

- The op-amp is a simplified high-gain voltage-controlled source; it does not model rail clipping, slew rate, or noise.
- The diode uses a small built-in SPICE model rather than a vendor-specific part.
- WebMCP availability depends on the browser’s experimental implementation. The session's human workbench remains fully usable when it is unavailable.

## Open source

Circuit Bench is available under the [MIT License](LICENSE). Contributions, issues, and experiments are welcome.
