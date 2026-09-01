"use client";

import "./workbench-redesign.css";
import "./workspace-data.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowClockwiseIcon, ArrowCounterClockwiseIcon, PlayIcon, WarningCircleIcon } from "@phosphor-icons/react";

import { api } from "@/lib/api";
import { useWebMCP } from "@/lib/useWebMCP";
import type { ChallengeSummary, Circuit, ComponentType, EvaluationResponse, Experiment, ExperimentDefinition, LabState, ParameterValue, SavedCircuitSummary, SimulationResult, ValidationResponse } from "@/lib/types";
import { ChallengeSelector } from "@/components/ChallengeSelector";
import { CircuitCanvas } from "@/components/CircuitCanvas";
import { ComponentTray } from "@/components/ComponentTray";
import { PropertyInspector } from "@/components/PropertyInspector";
import { ResultsPanel, type Analysis } from "@/components/ResultsPanel";
import { AppShell } from "@/components/AppShell";
import { ExperimentsWorkspace } from "@/components/ExperimentsWorkspace";
import { ExperimentBuilder } from "@/components/ExperimentBuilder";
import { ExperimentAnalysis } from "@/components/ExperimentAnalysis";
import { ExperimentExecution } from "@/components/ExperimentExecution";
import { ExperimentReport } from "@/components/ExperimentReport";
import { ReportsWorkspace } from "@/components/ReportsWorkspace";
import { WebMCPDiagnostics } from "@/components/WebMCPDiagnostics";

type AppSection = "workbench" | "experiments" | "reports";

