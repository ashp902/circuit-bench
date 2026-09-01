"use client";

import "./reports-workspace.css";

import { FileTextIcon } from "@phosphor-icons/react";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatExperimentType } from "@/lib/presentation";
import type { Experiment } from "@/lib/types";

export function ReportsWorkspace({ experiments, onCreateExperiment, onOpen }: { experiments: Experiment[]; onCreateExperiment: () => void; onOpen: (experiment: Experiment) => void }) {
  const available = experiments.filter((experiment) => (experiment.run_results?.length ?? 0) > 0);
  return <section className="reports-workspace"><header className="workspace-page-header"><div><h2>Reports</h2><p>Reproducible technical records generated from completed experiments.</p></div></header>{available.length ? <div className="data-table-wrap"><table className="reports-table data-table"><thead><tr><th>Report</th><th>Circuit</th><th className="numeric-column">Runs</th><th>Executed</th><th aria-label="Actions" /></tr></thead><tbody>{available.map((experiment) => <tr key={experiment.id}><td><button className="table-primary-link" onClick={() => onOpen(experiment)} type="button">{experiment.name ?? experiment.hypothesis}</button><span className="table-secondary-copy">{formatExperimentType(experiment.experiment_type)} experiment</span></td><td>{experiment.circuit_snapshot?.name ?? "Circuit"}<span className="table-secondary-copy">Revision {experiment.circuit_revision}</span></td><td className="numeric-column">{experiment.run_results?.length ?? 0}</td><td>{new Date(experiment.completed_at ?? experiment.created_at).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })}</td><td><button className="button button--secondary" onClick={() => onOpen(experiment)} type="button"><FileTextIcon aria-hidden size={14} />Open Report</button></td></tr>)}</tbody></table></div> : <EmptyState action={<button className="button button--primary" onClick={onCreateExperiment} type="button">Create Experiment</button>} title="No reports available"><span>Run an experiment to generate a reproducible engineering report.</span></EmptyState>}</section>;
}
