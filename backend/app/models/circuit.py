from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ComponentType(str, Enum):
    GROUND = "ground"
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    VOLTAGE_SOURCE = "voltage_source"
    DIODE = "diode"
    IDEAL_OPAMP = "ideal_opamp"


ParameterValue = float | int | str | bool
PIN_NAMES: dict[ComponentType, tuple[str, ...]] = {
    ComponentType.GROUND: (),
    ComponentType.RESISTOR: ("a", "b"),
    ComponentType.CAPACITOR: ("a", "b"),
    ComponentType.INDUCTOR: ("a", "b"),
    ComponentType.VOLTAGE_SOURCE: ("positive", "negative"),
    ComponentType.DIODE: ("anode", "cathode"),
    ComponentType.IDEAL_OPAMP: ("plus", "minus", "out"),
}
POSITIVE_LIMITS: dict[ComponentType, tuple[str, float, float]] = {
    ComponentType.RESISTOR: ("resistance_ohm", 1e-3, 1e12),
    ComponentType.CAPACITOR: ("capacitance_f", 1e-15, 10),
    ComponentType.INDUCTOR: ("inductance_h", 1e-12, 1e3),
}
ALLOWED_PARAMETERS: dict[ComponentType, set[str]] = {
    ComponentType.GROUND: set(),
    ComponentType.RESISTOR: {"resistance_ohm"},
    ComponentType.CAPACITOR: {"capacitance_f"},
    ComponentType.INDUCTOR: {"inductance_h"},
    ComponentType.VOLTAGE_SOURCE: {
        "mode",
        "voltage_v",
        "offset_v",
        "amplitude_v",
        "frequency_hz",
        "initial_v",
        "pulsed_v",
        "delay_s",
        "rise_time_s",
        "fall_time_s",
        "pulse_width_s",
        "period_s",
    },
    ComponentType.DIODE: {"model"},
    ComponentType.IDEAL_OPAMP: {"gain", "positive_rail_v", "negative_rail_v"},
}


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label: str = Field(min_length=1, max_length=64)


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    type: ComponentType
    params: dict[str, ParameterValue] = Field(default_factory=dict)
    pins: dict[str, str | None] = Field(default_factory=dict)
    position: Position | None = None
    rotation: Literal[0, 90, 180, 270] = 0
    layout_locked: bool = False

    @model_validator(mode="after")
    def validate_component_shape(self) -> Component:
        expected_pins = set(PIN_NAMES[self.type])
        unknown_pins = set(self.pins).difference(expected_pins)
        if unknown_pins:
            raise ValueError(f"Unsupported pins for {self.type}: {sorted(unknown_pins)}")
        unknown_parameters = set(self.params).difference(ALLOWED_PARAMETERS[self.type])
        if unknown_parameters:
            raise ValueError(f"Unsupported parameters for {self.type}: {sorted(unknown_parameters)}")

        if self.type in POSITIVE_LIMITS:
            name, lower, upper = POSITIVE_LIMITS[self.type]
            self._validate_number(name, lower, upper)
        elif self.type is ComponentType.VOLTAGE_SOURCE:
            mode = self.params.get("mode", "dc")
            if mode not in {"dc", "sine", "pulse"}:
                raise ValueError("Voltage source mode must be dc, sine, or pulse.")
            for key, value in self.params.items():
                if key != "mode" and isinstance(value, (int, float)) and not math.isfinite(float(value)):
                    raise ValueError(f"{key} must be finite.")
            frequency = self.params.get("frequency_hz", 0)
            if isinstance(frequency, (int, float)) and not 0 <= float(frequency) <= 1e10:
                raise ValueError("frequency_hz must be between 0 and 1e10.")
        elif self.type is ComponentType.IDEAL_OPAMP:
            self._validate_number("gain", 1, 1e9, required=False)
        return self

    def _validate_number(self, name: str, lower: float, upper: float, *, required: bool = True) -> None:
        value = self.params.get(name)
        if value is None and not required:
            return
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError(f"{name} must be a finite number.")
        if not lower <= float(value) <= upper:
            raise ValueError(f"{name} must be between {lower} and {upper}.")


class Constraint(BaseModel):
    id: str
    metric: str
    operator: Literal["<", "<=", ">", ">=", "between", "approximately"]
    target: float | tuple[float, float]
    tolerance: float | None = None

    @model_validator(mode="after")
    def validate_target_shape(self) -> Constraint:
        if self.operator == "between":
            if not isinstance(self.target, tuple):
                raise ValueError("between constraints require a two-value target.")
            if self.target[0] > self.target[1]:
                raise ValueError("between constraint bounds must be increasing.")
        elif isinstance(self.target, tuple):
            raise ValueError(f"{self.operator} constraints require a numeric target.")
        if self.tolerance is not None and self.tolerance < 0:
            raise ValueError("Constraint tolerance cannot be negative.")
        return self


