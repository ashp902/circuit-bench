import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ComponentTray } from "@/components/ComponentTray";
import { componentPins, pathFromPointsWithBridges } from "@/components/CircuitCanvas";
import { ExperimentTimeline } from "@/components/ExperimentTimeline";
import { ExperimentAnalysis } from "@/components/ExperimentAnalysis";
import { GoalPanel } from "@/components/GoalPanel";
import { PropertyInspector } from "@/components/PropertyInspector";
import { ResultsPanel } from "@/components/ResultsPanel";
import type { Challenge, Circuit, Experiment, SimulationResult } from "@/lib/types";

const challenge: Challenge = {
  id: "filter", title: "Filter Design", description: "Keep useful frequencies.", component_limit: 6,
  allowed_components: ["resistor", "capacitor", "voltage_source"], constraints: [{ id: "cutoff", metric: "cutoff_frequency_hz", operator: "between", target: [1400, 1800] }],
};
const circuit: Circuit = {
  id: "ckt", revision: 3, name: "Test circuit", metadata: {}, nodes: [{ id: "gnd", label: "Ground" }, { id: "out", label: "Output" }],
  components: [{ id: "R1", type: "resistor", params: { resistance_ohm: 1000 }, pins: { a: "out", b: "gnd" } }],
};

describe("shared workbench panels", () => {
  it("renders bridge bumps as one continuous wire path", () => {
    expect(pathFromPointsWithBridges(
      [{ x: 0, y: 20 }, { x: 100, y: 20 }],
      [{ x: 50, y: 20, horizontal: true }],
    )).toBe("M 0 20 L 42 20 Q 50 4 58 20 L 100 20");
    expect(pathFromPointsWithBridges(
      [{ x: 40, y: 0 }, { x: 40, y: 100 }],
      [{ x: 40, y: 50, horizontal: false }],
    )).toBe("M 40 0 L 40 42 Q 56 50 40 58 L 40 100");
  });

  it("rotates every component type's physical terminals with its symbol", () => {
    const samples = [
      { id: "R1", type: "resistor", pins: { a: "n1", b: "n2" }, params: { resistance_ohm: 1000 }, vertical: false },
      { id: "C1", type: "capacitor", pins: { a: "n1", b: "n2" }, params: { capacitance_f: 1e-9 }, vertical: true },
      { id: "L1", type: "inductor", pins: { a: "n1", b: "n2" }, params: { inductance_h: 1e-3 }, vertical: false },
      { id: "V1", type: "voltage_source", pins: { negative: "n1", positive: "n2" }, params: { voltage_v: 1 }, vertical: false },
      { id: "D1", type: "diode", pins: { anode: "n1", cathode: "n2" }, params: {}, vertical: false },
      { id: "U1", type: "ideal_opamp", pins: { plus: "n1", minus: "n2", out: "n3" }, params: { gain: 100000 }, vertical: false },
      { id: "G1", type: "ground", pins: { ground: "gnd" }, params: {}, vertical: false },
    ] as const;
    samples.forEach((sample) => {
      const original = componentPins(sample, { x: 100, y: 100 }, sample.vertical, false, 0);
      const rotated = componentPins(sample, { x: 100, y: 100 }, sample.vertical, false, 90);
      expect(rotated).toHaveLength(original.length);
      original.forEach((pin, index) => {
        expect(rotated[index].x).toBe(200 - pin.y);
        expect(rotated[index].y).toBe(pin.x);
        expect(rotated[index].direction).not.toBe(pin.direction);
      });
    });
  });

  it("renders constraints and the available component tray", () => {
    const add = vi.fn();
    render(<><GoalPanel challenge={challenge} evaluation={null} /><ComponentTray allowed={challenge.allowed_components} onAdd={add} /></>);
    expect(screen.getByText("Filter Design")).toBeInTheDocument();
    expect(screen.getByText(/cutoff frequency hz/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle("Add Resistor"));
    expect(add).toHaveBeenCalledWith("resistor", { resistance_ohm: 1000 });
    expect(screen.queryByTitle(/diode/i)).not.toBeInTheDocument();
  });

  it("sends selected property changes and pin connections to the parent", () => {
    const setValue = vi.fn(); const connect = vi.fn();
    render(<PropertyInspector circuit={circuit} component={circuit.components[0]} onConnect={connect} onDelete={vi.fn()} onSetValue={setValue} />);
    const input = screen.getByLabelText("R1 Resistance");
    fireEvent.change(input, { target: { value: "2.2" } }); fireEvent.blur(input);
    expect(setValue).toHaveBeenCalledWith("R1", "resistance_ohm", 2200);
    fireEvent.change(screen.getByLabelText("R1 a node"), { target: { value: "gnd" } });
    expect(connect).toHaveBeenCalledWith("R1", "a", "gnd");
  });

  it("renders saved experiments and requests a restore", () => {
    const restore = vi.fn();
    const experiment: Experiment = { id: "exp_001", sequence: 1, created_at: "2026-01-01T00:00:00Z", hypothesis: "Test it.", conclusion: "Pass.", circuit_revision: 1, circuit_snapshot: circuit, simulation_ids: ["sim_1"], measurements: {}, constraint_results: [] };
    render(<ExperimentTimeline experiments={[experiment]} onRestore={restore} onSave={vi.fn()} simulation={null} />);
    fireEvent.click(screen.getByRole("button", { name: /restore/i }));
    expect(restore).toHaveBeenCalledWith("exp_001");
  });

  it("renders simulator-derived response data and constraint measurements", () => {
    const simulation: SimulationResult = { success: true, analysis: "ac", circuit_revision: 3, simulation_id: "sim_1", measurements: {}, warnings: [], errors: [], series: { frequency_hz: [10, 100, 1_000], output_gain_db: [0, -1, -20], output_phase_deg: [0, -5, -45] } };
    function PanelHarness() { const [analysis, setAnalysis] = useState<"op" | "ac" | "transient">("ac"); return <ResultsPanel analysis={analysis} challenge={challenge} expanded measuredNode={circuit.nodes[1]} onAnalysisChange={setAnalysis} onToggle={vi.fn()} simulation={simulation} evaluation={{ measurements: { gain_db_at_1000hz: -20, component_count: 3 }, evaluation: { all_pass: true, passed: 1, failed: 0, not_evaluated: 0, results: [] } }} />; }
    render(<PanelHarness />);
    expect(screen.getByRole("button", { name: "AC sweep" })).toBeInTheDocument();
    expect(screen.getByText(/gain db at 1000hz/i)).toBeInTheDocument();
    expect(screen.getByText(/-20\.0 dB/)).toBeInTheDocument();
    expect(screen.queryByText(/component count/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Magnitude" }));
    expect(screen.getByText(/magnitude response \(vout \/ vin\)/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Phase" }));
    expect(screen.getByText("Phase Response")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Transient" }));
    expect(screen.getByRole("button", { name: "Transient" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Run" })).not.toBeInTheDocument();
  });

  it("renders Setup for persisted structured experiment measurements", () => {
    const structuredExperiment = {
      id: "exp_002", sequence: 2, created_at: "2026-01-01T00:00:00Z", hypothesis: "Verify filter response.", conclusion: "",
      circuit_revision: 3, circuit_snapshot: circuit, simulation_ids: [], measurements: {}, constraint_results: [], name: "Structured experiment",
      variables: [{ component_id: "R1", parameter: "resistance_ohm", label: "R1 Resistance", unit: "Ω", sweep: "linear", start: 900, stop: 1100, points: 2 }],
      measurement_definitions: [{ id: "gain_600_hz", kind: "gain_db", label: "Gain 600 Hz", unit: "dB", input_node: "vin", output_node: "out", frequency_hz: 600 }],
      requirement_definitions: [{ id: "gain_floor", measurement_id: "gain_600_hz", operator: ">=", target: -0.8 }],
      generated_runs: [{ index: 1, enabled: true, values: { "R1.resistance_ohm": 900 } }, { index: 2, enabled: true, values: { "R1.resistance_ohm": 1100 } }],
      run_results: [{ run_index: 1, status: "COMPLETED", parameters: { "R1.resistance_ohm": 900 }, measurements: { gain_600_hz: -0.6 }, requirement_results: [{ metric: "gain_600_hz", status: "PASS", actual: -0.6, target: -0.8 }] }],
    } as unknown as Experiment;
    render(<ExperimentAnalysis experiment={structuredExperiment} onBack={vi.fn()} />);
    fireEvent.click(screen.getByRole("tab", { name: "Setup" }));
    expect(screen.getAllByText("Gain 600 Hz").length).toBeGreaterThan(0);
    expect(screen.getByText(/operating point \+ ac sweep/i)).toBeInTheDocument();
  });
});
