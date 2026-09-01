"use client";

import { ArrowCounterClockwiseIcon, FloppyDiskIcon } from "@phosphor-icons/react";

import { engineering } from "@/lib/format";
import type { Experiment, SimulationResult } from "@/lib/types";

export function ExperimentTimeline({ experiments, simulation, onRestore, onSave }: { experiments: Experiment[]; simulation: SimulationResult | null; onRestore: (id: string) => void; onSave: () => void }) {
  return <section className="timeline panel" aria-label="Experiment timeline"><div className="timeline-heading"><div><p className="section-kicker">Experiment timeline</p><h2>Evidence, not guesses</h2></div>{simulation?.success && <button className="save-button" onClick={onSave} type="button"><FloppyDiskIcon aria-hidden size={16} />Save experiment</button>}</div>
    {experiments.length === 0 ? <p className="empty-copy">No experiments yet. The first simulation can be saved here.</p> : <div className="experiment-list">{experiments.map((experiment) => { const passed = experiment.constraint_results.filter((item) => item.status === "PASS").length; const failed = experiment.constraint_results.filter((item) => item.status === "FAIL").length; return <article className="experiment-card" key={experiment.id}><div><span className="experiment-number">Experiment #{experiment.sequence}</span><strong>{failed ? "FAIL" : passed ? "PASS" : "OPEN"}</strong></div><p><b>Hypothesis:</b> {experiment.hypothesis}</p><small><b>Result:</b> {experiment.conclusion || "No conclusion recorded."}</small><div className="experiment-metrics">{Object.entries(experiment.measurements).slice(0, 3).map(([metric, value]) => <span key={metric}>{metric.replaceAll("_", " ")}: {engineering(value)}</span>)}</div><small>{passed} pass · {failed} fail · revision {experiment.circuit_revision}</small><button onClick={() => onRestore(experiment.id)} type="button"><ArrowCounterClockwiseIcon aria-hidden size={15} />Restore</button></article>; })}</div>}</section>;
}
