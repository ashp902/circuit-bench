import type { ChallengeSummary, Circuit, ComponentType, EvaluationResponse, Experiment, ExperimentDefinition, LabState, ParameterValue, SavedCircuitSummary, SimulationResult, ValidationResponse, WebMCPDefinition } from "@/lib/types";

export type HealthResponse = { status: "ok"; service: string };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export async function getHealth(fetcher: typeof fetch = fetch): Promise<HealthResponse> {
  return request<HealthResponse>("/health", undefined, fetcher);
}

async function request<T>(path: string, init?: RequestInit, fetcher: typeof fetch = fetch): Promise<T> {
  const response = await fetcher(`${API_BASE_URL}${path}`, { cache: "no-store", headers: { "Content-Type": "application/json", ...init?.headers }, ...init });
  const body = (await response.json()) as T | { error?: { message?: string } };
  if (!response.ok) {
    const message = (body as { error?: { message?: string } }).error?.message;
    throw new Error(message ?? `API request failed with ${response.status}.`);
  }
  return body as T;
}

const json = (body: object): Pick<RequestInit, "body"> => ({ body: JSON.stringify(body) });

export const api = {
  getLab: () => request<LabState>("/api/lab"),
  getChallenges: () => request<ChallengeSummary[]>("/api/challenges"),
  loadChallenge: (challengeId: string) => request<LabState>(`/api/challenges/${challengeId}/load`, { method: "POST", ...json({}) }),
  createBlankCircuit: () => request<LabState>("/api/circuits/blank", { method: "POST", ...json({}) }),
  getSavedCircuits: () => request<SavedCircuitSummary[]>("/api/circuits"),
  saveCurrentCircuit: (name: string, circuitId?: string | null) => request<SavedCircuitSummary>("/api/circuits", { method: "POST", ...json({ name, circuit_id: circuitId ?? undefined }) }),
  openSavedCircuit: (circuitId: string) => request<LabState>(`/api/circuits/${circuitId}/open`, { method: "POST", ...json({}) }),
  deleteSavedCircuit: (circuitId: string) => request<LabState>(`/api/circuits/${circuitId}`, { method: "DELETE" }),
  getCircuit: () => request<Circuit>("/api/circuit"),
  restoreCircuit: (circuit: Circuit, expectedRevision: number) => request<Circuit>("/api/circuit/restore", { method: "POST", ...json({ circuit, expected_revision: expectedRevision }) }),
  getExperiments: () => request<Experiment[]>("/api/experiments"),
  saveExperimentDefinition: (definition: ExperimentDefinition) => request<Experiment>("/api/experiment-definitions", { method: "POST", ...json(definition) }),
  updateExperimentDefinition: (id: string, definition: ExperimentDefinition) => request<Experiment>(`/api/experiment-definitions/${id}`, { method: "PUT", ...json(definition) }),
  executeExperimentDefinition: (id: string) => request<Experiment>(`/api/experiment-definitions/${id}/execute`, { method: "POST", ...json({}) }),
  pauseExperimentDefinition: (id: string) => request<Experiment>(`/api/experiment-definitions/${id}/pause`, { method: "POST", ...json({}) }),
  resumeExperimentDefinition: (id: string) => request<Experiment>(`/api/experiment-definitions/${id}/resume`, { method: "POST", ...json({}) }),
  stopExperimentDefinition: (id: string) => request<Experiment>(`/api/experiment-definitions/${id}/stop`, { method: "POST", ...json({}) }),
  duplicateExperimentDefinition: (id: string) => request<Experiment>(`/api/experiment-definitions/${id}/duplicate`, { method: "POST", ...json({}) }),
  deleteExperimentDefinition: (id: string) => request<{ deleted: boolean }>(`/api/experiment-definitions/${id}`, { method: "DELETE" }),
  addComponent: (type: ComponentType, params: Record<string, ParameterValue>, expectedRevision: number, position?: { x: number; y: number }) => request<Circuit>("/api/components", { method: "POST", ...json({ type, params, expected_revision: expectedRevision, position }) }),
  setComponentLayout: (componentId: string, position: { x: number; y: number }, rotation: 0 | 90 | 180 | 270, expectedRevision: number) => request<Circuit>(`/api/components/${componentId}/layout`, { method: "PATCH", ...json({ position, rotation, expected_revision: expectedRevision }) }),
  renameNode: (nodeId: string, label: string, expectedRevision: number) => request<Circuit>(`/api/nodes/${nodeId}`, { method: "PATCH", ...json({ label, expected_revision: expectedRevision }) }),
  setComponentValue: (componentId: string, parameter: string, value: ParameterValue, expectedRevision: number) => request<Circuit>(`/api/components/${componentId}`, { method: "PATCH", ...json({ parameter, value, expected_revision: expectedRevision }) }),
  removeComponent: (componentId: string, expectedRevision: number) => request<Circuit>(`/api/components/${componentId}`, { method: "DELETE", ...json({ expected_revision: expectedRevision }) }),
  disconnect: (componentId: string, pin: string, expectedRevision: number) => request<Circuit>("/api/connections", { method: "DELETE", ...json({ component_id: componentId, pin, expected_revision: expectedRevision }) }),
  connect: (componentId: string, pin: string, nodeId: string, expectedRevision: number) => request<Circuit>("/api/connections", { method: "POST", ...json({ component_id: componentId, pin, node_id: nodeId, expected_revision: expectedRevision }) }),
  connectPins: (sourceComponentId: string, sourcePin: string, targetComponentId: string, targetPin: string, expectedRevision: number) => request<Circuit>("/api/connections/pins", { method: "POST", ...json({ source_component_id: sourceComponentId, source_pin: sourcePin, target_component_id: targetComponentId, target_pin: targetPin, expected_revision: expectedRevision }) }),
  validate: () => request<ValidationResponse>("/api/validate", { method: "POST", ...json({}) }),
  runOperatingPoint: (outputNodes: string[], currentComponents: string[] = []) => request<SimulationResult>("/api/simulations/op", { method: "POST", ...json({ output_nodes: outputNodes, current_components: currentComponents }) }),
  runAc: (inputNode: string, outputNode: string, currentComponents: string[] = []) => request<SimulationResult>("/api/simulations/ac", { method: "POST", ...json({ start_hz: 10, stop_hz: 100_000, points_per_decade: 50, input_node: inputNode, output_node: outputNode, current_components: currentComponents }) }),
  runTransient: (outputNodes: string[], currentComponents: string[] = []) => request<SimulationResult>("/api/simulations/transient", { method: "POST", ...json({ duration_s: 0.05, time_step_s: 0.00001, output_nodes: outputNodes, current_components: currentComponents }) }),
  evaluate: (simulationIds: string[]) => request<EvaluationResponse>("/api/constraints/evaluate", { method: "POST", ...json({ simulation_ids: simulationIds }) }),
  saveExperiment: (hypothesis: string, conclusion: string, simulationIds: string[]) => request<Experiment>("/api/experiments", { method: "POST", ...json({ hypothesis, conclusion, simulation_ids: simulationIds }) }),
  restoreExperiment: (experimentId: string, expectedRevision: number) => request<Circuit>(`/api/experiments/${experimentId}/restore`, { method: "POST", ...json({ expected_revision: expectedRevision }) }),
  restoreExperimentRun: (experimentId: string, runIndex: number, expectedRevision: number) => request<Circuit>(`/api/experiments/${experimentId}/runs/${runIndex}/restore`, { method: "POST", ...json({ expected_revision: expectedRevision }) }),
  getWebMCPTools: () => request<WebMCPDefinition[]>("/api/webmcp/tools"),
  invokeWebMCP: (tool: string, args: Record<string, unknown>) => request<unknown>("/api/webmcp/invoke", { method: "POST", ...json({ tool, arguments: args }) }),
};
