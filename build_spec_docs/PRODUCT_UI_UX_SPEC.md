# Build a Professional Virtual Electronics Lab UI/UX

You are acting as a senior product designer and senior frontend engineer.

Build the frontend and interaction design for a **human-first virtual electronics laboratory**.

The product should feel like a serious engineering tool used by students, researchers, and engineers.

It must NOT look like:

* an AI-generated landing page
* a generic SaaS dashboard
* a hackathon prototype
* a collection of oversized rounded cards
* a chatbot interface
* a futuristic AI product
* a Dribbble concept with poor usability

The UI should feel closer to a polished technical desktop application such as:

* professional CAD software
* circuit simulation software
* scientific analysis tools
* IDEs
* modern engineering applications

Do not copy any specific existing product. Use these only as references for information density, hierarchy, precision, and professionalism.

---

# 1. Product Philosophy

This is a laboratory, not a dashboard.

The primary concepts exposed to the user are:

* Project
* Circuit
* Component
* Probe
* Variable
* Measurement
* Requirement
* Experiment
* Run
* Result
* Report
* Circuit Revision

Users should interact with engineering concepts directly.

Avoid exposing simulator implementation details unless they belong in an advanced settings area.

The UX should always answer:

1. What circuit am I working on?
2. What am I testing?
3. What parameters am I changing?
4. What am I measuring?
5. What is currently running?
6. What did the experiment reveal?
7. Can I reproduce this result?

---

# 2. Visual Direction

Create a restrained, professional engineering application.

## Overall feel

Use:

* neutral backgrounds
* subtle borders
* clear typography
* compact controls
* strong alignment
* consistent spacing
* high information density without clutter
* restrained use of color
* excellent table and chart readability
* obvious selected/hover/focus states

Avoid:

* excessive gradients
* glassmorphism
* glowing elements
* neon accents
* giant hero typography
* huge empty spaces
* pill-shaped everything
* excessive border radius
* oversized cards
* excessive drop shadows
* decorative blobs
* floating UI for no functional reason
* emoji as interface icons
* random colorful icons
* “AI purple”
* fake metrics designed only to fill space

Use color primarily for meaning:

* neutral = normal/default
* green = pass/safe
* red = fail/error
* amber = warning/boundary
* blue or another restrained accent = selection/action

Do not overuse status colors.

---

# 3. Design System

Create a small reusable design system before building individual pages.

Define:

## Typography

Use a highly readable professional sans-serif font.

Have clear text levels:

* application title
* page title
* section heading
* control label
* body
* metadata
* monospace numeric/readout text where appropriate

Engineering values should align cleanly.

Examples:

4.700 kΩ
1.590 kHz
42.30 mA
-3.01 dB

Use tabular numbers when possible.

## Spacing

Use a consistent spacing scale.

Prefer compact professional layouts over oversized consumer-app spacing.

## Borders

Use subtle borders to establish structure.

Panels should generally be differentiated by:

* border
* background
* spacing

rather than heavy shadows.

## Radius

Use small or medium radius consistently.

Do not make every container heavily rounded.

## Controls

Create consistent components for:

* text input
* numeric input
* unit selector
* select
* checkbox
* radio group
* segmented control
* slider
* button
* icon button
* tabs
* property row
* data table
* resizable panel
* chart toolbar
* empty state
* toast
* inline validation
* status indicator

Numeric engineering inputs must support units naturally.

Example:

[ 4.7 ] [ kΩ ▼ ]

not:

Resistance: [4700]

---

# 4. Application Shell

Use a desktop-first application layout.

Top navigation should be minimal.

Primary project navigation:

* Workbench
* Experiments
* Reports

Show the current project name prominently but compactly.

Example:

Project: RC Low-Pass Filter

Workbench | Experiments | Reports

Save status and major actions can live on the right side.

Do not use a generic SaaS left sidebar containing 15 unrelated navigation items.

---

# 5. Workbench

The Workbench is the central circuit-building experience.

Use a three-panel layout:

LEFT:
Component library

CENTER:
Circuit canvas

RIGHT:
Properties inspector

BOTTOM:
Optional collapsible simulation/output panel

Conceptual structure:

