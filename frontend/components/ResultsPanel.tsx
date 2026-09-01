"use client";

import { useState } from "react";
import { CaretDownIcon, CaretRightIcon, ChartLineUpIcon, WarningIcon } from "@phosphor-icons/react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { engineering } from "@/lib/format";
import { formatResultStatus, getMeasurementDisplayName, getMeasurementUnit } from "@/lib/presentation";
import type { Challenge, CircuitNode, EvaluationResponse, SimulationResult } from "@/lib/types";

export type Analysis = "op" | "ac" | "transient";
type InstrumentView = "measurements" | "magnitude" | "phase" | "console";

type AcPoint = { x: number; magnitude: number; phase: number };
type TooltipPayload = { payload?: AcPoint; value?: number };

function AcTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length || !payload[0]?.payload) return null;
  const point = payload[0].payload;
  return <div className="chart-tooltip"><strong>AC response</strong><span>Frequency <b>{engineering(point.x, "Hz")}</b></span><span>Gain <b>{engineering(point.magnitude, "dB")}</b></span>{Number.isFinite(point.phase) && <span>Phase <b>{engineering(point.phase, "°")}</b></span>}</div>;
}

function findCutoff(points: AcPoint[]): number | null {
  if (points.length < 2) return null;
  const target = points[0].magnitude - 3;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1]; const current = points[index];
    if (previous.magnitude >= target && current.magnitude <= target) {
      const span = current.magnitude - previous.magnitude;
      const ratio = Math.abs(span) < 1e-12 ? 0 : (target - previous.magnitude) / span;
      return previous.x + (current.x - previous.x) * Math.max(0, Math.min(1, ratio));
    }
  }
  return null;
}

