from __future__ import annotations

import shutil
import time

import pytest

from app.db.repository import LabRepository
from app.models.circuit import Experiment, SimulationError, SimulationResult
from app.services.errors import CircuitError
from app.services.lab_service import LabService, default_lab
from app.webmcp.tools import WebMCPToolRegistry


EXPECTED_TOOLS = {
    "get_lab_state",
    "list_challenges",
    "load_challenge",
    "create_blank_circuit",
    "list_saved_circuits",
    "rename_circuit",
    "open_saved_circuit",
    "delete_saved_circuit",
    "reset_lab",
    "get_circuit",
    "get_constraints",
    "add_component",
    "create_node",
    "rename_net",
    "connect",
    "connect_pins",
    "disconnect",
    "set_component_value",
    "remove_component",
    "restore_circuit",
    "validate_circuit",
    "run_operating_point",
    "run_ac_analysis",
    "run_transient",
    "measure_voltage",
    "measure_current",
    "measure_gain",
    "measure_cutoff_frequency",
    "measure_rise_time",
    "evaluate_constraints",
    "create_experiment",
    "get_experiment",
    "list_experiments",
    "update_experiment",
    "get_experiment_plan",
    "run_experiment",
    "pause_experiment",
    "resume_experiment",
    "stop_experiment",
    "get_experiment_results",
    "get_experiment_run",
    "get_experiment_analysis",
    "get_report",
    "export_report",
    "export_run_data",
    "duplicate_experiment",
    "delete_experiment",
    "restore_experiment",
    "restore_experiment_run",
}


def registry(tmp_path) -> tuple[WebMCPToolRegistry, LabService]:
    repository = LabRepository(tmp_path / "webmcp.db")
    repository.initialize(*default_lab())
    labs = LabService(repository)
    return WebMCPToolRegistry(labs), labs


class DeterministicSimulator:
    """Fast simulator double for lifecycle parity, not a second execution path."""

    def run_operating_point(self, circuit, output_nodes):
        return SimulationResult(success=True, analysis="operating_point", circuit_revision=circuit.revision, simulation_id="op-test", measurements={f"voltage_v:{node}": 1.25 for node in output_nodes})

    def run_ac(self, circuit, _analysis):
        return SimulationResult(success=True, analysis="ac", circuit_revision=circuit.revision, simulation_id="ac-test", measurements={}, series={"frequency_hz": [10.0, 1_000.0], "output_gain_db": [-1.0, -2.0]})


class TwoFrequencySimulator(DeterministicSimulator):
    def run_ac(self, circuit, _analysis):
        resistance = float(next(item for item in circuit.components if item.id == "R1").params["resistance_ohm"])
        capacitance = float(next(item for item in circuit.components if item.id == "C1").params["capacitance_f"])
        shift = (resistance / 1_000.0 - 1.0) + (capacitance / 100e-9 - 1.0)
        return SimulationResult(success=True, analysis="ac", circuit_revision=circuit.revision, simulation_id=f"ac-{resistance:g}-{capacitance:g}", measurements={}, series={"frequency_hz": [80.0, 800.0, 15_000.0, 150_000.0], "output_gain_db": [-0.1, -0.5 - shift, -35.0 + shift, -55.0]})


class FailingAcSimulator(DeterministicSimulator):
    def run_ac(self, circuit, _analysis):
        return SimulationResult(
            success=False,
            analysis="ac",
            circuit_revision=circuit.revision,
            simulation_id="ac-failed",
            errors=[SimulationError(code="SIMULATION_FAILED", message="AC solver failed.")],
        )


class BlockingSimulator(DeterministicSimulator):
    def __init__(self) -> None:
        from threading import Event

        self.started = Event()
        self.release = Event()

    def run_operating_point(self, circuit, output_nodes):
        self.started.set()
        assert self.release.wait(1)
        return super().run_operating_point(circuit, output_nodes)


def wait_for_execution(labs: LabService, experiment_id: str) -> None:
    for _ in range(200):
        experiment = labs.repository.get_experiment(experiment_id)
        if experiment.execution_status in {"completed", "failed", "interrupted"}:
            return
        time.sleep(0.01)
    raise AssertionError("Experiment execution did not complete.")