┌─────────────────────────────────────────────────────────────┐
│ RC Low-Pass Filter     Workbench Experiments Reports        │
├──────────────┬──────────────────────────────┬───────────────┤
│ Components   │                              │ Properties    │
│              │                              │               │
│ Resistor     │        Circuit Canvas        │ R1            │
│ Capacitor    │                              │ Resistance    │
│ Source       │                              │ 10 kΩ         │
│ Ground       │                              │               │
│ Probe        │                              │ Tolerance 5%  │
│              │                              │               │
├──────────────┴──────────────────────────────┴───────────────┤
│ Measurements / simulation output                           │
└─────────────────────────────────────────────────────────────┘

Panels should be resizable where practical.

---

# 6. Component Library

Make the component library compact and scannable.

Categories may include:

* Passive
* Sources
* Semiconductor
* Measurement
* Utility

For the MVP support only the components actually implemented.

Do not show fake components.

Users should be able to drag components onto the canvas.

Each component should have:

* recognizable schematic symbol
* name
* optional shortcut or tooltip

Avoid large decorative component cards.

---

# 7. Circuit Canvas

The canvas is the visual center of the application.

Support:

* drag
* drop
* wire connection
* component selection
* multiselect if feasible
* pan
* zoom
* rotate
* duplicate
* delete
* node labels
* probes
* snap/grid behavior
* keyboard shortcuts

Selected components must have a clear but restrained selection treatment.

Do not make the canvas look like a flowchart builder.

Use proper electronic schematic conventions wherever possible.

---

# 8. Properties Inspector

Selecting a component opens its properties on the right.

Example for resistor:

R1
Resistor

Resistance
[ 10 ] [ kΩ ]

Tolerance
[ 5 ] [ % ]

Label
[ R1 ]

Include as experiment variable
[ checkbox ]

Advanced
[ collapsed ]

Changes should feel immediate and predictable.

Group related controls.

Do not put every property inside separate cards.

Use property rows and sections.

---

# 9. Probes and Measurements

Users must be able to place measurement probes directly onto the circuit.

Supported examples:

* node voltage
* branch current
* differential voltage

Probe properties should include:

Name
Measurement type
Reference node where relevant
Include in experiments

Example:

Output Voltage

Measurement
Voltage

Node
VOUT

Reference
GND

[✓] Record during experiments

Derived measurements can be supported separately.

Examples:

Gain = Vout / Vin
Power = Vin × Iin

Keep advanced expression creation optional.

---

# 10. Quick Run

The Workbench must support a simple one-off simulation.

Primary action:

Run

This runs the current circuit using current component values.

Display useful measurements in the bottom panel.

Example:

Output Voltage     3.142 V
Input Current      18.20 mA
Power              91.0 mW

For waveform-capable simulations, allow chart viewing.

Quick Run is distinct from an Experiment.

Make that distinction obvious.

---

# 11. Experiments Page

The Experiments page contains:

* previous experiments
* current status
* create experiment action

Do not make this a grid of giant cards.

Prefer a professional table/list.

Columns:

Experiment
Circuit Revision
Type
Runs
Status
Created
Last Run

Example:

Frequency Response
Rev 4
Sweep
100 runs
Completed
Aug 29

Clicking opens the experiment.

---

# 12. Experiment Builder

The experiment should have a clear internal navigation:

Setup
Variables
Measurements
Requirements
Runs
Results

A horizontal step navigation or compact tab system is appropriate.

Do not use a giant multi-page wizard with full-page transitions for every field.

Users should be able to move between sections easily.

---

# 13. Experiment Setup

Fields:

Experiment Name

Description / Purpose

Optional type:

* Characterization
* Validation
* Optimization
* Robustness
* Manual

Do not require the user to select a type if it is unnecessary to execution.

The type should help organize the UX, not restrict the user.

---

# 14. Variables

Allow users to select parameters from the actual circuit.

Example:

Available Parameters

[ ] R1 Resistance       10 kΩ
[x] C1 Capacitance      100 nF
[x] Source Frequency    1 kHz
[ ] Source Voltage      5 V

Once selected, allow sweep configuration.

Sweep types:

* Linear
* Logarithmic
* Explicit list

Example:

