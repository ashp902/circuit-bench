from __future__ import annotations

import re
from datetime import datetime, timezone

from app.db.repository import LabRepository
from app.models.circuit import (
    Challenge,
    Circuit,
    ConstraintEvaluation,
    Experiment,
    ParameterValue,
    SavedCircuit,
    SimulationResult,
)
from app.services.circuit_service import CircuitService
from app.services.challenge_catalog import blank_circuit, sensor_interface
from app.services.constraint_service import ConstraintService
from app.services.errors import CircuitError
from app.services.experiment_service import ExperimentService
from app.services.measurement_service import MeasurementService
from app.services.netlist_service import AcAnalysis, TransientAnalysis
from app.services.simulation_service import NgspiceSimulator


GAIN_METRIC = re.compile(r"^gain_db_at_([0-9]+(?:\.[0-9]+)?)hz$")


def default_lab() -> tuple[Challenge, Circuit]:
    return sensor_interface()


class LabService:
    """Canonical application boundary shared by REST now and WebMCP next."""

    def __init__(self, repository: LabRepository, simulator: NgspiceSimulator | None = None) -> None:
        self.repository = repository
        self.simulator = simulator or NgspiceSimulator()
        self.measurements = MeasurementService()
        self.constraints = ConstraintService()
        self.experiments = ExperimentService(repository)

    def get_state(self) -> dict[str, object]:
        challenge = self.repository.get_challenge()
        return {
            "challenge": challenge,
            "circuit": self.repository.get_circuit(),
            "latest_experiment": next(iter(self.experiments.list(active_only=True)), None),
            "active_saved_circuit_id": self.repository.get_active_saved_circuit_id(),
        }

    def reset(self, challenge: Challenge, circuit: Circuit) -> dict[str, object]:
        if len(circuit.components) > challenge.component_limit:
            raise CircuitError("COMPONENT_LIMIT_EXCEEDED", "Starting circuit exceeds the challenge component limit.")
        self.repository.reset(challenge, circuit)
        return self.get_state()

    def create_blank_circuit(self, name: str | None = None) -> dict[str, object]:
        circuit_name = name.strip() if name and name.strip() else self._next_new_circuit_name()
        challenge, circuit = blank_circuit(circuit_name)
        saved = self._new_saved_circuit(circuit_name, challenge, circuit)
        self.repository.save_saved_circuit(saved)
        self.repository.activate_saved_circuit(saved)
        state = self.get_state()
        state["latest_experiment"] = None
        return state

    def save_current_circuit(self, name: str, circuit_id: str | None = None) -> SavedCircuit:
        circuit = self.repository.get_circuit()
        challenge = self.repository.get_challenge()
        if circuit_id is not None:
            existing = self.repository.get_saved_circuit(circuit_id)
            snapshot = circuit.model_copy(deep=True)
            snapshot.name = name.strip()
            saved = SavedCircuit(id=existing.id, name=name.strip(), created_at=existing.created_at, challenge_snapshot=challenge, circuit_snapshot=snapshot)
        else:
            saved = self._new_saved_circuit(name, challenge, circuit)
        self.repository.save_saved_circuit(saved)
        self.repository.activate_saved_circuit(saved)
        return saved

    def delete_saved_circuit(self, circuit_id: str) -> dict[str, object]:
        """Delete a saved circuit, returning to the default lab if it was open."""
        was_active = self.repository.get_active_saved_circuit_id() == circuit_id
        self.repository.delete_saved_circuit(circuit_id)
        if was_active:
            challenge, circuit = blank_circuit()
            self.repository.activate_lab(challenge, circuit)
        return self.get_state()

    def list_saved_circuits(self) -> list[SavedCircuit]:
        return self.repository.list_saved_circuits()

    def open_saved_circuit(self, circuit_id: str) -> dict[str, object]:
        self.repository.activate_saved_circuit(self.repository.get_saved_circuit(circuit_id))
        return self.get_state()

    def _new_saved_circuit(self, name: str, challenge: Challenge, circuit: Circuit) -> SavedCircuit:
        sequence = self.repository.next_saved_circuit_sequence()
        clean_name = name.strip() or "Untitled Circuit"
        snapshot = circuit.model_copy(deep=True)
        snapshot.name = clean_name
        return SavedCircuit(id=f"circuit_{sequence:03d}", name=clean_name, challenge_snapshot=challenge.model_copy(deep=True), circuit_snapshot=snapshot)

    def _next_new_circuit_name(self) -> str:
        existing_names = {circuit.name.casefold() for circuit in self.repository.list_saved_circuits()}
        candidate = "New Circuit"
        suffix = 0
        while candidate.casefold() in existing_names:
            suffix += 1
            candidate = f"New Circuit {suffix}"
        return candidate

    def restore_circuit(self, snapshot: Circuit, expected_revision: int) -> Circuit:
        """Restore a local undo snapshot without rewinding canonical revision history."""
        current = self.repository.get_circuit()
        if current.revision != expected_revision:
            raise CircuitError("STALE_REVISION", f"Circuit changed since revision {expected_revision}.", "Reload the circuit and retry the undo.")
        challenge = self.repository.get_challenge()
        if snapshot.id != current.id:
            raise CircuitError("INVALID_PARAMETER", "Undo snapshot belongs to a different circuit.")
        if len(snapshot.components) > challenge.component_limit:
            raise CircuitError("COMPONENT_LIMIT_EXCEEDED", "The restored circuit exceeds this challenge's component limit.")
        unsupported = {component.type for component in snapshot.components} - challenge.allowed_components
        if unsupported:
            raise CircuitError("UNSUPPORTED_COMPONENT", "The restored circuit uses components unavailable in this challenge.")
        restored = snapshot.model_copy(deep=True)
        restored.revision = current.revision + 1
        self.repository.save_circuit(restored, expected_revision)
        self._sync_active_saved_circuit(restored)
        return restored

    def add_component(self, component_type: ComponentType, params: dict[str, ParameterValue], expected_revision: int, position: object | None = None) -> Circuit:
        from app.models.circuit import Position

        service = self._circuit_service()
        service.add_component(component_type, params, expected_revision, Position.model_validate(position) if position is not None else None)
        return self._save_mutation(service, expected_revision)

    def set_parameter(self, component_id: str, parameter: str, value: ParameterValue, expected_revision: int) -> Circuit:
        service = self._circuit_service()
        service.set_parameter(component_id, parameter, value, expected_revision)
        return self._save_mutation(service, expected_revision)

    def remove_component(self, component_id: str, expected_revision: int) -> Circuit:
        service = self._circuit_service()
        service.remove_component(component_id, expected_revision)
        return self._save_mutation(service, expected_revision)

    def create_node(self, label: str, expected_revision: int) -> Circuit:
        service = self._circuit_service()
        service.create_node(label, expected_revision)
        return self._save_mutation(service, expected_revision)

    def rename_node(self, node_id: str, label: str, expected_revision: int) -> Circuit:
        service = self._circuit_service()
        service.rename_node(node_id, label, expected_revision)
        return self._save_mutation(service, expected_revision)

    def set_component_layout(self, component_id: str, position: object, rotation: int, expected_revision: int) -> Circuit:
        from app.models.circuit import Position

        service = self._circuit_service()
        service.set_layout(component_id, Position.model_validate(position), rotation, expected_revision)
        return self._save_mutation(service, expected_revision)

    def auto_layout(self, expected_revision: int, *, preserve_manual: bool = True) -> Circuit:
        service = self._circuit_service()
        service.auto_layout(expected_revision, preserve_manual=preserve_manual)
        return self._save_mutation(service, expected_revision)

    def connect(self, component_id: str, pin: str, node_id: str, expected_revision: int, *, auto_layout: bool = False) -> Circuit:
        service = self._circuit_service()
        service.connect(component_id, pin, node_id, expected_revision)
        if auto_layout:
            service.apply_auto_layout(preserve_manual=True)
        return self._save_mutation(service, expected_revision)

    def connect_pins(
        self,
        source_component_id: str,
        source_pin: str,
        target_component_id: str,
        target_pin: str,
        expected_revision: int,
        *,
        auto_layout: bool = False,
    ) -> Circuit:
        service = self._circuit_service()
        service.connect_pins(source_component_id, source_pin, target_component_id, target_pin, expected_revision)
        if auto_layout:
            service.apply_auto_layout(preserve_manual=True)
        return self._save_mutation(service, expected_revision)

    def disconnect(self, component_id: str, pin: str, expected_revision: int) -> Circuit:
        service = self._circuit_service()
        service.disconnect(component_id, pin, expected_revision)
        return self._save_mutation(service, expected_revision)

    def validate(self) -> dict[str, object]:
        issues = self._circuit_service().validate()
        return {
            "valid": not issues,
            "issues": [
                {"code": issue.code, "message": issue.message, "recovery_hint": issue.recovery_hint}
                for issue in issues
            ],
        }

    def run_operating_point(self, output_nodes: list[str], current_components: list[str] | None = None) -> SimulationResult:
        circuit = self._validated_circuit()
        return self._save_simulation(self.simulator.run_operating_point(circuit, output_nodes, current_components) if current_components else self.simulator.run_operating_point(circuit, output_nodes))

    def run_ac(self, analysis: AcAnalysis, current_components: list[str] | None = None) -> SimulationResult:
        circuit = self._validated_circuit()
        return self._save_simulation(self.simulator.run_ac(circuit, analysis, current_components) if current_components else self.simulator.run_ac(circuit, analysis))

    def run_transient(self, analysis: TransientAnalysis, current_components: list[str] | None = None) -> SimulationResult:
        circuit = self._validated_circuit()
        return self._save_simulation(self.simulator.run_transient(circuit, analysis, current_components) if current_components else self.simulator.run_transient(circuit, analysis))

    def evaluate(self, simulation_ids: list[str]) -> tuple[dict[str, float], ConstraintEvaluation]:
        metrics = self._collect_metrics(simulation_ids)
        return metrics, self.constraints.evaluate(self.repository.get_challenge().constraints, metrics)

    def save_experiment(self, hypothesis: str, conclusion: str, simulation_ids: list[str]) -> Experiment:
        metrics, evaluation = self.evaluate(simulation_ids)
        return self.experiments.save(
            self.repository.get_circuit(),
            hypothesis,
            conclusion,
            simulation_ids,
            metrics,
            evaluation,
        )

    def _collect_metrics(self, simulation_ids: list[str]) -> dict[str, float]:
        metrics: dict[str, float] = {"component_count": float(len(self.repository.get_circuit().components))}
        output_node = self.repository.get_circuit().metadata.get("output_node", "out")
        requested_metrics = {constraint.metric for constraint in self.repository.get_challenge().constraints}
        for simulation_id in simulation_ids:
            simulation = self.repository.get_simulation(simulation_id)
            metrics.update(simulation.measurements)
            if simulation.analysis == "ac":
                if "cutoff_frequency_hz" in requested_metrics:
                    cutoff = self.measurements.measure_cutoff_frequency(simulation)
                    if cutoff is not None:
                        metrics["cutoff_frequency_hz"] = cutoff
                for metric in requested_metrics:
                    match = GAIN_METRIC.match(metric)
                    if match:
                        metrics[metric] = self.measurements.measure_gain(simulation, float(match.group(1)))
            elif simulation.analysis == "transient":
                if "max_output_voltage_v" in requested_metrics:
                    metrics["max_output_voltage_v"] = self.measurements.measure_voltage(simulation, output_node, "max")
                if "min_output_voltage_v" in requested_metrics:
                    metrics["min_output_voltage_v"] = self.measurements.measure_voltage(simulation, output_node, "min")
                if "rise_time_s" in requested_metrics:
                    metrics["rise_time_s"] = self.measurements.measure_rise_time(simulation, output_node)
        return metrics

    def _circuit_service(self) -> CircuitService:
        return CircuitService(self.repository.get_circuit(), self.repository.get_challenge())

    def _save_mutation(self, service: CircuitService, previous_revision: int) -> Circuit:
        circuit = service.get_circuit()
        self.repository.save_circuit(circuit, previous_revision)
        self._sync_active_saved_circuit(circuit)
        return circuit

    def _sync_active_saved_circuit(self, circuit: Circuit) -> None:
        """Persist every accepted edit, promoting an edited template to a saved circuit."""
        active_id = self.repository.get_active_saved_circuit_id()
        if active_id is None:
            saved = self._new_saved_circuit(circuit.name, self.repository.get_challenge(), circuit)
            self.repository.save_saved_circuit(saved)
            self.repository.activate_saved_circuit(saved)
            return
        existing = self.repository.get_saved_circuit(active_id)
        self.repository.save_saved_circuit(
            SavedCircuit(
                id=existing.id,
                name=circuit.name,
                created_at=existing.created_at,
                updated_at=datetime.now(timezone.utc),
                challenge_snapshot=self.repository.get_challenge().model_copy(deep=True),
                circuit_snapshot=circuit.model_copy(deep=True),
            )
        )

    def _validated_circuit(self) -> Circuit:
        service = self._circuit_service()
        issues = service.validate()
        if issues:
            summary = "; ".join(issue.message for issue in issues[:5])
            raise CircuitError("INVALID_CIRCUIT", summary, "Call validate_circuit and fix each reported issue.")
        return service.get_circuit()

    def _save_simulation(self, simulation: SimulationResult) -> SimulationResult:
        self.repository.save_simulation(simulation)
        return simulation