def test_exposes_exact_semantic_tool_surface(tmp_path) -> None:
    tools, _labs = registry(tmp_path)
    definitions = tools.definitions()

    assert {definition.name for definition in definitions} == EXPECTED_TOOLS
    assert all(definition.description and definition.input_schema["type"] == "object" for definition in definitions)
    assert next(item for item in definitions if item.name == "get_circuit").read_only is True
    assert next(item for item in definitions if item.name == "add_component").read_only is False
    voltage_params = next(item for item in definitions if item.name == "add_component").input_schema["allOf"][0]["then"]["properties"]["params"]
    assert "normalized 1 V" in voltage_params["description"]
    assert "DC source voltage" in voltage_params["properties"]["voltage_v"]["description"]
    assert "VOUT/VIN" in next(item for item in definitions if item.name == "run_ac_analysis").description


def test_invalid_tool_input_returns_stable_machine_error(tmp_path) -> None:
    tools, _labs = registry(tmp_path)

    with pytest.raises(CircuitError) as error:
        tools.invoke("get_circuit", {"unexpected": True})

    assert error.value.code == "INVALID_PARAMETER"
    assert "Invalid input for get_circuit" in error.value.message


def test_experiment_tool_schema_is_strongly_typed_and_links_requirements(tmp_path) -> None:
    tools, _labs = registry(tmp_path)
    definition = next(item for item in tools.definitions() if item.name == "create_experiment")
    schema = definition.input_schema
    schema_text = str(schema)
    assert "AcGainExperimentMeasurementInput" in schema_text
    assert all(field in schema_text for field in ("input_node", "output_node", "frequency_hz", "measurement_id"))
    assert all(sweep in schema_text for sweep in ("linear", "logarithmic", "explicit"))
    assert set(schema["$defs"]["AcGainExperimentMeasurementInput"]["required"]) == {"id", "type", "input_node", "output_node", "frequency_hz"}
    assert "generated_runs" not in schema["properties"]

    with pytest.raises(CircuitError) as raised:
        tools.invoke("create_experiment", {
            "name": "Invalid links",
            "experiment_type": "validation",
            "circuit_revision": 0,
            "variables": [{"component_id": "R1", "parameter": "resistance_ohm", "sweep": "explicit", "values": [1_000]}],
            "measurement_definitions": [{"id": "gain_800_hz", "type": "ac_gain_db", "input_node": "sensor", "output_node": "out", "frequency_hz": 800}],
            "requirement_definitions": [{"id": "missing_link", "measurement_id": "gain_15khz", "operator": "<=", "target": -28}],
        })
    assert raised.value.code == "INVALID_PARAMETER"
    assert "unknown measurement ids" in (raised.value.recovery_hint or "")

    with pytest.raises(CircuitError) as bad_node:
        tools.invoke("create_experiment", {
            "name": "Invalid circuit reference",
            "experiment_type": "validation",
            "circuit_revision": 0,
            "variables": [{"component_id": "R1", "parameter": "resistance_ohm", "sweep": "explicit", "values": [1_000]}],
            "measurement_definitions": [{"id": "gain_800_hz", "type": "ac_gain_db", "input_node": "missing", "output_node": "out", "frequency_hz": 800}],
            "requirement_definitions": [{"id": "passband", "measurement_id": "gain_800_hz", "operator": ">=", "target": -1}],
        })
    assert bad_node.value.code == "INVALID_EXPERIMENT"
    assert "unknown nodes" in bad_node.value.message


def test_verification_plan_without_measurements_has_clear_readiness_error(tmp_path) -> None:
    tools, _labs = registry(tmp_path)
    created = tools.invoke("create_experiment", {
        "name": "Unconfigured verification",
        "experiment_type": "validation",
        "circuit_revision": 0,
        "variables": [],
        "measurement_definitions": [],
        "requirement_definitions": [],
    })

    assert created["ready"] is False
    assert "VERIFICATION_MEASUREMENTS_REQUIRED" in {item["code"] for item in created["readiness_errors"]}
    plan = tools.invoke("get_experiment_plan", {"experiment_id": created["id"]})
    assert plan["ready"] is False
    assert "VERIFICATION_MEASUREMENTS_REQUIRED" in {item["code"] for item in plan["validation_errors"]}
    with pytest.raises(CircuitError) as raised:
        tools.invoke("run_experiment", {"experiment_id": created["id"]})
    assert raised.value.code in {"INVALID_PARAMETER", "EXPERIMENT_NOT_READY"}


