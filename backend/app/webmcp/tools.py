from __future__ import annotations

import csv
import io
import json
import math
import time
from collections.abc import Callable
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.api.schemas import (
    AcRequest,
    AddComponentRequest,
    ConnectionRequest,
    CreateBlankCircuitRequest,
    CreateNodeRequest,
    DisconnectRequest,
    OperatingPointRequest,
    PinPairConnectionRequest,
    ResetLabRequest,
    RevisionRequest,
    RestoreCircuitRequest,
    RenameNodeRequest,
    SetParameterRequest,
    TransientRequest,
)
from app.models.circuit import Experiment, SimulationResult
from app.services.challenge_catalog import list_challenges, load_challenge
from app.services.errors import CircuitError
from app.services.lab_service import LabService
from app.services.netlist_service import AcAnalysis, TransientAnalysis


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(ToolInput):
    pass


class ComponentInput(ToolInput):
    component_id: str


class VoltageMeasurementInput(ToolInput):
    simulation_id: str
    node: str
    mode: Literal["dc", "max", "min", "final"]


class CurrentMeasurementInput(ToolInput):
    simulation_id: str
    component_id: str
    mode: Literal["dc", "max", "min", "final"]


class GainMeasurementInput(ToolInput):
    simulation_id: str
    input_node: str
    output_node: str
    frequency_hz: float


class SimulationInput(ToolInput):
    simulation_id: str


class RiseTimeInput(ToolInput):
    simulation_id: str
    node: str


class EvaluateInput(ToolInput):
    simulation_ids: list[str] = Field(min_length=1, max_length=20)


class ListExperimentsInput(ToolInput):
    limit: int = Field(default=20, ge=1, le=100)


class RestoreInput(RevisionRequest):
    model_config = ConfigDict(extra="forbid")
    experiment_id: str


class ChallengeInput(ToolInput):
    challenge_id: str


class CreateBlankCircuitInput(CreateBlankCircuitRequest):
    model_config = ConfigDict(extra="forbid")


class SavedCircuitIdInput(ToolInput):
    circuit_id: str


class RenameNodeInput(RenameNodeRequest):
    model_config = ConfigDict(extra="forbid")
    node_id: str


class RenameCircuitInput(ToolInput):
    name: str = Field(min_length=1, max_length=160)


class ResetLabInput(ResetLabRequest):
    model_config = ConfigDict(extra="forbid")


class DisconnectInput(DisconnectRequest):
    model_config = ConfigDict(extra="forbid")


class ConnectPinsInput(PinPairConnectionRequest):
    model_config = ConfigDict(extra="forbid")


class RestoreCircuitInput(RestoreCircuitRequest):
    model_config = ConfigDict(extra="forbid")


class ExperimentIdInput(ToolInput):
    experiment_id: str


class LinearSweepVariableInput(ToolInput):
    component_id: str = Field(min_length=1)
    parameter: str = Field(min_length=1)
    label: str = Field(default="", max_length=160)
    unit: str = Field(default="", max_length=32)
    sweep: Literal["linear"]
    start: float
    stop: float
    points: int = Field(ge=2, le=1_000)

    @model_validator(mode="after")
    def increasing_range(self) -> "LinearSweepVariableInput":
        if not math.isfinite(self.start) or not math.isfinite(self.stop) or self.start >= self.stop:
            raise ValueError("linear sweep start and stop must be finite and increasing")
        return self


class LogarithmicSweepVariableInput(LinearSweepVariableInput):
    sweep: Literal["logarithmic"]

    @model_validator(mode="after")
    def positive_range(self) -> "LogarithmicSweepVariableInput":
        if self.start <= 0:
            raise ValueError("logarithmic sweep start must be positive")
        return self


class ExplicitSweepVariableInput(ToolInput):
    component_id: str = Field(min_length=1)
    parameter: str = Field(min_length=1)
    label: str = Field(default="", max_length=160)
    unit: str = Field(default="", max_length=32)
    sweep: Literal["explicit"]
    values: list[float] = Field(min_length=1, max_length=1_000)

    @field_validator("values")
    @classmethod
    def finite_values(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("explicit sweep values must be finite")
        return values


SweepVariableInput = Annotated[
    LinearSweepVariableInput | LogarithmicSweepVariableInput | ExplicitSweepVariableInput,
    Field(discriminator="sweep"),
]


class AcGainExperimentMeasurementInput(ToolInput):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    type: Literal["ac_gain_db"]
    input_node: str = Field(min_length=1)
    output_node: str = Field(min_length=1)
    frequency_hz: float = Field(gt=0)


class DcVoltageExperimentMeasurementInput(ToolInput):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    type: Literal["dc_voltage"]
    node: str = Field(min_length=1)


ExperimentMeasurementInput = Annotated[
    AcGainExperimentMeasurementInput | DcVoltageExperimentMeasurementInput,
    Field(discriminator="type"),
]


class ExperimentRequirementInput(ToolInput):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    measurement_id: str = Field(min_length=1, max_length=120)
    operator: Literal[">=", "<=", ">", "<"]
    target: float


class ExperimentDefinitionInput(ToolInput):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    experiment_type: str = Field(default="manual", min_length=1, max_length=80)
    circuit_revision: int = Field(ge=0)
    variables: list[SweepVariableInput] = Field(default_factory=list, max_length=2)
    measurement_definitions: list[ExperimentMeasurementInput] = Field(default_factory=list, max_length=100)
    requirement_definitions: list[ExperimentRequirementInput] = Field(default_factory=list, max_length=100)
    collection_name: str = Field(default="", max_length=120)
    run_by: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def validate_definition_links(self) -> "ExperimentDefinitionInput":
        variable_keys = [(item.component_id, item.parameter) for item in self.variables]
        if len(variable_keys) != len(set(variable_keys)):
            raise ValueError("sweep variables must use unique component_id/parameter pairs")
        measurement_ids = [item.id for item in self.measurement_definitions]
        if len(measurement_ids) != len(set(measurement_ids)):
            raise ValueError("measurement ids must be unique")
        requirement_ids = [item.id for item in self.requirement_definitions]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement ids must be unique")
        unknown = sorted({item.measurement_id for item in self.requirement_definitions}.difference(measurement_ids))
        if unknown:
            raise ValueError(f"requirements reference unknown measurement ids: {', '.join(unknown)}")
        return self


class UpdateExperimentInput(ExperimentDefinitionInput):
    experiment_id: str


class RunExperimentInput(ExperimentIdInput):
    wait_for_completion: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)