class ConstraintResult(BaseModel):
    constraint_id: str
    status: Literal["PASS", "FAIL", "NOT_EVALUATED"]
    actual: float | None = None
    target: float | tuple[float, float]
    message: str


class ConstraintEvaluation(BaseModel):
    all_pass: bool
    passed: int
    failed: int
    not_evaluated: int
    results: list[ConstraintResult]


class Challenge(BaseModel):
    id: str
    title: str
    description: str
    component_limit: int = Field(ge=1)
    allowed_components: set[ComponentType] = Field(default_factory=lambda: set(ComponentType))
    constraints: list[Constraint] = Field(default_factory=list)


class Circuit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    revision: int = Field(default=0, ge=0)
    name: str
    components: list[Component] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("components")
    @classmethod
    def component_ids_are_unique(cls, components: list[Component]) -> list[Component]:
        ids = [component.id for component in components]
        if len(ids) != len(set(ids)):
            raise ValueError("Component IDs must be unique.")
        return components

    @field_validator("nodes")
    @classmethod
    def node_ids_are_unique(cls, nodes: list[Node]) -> list[Node]:
        ids = [node.id for node in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Node IDs must be unique.")
        return nodes


class SavedCircuit(BaseModel):
    id: str = Field(pattern=r"^circuit_[0-9]{3,}$")
    name: str = Field(min_length=1, max_length=160)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    challenge_snapshot: Challenge
    circuit_snapshot: Circuit


class SimulationError(BaseModel):
    code: Literal["SIMULATION_FAILED", "SIMULATION_TIMEOUT"]
    message: str
    details: str | None = None


class SimulationResult(BaseModel):
    success: bool
    analysis: Literal["operating_point", "ac", "transient"]
    circuit_revision: int
    simulation_id: str
    measurements: dict[str, float] = Field(default_factory=dict)
    series: dict[str, list[float]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[SimulationError] = Field(default_factory=list)


class Experiment(BaseModel):
    id: str
    sequence: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hypothesis: str
    conclusion: str = ""
    circuit_revision: int
    circuit_snapshot: Circuit
    simulation_ids: list[str] = Field(default_factory=list)
    measurements: dict[str, float] = Field(default_factory=dict)
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    name: str | None = None
    description: str = ""
    # Experiment types are user-defined taxonomy values.  Keep this open-ended so
    # persisted experiments created by WebMCP clients (for example
    # ``ac_tolerance``) remain loadable across application upgrades.
    experiment_type: str = Field(default="manual", min_length=1, max_length=80)
    status: Literal["draft", "ready", "completed", "failed", "interrupted"] = "draft"
    variables: list[dict[str, object]] = Field(default_factory=list)
    # Structured measurement descriptors: {id, kind, node/component, label, unit}.
    # Legacy strings remain accepted for backwards-compatible stored experiments.
    measurement_definitions: list[dict[str, object] | str] = Field(default_factory=list)
    requirement_definitions: list[dict[str, object]] = Field(default_factory=list)
    generated_runs: list[dict[str, object]] = Field(default_factory=list)
    execution_status: Literal["draft", "ready", "running", "paused", "completed", "failed", "interrupted"] = "draft"
    run_results: list[dict[str, object]] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    collection_name: str = ""
    run_by: str = ""
    notes: str = ""
    circuit_id: str | None = None

    @model_validator(mode="after")
    def completed_runs_require_configured_measurements(self) -> "Experiment":
        """Correct legacy run labels without fabricating missing evidence."""
        required_ids = {
            str(definition.get("id"))
            for definition in self.measurement_definitions
            if isinstance(definition, dict) and definition.get("id")
        }
        corrected = False
        for run in self.run_results:
            measurements = run.get("measurements")
            recorded_ids = set(measurements) if isinstance(measurements, dict) else set()
            missing = sorted(required_ids.difference(recorded_ids))
            if str(run.get("status", "")).upper() == "COMPLETED" and missing:
                run["status"] = "INCOMPLETE"
                run.setdefault("incomplete_reason", f"Missing required measurements: {', '.join(missing)}.")
                corrected = True
        if corrected and self.execution_status == "completed":
            self.execution_status = "failed"
        return self