def test_add_component_uses_a_valid_resistor_default(tmp_path) -> None:
    tools, labs = registry(tmp_path)

    result = tools.invoke("add_component", {"type": "resistor", "expected_revision": 0})

    assert result["component"].params["resistance_ohm"] == 1_000.0
    assert result["new_revision"] == 1
    assert len(labs.repository.get_circuit().components) == 4


def test_reset_lab_accepts_the_current_valid_lab_payload(tmp_path) -> None:
    tools, labs = registry(tmp_path)
    payload = {"challenge": labs.repository.get_challenge().model_dump(), "circuit": labs.repository.get_circuit().model_dump()}

    result = tools.invoke("reset_lab", payload)

    assert result["circuit"].id == payload["circuit"]["id"]
    assert result["latest_experiment"] is None


def test_webmcp_can_create_a_blank_circuit_with_the_full_component_library(tmp_path) -> None:
    tools, labs = registry(tmp_path)

    created = tools.invoke("create_blank_circuit", {"name": "Scratch filter"})

    assert created["circuit"].name == "Scratch filter"
    assert created["circuit"].components == []
    assert {node.id for node in created["circuit"].nodes} == {"gnd"}
    assert {item.value for item in created["challenge"].allowed_components} == {"ground", "resistor", "capacitor", "inductor", "voltage_source", "diode", "ideal_opamp"}
    added = tools.invoke("add_component", {"type": "voltage_source", "params": {"mode": "dc", "voltage_v": 1}, "expected_revision": 0})
    assert added["component"].id == "V1"
    assert labs.repository.get_circuit().revision == 1
    saved = tools.invoke("list_saved_circuits", {})[0]
    assert saved["component_count"] == 1
    opened = tools.invoke("open_saved_circuit", {"circuit_id": saved["id"]})
    assert opened["circuit"].components[0].id == "V1"
    deleted = tools.invoke("delete_saved_circuit", {"circuit_id": saved["id"]})
    assert deleted["active_saved_circuit_id"] is None
    assert deleted["circuit"].name == "Untitled Circuit"


def test_webmcp_circuit_library_matches_human_new_and_rename_behavior(tmp_path) -> None:
    tools, _labs = registry(tmp_path)

    first = tools.invoke("create_blank_circuit", {})
    assert first["circuit"].name == "New Circuit"
    renamed = tools.invoke("rename_circuit", {"name": "Test 2"})
    assert renamed["name"] == "Test 2"
    assert tools.invoke("get_lab_state", {})["circuit"].name == "Test 2"

    second = tools.invoke("create_blank_circuit", {})
    third = tools.invoke("create_blank_circuit", {})
    assert [second["circuit"].name, third["circuit"].name] == ["New Circuit", "New Circuit 1"]


