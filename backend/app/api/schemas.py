from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.circuit import Challenge, Circuit, ComponentType, ParameterValue, Position


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResetLabRequest(ApiModel):
    challenge: Challenge
    circuit: Circuit


class CreateBlankCircuitRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)


class SaveCircuitRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    circuit_id: str | None = Field(default=None, pattern=r"^circuit_[0-9]{3,}$")


class RevisionRequest(ApiModel):
    expected_revision: int = Field(ge=0)


class RestoreCircuitRequest(RevisionRequest):
    """Restore an earlier client-held circuit snapshot as the next revision."""

    circuit: Circuit


class AddComponentRequest(RevisionRequest):
    type: ComponentType
    params: dict[str, ParameterValue] = Field(default_factory=dict)
    position: Position | None = None


class VoltageSourceParams(ApiModel):
    mode: Literal["dc", "sine", "pulse"] = "dc"


class SetParameterRequest(RevisionRequest):
    parameter: str
    value: ParameterValue


class CreateNodeRequest(RevisionRequest):
    label: str


class RenameNodeRequest(RevisionRequest):
    label: str = Field(min_length=1, max_length=64)


class ComponentLayoutRequest(RevisionRequest):
    position: Position
    rotation: int


class AutoLayoutRequest(RevisionRequest):
    preserve_manual: bool = True


class ConnectionRequest(RevisionRequest):
    component_id: str
    pin: str
    node_id: str


class PinPairConnectionRequest(RevisionRequest):
    """Connect two schematic terminals without exposing the net bookkeeping."""

    source_component_id: str
    source_pin: str
    target_component_id: str
    target_pin: str


class DisconnectRequest(RevisionRequest):
    component_id: str
    pin: str


class OperatingPointRequest(ApiModel):
    output_nodes: list[str] = Field(min_length=1, max_length=20)
    current_components: list[str] = Field(default_factory=list, max_length=20)


class AcRequest(ApiModel):
    start_hz: float
    stop_hz: float
    points_per_decade: int = 50
    input_node: str
    output_node: str
    current_components: list[str] = Field(default_factory=list, max_length=20)


class TransientRequest(ApiModel):
    duration_s: float
    time_step_s: float
    output_nodes: list[str] = Field(min_length=1, max_length=20)
    current_components: list[str] = Field(default_factory=list, max_length=20)


class EvaluateRequest(ApiModel):
    simulation_ids: list[str] = Field(min_length=1, max_length=20)


class SaveExperimentRequest(EvaluateRequest):
    hypothesis: str = Field(min_length=1, max_length=2_000)
    conclusion: str = Field(default="", max_length=2_000)


class ExperimentDefinitionRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    experiment_type: str = Field(default="manual", min_length=1, max_length=80)
    circuit_revision: int = Field(ge=0)
    variables: list[dict[str, object]] = Field(default_factory=list)
    # Structured descriptors are the canonical form; strings remain accepted
    # at the API boundary for older clients and are normalized during execution.
    measurement_definitions: list[dict[str, object] | str] = Field(default_factory=list)
    requirement_definitions: list[dict[str, object]] = Field(default_factory=list)
    generated_runs: list[dict[str, object]] = Field(default_factory=list)
    collection_name: str = Field(default="", max_length=120)
    run_by: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=4_000)


class UpdateExperimentDefinitionRequest(ExperimentDefinitionRequest):
    pass