export function LabWorkbench() {
  const { diagnostics: webmcpDiagnostics } = useWebMCP();
  const [lab, setLab] = useState<LabState | null>(null);
  const [challenges, setChallenges] = useState<ChallengeSummary[]>([]);
  const [section, setSection] = useState<AppSection>("workbench");
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [savedCircuits, setSavedCircuits] = useState<SavedCircuitSummary[]>([]);
  const [editingExperiment, setEditingExperiment] = useState(false);
  const [activeExperiment, setActiveExperiment] = useState<Experiment | null>(null);
  const [executingExperiment, setExecutingExperiment] = useState<Experiment | null>(null);
  const [analyzingExperiment, setAnalyzingExperiment] = useState<Experiment | null>(null);
  const [reportExperiment, setReportExperiment] = useState<Experiment | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [measuredNodeId, setMeasuredNodeId] = useState<string | null>(null);
  const [simulationExpanded, setSimulationExpanded] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis>("ac");
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renamingCircuit, setRenamingCircuit] = useState(false);
  const [circuitNameDraft, setCircuitNameDraft] = useState("");
  const undoHistory = useRef<Circuit[]>([]);
  const redoHistory = useRef<Circuit[]>([]);

  const refresh = useCallback(async () => {
    const [nextLab, nextExperiments, nextSavedCircuits] = await Promise.all([api.getLab(), api.getExperiments(), api.getSavedCircuits()]);
    setLab((current) => current && current.circuit.revision === nextLab.circuit.revision && current.circuit.name === nextLab.circuit.name && current.active_saved_circuit_id === nextLab.active_saved_circuit_id ? current : nextLab);
    setExperiments(nextExperiments);
    setSavedCircuits(nextSavedCircuits);
    setExecutingExperiment((current) => current ? nextExperiments.find((item) => item.id === current.id) ?? null : null);
    setAnalyzingExperiment((current) => current ? nextExperiments.find((item) => item.id === current.id) ?? null : null);
    setReportExperiment((current) => current ? nextExperiments.find((item) => item.id === current.id) ?? null : null);
  }, []);
  useEffect(() => { void Promise.all([refresh(), api.getChallenges().then(setChallenges)]).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load the lab.")); }, [refresh]);
  const activeExecution = experiments.some((experiment) => experiment.execution_status === "running" || experiment.execution_status === "paused");
  useEffect(() => {
    const sync = () => { if (!document.hidden) void refresh().catch(() => undefined); };
    const timer = window.setInterval(sync, activeExecution ? 750 : section === "workbench" ? 2_000 : 4_000);
    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", sync);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", sync); document.removeEventListener("visibilitychange", sync); };
  }, [activeExecution, refresh, section]);
  useEffect(() => {
    if (!lab) return;
    void api.validate().then(setValidation).catch(() => undefined);
  }, [lab?.circuit.revision]);
  const selected = useMemo(() => lab?.circuit.components.find((component) => component.id === selectedId) ?? null, [lab, selectedId]);
  const mutate = async (action: () => Promise<Circuit>) => { if (!lab) return null; const before = lab.circuit; setBusy(true); setError(null); try { const circuit = await action(); undoHistory.current = [...undoHistory.current.slice(-49), before]; redoHistory.current = []; setLab((current) => current ? { ...current, circuit } : current); setEvaluation(null); void Promise.all([api.getSavedCircuits(), api.getLab()]).then(([circuits, nextLab]) => { setSavedCircuits(circuits); setLab(nextLab); }).catch(() => undefined); return circuit; } catch (reason) { setError(reason instanceof Error ? reason.message : "Circuit change failed."); return null; } finally { setBusy(false); } };
  const run = async (kind: Analysis) => { if (!lab) return; setAnalysis(kind); setBusy(true); setError(null); setSimulationExpanded(true); try { const checked = await api.validate(); setValidation(checked); if (!checked.valid) return; const output = measuredNodeId ?? lab.circuit.metadata.output_node ?? lab.circuit.nodes.find((node) => node.id !== "gnd")?.id ?? "gnd"; const input = lab.circuit.metadata.input_node ?? lab.circuit.nodes.find((node) => node.id !== "gnd")?.id ?? "gnd"; const currentComponents = selected && selected.type !== "ground" ? [selected.id] : []; const result = kind === "op" ? await api.runOperatingPoint([output], currentComponents) : kind === "ac" ? await api.runAc(input, output, currentComponents) : await api.runTransient([output], currentComponents); setSimulation(result); if (result.success) setEvaluation(await api.evaluate([result.simulation_id])); await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Simulation failed."); } finally { setBusy(false); } };
  const chooseChallenge = async (challengeId: string) => { setBusy(true); setError(null); try { const nextLab = await api.loadChallenge(challengeId); undoHistory.current = []; redoHistory.current = []; setLab(nextLab); setSimulation(null); setEvaluation(null); setValidation(null); setSelectedId(null); setSelectedNodeId(null); setMeasuredNodeId(null); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load challenge."); } finally { setBusy(false); } };
  const createBlankCircuit = async () => { setBusy(true); setError(null); try { const nextLab = await api.createBlankCircuit(); undoHistory.current = []; redoHistory.current = []; setLab(nextLab); setSimulation(null); setEvaluation(null); setValidation(null); setSelectedId(null); setSelectedNodeId(null); setMeasuredNodeId(null); await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create a blank circuit."); } finally { setBusy(false); } };
  const renameCurrentCircuit = async (name: string) => { if (!lab) return; const nextName = name.trim(); setRenamingCircuit(false); if (!nextName || nextName === lab.circuit.name) return; setBusy(true); setError(null); try { await api.saveCurrentCircuit(nextName, lab.active_saved_circuit_id); await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not rename this circuit."); } finally { setBusy(false); } };
  const openSavedCircuit = async (circuitId: string) => { setBusy(true); setError(null); try { const nextLab = await api.openSavedCircuit(circuitId); undoHistory.current = []; redoHistory.current = []; setLab(nextLab); setSimulation(null); setEvaluation(null); setValidation(null); setSelectedId(null); setSelectedNodeId(null); setMeasuredNodeId(null); await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not open the saved circuit."); } finally { setBusy(false); } };
  const deleteSavedCircuit = async (circuitId: string) => { setBusy(true); setError(null); try { const nextLab = await api.deleteSavedCircuit(circuitId); if (lab?.active_saved_circuit_id === circuitId) { undoHistory.current = []; redoHistory.current = []; setLab(nextLab); setSimulation(null); setEvaluation(null); setValidation(null); setSelectedId(null); setSelectedNodeId(null); setMeasuredNodeId(null); } await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not delete this circuit."); } finally { setBusy(false); } };
  const restoreHistorySnapshot = useCallback(async (direction: "undo" | "redo") => { if (!lab || busy) return; const source = direction === "undo" ? undoHistory : redoHistory; const destination = direction === "undo" ? redoHistory : undoHistory; const snapshot = source.current.at(-1); if (!snapshot) return; setBusy(true); setError(null); try { const circuit = await api.restoreCircuit(snapshot, lab.circuit.revision); source.current = source.current.slice(0, -1); destination.current = [...destination.current.slice(-49), lab.circuit]; setLab((current) => current ? { ...current, circuit } : current); setSimulation(null); setEvaluation(null); setSelectedId(null); setSelectedNodeId(null); void api.getSavedCircuits().then(setSavedCircuits).catch(() => undefined); } catch (reason) { setError(reason instanceof Error ? reason.message : `Could not ${direction} the circuit change.`); } finally { setBusy(false); } }, [busy, lab]);
  useEffect(() => { const handleHistory = (event: KeyboardEvent) => { const target = event.target as HTMLElement | null; if (section !== "workbench" || (!event.metaKey && !event.ctrlKey) || target?.closest("input, textarea, select, [contenteditable='true']")) return; const redo = (event.key.toLowerCase() === "z" && event.shiftKey) || event.key.toLowerCase() === "y"; const undo = event.key.toLowerCase() === "z" && !event.shiftKey; if (!undo && !redo) return; event.preventDefault(); void restoreHistorySnapshot(redo ? "redo" : "undo"); }; window.addEventListener("keydown", handleHistory); return () => window.removeEventListener("keydown", handleHistory); }, [section, restoreHistorySnapshot]);
  useEffect(() => { const handleEditorShortcut = (event: KeyboardEvent) => { const target = event.target as HTMLElement | null; if (section !== "workbench" || busy || target?.closest("input, textarea, select, [contenteditable='true']")) return; if (event.key === "Escape") { setSelectedId(null); return; } if (!selected || !lab) return; if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); void mutate(() => api.removeComponent(selected.id, lab.circuit.revision)); } if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") { event.preventDefault(); void mutate(() => api.addComponent(selected.type, selected.params, lab.circuit.revision)); } }; window.addEventListener("keydown", handleEditorShortcut); return () => window.removeEventListener("keydown", handleEditorShortcut); }, [busy, lab, section, selected]);
  const saveDefinition = async (definition: ExperimentDefinition, runAfterSave = false) => { setBusy(true); setError(null); try { const saved = activeExperiment ? await api.updateExperimentDefinition(activeExperiment.id, definition) : await api.saveExperimentDefinition(definition); if (runAfterSave) { const executing = await api.executeExperimentDefinition(saved.id); setExecutingExperiment(executing); } await refresh(); setEditingExperiment(false); setActiveExperiment(null); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save experiment."); } finally { setBusy(false); } };
  const startExperiment = async () => { if (!executingExperiment) return; setError(null); try { await api.executeExperimentDefinition(executingExperiment.id); setExecutingExperiment({ ...executingExperiment, execution_status: "running" }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not start experiment."); } };
  const runExperimentFromList = async (experiment: Experiment) => { setError(null); setExecutingExperiment(experiment); try { const updated = await api.executeExperimentDefinition(experiment.id); setExecutingExperiment(updated); await refresh(); } catch (reason) { setExecutingExperiment(null); setError(reason instanceof Error ? reason.message : "Could not start experiment."); } };
  const controlExperiment = async (action: "pause" | "resume" | "stop") => { if (!executingExperiment) return; if (action === "stop" && !window.confirm("Stop this experiment? Completed runs will be preserved and remaining runs will not execute.")) return; setError(null); try { const updated = action === "pause" ? await api.pauseExperimentDefinition(executingExperiment.id) : action === "resume" ? await api.resumeExperimentDefinition(executingExperiment.id) : await api.stopExperimentDefinition(executingExperiment.id); setExecutingExperiment(updated); await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : `Could not ${action} experiment.`); } };
  const duplicateExperiment = async (experiment: Experiment) => { setError(null); try { await api.duplicateExperimentDefinition(experiment.id); await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not duplicate experiment."); } };
  const deleteExperiment = async (experiment: Experiment) => { if (!window.confirm(`Delete ${experiment.name ?? experiment.hypothesis}? This removes its recorded runs and report.`)) return; setError(null); try { await api.deleteExperimentDefinition(experiment.id); await refresh(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not delete experiment."); } };
  if (!lab) return <main aria-busy="true" aria-label="Loading workbench" className="loading-workbench"><header><span /><span /><span /></header><div className="loading-workbench__nav" /><div className="loading-workbench__workspace"><aside /><section /><aside /></div><div className="loading-workbench__dock" /></main>;
  const revision = lab.circuit.revision;
  const measuredNode = lab.circuit.nodes.find((node) => node.id === measuredNodeId) ?? lab.circuit.nodes.find((node) => node.id === lab.circuit.metadata.output_node) ?? null;
  const invalidPins = validation?.issues.filter((issue) => issue.code === "FLOATING_PIN").flatMap((issue) => {
    const match = /([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)/.exec(issue.message);
    return match ? [`${match[1]}:${match[2]}`] : [];
  }) ?? [];
  const validationIssueCount = validation?.issues.length ?? 0;
  const reviewValidation = () => {
    const first = validation?.issues[0];
    const match = first && /([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)/.exec(first.message);
    if (match) { setSelectedId(match[1]); setSelectedNodeId(null); }
  };
  return <AppShell activeWorkspace={section} onWorkspaceChange={setSection} projectControl={<ChallengeSelector activeId={lab.challenge.id} activeSavedCircuitId={lab.active_saved_circuit_id} activeTitle={lab.circuit.name} challenges={challenges} disabled={busy} onCreateBlank={() => void createBlankCircuit()} onDeleteSaved={(id) => void deleteSavedCircuit(id)} onLoad={(id) => void chooseChallenge(id)} onOpenSaved={(id) => void openSavedCircuit(id)} savedCircuits={savedCircuits} />} working={busy}>
    {error && <div className="notice notice--error" role="alert"><WarningCircleIcon aria-hidden size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError(null)} type="button">Dismiss</button></div>}
    <WebMCPDiagnostics diagnostics={webmcpDiagnostics} />
    {section === "workbench" && <section className="workbench-shell"><header className="workspace-toolbar"><div>{renamingCircuit ? <input aria-label="Circuit name" autoFocus className="workspace-circuit-name-input" onBlur={() => void renameCurrentCircuit(circuitNameDraft)} onChange={(event) => setCircuitNameDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.currentTarget.blur(); } if (event.key === "Escape") { setRenamingCircuit(false); } }} value={circuitNameDraft} /> : <button className="workspace-circuit-name" onClick={() => { setCircuitNameDraft(lab.circuit.name); setRenamingCircuit(true); }} title="Rename circuit" type="button">{lab.circuit.name}</button>}<span>Revision {revision}</span></div><div><button aria-label="Undo circuit change" className="toolbar-icon-button" disabled={busy || !undoHistory.current.length} onClick={() => void restoreHistorySnapshot("undo")} title="Undo circuit change (Ctrl/⌘ Z)" type="button"><ArrowCounterClockwiseIcon aria-hidden size={16} /></button><button aria-label="Redo circuit change" className="toolbar-icon-button" disabled={busy || !redoHistory.current.length} onClick={() => void restoreHistorySnapshot("redo")} title="Redo circuit change (Ctrl/⌘ Shift Z)" type="button"><ArrowClockwiseIcon aria-hidden size={16} /></button><button aria-label={validationIssueCount ? "Review wiring issues" : "Circuit ready"} className={`circuit-status ${validationIssueCount ? "circuit-status--warning" : ""}`} onClick={reviewValidation} type="button">{validationIssueCount ? `${validationIssueCount} wiring issue${validationIssueCount === 1 ? "" : "s"}` : "Circuit ready"}</button><span className="workspace-probe">Probe: {measuredNode?.label ?? "Output"}</span><button className="button button--primary" disabled={busy || Boolean(validationIssueCount)} onClick={() => void run(analysis)} type="button"><PlayIcon aria-hidden size={14} />Run {analysis === "op" ? "operating point" : analysis === "ac" ? "AC sweep" : "transient"}</button></div></header><div className="workbench"><ComponentTray allowed={lab.challenge.allowed_components} onAdd={(type: ComponentType, params: Record<string, ParameterValue>) => void mutate(() => api.addComponent(type, params, revision))} /><CircuitCanvas circuit={lab.circuit} invalidPins={invalidPins} onAddComponent={(type, params, point) => mutate(() => api.addComponent(type, params, revision, point))} onClearSelection={() => { setSelectedId(null); setSelectedNodeId(null); }} onConnectPins={(source, target) => void mutate(() => api.connectPins(source.componentId, source.pin, target.componentId, target.pin, revision))} onConnectToNode={(source, nodeId) => void mutate(() => api.connect(source.componentId, source.pin, nodeId, revision))} onSetLayout={(id, position, rotation) => void mutate(() => api.setComponentLayout(id, position, rotation, revision))} onSelectComponent={(id) => { setSelectedId(id); setSelectedNodeId(null); }} onSelectNode={(id) => { setSelectedNodeId(id); setSelectedId(null); }} selectedComponentId={selectedId} selectedNodeId={selectedNodeId} /><PropertyInspector circuit={lab.circuit} component={selected} onConnect={(id, pin, node) => void mutate(() => api.connect(id, pin, node, revision))} onDelete={(id) => void mutate(() => api.removeComponent(id, revision))} onRenameNode={(id, label) => void mutate(() => api.renameNode(id, label, revision))} onSetProbe={setMeasuredNodeId} onSetValue={(id, parameter, value) => void mutate(() => api.setComponentValue(id, parameter, value, revision))} probeNodeId={measuredNode?.id ?? null} selectedNode={selectedId || !selectedNodeId ? null : lab.circuit.nodes.find((node) => node.id === selectedNodeId) ?? null} /><ResultsPanel analysis={analysis} challenge={lab.challenge} evaluation={simulation?.circuit_revision === revision ? evaluation : null} expanded={simulationExpanded} measuredNode={measuredNode} onAnalysisChange={setAnalysis} onToggle={() => setSimulationExpanded((current) => !current)} simulation={simulation} stale={Boolean(simulation && simulation.circuit_revision !== revision)} /></div></section>}
    {section === "experiments" && (analyzingExperiment ? <ExperimentAnalysis experiment={analyzingExperiment} onBack={() => setAnalyzingExperiment(null)} onOpenReport={() => { setReportExperiment(analyzingExperiment); setAnalyzingExperiment(null); setSection("reports"); }} /> : executingExperiment ? <ExperimentExecution experiment={executingExperiment} onAnalyze={() => { setAnalyzingExperiment(executingExperiment); setExecutingExperiment(null); }} onBack={() => setExecutingExperiment(null)} onPause={() => void controlExperiment("pause")} onResume={() => void controlExperiment("resume")} onRun={() => void startExperiment()} onStop={() => void controlExperiment("stop")} /> : editingExperiment ? <ExperimentBuilder circuit={lab.circuit} collectionOptions={[...new Set(experiments.map((experiment) => experiment.collection_name?.trim()).filter((name): name is string => Boolean(name)))].sort()} initial={activeExperiment} onCancel={() => { setEditingExperiment(false); setActiveExperiment(null); }} onSave={(definition, runAfterSave) => void saveDefinition(definition, runAfterSave)} /> : <ExperimentsWorkspace experiments={experiments} onAnalyze={setAnalyzingExperiment} onCreate={() => { setActiveExperiment(null); setEditingExperiment(true); }} onDelete={(experiment) => void deleteExperiment(experiment)} onDuplicate={(experiment) => void duplicateExperiment(experiment)} onOpen={(experiment) => { if (experiment.run_results?.length) setAnalyzingExperiment(experiment); else { setActiveExperiment(experiment); setEditingExperiment(true); } }} onRun={(experiment) => void runExperimentFromList(experiment)} />)}
    {section === "reports" && (reportExperiment ? <ExperimentReport experiment={reportExperiment} onBack={() => setReportExperiment(null)} /> : <ReportsWorkspace experiments={experiments} onCreateExperiment={() => { setSection("experiments"); setActiveExperiment(null); setEditingExperiment(true); }} onOpen={setReportExperiment} />)}
  </AppShell>;
}