def test_webmcp_matches_human_experiment_lifecycle_and_canonical_state(tmp_path) -> None:
    tools, labs = registry(tmp_path)
    labs.simulator = DeterministicSimulator()

    challenges = tools.invoke("list_challenges", {})
    assert {challenge["id"] for challenge in challenges} >= {"challenge_filter_01", "challenge_sensor_01"}
    loaded = tools.invoke("load_challenge", {"challenge_id": "challenge_filter_01"})
    assert loaded["challenge"].id == "challenge_filter_01"

    circuit = tools.invoke("get_circuit", {})
    assert circuit.revision == 0
    tools.invoke("disconnect", {"component_id": "C1", "pin": "b", "expected_revision": 0})
    tools.invoke("connect", {"component_id": "C1", "pin": "b", "node_id": "gnd", "expected_revision": 1})
    tools.invoke("add_component", {"type": "resistor", "params": {"resistance_ohm": 2_200}, "expected_revision": 2})
    tools.invoke("connect_pins", {"source_component_id": "R2", "source_pin": "a", "target_component_id": "R1", "target_pin": "a", "expected_revision": 3})
    tools.invoke("remove_component", {"component_id": "R2", "expected_revision": 4})
    assert tools.invoke("validate_circuit", {})["valid"] is True
    assert labs.repository.get_circuit().revision == 5
    direct_simulation = tools.invoke("run_operating_point", {"output_nodes": ["out"]})
    assert direct_simulation["success"] is True

    create_payload = {
        "name": "WebMCP filter characterization",
        "description": "Sweep the RC resistance and record output voltage.",
        "experiment_type": "characterization",
        "circuit_revision": 5,
        "variables": [],
        "measurement_definitions": [],
        "requirement_definitions": [],
        "collection_name": "Parity",
        "run_by": "WebMCP test",
        "notes": "Created through the semantic tool surface.",
    }
    created = tools.invoke("create_experiment", create_payload)
    assert created["execution_status"] == "draft"
    experiment_id = created["id"]

    configured = {**create_payload, "experiment_id": experiment_id, "variables": [{"component_id": "R1", "parameter": "resistance_ohm", "label": "R1 resistance", "unit": "Ω", "sweep": "linear", "start": 1_000, "stop": 2_000, "points": 2}], "measurement_definitions": [{"id": "output_voltage", "type": "dc_voltage", "node": "out"}], "requirement_definitions": [{"id": "output_min", "measurement_id": "output_voltage", "operator": ">=", "target": 1.0}]}
    updated = tools.invoke("update_experiment", configured)
    assert updated["execution_status"] == "ready"
    plan = tools.invoke("get_experiment_plan", {"experiment_id": experiment_id, "sample_limit": 1})
    assert plan["ready"] is True
    assert plan["total_generated_runs"] == 2
    assert len(plan["representative_runs"]) == 1
    assert tools.invoke("get_experiment", {"experiment_id": experiment_id})["name"] == create_payload["name"]

    started = tools.invoke("run_experiment", {"experiment_id": experiment_id})
    assert started["execution_status"] == "completed"
    assert started["classification_counts"]["PASS"] == 2
    assert started["analysis"]["worst_case_requirements"][0]["measurement_id"] == "output_voltage"
    wait_for_execution(labs, experiment_id)
    results = tools.invoke("get_experiment_results", {"experiment_id": experiment_id, "offset": 0, "limit": 1})
    assert results["completed_runs"] == 2
    assert results["returned_runs"] == 1
    run = tools.invoke("get_experiment_run", {"experiment_id": experiment_id, "run_index": 1})
    assert run["run"]["measurements"]["output_voltage"] == 1.25
    assert tools.invoke("get_experiment_analysis", {"experiment_id": experiment_id})["measurement_ranges"]["output_voltage"]["minimum"] == 1.25
    report = tools.invoke("get_report", {"experiment_id": experiment_id})
    assert report["report"]["circuit_under_test"].revision == 5
    report_export = tools.invoke("export_report", {"experiment_id": experiment_id})
    assert '"experiment_id": "exp_001"' in report_export["content"]
    assert '"circuit_under_test": {' in report_export["content"]
    csv_export = tools.invoke("export_run_data", {"experiment_id": experiment_id})
    assert csv_export["content"].startswith("run,")
    assert "simulation_status" in csv_export["content"]

    with pytest.raises(CircuitError) as immutable:
        tools.invoke("update_experiment", configured)
    assert immutable.value.code == "EXPERIMENT_IMMUTABLE"
    duplicated = tools.invoke("duplicate_experiment", {"experiment_id": experiment_id})
    assert duplicated["id"] != experiment_id
    tools.invoke("delete_experiment", {"experiment_id": duplicated["id"]})
    snapshot = tools.invoke("get_circuit", {})
    restored_circuit = tools.invoke("restore_circuit", {"circuit": snapshot, "expected_revision": 5})
    assert restored_circuit["new_revision"] == 6
    restored = tools.invoke("restore_experiment", {"experiment_id": experiment_id, "expected_revision": 6})
    assert restored["new_revision"] == 7
    restored_run = tools.invoke("restore_experiment_run", {"experiment_id": experiment_id, "run_index": 1, "expected_revision": 7})
    assert restored_run["new_revision"] == 8
    reset = tools.invoke("reset_lab", {"challenge": loaded["challenge"], "circuit": loaded["circuit"]})
    assert reset["circuit"].revision == 0


