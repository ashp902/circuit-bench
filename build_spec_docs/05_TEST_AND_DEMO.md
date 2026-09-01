# Test, Validation, and Demo Plan

The project should be judged primarily on reliability of the agent-lab loop.

---

## 1. Test pyramid

```text
                    E2E agent tests
                 /                 \
             API integration tests
           /                       \
     simulation + measurement tests
   /                               \
schema, validation, helper unit tests
```

---

## 2. Backend unit tests

### Circuit model

Test:
- valid component,
- invalid value,
- unsupported type,
- duplicate ID,
- pin connection,
- disconnect,
- missing ground,
- floating pin,
- component count,
- revision conflict.

### Measurement engine

Use synthetic arrays where possible.

Test:
- gain calculation,
- interpolation,
- cutoff detection,
- cutoff absent,
- rise time,
- max/min voltage,
- overshoot.

### Constraint engine

Test every operator.

---

## 3. Simulator integration tests

These require ngspice.

Mark them separately:

```bash
pytest -m ngspice
```

Required circuits:

### Voltage divider

```text
5 V → 1k → out → 1k → GND
```

Expected:
- `out ≈ 2.5 V`.

### RC low pass

```text
R = 1 kΩ
C = 100 nF
```

Expected:
- cutoff near 1.59 kHz.

### RC transient

Expected:
- monotonic first-order response,
- finite positive rise time.

---

## 4. API integration test

One test should exercise the full backend:

```text
create challenge
→ fetch circuit
→ add resistor
→ add capacitor
→ create nodes
→ connect
→ validate
→ run AC
→ measure gain
→ evaluate constraints
→ save experiment
→ restore experiment
```

This test should run without the frontend.

---

## 5. WebMCP contract tests

For every tool verify:

- valid input,
- invalid input,
- stable output schema,
- machine-readable errors.

Mutation tool test:

```text
revision = 5

human mutation occurs
revision = 6

agent sends expected_revision = 5

expected:
STALE_REVISION
```

---

## 6. Frontend tests

Minimum:
- lab renders,
- challenge constraints render,
- adding component calls API,
- selected component property edit calls API,
- results chart renders simulation data,
- experiment timeline renders,
- restoring experiment updates canvas.

Do not over-invest in snapshot tests.

---

# 7. Flagship demo: Sensor Interface

## Starting situation

A virtual sensor emits:

```text
useful signal: around 10 Hz
amplitude: 20 to 150 mV
high-frequency interference: around 10 kHz
```

Target device:

```text
3.3 V ADC
```

### Challenge constraints

Example MVP values:

```text
1. Gain at 10 Hz >= 10x
2. Gain at 10 kHz <= -10 dB relative to useful-band gain
3. Maximum output <= 3.3 V
4. Minimum output >= 0 V
5. Rise time <= 25 ms
6. Components <= 10
7. Experiments <= 15
```

Exact values should be tuned so at least one solution exists using the supported idealized component set.

---

## User prompt

```text
Make this sensor signal safe and useful for the 3.3 V ADC.
Keep the useful slow-changing signal, reduce the high-frequency noise,
and do not use more than 10 components. You have 15 experiments.
```

No topology hint.

---

## Expected agent behavior

A good run might look like:

```text
1. inspect source and constraints
2. add amplification
3. run operating point/transient
4. discover clipping or inadequate gain
5. revise gain
6. add filtering
7. run AC
8. discover response/filtering tradeoff
9. tune filter
10. run transient and AC
11. evaluate all constraints
12. stop after PASS
```

The exact topology is not scripted.

---

## Demo success

The demo is successful if:

- agent performs at least two distinct experiments,
- at least one experiment fails a constraint,
- agent changes strategy based on evidence,
- final circuit passes all constraints.

---

# 8. Secondary demo: Filter Design

## User prompt

```text
Design the simplest circuit you can that loses less than 1 dB at 500 Hz
and attenuates 10 kHz by at least 30 dB.
Use no more than 6 components and no more than 10 experiments.
```

This is the easiest fallback demo.

It validates:
- AC analysis,
- component editing,
- frequency measurements,
- experiment loop.