class ExperimentPlanInput(ExperimentIdInput):
    offset: int = Field(default=0, ge=0)
    sample_limit: int = Field(default=20, ge=1, le=100)


class ExperimentResultsInput(ExperimentIdInput):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class ExperimentRunInput(ExperimentIdInput):
    run_index: int = Field(ge=1)


class RestoreRunInput(RevisionRequest):
    model_config = ConfigDict(extra="forbid")
    experiment_id: str
    run_index: int = Field(ge=1)


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, object]
    read_only: bool


class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, object] = Field(default_factory=dict)


Handler = Callable[[BaseModel], object]
ModelType = TypeVar("ModelType", bound=BaseModel)


class WebMCPToolRegistry:
    """Thin semantic WebMCP handlers over the same canonical LabService as REST."""

    def __init__(self, labs: LabService) -> None:
        self._labs = labs
        self._tools: dict[str, tuple[str, type[BaseModel], Handler, bool]] = {}
        self._register_tools()

    def definitions(self) -> list[ToolDefinition]:
        definitions: list[ToolDefinition] = []
        for name, (description, input_model, _handler, read_only) in self._tools.items():
            schema = input_model.model_json_schema()
            if name == "add_component":
                schema.setdefault("allOf", []).append({
                    "if": {"properties": {"type": {"const": "voltage_source"}}, "required": ["type"]},
                    "then": {"properties": {"params": {"type": "object", "properties": {
                        "mode": {"type": "string", "enum": ["dc", "sine", "pulse"], "description": "Source waveform used for DC/transient analysis; AC is an analysis mode, not a source mode."},
                        "voltage_v": {"type": "number", "description": "DC source voltage/bias in volts. AC analysis does not use this as its small-signal amplitude."},
                        "amplitude_v": {"type": "number", "description": "Sine-wave peak amplitude in volts for transient analysis only."},
                    }, "description": "AC sweeps always inject a normalized 1 V small-signal source and compute gain from VOUT/VIN. ac_amplitude and ac_amplitude_v are not supported parameters."}}},
                })
            definitions.append(ToolDefinition(name=name, description=description, input_schema=schema, read_only=read_only))
        return definitions

    def invoke(self, name: str, arguments: dict[str, object]) -> object:
        tool = self._tools.get(name)
        if tool is None:
            raise CircuitError("INVALID_PARAMETER", f"Unknown WebMCP tool {name}.")
        _description, input_model, handler, _read_only = tool
        try:
            parsed = input_model.model_validate(arguments)
        except ValidationError as error:
            raise CircuitError("INVALID_PARAMETER", f"Invalid input for {name}.", str(error)) from error
        return handler(parsed)

    def _register(self, name: str, description: str, input_model: type[BaseModel], handler: Handler, *, read_only: bool) -> None:
        self._tools[name] = (description, input_model, handler, read_only)

    def _register_tools(self) -> None:
        self._register("get_lab_state", "Inspect the active challenge, canonical circuit, and latest experiment. Call this before planning lab work.", EmptyInput, lambda _args: self._labs.get_state(), read_only=True)
        self._register("list_challenges", "List the available challenge templates and their engineering goals. Call this before load_challenge.", EmptyInput, lambda _args: [{"id": challenge.id, "title": challenge.title, "description": challenge.description} for challenge in list_challenges()], read_only=True)
        self._register("load_challenge", "Replace the active lab with one public challenge template and its canonical circuit. This discards the current active lab state.", ChallengeInput, self._load_challenge, read_only=False)
        self._register("create_blank_circuit", "Create a new unrestricted blank circuit with only the Ground reference. Components are placed deterministically and direct pin connections create nets automatically.", CreateBlankCircuitInput, self._create_blank_circuit, read_only=False)
        self._register("list_saved_circuits", "List named saved circuits available to open in this browser session's workbench.", EmptyInput, self._list_saved_circuits, read_only=True)
        self._register("rename_circuit", "Rename the active circuit. Its latest circuit state remains saved automatically.", RenameCircuitInput, self._rename_circuit, read_only=False)
        self._register("open_saved_circuit", "Open a named saved circuit as this browser session's active workbench circuit without deleting experiment history.", SavedCircuitIdInput, self._open_saved_circuit, read_only=False)
        self._register("delete_saved_circuit", "Delete a saved circuit. If it is open, this browser session's workbench returns to the default circuit.", SavedCircuitIdInput, self._delete_saved_circuit, read_only=False)
        self._register("reset_lab", "Replace the active challenge and circuit using the same backend reset behavior as the human application. This discards the current active lab state.", ResetLabInput, self._reset_lab, read_only=False)
        self._register("get_circuit", "Inspect components, electrical nodes, values, connections, and the current revision.", EmptyInput, lambda _args: self._labs.repository.get_circuit(), read_only=True)
        self._register("get_constraints", "Read the exact machine-evaluated engineering requirements for the active challenge.", EmptyInput, lambda _args: self._labs.repository.get_challenge().constraints, read_only=True)
        self._register("add_component", "Add one allowed primitive component with deterministic automatic placement. Use the current expected_revision to avoid overwriting human edits.", AddComponentRequest, self._add_component, read_only=False)
        self._register("create_node", "Create an optional named electrical net. Direct connect_pins creates a net automatically.", CreateNodeRequest, self._create_node, read_only=False)
        self._register("rename_net", "Rename an existing non-ground electrical net while preserving its stable id and topology.", RenameNodeInput, self._rename_net, read_only=False)
        self._register("connect", "Connect one component pin to an existing electrical node.", ConnectionRequest, self._connect, read_only=False)
        self._register("connect_pins", "Connect two component pins directly, automatically creating, reusing, or merging their electrical net. Use the current expected_revision.", ConnectPinsInput, self._connect_pins, read_only=False)
        self._register("disconnect", "Disconnect one component pin from its current electrical node. Use the current expected_revision; validate_circuit should normally follow.", DisconnectInput, self._disconnect, read_only=False)
        self._register("set_component_value", "Change one supported SI-unit component parameter using a revision-safe mutation.", SetParameterRequestWithId, self._set_component_value, read_only=False)
        self._register("remove_component", "Remove one component using a revision-safe mutation.", RemoveComponentInput, self._remove_component, read_only=False)
        self._register("restore_circuit", "Restore a caller-held circuit snapshot as the next revision without rewinding history. Use the current expected_revision.", RestoreCircuitInput, self._restore_circuit, read_only=False)
        self._register("validate_circuit", "Validate ground, pins, component values, limits, and graph integrity before simulation.", EmptyInput, lambda _args: self._labs.validate(), read_only=True)
        self._register("run_operating_point", "Run real ngspice DC operating-point analysis for bias, node voltages, and requested component currents.", OperatingPointRequest, self._run_operating_point, read_only=False)
        self._register("run_ac_analysis", "Run real ngspice frequency analysis for gain, attenuation, cutoff, bandwidth, and requested component currents. The source is normalized to AC 1 V and gain is computed from VOUT/VIN; voltage_v is DC bias and amplitude_v is transient sine amplitude.", AcRequest, self._run_ac, read_only=False)
        self._register("run_transient", "Run real ngspice time analysis for clipping, rise time, extrema, settling, and requested component currents.", TransientRequest, self._run_transient, read_only=False)
        self._register("measure_voltage", "Measure DC, maximum, minimum, or final voltage from an existing simulation.", VoltageMeasurementInput, self._measure_voltage, read_only=True)
        self._register("measure_current", "Measure actual ngspice branch current for a component included in an operating-point, AC, or transient simulation.", CurrentMeasurementInput, self._measure_current, read_only=True)
        self._register("measure_gain", "Interpolate Vout/Vin gain in dB at a requested frequency from an existing AC simulation.", GainMeasurementInput, self._measure_gain, read_only=True)
        self._register("measure_cutoff_frequency", "Measure the first descending minus-3-dB cutoff from an existing AC simulation.", SimulationInput, self._measure_cutoff, read_only=True)
        self._register("measure_rise_time", "Measure 10-to-90-percent rise time for a node from an existing transient simulation.", RiseTimeInput, self._measure_rise_time, read_only=True)
        self._register("evaluate_constraints", "Deterministically evaluate challenge constraints using existing simulation evidence.", EvaluateInput, self._evaluate, read_only=True)
        self._register("create_experiment", "Create a draft experiment bound to the current circuit revision and snapshot. Sweep variables, AC-gain measurements, and measurement-linked requirements are validated before persistence.", ExperimentDefinitionInput, self._create_experiment, read_only=False)
        self._register("get_experiment", "Read one experiment definition and traceability metadata without returning a full circuit snapshot. Call get_experiment_plan or get_experiment_results for focused detail.", ExperimentIdInput, self._get_experiment, read_only=True)
        self._register("list_experiments", "List concise saved experiment records in newest-first order. Use get_experiment for a complete definition.", ListExperimentsInput, self._list_experiments, read_only=True)
        self._register("update_experiment", "Update an unexecuted experiment with strongly typed sweep variables, measurements, and measurement-linked requirements. The Cartesian run matrix is generated automatically; executed experiments are immutable.", UpdateExperimentInput, self._update_experiment, read_only=False)
        self._register("get_experiment_plan", "Preview an experiment's sweep definitions, measurements, requirements, generated-run count, enabled count, representative runs, and readiness before execution.", ExperimentPlanInput, self._get_experiment_plan, read_only=True)
        self._register("run_experiment", "Execute every enabled sweep point through the canonical simulator, persist measurements and requirement PASS/FAIL outcomes, and by default wait for final counts and worst-case analysis.", RunExperimentInput, self._run_experiment, read_only=False)
        self._register("pause_experiment", "Pause an active experiment using the same execution control as the human application. Completed runs remain recorded.", ExperimentIdInput, self._pause_experiment, read_only=False)
        self._register("resume_experiment", "Resume a paused experiment using the same execution control as the human application.", ExperimentIdInput, self._resume_experiment, read_only=False)
        self._register("stop_experiment", "Stop an active experiment using the same execution control as the human application. Completed runs remain recorded.", ExperimentIdInput, self._stop_experiment, read_only=False)
        self._register("get_experiment_results", "Read a paginated result slice plus concise status, pass/fail, error, and measurement-range summaries. Use get_experiment_run for one full run.", ExperimentResultsInput, self._get_experiment_results, read_only=True)
        self._register("get_experiment_run", "Read one recorded run: parameters, measurements, requirement outcomes, simulator status, error, and timestamps.", ExperimentRunInput, self._get_experiment_run, read_only=True)
        self._register("get_experiment_analysis", "Read deterministic range, pass/fail, operating-region, response, and requirement analysis derived from recorded runs. It does not generate speculative conclusions.", ExperimentIdInput, self._get_experiment_analysis, read_only=True)
        self._register("get_report", "Read structured technical report data derived from the executed experiment, circuit snapshot, setup, results, and reproducibility record.", ExperimentIdInput, self._get_report, read_only=True)
        self._register("export_report", "Export the structured technical report as real JSON content for an executed experiment; it does not create a placeholder URL.", ExperimentIdInput, self._export_report, read_only=True)
        self._register("export_run_data", "Export recorded experiment runs as real CSV content for an executed experiment; it does not create a placeholder URL.", ExperimentIdInput, self._export_run_data, read_only=True)
        self._register("duplicate_experiment", "Duplicate an experiment definition to create a new independent execution record. Use this to repeat a completed experiment.", ExperimentIdInput, self._duplicate_experiment, read_only=False)
        self._register("delete_experiment", "Delete an experiment definition and its recorded runs. Active experiments cannot be deleted.", ExperimentIdInput, self._delete_experiment, read_only=False)
        self._register("restore_experiment", "Restore a saved experiment circuit snapshot as a new revision without erasing later history. Use the current expected_revision.", RestoreInput, self._restore_experiment, read_only=False)
        self._register("restore_experiment_run", "Restore one recorded run's parameterized circuit as a new revision without changing experiment history. Use the current expected_revision.", RestoreRunInput, self._restore_experiment_run, read_only=False)

    def _load_challenge(self, args: BaseModel) -> object:
        payload = self._expect(args, ChallengeInput)
        template = load_challenge(payload.challenge_id)
        if template is None:
            raise CircuitError("INVALID_PARAMETER", f"Unknown challenge template {payload.challenge_id}.")
        return self._labs.reset(*template)

    def _create_blank_circuit(self, args: BaseModel) -> object:
        payload = self._expect(args, CreateBlankCircuitInput)
        return self._labs.create_blank_circuit(payload.name)

    def _list_saved_circuits(self, _args: BaseModel) -> object:
        active_id = self._labs.repository.get_active_saved_circuit_id()
        return [{"id": circuit.id, "name": circuit.name, "component_count": len(circuit.circuit_snapshot.components), "updated_at": circuit.updated_at, "active": circuit.id == active_id} for circuit in self._labs.list_saved_circuits()]

    def _rename_circuit(self, args: BaseModel) -> object:
        payload = self._expect(args, RenameCircuitInput)
        circuit = self._labs.save_current_circuit(payload.name, self._labs.repository.get_active_saved_circuit_id())
        return {"id": circuit.id, "name": circuit.name, "updated_at": circuit.updated_at, "component_count": len(circuit.circuit_snapshot.components)}

    def _open_saved_circuit(self, args: BaseModel) -> object:
        payload = self._expect(args, SavedCircuitIdInput)
        return self._labs.open_saved_circuit(payload.circuit_id)

    def _delete_saved_circuit(self, args: BaseModel) -> object:
        payload = self._expect(args, SavedCircuitIdInput)
        return self._labs.delete_saved_circuit(payload.circuit_id)

    def _reset_lab(self, args: BaseModel) -> object:
        payload = self._expect(args, ResetLabInput)
        return self._labs.reset(payload.challenge, payload.circuit)

    def _connect_pins(self, args: BaseModel) -> object:
        payload = self._expect(args, ConnectPinsInput)
        circuit = self._labs.connect_pins(payload.source_component_id, payload.source_pin, payload.target_component_id, payload.target_pin, payload.expected_revision)
        return {"source": {"component_id": payload.source_component_id, "pin": payload.source_pin}, "target": {"component_id": payload.target_component_id, "pin": payload.target_pin}, "new_revision": circuit.revision}

    def _disconnect(self, args: BaseModel) -> object:
        payload = self._expect(args, DisconnectInput)
        circuit = self._labs.disconnect(payload.component_id, payload.pin, payload.expected_revision)
        return {"component_id": payload.component_id, "pin": payload.pin, "new_revision": circuit.revision}

    def _restore_circuit(self, args: BaseModel) -> object:
        payload = self._expect(args, RestoreCircuitInput)
        circuit = self._labs.restore_circuit(payload.circuit, payload.expected_revision)
        return {"circuit_id": circuit.id, "new_revision": circuit.revision}

    def _add_component(self, args: BaseModel) -> object:
        payload = self._expect(args, AddComponentRequest)
        circuit = self._labs.add_component(payload.type, payload.params, payload.expected_revision, payload.position)
        return {"component": circuit.components[-1], "new_revision": circuit.revision}

    def _create_node(self, args: BaseModel) -> object:
        payload = self._expect(args, CreateNodeRequest)
        circuit = self._labs.create_node(payload.label, payload.expected_revision)
        return {"node": circuit.nodes[-1], "new_revision": circuit.revision}

    def _rename_net(self, args: BaseModel) -> object:
        payload = self._expect(args, RenameNodeInput)
        circuit = self._labs.rename_node(payload.node_id, payload.label, payload.expected_revision)
        node = next(node for node in circuit.nodes if node.id == payload.node_id)
        return {"node": node, "new_revision": circuit.revision}

    def _connect(self, args: BaseModel) -> object:
        payload = self._expect(args, ConnectionRequest)
        circuit = self._labs.connect(payload.component_id, payload.pin, payload.node_id, payload.expected_revision)
        return {"component_id": payload.component_id, "pin": payload.pin, "node_id": payload.node_id, "new_revision": circuit.revision}

    def _set_component_value(self, args: BaseModel) -> object:
        payload = self._expect(args, SetParameterRequestWithId)
        circuit = self._labs.set_parameter(payload.component_id, payload.parameter, payload.value, payload.expected_revision)
        return {"component_id": payload.component_id, "parameter": payload.parameter, "value": payload.value, "new_revision": circuit.revision}

    def _remove_component(self, args: BaseModel) -> object:
        payload = self._expect(args, RemoveComponentInput)
        circuit = self._labs.remove_component(payload.component_id, payload.expected_revision)
        return {"removed_component_id": payload.component_id, "new_revision": circuit.revision}

    def _run_operating_point(self, args: BaseModel) -> object:
        payload = self._expect(args, OperatingPointRequest)
        return self._simulation_summary(self._labs.run_operating_point(payload.output_nodes, payload.current_components))

    def _run_ac(self, args: BaseModel) -> object:
        payload = self._expect(args, AcRequest)
        result = self._labs.run_ac(AcAnalysis(payload.start_hz, payload.stop_hz, payload.points_per_decade, payload.input_node, payload.output_node), payload.current_components)
        summary: dict[str, object] = self._simulation_summary(result)
        if result.success:
            summary["summary"] = {
                "low_frequency_gain_db": result.series["output_gain_db"][0],
                "peak_gain_db": max(result.series["output_gain_db"]),
                "points": len(result.series["frequency_hz"]),
            }
        return summary

    def _run_transient(self, args: BaseModel) -> object:
        payload = self._expect(args, TransientRequest)
        result = self._labs.run_transient(TransientAnalysis(payload.duration_s, payload.time_step_s, tuple(payload.output_nodes)), payload.current_components)
        return self._simulation_summary(result)

    def _measure_voltage(self, args: BaseModel) -> object:
        payload = self._expect(args, VoltageMeasurementInput)
        value = self._labs.measurements.measure_voltage(self._labs.repository.get_simulation(payload.simulation_id), payload.node, payload.mode)
        return {"simulation_id": payload.simulation_id, "node": payload.node, "mode": payload.mode, "voltage_v": value}

    def _measure_current(self, args: BaseModel) -> object:
        payload = self._expect(args, CurrentMeasurementInput)
        value = self._labs.measurements.measure_current(self._labs.repository.get_simulation(payload.simulation_id), payload.component_id, payload.mode)
        return {"simulation_id": payload.simulation_id, "component_id": payload.component_id, "mode": payload.mode, "current_a": value}

    def _measure_gain(self, args: BaseModel) -> object:
        payload = self._expect(args, GainMeasurementInput)
        gain = self._labs.measurements.measure_gain(self._labs.repository.get_simulation(payload.simulation_id), payload.frequency_hz)
        return {"simulation_id": payload.simulation_id, "frequency_hz": payload.frequency_hz, "gain_db": gain}

    def _measure_cutoff(self, args: BaseModel) -> object:
        payload = self._expect(args, SimulationInput)
        cutoff = self._labs.measurements.measure_cutoff_frequency(self._labs.repository.get_simulation(payload.simulation_id))
        return {"simulation_id": payload.simulation_id, "cutoff_frequency_hz": cutoff}

    def _measure_rise_time(self, args: BaseModel) -> object:
        payload = self._expect(args, RiseTimeInput)
        rise_time = self._labs.measurements.measure_rise_time(self._labs.repository.get_simulation(payload.simulation_id), payload.node)
        return {"simulation_id": payload.simulation_id, "node": payload.node, "rise_time_s": rise_time}

    def _evaluate(self, args: BaseModel) -> object:
        payload = self._expect(args, EvaluateInput)
        measurements, evaluation = self._labs.evaluate(payload.simulation_ids)
        return {"measurements": measurements, "evaluation": evaluation}

    def _create_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentDefinitionInput)
        experiment = self._labs.experiments.save_definition(self._labs.repository.get_circuit(), payload)
        return self._experiment_summary(experiment)

    def _get_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        return self._experiment_definition(self._labs.repository.get_experiment(payload.experiment_id))

    def _list_experiments(self, args: BaseModel) -> object:
        payload = self._expect(args, ListExperimentsInput)
        experiments = self._labs.experiments.list()[: payload.limit]
        return [self._experiment_summary(experiment) for experiment in experiments]

    def _update_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, UpdateExperimentInput)
        experiment = self._labs.experiments.update_definition(payload.experiment_id, self._labs.repository.get_circuit(), payload)
        return self._experiment_summary(experiment)

    def _get_experiment_plan(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentPlanInput)
        experiment = self._labs.repository.get_experiment(payload.experiment_id)
        return self._experiment_plan(experiment, payload.offset, payload.sample_limit)

    def _run_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, RunExperimentInput)
        experiment = self._labs.experiments.start_execution(payload.experiment_id, self._labs.simulator)
        if not payload.wait_for_completion:
            return self._execution_summary(experiment, execution_state="starting")
        deadline = time.monotonic() + payload.timeout_seconds
        while time.monotonic() < deadline:
            experiment = self._labs.repository.get_experiment(payload.experiment_id)
            if experiment.execution_status in {"completed", "failed", "interrupted"}:
                break
            time.sleep(0.01)
        response = self._execution_summary(experiment)
        response["analysis"] = self._experiment_analysis(experiment)
        response["timed_out_waiting"] = experiment.execution_status not in {"completed", "failed", "interrupted"}
        return response

    def _pause_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        return self._execution_summary(self._labs.experiments.pause_execution(payload.experiment_id))

    def _resume_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        return self._execution_summary(self._labs.experiments.resume_execution(payload.experiment_id))

    def _stop_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        return self._execution_summary(self._labs.experiments.stop_execution(payload.experiment_id))

    def _get_experiment_results(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentResultsInput)
        experiment = self._labs.repository.get_experiment(payload.experiment_id)
        results = experiment.run_results[payload.offset : payload.offset + payload.limit]
        return {
            **self._execution_summary(experiment),
            "offset": payload.offset,
            "limit": payload.limit,
            "returned_runs": len(results),
            "total_recorded_runs": len(experiment.run_results),
            "runs": results,
            "analysis": self._experiment_analysis(experiment, response_limit=0),
        }

    def _get_experiment_run(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentRunInput)
        experiment = self._labs.repository.get_experiment(payload.experiment_id)
        run = next((item for item in experiment.run_results if item.get("run_index") == payload.run_index), None)
        if run is None:
            raise CircuitError("EXPERIMENT_RUN_NOT_FOUND", f"Run {payload.run_index} was not found in experiment {payload.experiment_id}.")
        return {"experiment_id": experiment.id, "circuit_revision": experiment.circuit_revision, "variables": experiment.variables, "run": run}

    def _get_experiment_analysis(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        return self._experiment_analysis(self._labs.repository.get_experiment(payload.experiment_id))

    def _get_report(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        experiment = self._labs.repository.get_experiment(payload.experiment_id)
        return {"report": self._report_payload(experiment)}

    def _export_report(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        experiment = self._labs.repository.get_experiment(payload.experiment_id)
        report = self._report_payload(experiment)
        return {"filename": f"{self._export_name(experiment)}-report.json", "mime_type": "application/json", "content": json.dumps(report, indent=2, default=self._json_default)}

    def _export_run_data(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        experiment = self._labs.repository.get_experiment(payload.experiment_id)
        self._assert_reportable(experiment)
        buffer = io.StringIO()
        variables = experiment.variables
        metric_keys = sorted({str(key) for run in experiment.run_results if isinstance(run.get("measurements"), dict) for key, value in run["measurements"].items() if isinstance(value, (int, float)) and not isinstance(value, bool)})
        writer = csv.writer(buffer)
        writer.writerow(["run", *[f"{variable.get('component_id')}.{variable.get('parameter')}" for variable in variables], *metric_keys, "result", "simulation_status", "started_at", "completed_at", "run_by", "notes", "error"])
        for run in experiment.run_results:
            parameters = run.get("parameters") if isinstance(run.get("parameters"), dict) else {}
            measurements = run.get("measurements") if isinstance(run.get("measurements"), dict) else {}
            writer.writerow([run.get("run_index"), *[parameters.get(f"{variable.get('component_id')}.{variable.get('parameter')}", "") for variable in variables], *[measurements.get(key, "") for key in metric_keys], self._requirement_outcome(run), run.get("status", ""), run.get("started_at", ""), run.get("completed_at", ""), run.get("run_by", ""), run.get("notes", ""), run.get("error", "")])
        return {"filename": f"{self._export_name(experiment)}-run-data.csv", "mime_type": "text/csv", "content": buffer.getvalue()}

    def _duplicate_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        return self._experiment_summary(self._labs.experiments.duplicate_definition(payload.experiment_id))

    def _delete_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, ExperimentIdInput)
        self._labs.experiments.delete_definition(payload.experiment_id)
        return {"experiment_id": payload.experiment_id, "deleted": True}

    def _restore_experiment(self, args: BaseModel) -> object:
        payload = self._expect(args, RestoreInput)
        circuit = self._labs.experiments.restore(payload.experiment_id, payload.expected_revision)
        return {"experiment_id": payload.experiment_id, "new_revision": circuit.revision, "circuit": circuit}

    def _restore_experiment_run(self, args: BaseModel) -> object:
        payload = self._expect(args, RestoreRunInput)
        circuit = self._labs.experiments.restore_run(payload.experiment_id, payload.run_index, payload.expected_revision)
        return {"experiment_id": payload.experiment_id, "run_index": payload.run_index, "new_revision": circuit.revision, "circuit": circuit}

    @staticmethod
    def _experiment_summary(experiment: Experiment) -> dict[str, object]:
        readiness_errors = WebMCPToolRegistry._plan_errors(experiment)
        return {
            "id": experiment.id,
            "sequence": experiment.sequence,
            "name": experiment.name or experiment.hypothesis,
            "description": experiment.description,
            "experiment_type": experiment.experiment_type,
            "collection_name": experiment.collection_name,
            "run_by": experiment.run_by,
            "circuit_revision": experiment.circuit_revision,
            "execution_status": experiment.execution_status,
            "created_at": experiment.created_at,
            "started_at": experiment.started_at,
            "completed_at": experiment.completed_at,
            "planned_runs": len(experiment.generated_runs),
            "recorded_runs": len(experiment.run_results),
            "immutable": bool(experiment.run_results),
            "ready": experiment.execution_status == "ready" and not readiness_errors,
            "readiness_errors": readiness_errors,
        }

    def _experiment_definition(self, experiment: Experiment) -> dict[str, object]:
        return {
            **self._experiment_summary(experiment),
            "variables": experiment.variables,
            "measurement_definitions": experiment.measurement_definitions,
            "requirement_definitions": experiment.requirement_definitions,
            "generated_run_count": len(experiment.generated_runs),
            "enabled_run_count": sum(bool(run.get("enabled", True)) for run in experiment.generated_runs),
            "notes": experiment.notes,
            "legacy_simulation_ids": experiment.simulation_ids,
        }

    @staticmethod
    def _plan_errors(experiment: Experiment) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        variables = experiment.variables
        if len(variables) > 2:
            errors.append({"code": "TOO_MANY_VARIABLES", "message": "Human experiment plans support at most two swept parameters."})
        for variable in variables:
            sweep = variable.get("sweep")
            if sweep not in {"linear", "logarithmic", "explicit"}:
                errors.append({"code": "INVALID_SWEEP", "message": f"{variable.get('label', 'Variable')} has an unsupported sweep type."})
                continue
            if sweep == "explicit":
                values = variable.get("values")
                if not isinstance(values, list) or not values or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
                    errors.append({"code": "INVALID_SWEEP", "message": f"{variable.get('label', 'Variable')} needs one or more finite explicit values."})
                continue
            start, stop, points = variable.get("start"), variable.get("stop"), variable.get("points")
            if not isinstance(start, (int, float)) or not isinstance(stop, (int, float)) or isinstance(start, bool) or isinstance(stop, bool) or not isinstance(points, int) or points < 2 or start >= stop:
                errors.append({"code": "INVALID_SWEEP", "message": f"{variable.get('label', 'Variable')} needs increasing numeric start/stop values and at least two points."})
            elif sweep == "logarithmic" and start <= 0:
                errors.append({"code": "INVALID_SWEEP", "message": f"{variable.get('label', 'Variable')} needs a positive logarithmic start value."})
        if len(experiment.generated_runs) > 5_000:
            errors.append({"code": "RUN_LIMIT_EXCEEDED", "message": "Human experiment plans support at most 5,000 generated runs."})
        if not experiment.variables:
            errors.append({"code": "MISSING_VARIABLES", "message": "Select at least one swept parameter."})
        if not experiment.measurement_definitions:
            experiment_type = experiment.experiment_type.strip().lower()
            verification = any(token in experiment_type for token in ("verify", "validation", "robust", "tolerance", "qualification", "acceptance"))
            errors.append({
                "code": "VERIFICATION_MEASUREMENTS_REQUIRED" if verification else "MISSING_MEASUREMENTS",
                "message": "Verification experiments require at least one measurement before they can run." if verification else "Select at least one measurement.",
            })
        if not any(run.get("enabled", True) for run in experiment.generated_runs):
            errors.append({"code": "MISSING_ENABLED_RUNS", "message": "Enable at least one generated run."})
        return errors

    def _experiment_plan(self, experiment: Experiment, offset: int, sample_limit: int) -> dict[str, object]:
        generated_runs = experiment.generated_runs
        return {
            "experiment_id": experiment.id,
            "circuit_revision": experiment.circuit_revision,
            "execution_status": experiment.execution_status,
            "immutable": bool(experiment.run_results),
            "variables": experiment.variables,
            "measurements": experiment.measurement_definitions,
            "requirements": experiment.requirement_definitions,
            "total_generated_runs": len(generated_runs),
            "enabled_run_count": sum(bool(run.get("enabled", True)) for run in generated_runs),
            "offset": offset,
            "representative_runs": generated_runs[offset : offset + sample_limit],
            "ready": experiment.execution_status == "ready" and not self._plan_errors(experiment),
            "validation_errors": self._plan_errors(experiment),
        }

    @staticmethod
    def _requirement_outcome(run: dict[str, object]) -> str:
        if run.get("error") or str(run.get("status", "")).upper() in {"ERROR", "FAILED", "FAILURE"}:
            return "ERROR"
        requirements = run.get("requirement_results")
        if not isinstance(requirements, list) or not requirements:
            return "INCOMPLETE/UNCLASSIFIED"
        statuses = [item.get("status") for item in requirements if isinstance(item, dict)]
        if "FAIL" in statuses:
            return "FAIL"
        return "PASS" if statuses and all(status == "PASS" for status in statuses) else "INCOMPLETE/UNCLASSIFIED"

    def _execution_summary(self, experiment: Experiment, *, execution_state: str | None = None) -> dict[str, object]:
        results = experiment.run_results
        status_counts: dict[str, int] = {}
        classification_counts: dict[str, int] = {"PASS": 0, "FAIL": 0, "ERROR": 0, "INCOMPLETE/UNCLASSIFIED": 0}
        errors: list[dict[str, object]] = []
        for run in results:
            status = str(run.get("status", "UNKNOWN"))
            status_counts[status] = status_counts.get(status, 0) + 1
            classification = self._requirement_outcome(run)
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            if run.get("error"):
                errors.append({"run_index": run.get("run_index"), "error": run["error"]})
        return {
            "experiment_id": experiment.id,
            "execution_status": execution_state or experiment.execution_status,
            "total_runs": len(experiment.generated_runs),
            "completed_runs": status_counts.get("COMPLETED", 0),
            "recorded_runs": len(results),
            "remaining_runs": max(0, len(experiment.generated_runs) - len(results)),
            "status_counts": status_counts,
            "classification_counts": classification_counts,
            "simulation_errors": errors[:20],
            "started_at": experiment.started_at,
            "completed_at": experiment.completed_at,
        }

    def _experiment_analysis(self, experiment: Experiment, *, response_limit: int = 200) -> dict[str, object]:
        results = experiment.run_results
        completed = [run for run in results if run.get("status") == "COMPLETED"]
        measurement_values: dict[str, list[float]] = {}
        for run in completed:
            measurements = run.get("measurements")
            if isinstance(measurements, dict):
                for key, value in measurements.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        measurement_values.setdefault(str(key), []).append(float(value))
        measurement_ranges = {key: {"minimum": min(values), "maximum": max(values), "count": len(values)} for key, values in measurement_values.items() if values}
        tested_ranges: list[dict[str, object]] = []
        for variable in experiment.variables:
            component_id, parameter = variable.get("component_id"), variable.get("parameter")
            key = f"{component_id}.{parameter}"
            values = [run.get("parameters", {}).get(key) for run in completed if isinstance(run.get("parameters"), dict)]
            numeric = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
            if numeric:
                tested_ranges.append({"component_id": component_id, "parameter": parameter, "unit": variable.get("unit", ""), "minimum": min(numeric), "maximum": max(numeric), "count": len(numeric)})
        required_run_indices = {
            run.get("index") for run in experiment.generated_runs if run.get("enabled", True)
        }
        required_results = [
            run for run in results if not required_run_indices or run.get("run_index") in required_run_indices
        ]
        classifications = {"PASS": [], "FAIL": [], "ERROR": [], "INCOMPLETE/UNCLASSIFIED": []}
        for run in required_results:
            classifications[self._requirement_outcome(run)].append(run.get("run_index"))
        recorded_required_indices = {run.get("run_index") for run in required_results}
        missing_required_runs = len(required_run_indices.difference(recorded_required_indices))
        # Summarize worst-case requirement margins directly from persisted run
        # measurements (never from notes or generated prose).
        worst_case: list[dict[str, object]] = []
        for requirement in experiment.requirement_definitions:
            measurement_id = str(requirement.get("measurement_id") or requirement.get("metric") or "")
            observations = [(r.get("run_index"), r.get("measurements", {}).get(measurement_id)) for r in completed if isinstance(r.get("measurements"), dict)]
            numeric = [(run_id, float(value)) for run_id, value in observations if isinstance(value, (int, float)) and not isinstance(value, bool)]
            target = requirement.get("target")
            if not numeric or not isinstance(target, (int, float)):
                continue
            operator = str(requirement.get("operator", ""))
            margins = [value - float(target) for _, value in numeric] if operator in {"gte", ">=", "gt", ">"} else [float(target) - value for _, value in numeric] if operator in {"lte", "<=", "lt", "<"} else [-abs(value - float(target)) for _, value in numeric]
            worst_index = margins.index(min(margins))
            worst_case.append({"measurement_id": measurement_id, "operator": operator, "target": target, "worst_margin": margins[worst_index], "worst_value": numeric[worst_index][1], "run_id": numeric[worst_index][0]})
        response_data: list[dict[str, object]] = []
        if len(experiment.variables) == 1 and response_limit:
            variable = experiment.variables[0]
            key = f"{variable.get('component_id')}.{variable.get('parameter')}"
            for metric in measurement_values:
                points = [{"run_index": run.get("run_index"), "parameter": run.get("parameters", {}).get(key), "value": run.get("measurements", {}).get(metric)} for run in completed if isinstance(run.get("parameters"), dict) and isinstance(run.get("measurements"), dict) and isinstance(run["measurements"].get(metric), (int, float))]
                response_data.append({"metric": metric, "variable": {"component_id": variable.get("component_id"), "parameter": variable.get("parameter"), "unit": variable.get("unit", "")}, "points": sorted(points, key=lambda point: float(point["parameter"]))[:response_limit]})
        available = ["overview", "requirement_analysis"]
        if tested_ranges:
            available.append("operating_region")
        if response_data:
            available.append("response")
        enabled_runs = sum(bool(run.get("enabled", True)) for run in experiment.generated_runs)
        completed_enabled_runs = sum(run.get("status") == "COMPLETED" for run in results)
        if classifications["ERROR"]:
            design_search_status = "error"
        elif missing_required_runs or classifications["INCOMPLETE/UNCLASSIFIED"]:
            design_search_status = "incomplete"
        elif classifications["FAIL"]:
            design_search_status = "requirements_not_met"
        elif enabled_runs > 0 and len(classifications["PASS"]) == enabled_runs:
            design_search_status = "requirements_met"
        else:
            design_search_status = "incomplete"
        return {
            "experiment_id": experiment.id,
            "execution": self._execution_summary(experiment),
            "available_analysis": available,
            "tested_ranges": tested_ranges,
            "measurement_ranges": measurement_ranges,
            "requirement_analysis": {"has_requirements": bool(experiment.requirement_definitions), "pass_run_indices": classifications["PASS"][:200], "fail_run_indices": classifications["FAIL"][:200], "error_run_indices": classifications["ERROR"][:200], "incomplete_run_indices": classifications["INCOMPLETE/UNCLASSIFIED"][:200]},
            "worst_case_requirements": worst_case,
            "design_search_status": design_search_status,
            "planned_matrix_complete": enabled_runs > 0 and completed_enabled_runs == enabled_runs,
            "claim_guidance": "A design may be described as infeasible only after every required planned run and design revision has been evaluated; otherwise report not found yet.",
            "response_data": response_data,
        }

    def _report_payload(self, experiment: Experiment) -> dict[str, object]:
        self._assert_reportable(experiment)
        return {
            "experiment_id": experiment.id,
            "experiment_name": experiment.name or experiment.hypothesis,
            "objective": experiment.description or experiment.hypothesis,
            "experiment_type": experiment.experiment_type,
            "circuit_revision": experiment.circuit_revision,
            "collection_name": experiment.collection_name,
            "run_by": experiment.run_by,
            "notes": experiment.notes,
            "created_at": experiment.created_at,
            "started_at": experiment.started_at,
            "completed_at": experiment.completed_at,
            "circuit_under_test": experiment.circuit_snapshot,
            "setup": {"variables": experiment.variables, "measurements": experiment.measurement_definitions, "requirements": experiment.requirement_definitions},
            "execution": self._execution_summary(experiment),
            "analysis": self._experiment_analysis(experiment),
        }

    @staticmethod
    def _assert_reportable(experiment: Experiment) -> None:
        if not experiment.run_results:
            raise CircuitError("EXPERIMENT_NOT_EXECUTED", f"Experiment {experiment.id} has no recorded runs and cannot produce a report.")

    @staticmethod
    def _export_name(experiment: Experiment) -> str:
        name = "".join(character.lower() if character.isalnum() else "-" for character in (experiment.name or experiment.hypothesis)).strip("-")
        return name or "experiment"

    @staticmethod
    def _json_default(value: object) -> object:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            return isoformat()
        raise TypeError(f"Cannot serialize {type(value).__name__} to report JSON.")

    def _simulation_summary(self, result: SimulationResult) -> dict[str, object]:
        return {
            "simulation_id": result.simulation_id,
            "analysis": result.analysis,
            "success": result.success,
            "circuit_revision": result.circuit_revision,
            "measurements": result.measurements,
            "errors": result.errors,
        }

    @staticmethod
    def _expect(value: BaseModel, expected_type: type[ModelType]) -> ModelType:
        if not isinstance(value, expected_type):
            raise TypeError(f"Expected {expected_type.__name__}.")
        return value


class SetParameterRequestWithId(SetParameterRequest):
    model_config = ConfigDict(extra="forbid")
    component_id: str


class RemoveComponentInput(RevisionRequest):
    model_config = ConfigDict(extra="forbid")
    component_id: str