def test_structured_two_frequency_experiment_generates_and_executes_all_25_runs(tmp_path) -> None:
    tools, labs = registry(tmp_path)
    labs.simulator = TwoFrequencySimulator()
    loaded = tools.invoke("load_challenge", {"challenge_id": "challenge_filter_01"})
    base = {
        "name": "Two-frequency tolerance matrix",
        "description": "Record passband and stopband gain for every combination.",
        "experiment_type": "validation",
        "circuit_revision": loaded["circuit"].revision,
        "variables": [], "measurement_definitions": [], "requirement_definitions": [],
        "collection_name": "Regression", "run_by": "pytest", "notes": "",
    }
    experiment_id = tools.invoke("create_experiment", base)["id"]
    configured = {
        **base,
        "experiment_id": experiment_id,
        "variables": [
            {"component_id": "R1", "parameter": "resistance_ohm", "label": "R1", "unit": "ohm", "sweep": "linear", "start": 800.0, "stop": 1_200.0, "points": 5},
            {"component_id": "C1", "parameter": "capacitance_f", "label": "C1", "unit": "F", "sweep": "explicit", "values": [80e-9, 90e-9, 100e-9, 110e-9, 120e-9]},
        ],
        "measurement_definitions": [
            {"id": "gain_800_hz", "type": "ac_gain_db", "input_node": "vin", "output_node": "out", "frequency_hz": 800.0},
            {"id": "gain_15_khz", "type": "ac_gain_db", "input_node": "vin", "output_node": "out", "frequency_hz": 15_000.0},
        ],
        "requirement_definitions": [
            {"id": "passband", "measurement_id": "gain_800_hz", "operator": ">=", "target": -2.0},
            {"id": "stopband", "measurement_id": "gain_15_khz", "operator": "<=", "target": -30.0},
        ],
    }
    updated = tools.invoke("update_experiment", configured)
    assert updated["planned_runs"] == 25
    plan = tools.invoke("get_experiment_plan", {"experiment_id": experiment_id})
    assert plan["ready"] is True
    assert plan["total_generated_runs"] == plan["enabled_run_count"] == 25
    execution = tools.invoke("run_experiment", {"experiment_id": experiment_id})
    assert execution["execution_status"] == "completed"
    assert execution["classification_counts"]["PASS"] + execution["classification_counts"]["FAIL"] == 25
    assert {item["measurement_id"] for item in execution["analysis"]["worst_case_requirements"]} == {"gain_800_hz", "gain_15_khz"}
    wait_for_execution(labs, experiment_id)
    results = tools.invoke("get_experiment_results", {"experiment_id": experiment_id, "limit": 50})
    assert results["completed_runs"] == results["recorded_runs"] == 25
    assert all(set(run["measurements"]) >= {"gain_800_hz", "gain_15_khz"} for run in results["runs"])
    assert all(len(run["requirement_results"]) == 2 for run in results["runs"])
    assert all({item["status"] for item in run["requirement_results"]} <= {"PASS", "FAIL"} for run in results["runs"])
    analysis = tools.invoke("get_experiment_analysis", {"experiment_id": experiment_id})
    assert {item["measurement_id"] for item in analysis["worst_case_requirements"]} == {"gain_800_hz", "gain_15_khz"}
    assert all(item["run_id"] is not None and isinstance(item["worst_margin"], float) for item in analysis["worst_case_requirements"])
    assert analysis["design_search_status"] == "requirements_met"
    assert analysis["planned_matrix_complete"] is True