Do not market the whole product as a filter designer.

---

# 9. Secondary demo: Debug Amplifier

## Starting circuit

Use an intentionally flawed op-amp setup.

Possible failure:
- excessive closed-loop gain causes output to exceed the allowed output range,
- or incorrect bias produces unusable output.

## User prompt

```text
This amplifier should produce about 1 V from a 100 mV input,
but the output clips and becomes distorted.
Find the cause and fix it without reducing the gain below 8.
```

## Expected loop

```text
inspect
→ run operating point
→ run transient
→ measure max voltage
→ form diagnosis
→ change value
→ rerun
→ evaluate
```

This demonstrates investigation rather than generation.

---

# 10. Human-agent collaboration demo

Optional 20-second moment during flagship demo:

1. Agent gets close to solution.
2. Human manually changes `C2`.
3. Agent attempts stale edit.
4. Tool tells agent state changed.
5. Agent rereads circuit.
6. Agent continues from human change.

User says:

```text
I changed that capacitor because I want a faster response. Continue from here.
```

This is a strong WebMCP story because human and agent truly share application state.

---

# 11. Demo script

### 0:00 to 0:20

Explain:

```text
This is a virtual electronics lab.
A human can use it normally, but through WebMCP an AI agent can use the same
engineering capabilities directly.
```

### 0:20 to 0:40

Open Sensor Interface.

Show:
- source signal,
- constraints,
- empty/simple starting workbench,
- experiment budget.

### 0:40 to 1:40

Prompt agent.

Let it:
- inspect,
- build,
- simulate.

Do not talk over every tool call.

Point out:
- circuit changed live,
- simulator is real,
- one requirement failed.

### 1:40 to 2:20

Agent revises.

Graph changes.

Constraints turn green.

### 2:20 to 2:45

Human intervention:

```text
Use only one op-amp.
```

or manually edit a component.

Agent adapts.

### 2:45 to 3:00

Close:

```text
We are not asking the model to guess whether a circuit works.
WebMCP gives it a laboratory where it can test its own ideas.
```

---

# 12. Demo fallback strategy

Have three levels.

### Plan A

Live agent solves Sensor Interface.

### Plan B

Start from a saved intermediate experiment so the agent only needs 2 to 4 more experiments.

### Plan C

Run Filter Design, which is simpler and highly reliable.

Never fake simulator output.

---

# 13. Reliability checklist before recording

Run each item at least three times:

```text
[ ] Fresh Sensor challenge loads
[ ] Agent can inspect
[ ] Agent can mutate
[ ] Canvas reflects agent mutation
[ ] AC simulation works
[ ] transient simulation works
[ ] constraints evaluate correctly
[ ] experiment count decreases
[ ] failed experiment appears in timeline
[ ] restore works
[ ] stale revision recovery works
[ ] final solution can pass
```

---

# 14. Performance targets

Hackathon targets:

```text
Circuit mutation response: < 500 ms
OP simulation: < 2 s
AC simulation: < 3 s
Transient simulation: < 3 s
Tool response: concise enough for agent loop
UI state propagation: < 1 s
```

These are product targets, not hard scientific requirements.

---

# 15. Security tests

Verify:
- no arbitrary netlist submission,
- component IDs sanitized,
- no shell execution,
- timeout actually terminates process,
- oversized circuit rejected,
- oversized frequency ranges rejected,
- excessive transient points rejected,
- invalid numeric values rejected.

---

# 16. Final acceptance checklist

## Product

```text
[ ] shared human-agent lab
[ ] actual ngspice
[ ] design challenge
[ ] debug challenge
[ ] experiment history
[ ] experiment budget
[ ] constraint evaluation
```

## Agent

```text
[ ] can inspect
[ ] can edit
[ ] can simulate
[ ] can measure
[ ] can fail safely
[ ] can retry
[ ] can recover from human edits
[ ] cannot call solve_problem
```

## Demo

```text
[ ] visible failure
[ ] visible adaptation
[ ] visible graph change
[ ] visible PASS
[ ] polished 3 minute flow
```
