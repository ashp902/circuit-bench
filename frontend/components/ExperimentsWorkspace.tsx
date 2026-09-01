"use client";

import { CopyIcon, DotsThreeIcon, PlayIcon, PlusIcon, TrashIcon } from "@phosphor-icons/react";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatExecutionStatus, formatExperimentType, getParameterReferenceLabel } from "@/lib/presentation";
import type { Experiment } from "@/lib/types";

function statusTone(status?: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "running" || status === "paused") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

export function ExperimentsWorkspace({ experiments, onAnalyze, onCreate, onDelete, onDuplicate, onOpen, onRun }: { experiments: Experiment[]; onAnalyze: (experiment: Experiment) => void; onCreate: () => void; onDelete: (experiment: Experiment) => void; onDuplicate: (experiment: Experiment) => void; onOpen: (experiment: Experiment) => void; onRun: (experiment: Experiment) => void }) {
  const collections = experiments.reduce<Record<string, Experiment[]>>((groups, experiment) => {
    const name = experiment.collection_name?.trim() || "Unfiled";
    (groups[name] ??= []).push(experiment);
    return groups;
  }, {});
  const collectionEntries = Object.entries(collections).sort(([left], [right]) => left === "Unfiled" ? 1 : right === "Unfiled" ? -1 : left.localeCompare(right));
  return <section className="experiments-page">
    <header className="workspace-page-header"><div><h2>Experiments</h2><p>Define parameter sweeps, record measurements, and retain a traceable run record.</p></div>{experiments.length ? <button className="button button--primary" onClick={onCreate} type="button"><PlusIcon aria-hidden size={14} />New Experiment</button> : null}</header>
    {experiments.length ? <div className="data-table-wrap"><table className="experiments-table data-table"><thead><tr><th>Experiment</th><th>Circuit</th><th>Type</th><th className="numeric-column">Runs</th><th>Run by</th><th>Status</th><th>Completed</th><th aria-label="Actions" /></tr></thead>{collectionEntries.map(([collection, items]) => <tbody key={collection}><tr className="collection-row"><th colSpan={8}><span>{collection}</span><small>{items.length} experiment{items.length === 1 ? "" : "s"}</small></th></tr>{items.map((experiment) => { const active = experiment.execution_status === "running" || experiment.execution_status === "paused"; const canRun = experiment.execution_status === "ready" && Boolean(experiment.generated_runs?.some((run) => run.enabled !== false)); return <tr key={experiment.id}><td><button className="table-primary-link" onClick={() => onOpen(experiment)} type="button">{experiment.name ?? experiment.hypothesis}</button>{experiment.description ? <span className="table-secondary-copy">{experiment.description}</span> : null}</td><td>{experiment.circuit_snapshot?.name ?? "Circuit"}<span className="table-secondary-copy">Revision {experiment.circuit_revision}</span></td><td>{formatExperimentType(experiment.experiment_type)}</td><td className="numeric-column">{experiment.generated_runs?.length ?? 0}</td><td>{experiment.run_by || <span className="table-muted">Not recorded</span>}</td><td><StatusBadge tone={statusTone(experiment.execution_status)}>{formatExecutionStatus(experiment.execution_status)}</StatusBadge></td><td>{experiment.completed_at ? new Date(experiment.completed_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "Not run"}</td><td className="table-actions"><details><summary aria-label={`Actions for ${experiment.name ?? experiment.hypothesis}`}><DotsThreeIcon aria-hidden size={18} /></summary><div className="table-action-menu"><button onClick={() => onOpen(experiment)} type="button">Open experiment</button>{canRun ? <button onClick={() => onRun(experiment)} type="button"><PlayIcon aria-hidden size={13} />Run</button> : null}{experiment.run_results?.length ? <button onClick={() => onAnalyze(experiment)} type="button">View analysis</button> : null}<button onClick={() => onDuplicate(experiment)} type="button"><CopyIcon aria-hidden size={13} />Duplicate</button><button className="table-action-menu__danger" disabled={active} onClick={() => onDelete(experiment)} title={active ? "Stop the experiment before deleting it" : "Delete experiment"} type="button"><TrashIcon aria-hidden size={13} />Delete</button></div></details></td></tr>; })}</tbody>)}</table></div> : <EmptyState action={<button className="button button--primary" onClick={onCreate} type="button">Create Experiment</button>} title="No experiments yet"><span>Create an experiment to vary circuit parameters and record measurements across simulation runs.</span></EmptyState>}
  </section>;
}
