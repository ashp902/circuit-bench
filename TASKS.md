# Implementation Checklist

This checklist mirrors `build_spec_docs/03_IMPLEMENTATION_PHASES.md`. Completed phases are recorded only after their acceptance commands pass.

- [x] Phase 0 — Bootstrap monorepo, health integration, commands, CI, documentation.
- [x] Phase 1 — Prove real ngspice divider integration with timeout handling.
- [x] Phase 2 — Canonical Pydantic circuit model, validation, revision-safe mutations.
- [x] Phase 3 — Deterministic netlists plus operating-point, AC, and transient simulation.
- [x] Phase 4 — Measurements and deterministic constraint evaluation.
- [x] Phase 5 — REST API, SQLite experiment persistence, restore flow.
- [x] Phase 6 — Semantic WebMCP surface over the same backend services.
- [x] Phase 7 — Shared lab UI with canvas, controls, results, and history.
- [x] Phase 8 — Filter Design, Sensor Interface, and Debug Amplifier templates.
- [x] Phase 9 — Agent-loop reliability validation against all templates.
- [x] Phase 10 — Demo activity, graphs, timeline, and presentation polish.

## Local dependency status

- Python 3.10: available (project supports 3.10+ locally).
- Node.js 23 / npm 11: available.
- GNU Make: available.
- ngspice 47: installed and verified.