Source Frequency

Sweep
Logarithmic

Start
10 Hz

Stop
100 kHz

Points
100

Always show:

100 values

If multiple variables are selected, calculate total runs.

Example:

Frequency    100 values
R1            20 values

Total runs: 2,000

Make large run counts obvious before execution.

---

# 15. Measurements

Show the measurements available from existing probes and supported circuit analysis.

Example:

Record during each run

[x] Output Voltage
[x] Input Current
[x] Gain
[x] Power Consumption
[ ] Phase Difference

For advanced circuit analyses, support metrics where technically valid.

Possible metrics include:

AC:

* gain
* phase
* cutoff frequency
* bandwidth
* resonant frequency

Transient:

* rise time
* fall time
* settling time
* overshoot
* peak
* RMS
* steady state

General:

* voltage
* current
* power
* min
* max
* average
* RMS

Only expose metrics that the simulator can compute correctly.

Never display fabricated engineering data.

---

# 16. Requirements

Allow optional engineering constraints.

Examples:

Output Voltage
4.75 V ≤ Vout ≤ 5.25 V

Current
Iin < 100 mA

Power
Power < 500 mW

Requirements should support:

* minimum
* maximum
* target ± tolerance
* equality where meaningful

If requirements exist, each run receives:

PASS
FAIL
ERROR

If requirements do not exist, do not artificially classify runs as passing or failing.

---

# 17. Run Matrix

Before execution, allow users to inspect generated runs.

Use a dense data table.

Example:

Run   R1      Frequency    Vin
001   1 kΩ    10 Hz        5 V
002   1 kΩ    12.6 Hz      5 V
003   1 kΩ    15.8 Hz      5 V

Features:

* sorting
* filtering
* row selection
* disable run
* inspect configuration

Do not render thousands of DOM rows simultaneously if virtualization is appropriate.

---

# 18. Running Experiment Screen

This should feel like a scientific automated test bench.

Show:

Experiment name
Progress
Current run
Current parameter values
Current measurements
Pass/fail/error counts where applicable
Elapsed execution information if available
Pause
Stop

Example:

Frequency Response

143 / 500 runs

Current Configuration

Frequency      4.2 kHz
R1             4.7 kΩ

Measurements

Vout           3.81 V
Gain           0.762
Phase         -32.1°
Power          38 mW

Passed          91
Failed          52
Errors           0

Include a live-updating chart where useful.

Do not use decorative animated loaders as the main feedback.

The user should see actual experimental progress.

---

# 19. Results UX

Results must follow this hierarchy:

1. Summary
2. Charts
3. Operating Region
4. Run Explorer
5. Experimental Setup
6. Raw Data

Do not immediately show a massive table.

---

# 20. Result Summary

The summary should display experiment-specific engineering findings.

Do not build a generic dashboard containing random averages.

Example for frequency response:

Runs
100

DC Gain
0.992

-3 dB Cutoff
1.59 kHz

Bandwidth
1.58 kHz

Phase at Cutoff
-44.8°

Valid Frequency Range
10 Hz – 1.47 kHz

Use compact metric blocks, not oversized marketing cards.

---

# 21. Charts

Charts must prioritize engineering interpretation.

Examples:

* Vout vs Vin
* Gain vs Frequency
* Phase vs Frequency
* Current vs Resistance
* Power vs Load
* transient waveform

Chart requirements:

* readable axis titles
* units
* useful tick formatting
* hover inspection
* zoom where helpful
* point selection
* selected-run highlighting
* accessible legend
* no decorative chartjunk

Clicking a data point should reveal the corresponding run.

Example:

Run #143

Frequency      4.2 kHz
R1             4.7 kΩ

Vout           3.81 V
Gain           0.762
Phase         -32.1°

Provide:

Open Run in Workbench

This should restore that circuit configuration for inspection.

---

# 22. Two-Variable Heatmaps

For two-parameter experiments, provide a heatmap.

Axes:
Variable A
Variable B

Metric can be switched.

Example selector:

Display:
Output Voltage
Power
Gain
Current
Pass/Fail

Heatmaps must have:

* clear axis units
* meaningful color scale
* legend
* hover details
* selected cell state

