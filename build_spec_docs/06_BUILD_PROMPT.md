# Build Prompt for an AI Coding Agent

Copy this prompt into the coding agent after placing all specification files in the repository.

```text
Build this project end to end.

First read:
- AGENTS.md
- 00_MASTER_SPEC.md
- 01_DOMAIN_AND_SIMULATION.md
- 02_WEBMCP_AND_AGENT.md
- 03_IMPLEMENTATION_PHASES.md
- 04_UI_UX_SPEC.md
- 05_TEST_AND_DEMO.md

Treat these files as the product contract.

Execution rules:
1. Follow the implementation phases in order.
2. Do not skip the ngspice spike.
3. Do not build fake simulator results.
4. Do not create solver shortcuts such as optimize_circuit or solve_challenge.
5. The backend must be the canonical state shared by human UI and WebMCP.
6. Every circuit mutation must use revision checks.
7. Add tests as each phase is completed.
8. Run all tests before moving to the next phase.
9. Keep the component library and UI intentionally small.
10. Prioritize a reliable Sensor Interface demo over extra features.

At the start:
- inspect the repository,
- create a concrete task checklist mapped to the documented phases,
- identify missing local dependencies such as ngspice,
- begin Phase 0 immediately.

After each phase, report:
- what you implemented,
- files changed,
- tests run,
- whether acceptance criteria passed,
- remaining issues.

Do not stop at scaffolding.
Continue until the complete MVP is implemented or you encounter a blocker that cannot be solved from the repository/environment.

If a detail is ambiguous, choose the simplest implementation consistent with the specs and document the decision.
```