@pytest.mark.parametrize(
    ("outcomes", "exceptional_status", "expected"),
    [
        (["PASS"] * 25, None, "requirements_met"),
        (["PASS"] * 24 + ["FAIL"], None, "requirements_not_met"),
        (["PASS"] * 24 + ["INCOMPLETE/UNCLASSIFIED"], "INCOMPLETE", "incomplete"),
        (["PASS"] * 24 + ["INCOMPLETE/UNCLASSIFIED"], "ERROR", "error"),
    ],
    ids=["25-pass", "24-pass-1-fail", "incomplete-run", "simulation-error"],
)
def test_design_search_status_requires_all_persisted_runs_to_pass(
    tmp_path, outcomes: list[str], exceptional_status: str | None, expected: str
) -> None:
    tools, labs = registry(tmp_path)
    circuit = labs.repository.get_circuit()
    generated_runs = [{"index": index, "values": {}, "enabled": True} for index in range(1, 26)]
    run_results = []
    for index, outcome in enumerate(outcomes, start=1):
        is_exceptional = index == 25 and exceptional_status is not None
        run_results.append({
            "run_index": index,
            "status": exceptional_status if is_exceptional else "COMPLETED",
            "measurements": {} if is_exceptional else {"gain_800_hz": -0.5},
            "requirement_results": [{
                "id": "passband",
                "measurement_id": "gain_800_hz",
                "status": outcome,
                "actual": None if is_exceptional else -0.5,
                "target": -1.0,
                "margin": None if is_exceptional else 0.5,
            }],
            "error": "ngspice failed" if exceptional_status == "ERROR" and is_exceptional else None,
        })
    experiment = Experiment(
        id="exp_001",
        sequence=1,
        hypothesis="Persisted status regression",
        circuit_id=circuit.id,
        circuit_revision=circuit.revision,
        circuit_snapshot=circuit,
        measurement_definitions=[{"id": "gain_800_hz", "type": "ac_gain_db"}],
        requirement_definitions=[{"id": "passband", "measurement_id": "gain_800_hz", "operator": ">=", "target": -1.0}],
        generated_runs=generated_runs,
        run_results=run_results,
        execution_status="failed" if exceptional_status else "completed",
    )
    labs.repository.save_experiment(experiment)

    analysis = tools.invoke("get_experiment_analysis", {"experiment_id": experiment.id})

    assert analysis["design_search_status"] == expected


def test_failed_ac_measurement_never_records_a_completed_run(tmp_path) -> None:
    tools, labs = registry(tmp_path)
    labs.simulator = FailingAcSimulator()
    definition = {
        "name": "Failed AC measurement",
        "description": "Measurement failures must remain explicit.",
        "experiment_type": "validation",
        "circuit_revision": 0,
        "variables": [{"component_id": "R1", "parameter": "resistance_ohm", "sweep": "explicit", "values": [1_000]}],
        "measurement_definitions": [{"id": "gain_800_hz", "type": "ac_gain_db", "input_node": "sensor", "output_node": "out", "frequency_hz": 800.0}],
        "requirement_definitions": [{"id": "passband", "measurement_id": "gain_800_hz", "operator": ">=", "target": -1.0}],
        "collection_name": "",
        "run_by": "pytest",
        "notes": "",
    }
    experiment_id = tools.invoke("create_experiment", definition)["id"]

    tools.invoke("run_experiment", {"experiment_id": experiment_id})
    wait_for_execution(labs, experiment_id)
    result = tools.invoke("get_experiment_run", {"experiment_id": experiment_id, "run_index": 1})["run"]

    assert result["status"] == "ERROR"
    assert result["measurements"] == {}
    assert result["requirement_results"][0]["status"] == "INCOMPLETE/UNCLASSIFIED"
    assert "gain_800_hz" in result["error"]


@pytest.mark.ngspice
@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_real_ngspice_experiment_executes_ac_gain_definitions(tmp_path) -> None:
    tools, labs = registry(tmp_path)
    loaded = tools.invoke("load_challenge", {"challenge_id": "challenge_filter_01"})
    definition = {
        "name": "Real AC gain regression",
        "description": "Exercise the canonical ngspice and gain-measurement path.",
        "experiment_type": "validation",
        "circuit_revision": loaded["circuit"].revision,
        "variables": [{"component_id": "R1", "parameter": "resistance_ohm", "sweep": "explicit", "values": [1_000]}],
        "measurement_definitions": [
            {"id": "gain_800_hz", "type": "ac_gain_db", "input_node": "vin", "output_node": "out", "frequency_hz": 800.0},
            {"id": "gain_15000_hz", "type": "ac_gain_db", "input_node": "vin", "output_node": "out", "frequency_hz": 15_000.0},
        ],
        "requirement_definitions": [
            {"id": "passband", "measurement_id": "gain_800_hz", "operator": ">=", "target": -100.0},
            {"id": "stopband", "measurement_id": "gain_15000_hz", "operator": "<=", "target": 100.0},
        ],
        "collection_name": "Regression",
        "run_by": "pytest",
        "notes": "",
    }
    experiment_id = tools.invoke("create_experiment", definition)["id"]

    tools.invoke("run_experiment", {"experiment_id": experiment_id})
    wait_for_execution(labs, experiment_id)
    run = tools.invoke("get_experiment_run", {"experiment_id": experiment_id, "run_index": 1})["run"]

    assert run["status"] == "COMPLETED"
    assert set(run["measurements"]) == {"gain_800_hz", "gain_15000_hz"}
    assert all(isinstance(value, float) for value in run["measurements"].values())
    assert [item["status"] for item in run["requirement_results"]] == ["PASS", "PASS"]