Never use a rainbow color scale by default.

---

# 23. Operating Region

If requirements are defined, identify combinations satisfying all requirements.

Show this visually.

Example:

Valid operating region

R1: 3.2 – 5.8 kΩ
R2: 36 – 61 kΩ

Within region:

Vout     4.76 – 5.23 V
Current  42 – 78 mA
Power    210 – 390 mW

Highlight this region on heatmaps/charts.

This should be treated as a core engineering result.

---

# 24. Constraint Margins

For passing configurations, calculate distance to requirement boundaries when mathematically meaningful.

Example:

Output Voltage margin    8.3%
Current margin          39%
Power margin            46%

Do not simply rank every passing configuration equally.

This helps users distinguish robust configurations from edge cases.

---

# 25. Recommended Configurations

When an objective exists, allow successful configurations to be ranked.

Do not decide what “best” means without user input.

Possible ranking methods:

* closest to target
* lowest power
* highest output
* largest overall constraint margin
* custom metric

Example:

Rank by:
Largest Safety Margin

Rank   R1     R2     Vout    Power    Margin
1      4.7k   47k    5.01V   280mW    44%
2      4.3k   47k    4.98V   265mW    41%
3      5.1k   51k    5.03V   291mW    39%

---

# 26. Sensitivity

Where the data supports it, show how strongly parameters influence selected outputs.

Example:

Effect on Output Voltage

R2          High
R1          Medium
Frequency   Low

Whenever quantitative sensitivity is shown, make the calculation method clear.

Do not fabricate causal conclusions from insufficient data.

---

# 27. Robustness / Tolerance Analysis

If component tolerances are supported, expose a dedicated experiment/report mode.

Example:

R1
10 kΩ ±5%

C1
100 nF ±10%

Results:

Samples
1,000

Within specification
963

Estimated simulated yield
96.3%

Output mean
5.01 V

Output range
4.68 – 5.34 V

Most influential parameter
R1 tolerance

Clearly label these as simulation-based estimates.

---

# 28. Run Explorer

Provide a professional data table.

Columns depend on experiment.

Example:

Run
R1
R2
Vin
Vout
Current
Power
Result

Users must be able to:

* sort
* filter
* search
* inspect
* compare selected runs
* export CSV
* reopen a run in the Workbench

---

# 29. Run Comparison

Allow users to compare multiple runs.

Use a property comparison table.

Example:

```
             Run 143    Run 188
```

R1               4.7 kΩ     5.1 kΩ
R2                47 kΩ      51 kΩ
Vout              5.01 V     5.03 V
Current           56 mA      61 mA
Power             280 mW     305 mW
Power Margin      44%        39%

Make differences visually easy to scan without excessive color.

---

# 30. Reports

Reports should resemble engineering laboratory reports, not business dashboards.

A report should contain:

1. Experiment Objective

2. Circuit Under Test

   * circuit diagram
   * circuit revision
   * component values

3. Experiment Setup

   * variables
   * fixed conditions
   * measurements
   * requirements
   * simulation settings

4. Test Plan

   * sweep ranges
   * run count
   * strategy

5. Results

   * important metrics
   * response curves
   * heatmaps
   * operating region

6. Analysis

   * major observed behavior
   * constraint failures
   * sensitivity where valid
   * selected configuration

7. Reproducibility Information

   * circuit revision
   * experiment settings
   * simulator configuration
   * run IDs

8. Raw Data / Appendix

Provide export options if implemented:

PDF
CSV
JSON

Do not include generic filler prose.

---

# 31. Circuit Revisioning

Every experiment must be tied to the exact circuit revision it tested.

Example:

Circuit Revision 4

Used by:
Frequency Response
Tolerance Analysis

If the user modifies a circuit that has experiment history, create or prompt for a new revision according to the application's save model.

Old experiment results must never silently point to a modified circuit.

---

# 32. Empty States

Empty states should be useful and understated.

Bad:

“Unlock the power of experimentation 🚀”

Good:

No experiments yet.

Create an experiment to vary circuit parameters and record measurements across multiple simulation runs.

[Create Experiment]

Avoid marketing language inside the application.

---

# 33. Writing Style

Use concise professional language.

Prefer:

