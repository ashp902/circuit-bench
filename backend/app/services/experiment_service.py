from __future__ import annotations

import itertools
import math
from threading import Event, Lock, Thread

from app.db.repository import LabRepository
from app.models.circuit import Circuit, ConstraintEvaluation, Experiment
from app.services.netlist_service import AcAnalysis


class ExperimentService:
    def __init__(self, repository: LabRepository) -> None:
        self._repository = repository
        self._active: set[str] = set()
        self._controls: dict[str, tuple[Event, Event]] = {}
        self._lock = Lock()

    def save(
        self,
        circuit: Circuit,
        hypothesis: str,
        conclusion: str,
        simulation_ids: list[str],
        measurements: dict[str, float],
        evaluation: ConstraintEvaluation,
    ) -> Experiment:
        sequence = self._repository.next_experiment_sequence()
        experiment = Experiment(
            id=f"exp_{sequence:03d}",
            sequence=sequence,
            hypothesis=hypothesis,
            conclusion=conclusion,
            circuit_revision=circuit.revision,
            circuit_snapshot=circuit.model_copy(deep=True),
            simulation_ids=simulation_ids,
            measurements=measurements,
            constraint_results=evaluation.results,
        )
        self._repository.save_experiment(experiment)
        return experiment

    def restore(self, experiment_id: str, expected_revision: int) -> Circuit:
        current = self._repository.get_circuit()
        if current.revision != expected_revision:
            from app.services.errors import CircuitError

            raise CircuitError(
                "STALE_REVISION",
                f"Circuit changed since revision {expected_revision}.",
                "Call get_circuit and retry using the latest revision.",
            )
        snapshot = self._repository.get_experiment(experiment_id).circuit_snapshot.model_copy(deep=True)
        snapshot.revision = current.revision + 1
        self._repository.save_circuit(snapshot, previous_revision=current.revision)
        return snapshot

    def restore_run(self, experiment_id: str, run_index: int, expected_revision: int) -> Circuit:
        current = self._repository.get_circuit()
        if current.revision != expected_revision:
            from app.services.errors import CircuitError
            raise CircuitError("STALE_REVISION", f"Circuit changed since revision {expected_revision}.", "Refresh the circuit and retry.")
        experiment = self._repository.get_experiment(experiment_id)
        run = next((item for item in experiment.run_results if item.get("run_index") == run_index), None)
        if run is None:
            from app.services.errors import CircuitError
            raise CircuitError("EXPERIMENT_RUN_NOT_FOUND", f"Run {run_index} was not found in experiment {experiment_id}.")
        snapshot = experiment.circuit_snapshot.model_copy(deep=True)
        for key, value in dict(run.get("parameters", {})).items():
            component_id, parameter = str(key).split(".", 1)
            component = next((item for item in snapshot.components if item.id == component_id), None)
            if component is not None:
                component.params[parameter] = value
        snapshot.revision = current.revision + 1
        self._repository.save_circuit(snapshot, previous_revision=current.revision)
        return snapshot

    def list(self, *, active_only: bool = True) -> list[Experiment]:
        return self._repository.list_experiments(active_circuit_id=self._repository.get_circuit().id if active_only else None)

    def save_definition(self, circuit: Circuit, payload: object) -> Experiment:
        data = payload.model_dump()  # type: ignore[union-attr]
        if data["circuit_revision"] != circuit.revision:
            from app.services.errors import CircuitError
            raise CircuitError("STALE_REVISION", "The circuit revision changed before this experiment was saved.")
        data = self._normalize_definition(data, circuit)
        sequence = self._repository.next_experiment_sequence()
        status = "ready" if data["variables"] and data["measurement_definitions"] and any(run.get("enabled", True) for run in data["generated_runs"]) else "draft"
        try:
            experiment = Experiment(id=f"exp_{sequence:03d}", sequence=sequence, hypothesis=data["name"], circuit_id=circuit.id, circuit_revision=circuit.revision, circuit_snapshot=circuit.model_copy(deep=True), name=data["name"], description=data["description"], experiment_type=data["experiment_type"], variables=data["variables"], measurement_definitions=data["measurement_definitions"], requirement_definitions=data["requirement_definitions"], generated_runs=data["generated_runs"], collection_name=data["collection_name"].strip(), run_by=data["run_by"].strip(), notes=data["notes"].strip(), execution_status=status)
        except ValueError as error:
            from app.services.errors import CircuitError
            raise CircuitError("INVALID_EXPERIMENT", "The experiment definition is invalid.", str(error)) from error
        self._repository.save_experiment(experiment)
        return experiment

    def update_definition(self, experiment_id: str, circuit: Circuit, payload: object) -> Experiment:
        experiment = self._repository.get_experiment(experiment_id)
        data = payload.model_dump()  # type: ignore[union-attr]
        if experiment.run_results:
            from app.services.errors import CircuitError
            raise CircuitError("EXPERIMENT_IMMUTABLE", "Executed experiments are immutable to preserve their recorded run history.", "Create a new experiment from this circuit revision to change the test plan.")
        if experiment.circuit_revision != data["circuit_revision"] or circuit.revision != experiment.circuit_revision:
            from app.services.errors import CircuitError
            raise CircuitError("STALE_REVISION", "Experiment definitions remain tied to their original circuit revision.")
        data = self._normalize_definition(data, circuit)
        # WebMCP wraps the same definition payload with an experiment identifier;
        # only fields belonging to the persisted experiment definition are mutable.
        for key, value in data.items():
            if key in Experiment.model_fields:
                setattr(experiment, key, value)
        experiment.execution_status = "ready" if data["variables"] and data["measurement_definitions"] and any(run.get("enabled", True) for run in data["generated_runs"]) else "draft"
        experiment.hypothesis = experiment.name or experiment.hypothesis
        self._repository.update_experiment(experiment)
        return experiment

    def _normalize_definition(self, data: dict[str, object], circuit: Circuit) -> dict[str, object]:
        variables = [self._normalize_variable(item) for item in data.get("variables", []) if isinstance(item, dict)]
        measurements = [self._normalize_measurement(item, circuit, index) for index, item in enumerate(data.get("measurement_definitions", []), start=1)]
        measurement_aliases = {str(item.get("id")): str(item.get("id")) for item in measurements}
        measurement_aliases.update({str(item.get("label")): str(item.get("id")) for item in measurements})
        requirements = [self._normalize_requirement(item, measurement_aliases) for item in data.get("requirement_definitions", []) if isinstance(item, dict)]
        supplied = data.get("generated_runs")
        try:
            generated = self._generate_runs(variables)
        except Exception:
            if isinstance(supplied, list) and supplied:
                generated = [dict(item) for item in supplied if isinstance(item, dict)]
            else:
                raise
        if isinstance(supplied, list) and supplied:
            enabled_by_values = {tuple(sorted(dict(item.get("values", {})).items())): bool(item.get("enabled", True)) for item in supplied if isinstance(item, dict)}
            for run in generated:
                run["enabled"] = enabled_by_values.get(tuple(sorted(dict(run["values"]).items())), True)
        self._validate_definition_references(circuit, variables, measurements)
        data.update({"variables": variables, "measurement_definitions": measurements, "requirement_definitions": requirements, "generated_runs": generated})
        return data

    @staticmethod
    def _validate_definition_references(
        circuit: Circuit,
        variables: list[dict[str, object]],
        measurements: list[dict[str, object]],
    ) -> None:
        from app.services.errors import CircuitError

        components = {component.id: component for component in circuit.components}
        nodes = {node.id for node in circuit.nodes}
        for variable in variables:
            component_id = str(variable.get("component_id") or "")
            parameter = str(variable.get("parameter") or "")
            component = components.get(component_id)
            if component is None:
                raise CircuitError("INVALID_EXPERIMENT", f"Sweep variable references unknown component {component_id or '(missing)' }.")
            if parameter not in component.params:
                raise CircuitError("INVALID_EXPERIMENT", f"Sweep variable references unsupported parameter {component_id}.{parameter or '(missing)' }.")
        measurement_ids: set[str] = set()
        for measurement in measurements:
            measurement_id = str(measurement.get("id") or "")
            if measurement_id in measurement_ids:
                raise CircuitError("INVALID_EXPERIMENT", f"Measurement id {measurement_id} is duplicated.")
            measurement_ids.add(measurement_id)
            if measurement.get("kind") == "gain_db":
                input_node = str(measurement.get("input_node") or "")
                output_node = str(measurement.get("output_node") or "")
                unknown_nodes = sorted({input_node, output_node}.difference(nodes))
                if unknown_nodes:
                    raise CircuitError("INVALID_EXPERIMENT", f"AC gain measurement {measurement_id} references unknown nodes: {', '.join(unknown_nodes)}.")
                frequency_hz = measurement.get("frequency_hz")
                if not isinstance(frequency_hz, (int, float)) or isinstance(frequency_hz, bool) or not math.isfinite(float(frequency_hz)) or frequency_hz <= 0:
                    raise CircuitError("INVALID_EXPERIMENT", f"AC gain measurement {measurement_id} requires a positive finite frequency_hz.")
            elif measurement.get("kind") in {"output_voltage", "voltage", "dc_voltage"}:
                node = str(measurement.get("node") or measurement.get("output_node") or "")
                if node not in nodes:
                    raise CircuitError("INVALID_EXPERIMENT", f"Voltage measurement {measurement_id} references unknown node {node or '(missing)' }.")

    @staticmethod
    def _normalize_variable(variable: dict[str, object]) -> dict[str, object]:
        normalized = dict(variable)
        nested = normalized.get("sweep")
        if isinstance(nested, dict):
            for key, value in nested.items():
                if key != "type": normalized.setdefault(key, value)
            normalized["sweep"] = nested.get("type", "explicit" if nested.get("values") else "linear")
        elif not isinstance(nested, str):
            normalized["sweep"] = "explicit" if normalized.get("values") else "linear"
        if not normalized.get("component_id") or not normalized.get("parameter"):
            from app.services.errors import CircuitError
            raise CircuitError("INVALID_EXPERIMENT", "Every sweep variable needs component_id and parameter.")
        return normalized

    @staticmethod
    def _normalize_measurement(item: object, circuit: Circuit, index: int) -> dict[str, object]:
        if isinstance(item, str):
            if item == "AC Gain": return {"id": "ac_gain_db_at_1khz", "kind": "gain_db", "label": item, "frequency_hz": 1_000.0, "unit": "dB", "input_node": circuit.metadata.get("input_node"), "output_node": circuit.metadata.get("output_node")}
            if item == "Cutoff Frequency": return {"id": "cutoff_frequency_hz", "kind": "cutoff_frequency", "label": item, "unit": "Hz", "input_node": circuit.metadata.get("input_node"), "output_node": circuit.metadata.get("output_node")}
            if item.startswith("Branch Current:"): return {"id": f"current_a:{item.split(':', 1)[1]}", "kind": "branch_current", "component_id": item.split(':', 1)[1], "label": item, "unit": "A"}
            output_node = circuit.metadata.get("output_node")
            return {"id": f"voltage_v:{output_node}", "kind": "output_voltage", "node": output_node, "label": item, "unit": "V"}
        if not isinstance(item, dict):
            from app.services.errors import CircuitError
            raise CircuitError("INVALID_EXPERIMENT", "Measurement definitions must be strings or objects.")
        result = dict(item)
        settings = result.get("settings")
        if isinstance(settings, dict):
            for key, value in settings.items(): result.setdefault(str(key), value)
        frequency = result.get("frequency_hz", result.get("frequency"))
        kind = str(result.get("kind") or result.get("type") or result.get("measurement_type") or ("gain_db" if frequency is not None else ""))
        measurement_id = str(result.get("id") or result.get("measurement_id") or result.get("name") or f"measurement_{index}")
        kind = kind.strip().lower()
        aliases = {
            "ac_gain": "gain_db",
            "ac_gain_db": "gain_db",
            "gain": "gain_db",
            "gain_at_frequency": "gain_db",
            "voltage": "output_voltage",
        }
        result.update({"id": measurement_id, "kind": aliases.get(kind, kind), "label": str(result.get("label") or measurement_id)})
        if frequency is not None: result["frequency_hz"] = float(frequency)
        result.setdefault("input_node", circuit.metadata.get("input_node"))
        result.setdefault("output_node", circuit.metadata.get("output_node"))
        return result

    @staticmethod
    def _normalize_requirement(item: dict[str, object], measurement_aliases: dict[str, str]) -> dict[str, object]:
        result = dict(item)
        measurement_id = str(result.get("measurement_id") or result.get("metric") or "")
        measurement_id = measurement_aliases.get(measurement_id, measurement_id)
        if not measurement_id or measurement_id not in measurement_aliases.values():
            from app.services.errors import CircuitError
            raise CircuitError("INVALID_EXPERIMENT", f"Requirement references unknown measurement {measurement_id or '(missing)'}.")
        operator_aliases = {"gte": ">=", "lte": "<=", "gt": ">", "lt": "<"}
        result["measurement_id"] = measurement_id
        result["operator"] = operator_aliases.get(str(result.get("operator", "")), str(result.get("operator", "")))
        result.setdefault("id", f"requirement_{measurement_id}")
        return result

    @classmethod
    def _generate_runs(cls, variables: list[dict[str, object]]) -> list[dict[str, object]]:
        if not variables: return []
        value_sets: list[list[float]] = []
        keys: list[str] = []
        for variable in variables:
            keys.append(f"{variable['component_id']}.{variable['parameter']}")
            sweep = str(variable.get("sweep", "linear"))
            if sweep == "explicit":
                values = variable.get("values")
                numeric = [float(value) for value in values] if isinstance(values, list) and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in values) else []
            else:
                start, stop, points = variable.get("start"), variable.get("stop"), variable.get("points")
                if not isinstance(start, (int, float)) or not isinstance(stop, (int, float)) or not isinstance(points, int) or points < 2:
                    numeric = []
                elif sweep == "logarithmic" and start > 0 and stop > start:
                    step = (math.log10(float(stop)) - math.log10(float(start))) / (points - 1)
                    numeric = [10 ** (math.log10(float(start)) + step * i) for i in range(points)]
                elif sweep == "linear" and stop > start:
                    numeric = [float(start) + (float(stop) - float(start)) * i / (points - 1) for i in range(points)]
                else: numeric = []
            if not numeric:
                from app.services.errors import CircuitError
                raise CircuitError("INVALID_EXPERIMENT", f"Sweep {keys[-1]} does not define valid values.")
            value_sets.append(numeric)
        combinations = list(itertools.product(*value_sets))
        if len(combinations) > 5_000:
            from app.services.errors import CircuitError
            raise CircuitError("RUN_LIMIT_EXCEEDED", "Experiment plans support at most 5,000 runs.")
        return [{"index": index, "values": dict(zip(keys, values)), "enabled": True} for index, values in enumerate(combinations, start=1)]

    def duplicate_definition(self, experiment_id: str) -> Experiment:
        from datetime import datetime, timezone

        source = self._repository.get_experiment(experiment_id)
        sequence = self._repository.next_experiment_sequence()
        duplicate = source.model_copy(deep=True)
        duplicate.id = f"exp_{sequence:03d}"
        duplicate.sequence = sequence
        duplicate.created_at = datetime.now(timezone.utc)
        duplicate.name = f"{source.name or source.hypothesis} copy"
        duplicate.hypothesis = duplicate.name
        duplicate.conclusion = ""
        duplicate.simulation_ids = []
        duplicate.measurements = {}
        duplicate.constraint_results = []
        duplicate.run_results = []
        duplicate.execution_status = "ready"
        duplicate.started_at = None
        duplicate.completed_at = None
        duplicate.run_by = ""
        duplicate.notes = ""
        self._repository.save_experiment(duplicate)
        return duplicate

    def delete_definition(self, experiment_id: str) -> None:
        with self._lock:
            if experiment_id in self._active:
                from app.services.errors import CircuitError
                raise CircuitError("EXPERIMENT_ACTIVE", "Stop the active experiment before deleting it.")
        self._repository.delete_experiment(experiment_id)

    def start_execution(self, experiment_id: str, simulator: object) -> Experiment:
        with self._lock:
            if experiment_id in self._active:
                from app.services.errors import CircuitError
                raise CircuitError("INVALID_PARAMETER", "Experiment execution is already active.")
            self._active.add(experiment_id)
            resume, stop = Event(), Event()
            resume.set()
            self._controls[experiment_id] = (resume, stop)
        experiment = self._repository.get_experiment(experiment_id)
        if experiment.run_results:
            with self._lock:
                self._active.discard(experiment_id)
                self._controls.pop(experiment_id, None)
            from app.services.errors import CircuitError
            raise CircuitError("EXPERIMENT_ALREADY_EXECUTED", "This experiment already has recorded runs and cannot be rerun.", "Create a new experiment to preserve the original result history.")
        if not experiment.generated_runs:
            with self._lock:
                self._active.discard(experiment_id)
                self._controls.pop(experiment_id, None)
            from app.services.errors import CircuitError
            raise CircuitError("INVALID_PARAMETER", "Experiment has no enabled generated runs.")
        if not experiment.measurement_definitions:
            with self._lock:
                self._active.discard(experiment_id)
                self._controls.pop(experiment_id, None)
            from app.services.errors import CircuitError
            raise CircuitError("EXPERIMENT_NOT_READY", "Experiment has no measurement definitions.", "Add at least one measurement before running the experiment.")
        Thread(target=self._execute_definition, args=(experiment_id, simulator), daemon=True).start()
        return experiment

    def pause_execution(self, experiment_id: str) -> Experiment:
        with self._lock:
            controls = self._controls.get(experiment_id)
            if experiment_id not in self._active or controls is None:
                from app.services.errors import CircuitError
                raise CircuitError("EXPERIMENT_NOT_ACTIVE", "Experiment execution is not active.")
            controls[0].clear()
        experiment = self._repository.get_experiment(experiment_id)
        if experiment.execution_status == "running":
            experiment.execution_status = "paused"
            self._repository.update_experiment(experiment)
        return experiment

    def resume_execution(self, experiment_id: str) -> Experiment:
        with self._lock:
            controls = self._controls.get(experiment_id)
            if experiment_id not in self._active or controls is None:
                from app.services.errors import CircuitError
                raise CircuitError("EXPERIMENT_NOT_ACTIVE", "Experiment execution is not active.")
            controls[0].set()
        experiment = self._repository.get_experiment(experiment_id)
        if experiment.execution_status == "paused":
            experiment.execution_status = "running"
            self._repository.update_experiment(experiment)
        return experiment

    def stop_execution(self, experiment_id: str) -> Experiment:
        with self._lock:
            controls = self._controls.get(experiment_id)
            if experiment_id not in self._active or controls is None:
                from app.services.errors import CircuitError
                raise CircuitError("EXPERIMENT_NOT_ACTIVE", "Experiment execution is not active.")
            controls[1].set()
            controls[0].set()
        experiment = self._repository.get_experiment(experiment_id)
        experiment.execution_status = "interrupted"
        self._repository.update_experiment(experiment)
        return experiment

    def _execute_definition(self, experiment_id: str, simulator: object) -> Experiment:
        from datetime import datetime, timezone

        experiment = self._repository.get_experiment(experiment_id)
        experiment.execution_status = "running"
        experiment.started_at = datetime.now(timezone.utc)
        experiment.run_results = []
        self._repository.update_experiment(experiment)
        non_ground_nodes = [node.id for node in experiment.circuit_snapshot.nodes if node.id != "gnd"]
        input_node = experiment.circuit_snapshot.metadata.get("input_node", non_ground_nodes[0] if non_ground_nodes else "gnd")
        output_node = experiment.circuit_snapshot.metadata.get("output_node", non_ground_nodes[-1] if non_ground_nodes else "gnd")
        measurement_definitions = [self._normalize_measurement(item, experiment.circuit_snapshot, index) for index, item in enumerate(experiment.measurement_definitions, start=1)]
        try:
            for run in experiment.generated_runs:
                with self._lock:
                    controls = self._controls.get(experiment_id)
                if controls is None or controls[1].is_set():
                    experiment.execution_status = "interrupted"
                    break
                controls[0].wait()
                if controls[1].is_set():
                    experiment.execution_status = "interrupted"
                    break
                if not run.get("enabled", True):
                    timestamp = datetime.now(timezone.utc)
                    experiment.run_results.append({"run_index": run.get("index"), "status": "SKIPPED", "parameters": run.get("values", {}), "started_at": timestamp, "completed_at": timestamp, "run_by": experiment.run_by, "notes": experiment.notes})
                    self._repository.update_experiment(experiment)
                    continue
                run_started_at = datetime.now(timezone.utc)
                circuit = experiment.circuit_snapshot.model_copy(deep=True)
                for key, value in dict(run.get("values", {})).items():
                    component_id, parameter = str(key).split(".", 1)
                    component = next((item for item in circuit.components if item.id == component_id), None)
                    if component is not None: component.params[parameter] = value
                measurements, measurement_errors, simulation_ids = self._execute_measurements(
                    simulator,
                    circuit,
                    measurement_definitions,
                    input_node,
                    output_node,
                )
                requirements = []
                for requirement in experiment.requirement_definitions:
                    metric = str(requirement.get("measurement_id") or requirement.get("metric") or "")
                    actual = measurements.get(metric)
                    operator = str(requirement.get("operator", "")); target = requirement.get("target")
                    tolerance = requirement.get("tolerance")
                    passed = self._requirement_passes(actual, operator, target, tolerance)
                    margin = self._requirement_margin(actual, operator, target, tolerance)
                    requirements.append({"id": requirement.get("id"), "measurement_id": metric, "metric": metric, "operator": operator, "status": "PASS" if passed else "FAIL" if actual is not None else "INCOMPLETE/UNCLASSIFIED", "actual": actual, "target": target, "margin": margin})
                expected_measurements = {str(item["id"]) for item in measurement_definitions}
                missing_measurements = sorted(expected_measurements.difference(measurements))
                if measurement_errors:
                    run_status = "ERROR"
                    error_message = "; ".join(measurement_errors)
                    incomplete_reason = None
                elif missing_measurements:
                    run_status = "INCOMPLETE"
                    error_message = None
                    incomplete_reason = f"Missing required measurements: {', '.join(missing_measurements)}."
                else:
                    run_status = "COMPLETED"
                    error_message = None
                    incomplete_reason = None
                experiment.run_results.append({"run_index": run.get("index"), "status": run_status, "parameters": run.get("values", {}), "measurements": measurements, "requirement_results": requirements, "simulation_ids": simulation_ids, "error": error_message, "incomplete_reason": incomplete_reason, "started_at": run_started_at, "completed_at": datetime.now(timezone.utc), "run_by": experiment.run_by, "notes": experiment.notes})
                self._repository.update_experiment(experiment)
            if experiment.execution_status != "interrupted":
                experiment.execution_status = "completed" if all(item["status"] in {"COMPLETED", "SKIPPED"} for item in experiment.run_results) else "failed"
        except Exception:
            experiment.execution_status = "failed"
        finally:
            with self._lock:
                controls = self._controls.get(experiment_id)
                stopped = controls is not None and controls[1].is_set()
            if stopped:
                experiment.execution_status = "interrupted"
            experiment.completed_at = datetime.now(timezone.utc)
            self._repository.update_experiment(experiment)
            with self._lock:
                self._active.discard(experiment_id)
                self._controls.pop(experiment_id, None)
        return experiment

    def _execute_measurements(
        self,
        simulator: object,
        circuit: Circuit,
        definitions: list[dict[str, object]],
        default_input_node: str,
        default_output_node: str,
    ) -> tuple[dict[str, float], list[str], list[str]]:
        """Execute experiment measurements through the canonical simulator/measurement services."""
        from app.services.measurement_service import MeasurementService

        measurement_service = MeasurementService()
        measurements: dict[str, float] = {}
        errors: list[str] = []
        simulation_ids: list[str] = []

        operating_definitions = [
            item for item in definitions if item.get("kind") in {"output_voltage", "voltage", "dc_voltage", "branch_current"}
        ]
        if operating_definitions:
            voltage_nodes = sorted({
                str(item.get("node") or item.get("output_node") or default_output_node)
                for item in operating_definitions
                if item.get("kind") in {"output_voltage", "voltage", "dc_voltage"}
            })
            current_components = sorted({
                str(item.get("component_id"))
                for item in operating_definitions
                if item.get("kind") == "branch_current" and item.get("component_id")
            })
            try:
                operating_point = simulator.run_operating_point(circuit, voltage_nodes, current_components) if current_components else simulator.run_operating_point(circuit, voltage_nodes)
                simulation_ids.append(str(operating_point.simulation_id))
                for definition in operating_definitions:
                    measurement_id = str(definition["id"])
                    try:
                        if definition.get("kind") == "branch_current":
                            component_id = str(definition.get("component_id"))
                            measurements[measurement_id] = measurement_service.measure_current(operating_point, component_id, "dc")
                        else:
                            node = str(definition.get("node") or definition.get("output_node") or default_output_node)
                            measurements[measurement_id] = measurement_service.measure_voltage(operating_point, node, "dc")
                    except Exception as error:
                        errors.append(f"{measurement_id}: {error}")
            except Exception as error:
                errors.append(f"Operating-point simulation failed: {error}")

        ac_groups: dict[tuple[str, str], list[dict[str, object]]] = {}
        for definition in definitions:
            if definition.get("kind") in {"gain_db", "cutoff_frequency"}:
                input_node = str(definition.get("input_node") or default_input_node)
                output_node = str(definition.get("output_node") or default_output_node)
                ac_groups.setdefault((input_node, output_node), []).append(definition)

        for (input_node, output_node), group in ac_groups.items():
            frequencies = [
                float(item["frequency_hz"])
                for item in group
                if isinstance(item.get("frequency_hz"), (int, float)) and not isinstance(item.get("frequency_hz"), bool)
            ]
            start_hz = max(1e-6, min(frequencies) / 10.0) if frequencies else 10.0
            stop_hz = max(frequencies) * 10.0 if frequencies else 100_000.0
            try:
                ac_result = simulator.run_ac(circuit, AcAnalysis(start_hz, stop_hz, 50, input_node, output_node))
                simulation_ids.append(str(ac_result.simulation_id))
                for definition in group:
                    measurement_id = str(definition["id"])
                    try:
                        if definition.get("kind") == "gain_db":
                            frequency_hz = definition.get("frequency_hz")
                            if not isinstance(frequency_hz, (int, float)) or isinstance(frequency_hz, bool) or frequency_hz <= 0:
                                raise ValueError("AC gain requires a positive frequency_hz.")
                            measurements[measurement_id] = measurement_service.measure_gain(ac_result, float(frequency_hz))
                        else:
                            cutoff = measurement_service.measure_cutoff_frequency(ac_result)
                            if cutoff is None:
                                raise ValueError("No descending -3 dB cutoff was found in the simulated range.")
                            measurements[measurement_id] = cutoff
                    except Exception as error:
                        errors.append(f"{measurement_id}: {error}")
            except Exception as error:
                errors.append(f"AC simulation {input_node} to {output_node} failed: {error}")

        supported_kinds = {"output_voltage", "voltage", "dc_voltage", "branch_current", "gain_db", "cutoff_frequency"}
        for definition in definitions:
            if definition.get("kind") not in supported_kinds:
                errors.append(f"{definition['id']}: unsupported measurement type {definition.get('kind') or '(missing)' }.")

        return measurements, errors, simulation_ids

    @staticmethod
    def _measure_gain(simulation: object, frequency_hz: float) -> float:
        from app.services.measurement_service import MeasurementService
        return MeasurementService().measure_gain(simulation, frequency_hz)  # type: ignore[arg-type]

    @staticmethod
    def _measure_cutoff(simulation: object) -> float | None:
        from app.services.measurement_service import MeasurementService
        return MeasurementService().measure_cutoff_frequency(simulation)  # type: ignore[arg-type]

    @staticmethod
    def _requirement_margin(actual: object, operator: str, target: object, tolerance: object = None) -> float | None:
        if not isinstance(actual, (int, float)) or isinstance(actual, bool): return None
        if operator in {">=", ">"} and isinstance(target, (int, float)): return float(actual) - float(target)
        if operator in {"<=", "<"} and isinstance(target, (int, float)): return float(target) - float(actual)
        if operator == "between" and isinstance(target, (list, tuple)) and len(target) == 2: return min(float(actual) - float(target[0]), float(target[1]) - float(actual))
        if operator == "approximately" and isinstance(target, (int, float)) and isinstance(tolerance, (int, float)): return float(tolerance) - abs(float(actual) - float(target))
        return None

    @staticmethod
    def _requirement_passes(actual: object, operator: str, target: object, tolerance: object = None) -> bool:
        if not isinstance(actual, (int, float)):
            return False
        if operator == "between" and isinstance(target, (list, tuple)) and len(target) == 2:
            lower, upper = target
            return isinstance(lower, (int, float)) and isinstance(upper, (int, float)) and lower <= actual <= upper
        if operator == "approximately" and isinstance(target, (int, float)) and isinstance(tolerance, (int, float)):
            return abs(actual - target) <= abs(tolerance)
        if not isinstance(target, (int, float)):
            return False
        return (operator in {">=", ">"} and actual >= target) or (operator in {"<=", "<"} and actual <= target)