def test_webmcp_experiment_execution_controls_match_the_human_service(tmp_path) -> None:
    tools, labs = registry(tmp_path)
    simulator = BlockingSimulator()
    labs.simulator = simulator
    definition = {
        "name": "Controllable experiment",
        "description": "Exercise shared execution controls.",
        "experiment_type": "validation",
        "circuit_revision": 0,
        "variables": [{"component_id": "R1", "parameter": "resistance_ohm", "label": "R1 resistance", "unit": "Ω", "sweep": "explicit", "values": [1_000]}],
        "measurement_definitions": [{"id": "output_voltage", "type": "dc_voltage", "node": "out"}],
        "requirement_definitions": [],
        "collection_name": "",
        "run_by": "Test",
        "notes": "",
    }
    experiment = tools.invoke("create_experiment", definition)
    experiment_id = experiment["id"]
    tools.invoke("run_experiment", {"experiment_id": experiment_id, "wait_for_completion": False})
    assert simulator.started.wait(1)
    assert tools.invoke("pause_experiment", {"experiment_id": experiment_id})["execution_status"] == "paused"
    assert tools.invoke("resume_experiment", {"experiment_id": experiment_id})["execution_status"] == "running"
    assert tools.invoke("stop_experiment", {"experiment_id": experiment_id})["execution_status"] == "interrupted"
    simulator.release.set()
    wait_for_execution(labs, experiment_id)
    assert labs.repository.get_experiment(experiment_id).execution_status == "interrupted"


@pytest.mark.ngspice
@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_mock_agent_completes_required_tool_flow_and_stale_write_is_rejected(tmp_path) -> None:
    tools, labs = registry(tmp_path)

    circuit = tools.invoke("get_circuit", {})
    assert circuit.revision == 0

    added = tools.invoke(
        "add_component",
        {"type": "resistor", "params": {"resistance_ohm": 47_000}, "expected_revision": 0},
    )
    assert added["component"].id == "R2"
    node = tools.invoke("create_node", {"label": "Agent test node", "expected_revision": 1})
    assert node["node"].id == "n1"
    tools.invoke("connect", {"component_id": "R2", "pin": "a", "node_id": "n1", "expected_revision": 2})
    tools.invoke("connect", {"component_id": "R2", "pin": "b", "node_id": "gnd", "expected_revision": 3})
    assert tools.invoke("validate_circuit", {})["valid"] is True

    simulation = tools.invoke(
        "run_ac_analysis",
        {
            "start_hz": 10,
            "stop_hz": 100_000,
            "points_per_decade": 50,
            "input_node": "sensor",
            "output_node": "out",
            "current_components": ["R1"],
        },
    )
    assert "series" not in simulation
    assert simulation["success"] is True
    simulation_id = simulation["simulation_id"]

    gain = tools.invoke(
        "measure_gain",
        {"simulation_id": simulation_id, "input_node": "sensor", "output_node": "out", "frequency_hz": 500},
    )
    assert gain["gain_db"] < 0
    current = tools.invoke("measure_current", {"simulation_id": simulation_id, "component_id": "R1", "mode": "final"})
    assert current["current_a"] >= 0
    evaluation = tools.invoke("evaluate_constraints", {"simulation_ids": [simulation_id]})
    assert evaluation["evaluation"].all_pass is False
    with pytest.raises(CircuitError) as removed_legacy_tool:
        tools.invoke("save_experiment", {})
    assert removed_legacy_tool.value.code == "INVALID_PARAMETER"

    labs.set_parameter("C1", "capacitance_f", 110e-9, expected_revision=4)
    with pytest.raises(CircuitError) as stale:
        tools.invoke(
            "set_component_value",
            {"component_id": "R1", "parameter": "resistance_ohm", "value": 2_200, "expected_revision": 4},
        )
    assert stale.value.code == "STALE_REVISION"