Create Experiment
Run Experiment
Output Voltage
100 runs
Simulation failed
No requirements defined

Avoid:

Let's explore!
Supercharge your circuit!
Amazing!
AI-powered insights
Your experiment journey
Unlock powerful analytics

Do not use cute language.

---

# 34. Interaction Quality

The UI should feel responsive and intentional.

Implement:

* keyboard accessibility
* focus states
* hover states
* disabled states
* loading states
* error states
* undo where appropriate
* confirmation only for destructive actions
* inline form validation
* persistent unsaved-change indicators
* useful tooltips for unfamiliar engineering controls

Avoid unnecessary confirmation dialogs.

---

# 35. Progressive Disclosure

Keep normal workflows simple.

Advanced simulator settings should be collapsed under:

Advanced Settings

Do not make beginners configure:

* solver tolerances
* integration methods
* convergence controls
* obscure numerical parameters

unless needed.

Advanced users should still be able to access them.

---

# 36. Responsiveness

Prioritize desktop and laptop use.

This is a professional engineering workspace and does not need to pretend the circuit editor works equally well on a phone.

Tablet can be usable.

Mobile may provide:

* experiment viewing
* report viewing
* simple result inspection

Do not compromise the desktop Workbench merely to make every layout mobile-first.

---

# 37. Implementation Quality

Build reusable components.

Avoid giant monolithic page components.

Separate:

* application shell
* circuit workbench
* property inspector
* experiment configuration
* run execution
* result visualization
* report rendering

Keep experiment state and simulator execution state well structured.

Do not hardcode demo results directly into UI components.

Create typed data models for:

Project
Circuit
CircuitRevision
Component
Probe
Experiment
ExperimentVariable
Measurement
Requirement
ExperimentRun
RunMeasurement
ExperimentResult

Use mock data only through a clearly separated mock/service layer if the backend is not yet implemented.

---

# 38. Important Rule About Visual Quality

Before declaring a screen complete, inspect it as if it were a professional shipped engineering product.

Specifically check:

* Is anything unnecessarily oversized?
* Are there too many cards?
* Are containers nested inside containers without purpose?
* Is there excessive rounding?
* Are controls aligned?
* Are numeric values easy to compare?
* Are units displayed consistently?
* Is whitespace helping hierarchy rather than wasting space?
* Is the primary action obvious?
* Can the user understand the screen without onboarding text?
* Does this look like software designed for actual work?

If the answer is no, revise the interface before continuing.

Do not stop at “functional.”

The final product must be visually coherent, professional, compact, and easy to understand.

---

# 39. Build Order

Implement in this order:

## Phase 1: Design foundation

* application shell
* typography
* spacing
* colors
* control components
* panels
* tables
* tabs
* status states

## Phase 2: Workbench

* component library
* circuit canvas
* properties inspector
* probes
* quick simulation results

## Phase 3: Experiment creation

* experiment list
* setup
* variables
* measurements
* requirements
* generated run matrix

## Phase 4: Experiment execution

* sequential run engine integration
* progress
* current configuration
* live measurements
* pause/stop
* live charts

## Phase 5: Analysis

* result summary
* response charts
* heatmaps
* operating region
* requirement margins
* run explorer
* run comparison

## Phase 6: Reports

* structured report view
* circuit revision metadata
* reproducibility information
* export

After each phase, ensure existing workflows remain functional before moving forward.

---

# 40. Final Product Standard

A user unfamiliar with the codebase should be able to:

1. Create/open a project.
2. Build a circuit.
3. Configure components.
4. Place measurement probes.
5. Run the circuit once.
6. Create an experiment.
7. Select parameters to vary.
8. Define ranges.
9. Choose measurements.
10. Define optional requirements.
11. Preview generated runs.
12. Execute the experiment.
13. Watch progress and live measurements.
14. View engineering-specific results.
15. Explore charts/heatmaps.
16. Inspect individual runs.
17. Identify valid operating regions.
18. Compare configurations.
19. Reopen a configuration on the Workbench.
20. Generate a reproducible engineering report.

Build the product around this workflow.

Do not add AI features, chat interfaces, assistants, or AI branding.

This version of the product is entirely human-focused.
