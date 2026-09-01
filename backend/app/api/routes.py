from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas import (
    AcRequest,
    AddComponentRequest,
    ConnectionRequest,
    CreateBlankCircuitRequest,
    CreateNodeRequest,
    RenameNodeRequest,
    ComponentLayoutRequest,
    DisconnectRequest,
    ExperimentDefinitionRequest,
    EvaluateRequest,
    OperatingPointRequest,
    PinPairConnectionRequest,
    ResetLabRequest,
    RestoreCircuitRequest,
    SaveCircuitRequest,
    RevisionRequest,
    SaveExperimentRequest,
    SetParameterRequest,
    TransientRequest,
)
from app.models.circuit import Circuit, Experiment, SimulationResult
from app.services.challenge_catalog import list_challenges, load_challenge
from app.services.errors import CircuitError
from app.services.lab_service import LabService
from app.services.netlist_service import AcAnalysis, TransientAnalysis
from app.webmcp.tools import ToolCall, ToolDefinition, WebMCPToolRegistry


router = APIRouter(prefix="/api")


def service(request: Request) -> LabService:
    return request.app.state.lab_service


def webmcp(request: Request) -> WebMCPToolRegistry:
    return request.app.state.webmcp_tools


@router.get("/lab")
def get_lab(request: Request) -> dict[str, object]:
    return service(request).get_state()


@router.get("/challenges")
def get_challenges() -> list[dict[str, object]]:
    return [{"id": challenge.id, "title": challenge.title, "description": challenge.description} for challenge in list_challenges()]


@router.post("/challenges/{challenge_id}/load")
def load_template(challenge_id: str, request: Request) -> dict[str, object]:
    template = load_challenge(challenge_id)
    if template is None:
        raise CircuitError("INVALID_PARAMETER", f"Unknown challenge template {challenge_id}.")
    return service(request).reset(*template)


@router.post("/lab")
def reset_lab(payload: ResetLabRequest, request: Request) -> dict[str, object]:
    return service(request).reset(payload.challenge, payload.circuit)


@router.post("/circuits/blank")
def create_blank_circuit(payload: CreateBlankCircuitRequest, request: Request) -> dict[str, object]:
    return service(request).create_blank_circuit(payload.name)


@router.get("/circuits")
def list_saved_circuits(request: Request) -> list[dict[str, object]]:
    active_id = service(request).repository.get_active_saved_circuit_id()
    return [
        {"id": circuit.id, "name": circuit.name, "created_at": circuit.created_at, "updated_at": circuit.updated_at, "component_count": len(circuit.circuit_snapshot.components), "active": circuit.id == active_id}
        for circuit in service(request).list_saved_circuits()
    ]


@router.post("/circuits")
def save_current_circuit(payload: SaveCircuitRequest, request: Request) -> dict[str, object]:
    saved = service(request).save_current_circuit(payload.name, payload.circuit_id)
    return {"id": saved.id, "name": saved.name, "created_at": saved.created_at, "updated_at": saved.updated_at, "component_count": len(saved.circuit_snapshot.components), "active": True}


@router.post("/circuits/{circuit_id}/open")
def open_saved_circuit(circuit_id: str, request: Request) -> dict[str, object]:
    return service(request).open_saved_circuit(circuit_id)


@router.delete("/circuits/{circuit_id}")
def delete_saved_circuit(circuit_id: str, request: Request) -> dict[str, object]:
    return service(request).delete_saved_circuit(circuit_id)


@router.get("/circuit")
def get_circuit(request: Request) -> Circuit:
    return service(request).repository.get_circuit()


@router.post("/circuit/restore")
def restore_circuit(payload: RestoreCircuitRequest, request: Request) -> Circuit:
    return service(request).restore_circuit(payload.circuit, payload.expected_revision)


@router.post("/components")
def add_component(payload: AddComponentRequest, request: Request) -> Circuit:
    return service(request).add_component(payload.type, payload.params, payload.expected_revision, payload.position)


@router.patch("/components/{component_id}")
def set_component_parameter(component_id: str, payload: SetParameterRequest, request: Request) -> Circuit:
    return service(request).set_parameter(component_id, payload.parameter, payload.value, payload.expected_revision)


@router.patch("/components/{component_id}/layout")
def set_component_layout(component_id: str, payload: ComponentLayoutRequest, request: Request) -> Circuit:
    return service(request).set_component_layout(component_id, payload.position, payload.rotation, payload.expected_revision)


@router.delete("/components/{component_id}")
def remove_component(component_id: str, payload: RevisionRequest, request: Request) -> Circuit:
    return service(request).remove_component(component_id, payload.expected_revision)


@router.post("/nodes")
def create_node(payload: CreateNodeRequest, request: Request) -> Circuit:
    return service(request).create_node(payload.label, payload.expected_revision)


@router.patch("/nodes/{node_id}")
def rename_node(node_id: str, payload: RenameNodeRequest, request: Request) -> Circuit:
    return service(request).rename_node(node_id, payload.label, payload.expected_revision)


