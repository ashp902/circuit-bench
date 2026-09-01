# UI and UX Specification

The UI is a shared workbench, not a professional CAD application.

Its job is to make the human-agent collaboration obvious.

---

## 1. Main desktop layout

```text
┌────────────────────────────────────────────────────────────────────┐
│ Autonomous Electronics Lab                        Challenge ▾      │
├──────────────────┬───────────────────────────────┬─────────────────┤
│ GOAL             │                               │ RESULTS         │
│                  │                               │                 │
│ User objective   │        CIRCUIT CANVAS         │ Measurements    │
│                  │                               │                 │
│ Constraints      │                               │ Bode/Transient  │
│ ✓ ...            │                               │ graph           │
│ ✗ ...            │                               │                 │
│ ? ...            │                               │                 │
│                  │                               │                 │
│ Budget: 7 / 15   │                               │                 │
├──────────────────┴───────────────────────────────┴─────────────────┤
│ COMPONENT TRAY                                                     │
│ R   C   L   Diode   Op-Amp   Source   Ground                      │
├────────────────────────────────────────────────────────────────────┤
│ EXPERIMENT TIMELINE                                                │
│ #1 FAIL  #2 FAIL  #3 CLOSE  #4 PASS                                │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. Goal panel

Show:

### Challenge title

Example:

```text
Sensor Interface
```

### Human-readable objective

Example:

```text
Make the sensor output usable by a 3.3 V ADC.
Reduce high-frequency noise while keeping the response fast enough.
```

### Constraint cards

Example:

```text
✓ Max output ≤ 3.3 V
✗ Gain at 10 Hz ≥ 10x
✓ 10 kHz attenuation ≥ 20 dB
? Rise time ≤ 20 ms
✓ Components ≤ 10
```

Status:
- green check: pass,
- red x: fail,
- gray question: not yet measured.

Do not use only color. Include icon/text.

---

## 3. Experiment budget

Always visible.

Example:

```text
Experiments remaining
████████████░░░  8 / 15
```

A simulator execution consumes one.

When zero remains:

```text
Experiment budget exhausted
```

Disable further runs while still allowing inspection and restore.

---

## 4. Component tray

MVP tray:

```text
Resistor
Capacitor
Inductor
Diode
Ideal Op-Amp
Voltage Source
Ground
```

Clicking a component:
- adds it near canvas center,
- uses a safe default value,
- opens property inspector.

Human drag-and-drop is optional.

A simple click-to-add UI is acceptable.

---

## 5. Circuit canvas

Use React Flow.

### Node visual

Each component card shows:

```text
┌───────────────┐
│ R1            │
│ Resistor      │
│ 10 kΩ         │
│               │
│ ● a       b ● │
└───────────────┘
```

Op-amp:

```text
       ┌─────────────┐
 plus ●│ +           │
minus ●│ -      out  │●
       └─────────────┘
```

### Required interactions

- select component,
- edit numeric value,
- delete,
- connect pin to electrical node,
- pan/zoom,
- auto-layout button.

Avoid spending hackathon time on perfect schematic symbols.

---

## 6. Node representation

For speed, electrical nodes can be visible hub nodes.

Example:

```text
R1.b ───● out ─── C1.a
```

This is easier to implement than professional wire junction semantics.

---

## 7. Component property panel

When a component is selected:

```text
R1
Type: Resistor

Resistance
[ 10000 ] Ω

[Delete component]
```

Frontend sends SI values to backend.

Support user-friendly suffix parsing if easy:

```text
10k
4.7k
100n
1u
```

But normalize immediately.

---

## 8. Results panel

Tabs:

```text
Measurements | Frequency | Time
```

### Measurements

```text
Output max        3.12 V
Gain @ 10 Hz      12.4x
Gain @ 10 kHz     -24.1 dB
Cutoff            1.03 kHz
Rise time         14.2 ms
```

### Frequency

Bode-style graph:
- X: logarithmic frequency,
- Y: gain in dB.

### Time

Transient graph:
- X: time,
- Y: voltage.

Keep charts interactive enough for hover values.

---

## 9. Experiment timeline

This is a first-class feature.

Each experiment card:

```text
Experiment 4                        FAIL