export function ResultsPanel({ challenge, expanded, measuredNode, simulation, evaluation, stale = false, analysis, onAnalysisChange, onToggle }: { challenge: Challenge; expanded: boolean; measuredNode: CircuitNode | null; simulation: SimulationResult | null; evaluation: EvaluationResponse | null; stale?: boolean; canRun?: boolean; analysis: Analysis; onAnalysisChange: (analysis: Analysis) => void; onRun?: (kind: Analysis) => void; onToggle: () => void }) {
  const [view, setView] = useState<InstrumentView>("measurements");
  const isAc = simulation?.analysis === "ac";
  const series = simulation?.series;
  const outputSeries = measuredNode ? series?.[`voltage_v:${measuredNode.id}`] : undefined;
  const acPoints: AcPoint[] = isAc && series ? series.frequency_hz.map((frequency, index) => ({ x: frequency, magnitude: series.output_gain_db[index] ?? Number.NaN, phase: series.output_phase_deg?.[index] ?? Number.NaN })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.magnitude)) : [];
  const phasePoints = acPoints.filter((point) => Number.isFinite(point.phase));
  const cutoffFrequency = findCutoff(acPoints);
  const selectedFrequency = acPoints.length ? acPoints.reduce((closest, point) => Math.abs(point.x - 1_000) < Math.abs(closest.x - 1_000) ? point : closest, acPoints[0]) : null;
  const currentSeriesRows = Object.entries(series ?? {}).filter(([key]) => key.startsWith("current_a:") || key.startsWith("current_magnitude_a:")).map(([key, values]) => [key, values.at(-1) ?? Number.NaN] as [string, number]);
  const measureRows = (simulation?.analysis === "operating_point" ? Object.entries(simulation.measurements) : [...Object.entries(evaluation?.measurements ?? {}), ...currentSeriesRows]).filter(([key]) => key !== "component_count");
  const messages = [...(simulation?.warnings ?? []), ...(simulation?.errors.map((error) => error.message) ?? [])];

  const acView = view === "magnitude" || view === "phase";
  return <section className={`simulation-panel panel ${expanded ? "is-expanded" : ""}`} aria-label="Simulation instruments">
    <div className="simulation-panel__bar"><button aria-expanded={expanded} className="simulation-disclosure" onClick={onToggle} type="button">{expanded ? <CaretDownIcon aria-hidden size={15} /> : <CaretRightIcon aria-hidden size={15} />}<span><b>Instruments</b><small>{simulation ? `${simulation.analysis.replace("_", " ")} · Revision ${simulation.circuit_revision}${stale ? " · Stale" : ""}` : "No simulation recorded"}</small></span></button><div className="simulation-summary"><span className="probe-readout">Probe: {measuredNode?.label ?? "Output"}</span></div></div>
    {expanded && <div className="instrument-dock">
      <div className="instrument-toolbar"><nav aria-label="Instrument views">{([ ["measurements", "Measurements"], ["magnitude", "Magnitude"], ["phase", "Phase"], ["console", "Console"] ] as const).map(([id, label]) => <button aria-current={view === id ? "page" : undefined} className={view === id ? "is-active" : ""} key={id} onClick={() => setView(id)} type="button">{label}</button>)}</nav><div className="quick-run-controls"><span>Simulation</span>{([ ["op", "Operating point"], ["ac", "AC sweep"], ["transient", "Transient"] ] as const).map(([kind, label]) => <button aria-pressed={analysis === kind} className={analysis === kind ? "is-active" : ""} key={kind} onClick={() => onAnalysisChange(kind)} type="button">{label}</button>)}</div></div>
      {stale ? <div className="instrument-stale" role="status"><WarningIcon aria-hidden size={16} /><span><strong>Results are from an earlier circuit revision.</strong> Run the current circuit before using these measurements.</span></div> : null}
      <div className="instrument-content">
        {view === "measurements" && <div className="instrument-measurements"><section aria-label="Measurements"><header><h3>Recorded measurements</h3><span>{measuredNode?.label ?? "Output"}</span></header>{isAc && cutoffFrequency !== null && !Object.hasOwn(evaluation?.measurements ?? {}, "cutoff_frequency_hz") && <div className="measurement-row"><span>Cutoff Frequency</span><strong>{engineering(cutoffFrequency, "Hz")}</strong></div>}{isAc && selectedFrequency && !Object.hasOwn(evaluation?.measurements ?? {}, "gain_db_at_1000hz") && <div className="measurement-row"><span>Gain @ {engineering(selectedFrequency.x, "Hz")}</span><strong>{engineering(selectedFrequency.magnitude, "dB")}</strong></div>}{measureRows.length ? measureRows.map(([key, value]) => <div className="measurement-row" key={key}><span>{getMeasurementDisplayName(key)}</span><strong>{Number.isFinite(value) ? engineering(value, getMeasurementUnit(key)) : "Not available"}</strong></div>) : !isAc && <p className="empty-copy">Run the circuit to record measurements at the selected probe.</p>}</section><section aria-label="Acceptance criteria"><header><h3>Acceptance criteria</h3><span>{challenge.constraints.length}</span></header>{challenge.constraints.map((constraint) => <div className="measurement-row" key={constraint.id}><span>{getMeasurementDisplayName(constraint.metric)}</span><strong>{formatResultStatus(evaluation?.evaluation.results.find((item) => item.constraint_id === constraint.id)?.status ?? "NOT_EVALUATED")}</strong></div>)}</section></div>}
        {acView && ((view === "magnitude" ? acPoints : phasePoints).length > 0 ? <div className="instrument-waveform"><div className="chart-label"><ChartLineUpIcon aria-hidden size={16} /><span>{view === "magnitude" ? "Magnitude Response (VOUT / VIN)" : "Phase Response"}</span></div><div className="instrument-chart"><ResponsiveContainer height="100%" width="100%"><LineChart data={view === "magnitude" ? acPoints : phasePoints}><CartesianGrid stroke="var(--color-divider)" strokeDasharray="2 3" vertical={false} /><XAxis allowDataOverflow dataKey="x" domain={["dataMin", "dataMax"]} scale="log" tickFormatter={(value) => engineering(Number(value), "Hz")} type="number" /><YAxis domain={["auto", "auto"]} tickFormatter={(value) => engineering(Number(value), view === "magnitude" ? "dB" : "°")} /><Tooltip content={<AcTooltip />} />{view === "magnitude" && <ReferenceLine ifOverflow="extendDomain" label={{ fill: "var(--text-secondary)", fontSize: 10, position: "insideTopRight", value: "−3 dB" }} stroke="var(--text-secondary)" strokeDasharray="4 4" y={-3} />}<Line dataKey={view === "magnitude" ? "magnitude" : "phase"} dot={false} name={view === "magnitude" ? "Gain" : "Phase"} stroke="var(--color-accent)" strokeWidth={2} type="monotone" /></LineChart></ResponsiveContainer></div></div> : <div className="results-empty"><ChartLineUpIcon aria-hidden size={21} /><div><b>{simulation ? "No AC response available" : "No AC response recorded"}</b><p>Run an AC sweep to record magnitude and phase response.</p></div></div>)}
        {view === "console" && <div className="instrument-console"><header><strong>Simulator output</strong><span>{messages.length ? `${messages.length} ${messages.length === 1 ? "message" : "messages"}` : "Clear"}</span></header><div aria-live="polite" className="instrument-console__body" role="log">{messages.length ? messages.map((message, index) => <p key={`${message}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><code>{message}</code></p>) : <div className="instrument-console__empty"><strong>No simulator messages</strong><span>ngspice completed without warnings or errors for this revision.</span></div>}</div></div>}
      </div>
    </div>}
  </section>;
}
