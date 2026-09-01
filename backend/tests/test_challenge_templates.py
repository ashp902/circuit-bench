from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.circuit import Circuit, Component, ComponentType, Node
from app.services.challenge_catalog import debug_amplifier, filter_design, sensor_interface
from app.services.netlist_service import AcAnalysis, TransientAnalysis


pytestmark = [pytest.mark.ngspice, pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")]


def _filter_solution() -> Circuit:
    challenge, _ = filter_design()
    return Circuit(
        id="known_filter_solution",
        name="Known two-pole passive filter",
        nodes=[Node(id="gnd", label="Ground"), Node(id="vin", label="Input"), Node(id="n1", label="Filter stage"), Node(id="out", label="Output")],
        components=[
            Component(id="V1", type=ComponentType.VOLTAGE_SOURCE, params={"mode": "dc", "voltage_v": 0}, pins={"positive": "vin", "negative": "gnd"}),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 100}, pins={"a": "vin", "b": "n1"}),
            Component(id="C1", type=ComponentType.CAPACITOR, params={"capacitance_f": 1e-6}, pins={"a": "n1", "b": "gnd"}),
            Component(id="R2", type=ComponentType.RESISTOR, params={"resistance_ohm": 10_000}, pins={"a": "n1", "b": "out"}),
            Component(id="C2", type=ComponentType.CAPACITOR, params={"capacitance_f": 10e-9}, pins={"a": "out", "b": "gnd"}),
        ],
        metadata={"input_node": "vin", "output_node": "out"},
    )


def _sensor_solution() -> Circuit:
    return Circuit(
        id="known_sensor_solution",
        name="Known sensor interface",
        nodes=[Node(id="gnd", label="Ground"), Node(id="sensor", label="Sensor"), Node(id="filt", label="Filtered signal"), Node(id="minus", label="Feedback"), Node(id="out", label="ADC output")],
        components=[
            Component(id="V1", type=ComponentType.VOLTAGE_SOURCE, params={"mode": "sine", "offset_v": 0, "amplitude_v": 0.1, "frequency_hz": 10}, pins={"positive": "sensor", "negative": "gnd"}),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "sensor", "b": "filt"}),
            Component(id="C1", type=ComponentType.CAPACITOR, params={"capacitance_f": 560e-9}, pins={"a": "filt", "b": "gnd"}),
            Component(id="U1", type=ComponentType.IDEAL_OPAMP, params={"gain": 100_000}, pins={"plus": "filt", "minus": "minus", "out": "out"}),
            Component(id="R2", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "minus", "b": "gnd"}),
            Component(id="R3", type=ComponentType.RESISTOR, params={"resistance_ohm": 9_000}, pins={"a": "out", "b": "minus"}),
        ],
        metadata={"input_node": "sensor", "output_node": "out"},
    )


def _debug_solution() -> Circuit:
    _, starting = debug_amplifier()
    known = starting.model_copy(deep=True)
    next(component for component in known.components if component.id == "R2").params["resistance_ohm"] = 9_000
    known.id = "known_debug_solution"
    known.name = "Known repaired amplifier"
    return known


@pytest.mark.parametrize(
    ("factory", "solution_factory", "needs_transient"),
    [(filter_design, _filter_solution, False), (sensor_interface, _sensor_solution, True), (debug_amplifier, _debug_solution, True)],
)
def test_every_public_template_has_a_real_ngspice_valid_solution(tmp_path, factory, solution_factory, needs_transient) -> None:
    application = create_app(tmp_path / "templates.db")
    service = application.state.lab_service
    challenge, _ = factory()
    service.reset(challenge, solution_factory())
    circuit = service.repository.get_circuit()
    ac = service.run_ac(AcAnalysis(10, 100_000, 100, circuit.metadata["input_node"], circuit.metadata["output_node"]))
    simulation_ids = [ac.simulation_id]
    if needs_transient:
        transient = service.run_transient(TransientAnalysis(0.05, 0.00001, (circuit.metadata["output_node"],)))
        simulation_ids.append(transient.simulation_id)
    _, evaluation = service.evaluate(simulation_ids)
    assert evaluation.all_pass, evaluation.results


def test_catalog_exposes_exactly_three_starting_templates(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "catalog.db"))
    templates = client.get("/api/challenges")
    assert templates.status_code == 200
    assert [template["id"] for template in templates.json()] == ["challenge_filter_01", "challenge_sensor_01", "challenge_debug_01"]
    loaded = client.post("/api/challenges/challenge_debug_01/load", json={})
    assert loaded.status_code == 200
    assert loaded.json()["challenge"]["title"] == "Debug Amplifier"
    assert loaded.json()["circuit"]["name"] == "Debug Amplifier — excessive feedback gain"