@router.post("/connections")
def connect(payload: ConnectionRequest, request: Request) -> Circuit:
    return service(request).connect(payload.component_id, payload.pin, payload.node_id, payload.expected_revision)


@router.post("/connections/pins")
def connect_pins(payload: PinPairConnectionRequest, request: Request) -> Circuit:
    return service(request).connect_pins(
        payload.source_component_id,
        payload.source_pin,
        payload.target_component_id,
        payload.target_pin,
        payload.expected_revision,
    )


@router.delete("/connections")
def disconnect(payload: DisconnectRequest, request: Request) -> Circuit:
    return service(request).disconnect(payload.component_id, payload.pin, payload.expected_revision)


@router.post("/validate")
def validate(request: Request) -> dict[str, object]:
    return service(request).validate()


@router.post("/simulations/op")
def run_operating_point(payload: OperatingPointRequest, request: Request) -> SimulationResult:
    return service(request).run_operating_point(payload.output_nodes, payload.current_components)


@router.post("/simulations/ac")
def run_ac(payload: AcRequest, request: Request) -> SimulationResult:
    return service(request).run_ac(
        AcAnalysis(
            start_hz=payload.start_hz,
            stop_hz=payload.stop_hz,
            points_per_decade=payload.points_per_decade,
            input_node=payload.input_node,
            output_node=payload.output_node,
        ),
        payload.current_components,
    )


@router.post("/simulations/transient")
def run_transient(payload: TransientRequest, request: Request) -> SimulationResult:
    return service(request).run_transient(
        TransientAnalysis(
            duration_s=payload.duration_s,
            time_step_s=payload.time_step_s,
            output_nodes=tuple(payload.output_nodes),
        ),
        payload.current_components,
    )


@router.post("/constraints/evaluate")
def evaluate_constraints(payload: EvaluateRequest, request: Request) -> dict[str, object]:
    metrics, evaluation = service(request).evaluate(payload.simulation_ids)
    return {"measurements": metrics, "evaluation": evaluation}


@router.get("/experiments")
def list_experiments(request: Request) -> list[Experiment]:
    return service(request).experiments.list()


@router.post("/experiments")
def save_experiment(payload: SaveExperimentRequest, request: Request) -> Experiment:
    return service(request).save_experiment(payload.hypothesis, payload.conclusion, payload.simulation_ids)


@router.post("/experiment-definitions")
def save_experiment_definition(payload: ExperimentDefinitionRequest, request: Request) -> Experiment:
    return service(request).experiments.save_definition(service(request).repository.get_circuit(), payload)


@router.put("/experiment-definitions/{experiment_id}")
def update_experiment_definition(experiment_id: str, payload: ExperimentDefinitionRequest, request: Request) -> Experiment:
    return service(request).experiments.update_definition(experiment_id, service(request).repository.get_circuit(), payload)


@router.post("/experiment-definitions/{experiment_id}/execute")
def execute_experiment_definition(experiment_id: str, request: Request) -> Experiment:
    return service(request).experiments.start_execution(experiment_id, service(request).simulator)


@router.post("/experiment-definitions/{experiment_id}/pause")
def pause_experiment_definition(experiment_id: str, request: Request) -> Experiment:
    return service(request).experiments.pause_execution(experiment_id)


@router.post("/experiment-definitions/{experiment_id}/resume")
def resume_experiment_definition(experiment_id: str, request: Request) -> Experiment:
    return service(request).experiments.resume_execution(experiment_id)


@router.post("/experiment-definitions/{experiment_id}/stop")
def stop_experiment_definition(experiment_id: str, request: Request) -> Experiment:
    return service(request).experiments.stop_execution(experiment_id)


@router.post("/experiment-definitions/{experiment_id}/duplicate")
def duplicate_experiment_definition(experiment_id: str, request: Request) -> Experiment:
    return service(request).experiments.duplicate_definition(experiment_id)


@router.delete("/experiment-definitions/{experiment_id}")
def delete_experiment_definition(experiment_id: str, request: Request) -> dict[str, bool]:
    service(request).experiments.delete_definition(experiment_id)
    return {"deleted": True}


@router.post("/experiments/{experiment_id}/restore")
def restore_experiment(experiment_id: str, payload: RevisionRequest, request: Request) -> Circuit:
    return service(request).experiments.restore(experiment_id, payload.expected_revision)


@router.post("/experiments/{experiment_id}/runs/{run_index}/restore")
def restore_experiment_run(experiment_id: str, run_index: int, payload: RevisionRequest, request: Request) -> Circuit:
    return service(request).experiments.restore_run(experiment_id, run_index, payload.expected_revision)


@router.get("/webmcp/tools")
def list_webmcp_tools(request: Request) -> list[ToolDefinition]:
    return webmcp(request).definitions()


@router.post("/webmcp/invoke")
def invoke_webmcp_tool(payload: ToolCall, request: Request) -> object:
    return webmcp(request).invoke(payload.tool, payload.arguments)