Hypothesis
"Filtering is too aggressive, so I will raise the cutoff."

Changes
C2: 220 nF → 100 nF

Simulations
AC analysis

Results
500 Hz gain: -2.1 dB → -0.8 dB
10 kHz gain: -37 dB → -28 dB

Constraints
3 pass
1 fail

[Restore]
```

Collapsed timeline cards may show only:

```text
#4  3/4 constraints  FAIL
```

---

## 10. Agent activity

If the product can surface tool calls, show them as lightweight activity.

Example:

```text
AI Engineer
• inspected current circuit
• changed C2 to 100 nF
• validated circuit
• ran AC analysis
• measured gain at 10 kHz
```

Do not expose internal chain-of-thought.

Show only observable actions and optional short agent-provided hypotheses/conclusions.

---

## 11. Manual simulation controls

Humans should also be able to use the lab.

Buttons:

```text
Run OP
Run AC
Run Transient
```

For challenge mode, simulation defaults should be preconfigured.

Advanced settings may live in a collapsible panel.

---

## 12. Challenge selector

Home screen:

```text
Choose a lab challenge

[ Sensor Interface ]
Condition a weak noisy sensor for a 3.3 V ADC.
Flagship

[ Filter Design ]
Design a circuit that meets frequency constraints.
Easy

[ Debug Amplifier ]
Find why an existing amplifier fails and repair it.
Medium
```

Also offer:

```text
[ Blank Lab ]
```

Blank Lab does not need constraint evaluation beyond basic validation.

---

## 13. Human edits during agent work

Human interactions must remain enabled while agent is active.

If the human changes the circuit:

```text
Human changed R2 from 10 kΩ to 4.7 kΩ
```

The circuit revision increments.

If agent sends a stale change, tool returns `STALE_REVISION`.

The UI should not treat that as a catastrophic error.

---

## 14. Responsive behavior

Hackathon priority is desktop.

Minimum:
- usable at 1280px wide,
- no requirement for mobile schematic editing.

At small widths:
- stack panels,
- canvas remains first.

---

## 15. Empty states

### No simulation

```text
No simulation yet.
Run an experiment to see measurements.
```

### No experiments

```text
No experiments yet.
The first simulation will appear here.
```

### Invalid circuit

Show specific issues:

```text
Circuit cannot be simulated

• C2 pin b is not connected
• Ground is missing
```

---

## 16. Loading states

Simulation:

```text
Running transient analysis...
```

Agent edit:

```text
AI Engineer is modifying the circuit...
```

Do not lock the whole page.

---

## 17. Error presentation

Map backend error codes to human messages.

Example:

```text
SIMULATION_TIMEOUT

The simulator exceeded the 5 second limit.
Try a shorter transient duration or a simpler circuit.
```

Keep raw logs behind an optional developer details disclosure.

---

## 18. Visual priority

Spend polish time in this order:

1. clear circuit state,
2. live agent edits,
3. graph updates,
4. constraint status changes,
5. experiment timeline,
6. component styling.

The visual story should be:

```text
AI changes something
→ graph changes
→ requirement changes from red to green
```

That is the demo.

---

## 19. Accessibility basics

- buttons have text labels,
- keyboard focus visible,
- graph has numeric measurement equivalents,
- status never depends on color alone,
- component values are readable text,
- canvas zoom controls available.

---

## 20. Demo mode

Add a query parameter or toggle:

```text
?demo=1
```

Demo mode may:
- open directly to Sensor Interface,
- pre-open experiment timeline,
- simplify advanced controls,
- increase visual emphasis on agent actions.

Do not fake simulation results in demo mode.
