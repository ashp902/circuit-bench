from __future__ import annotations

import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


pytestmark = [pytest.mark.ngspice, pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")]


def test_api_only_experiment_flow_persists_and_restores(tmp_path) -> None:
    database_path = tmp_path / "integration.db"
    client = TestClient(create_app(database_path))

    reset = client.post("/api/challenges/challenge_filter_01/load", json={})
    assert reset.status_code == 200
    assert "remaining_experiments" not in reset.json()

    edited = client.patch(
        "/api/components/C1",
        json={"parameter": "capacitance_f", "value": 110e-9, "expected_revision": 0},
    )
    assert edited.status_code == 200
    assert edited.json()["revision"] == 1

    validation = client.post("/api/validate")
    assert validation.json() == {"valid": True, "issues": []}

    simulation = client.post(
        "/api/simulations/ac",
        json={
            "start_hz": 10,
            "stop_hz": 100_000,
            "points_per_decade": 100,
            "input_node": "vin",
            "output_node": "out",
        },
    )
    assert simulation.status_code == 200
    simulation_body = simulation.json()
    assert simulation_body["success"] is True
    simulation_id = simulation_body["simulation_id"]
    second_simulation = client.post(
        "/api/simulations/ac",
        json={
            "start_hz": 10,
            "stop_hz": 100_000,
            "points_per_decade": 100,
            "input_node": "vin",
            "output_node": "out",
        },
    )
    assert second_simulation.status_code == 200

    evaluation = client.post("/api/constraints/evaluate", json={"simulation_ids": [simulation_id]})
    assert evaluation.status_code == 200
    assert evaluation.json()["evaluation"]["all_pass"] is False
    assert evaluation.json()["measurements"]["gain_db_at_500hz"] == pytest.approx(-0.46, abs=0.08)

    saved = client.post(
        "/api/experiments",
        json={
            "hypothesis": "A slightly larger capacitor should keep cutoff inside the target band.",
            "conclusion": "The measured cutoff is inside the required band.",
            "simulation_ids": [simulation_id],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["id"] == "exp_001"

    changed_again = client.patch(
        "/api/components/C1",
        json={"parameter": "capacitance_f", "value": 220e-9, "expected_revision": 1},
    )
    assert changed_again.json()["revision"] == 2

    restored = client.post("/api/experiments/exp_001/restore", json={"expected_revision": 2})
    assert restored.status_code == 200
    restored_body = restored.json()
    assert restored_body["revision"] == 3
    restored_capacitor = next(component for component in restored_body["components"] if component["id"] == "C1")
    assert restored_capacitor["params"]["capacitance_f"] == pytest.approx(110e-9)
    assert len(client.get("/api/experiments").json()) == 1

    stale = client.patch(
        "/api/components/C1",
        json={"parameter": "capacitance_f", "value": 100e-9, "expected_revision": 2},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_REVISION"

    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"labs", "circuits", "simulations", "experiments"}.issubset(tables)


def test_blank_circuit_can_be_built_and_simulated(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "blank.db"))

    created = client.post("/api/circuits/blank", json={"name": "Scratch RC"})
    assert created.status_code == 200
    assert created.json()["circuit"]["name"] == "Scratch RC"
    assert created.json()["circuit"]["components"] == []
    assert set(created.json()["challenge"]["allowed_components"]) == {"ground", "resistor", "capacitor", "inductor", "voltage_source", "diode", "ideal_opamp"}

    revision = 0
    for component_type, params in [("voltage_source", {"mode": "dc", "voltage_v": 1}), ("resistor", {"resistance_ohm": 1_000}), ("capacitor", {"capacitance_f": 100e-9})]:
        response = client.post("/api/components", json={"type": component_type, "params": params, "expected_revision": revision})
        assert response.status_code == 200
        revision = response.json()["revision"]
    for source_id, source_pin, target_id, target_pin in [("V1", "positive", "R1", "a"), ("R1", "b", "C1", "a")]:
        response = client.post("/api/connections/pins", json={"source_component_id": source_id, "source_pin": source_pin, "target_component_id": target_id, "target_pin": target_pin, "expected_revision": revision})
        assert response.status_code == 200
        revision = response.json()["revision"]
    for component_id, pin in [("V1", "negative"), ("C1", "b")]:
        response = client.post("/api/connections", json={"component_id": component_id, "pin": pin, "node_id": "gnd", "expected_revision": revision})
        assert response.status_code == 200
        revision = response.json()["revision"]

    output_node = next(node for node in response.json()["nodes"] if node["label"] == "N002")
    renamed = client.patch(f"/api/nodes/{output_node['id']}", json={"label": "VOUT", "expected_revision": revision})
    assert renamed.status_code == 200
    revision = renamed.json()["revision"]

    assert client.post("/api/validate").json()["valid"] is True
    nodes = {node["label"]: node["id"] for node in renamed.json()["nodes"]}
    simulation = client.post("/api/simulations/ac", json={"start_hz": 10, "stop_hz": 100_000, "points_per_decade": 50, "input_node": nodes["N001"], "output_node": nodes["VOUT"]})
    assert simulation.status_code == 200
    assert simulation.json()["success"] is True


def test_new_circuits_are_named_sequentially_only_when_needed(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "names.db"))

    landing = client.get("/api/lab").json()
    assert landing["circuit"]["name"] == "Untitled Circuit"
    assert landing["circuit"]["components"] == []
    assert landing["active_saved_circuit_id"] is None

    first = client.post("/api/circuits/blank", json={})
    second = client.post("/api/circuits/blank", json={})
    third = client.post("/api/circuits/blank", json={})

    assert [response.json()["circuit"]["name"] for response in [first, second, third]] == ["New Circuit", "New Circuit 1", "New Circuit 2"]


def test_component_and_node_endpoints_share_canonical_revision(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "mutations.db"))

    node = client.post("/api/nodes", json={"label": "Aux", "expected_revision": 0})
    assert node.status_code == 200
    assert node.json()["revision"] == 1
    node_id = node.json()["nodes"][-1]["id"]

    component = client.post(
        "/api/components",
        json={"type": "resistor", "params": {"resistance_ohm": 4_700}, "expected_revision": 1},
    )
    assert component.status_code == 200
    assert component.json()["revision"] == 2
    component_id = component.json()["components"][-1]["id"]

    connected = client.post(
        "/api/connections",
        json={"component_id": component_id, "pin": "a", "node_id": node_id, "expected_revision": 2},
    )
    assert connected.status_code == 200
    assert connected.json()["revision"] == 3
    assert client.get("/api/circuit").json()["revision"] == 3


def test_circuit_restore_creates_a_new_revision_for_undo(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "undo.db"))
    original = client.get("/api/circuit").json()

    changed = client.post("/api/components", json={"type": "resistor", "params": {"resistance_ohm": 220}, "expected_revision": 0})
    assert changed.status_code == 200

    restored = client.post("/api/circuit/restore", json={"circuit": original, "expected_revision": 1})
    assert restored.status_code == 200
    assert restored.json()["revision"] == 2
    assert restored.json()["components"] == []


def test_component_layout_survives_save_and_reopen(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "layout.db"))
    created = client.post("/api/circuits/blank", json={}).json()
    circuit_id = created["active_saved_circuit_id"]
    added = client.post(
        "/api/components",
        json={"type": "resistor", "params": {"resistance_ohm": 1_000}, "position": {"x": 176, "y": 240}, "expected_revision": 0},
    ).json()
    laid_out = client.patch(
        "/api/components/R1/layout",
        json={"position": {"x": 512, "y": 304}, "rotation": 90, "expected_revision": added["revision"]},
    )
    assert laid_out.status_code == 200

    client.post("/api/circuits/blank", json={})
    reopened = client.post(f"/api/circuits/{circuit_id}/open", json={}).json()
    resistor = next(component for component in reopened["circuit"]["components"] if component["id"] == "R1")
    assert resistor["position"] == {"x": 512.0, "y": 304.0}
    assert resistor["rotation"] == 90


def test_auto_layout_endpoint_rearranges_components_and_clears_manual_locks(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "auto-layout.db"))
    client.post("/api/circuits/blank", json={})
    first = client.post(
        "/api/components",
        json={"type": "resistor", "params": {"resistance_ohm": 1_000}, "position": {"x": 720, "y": 112}, "expected_revision": 0},
    ).json()
    second = client.post(
        "/api/components",
        json={"type": "capacitor", "params": {"capacitance_f": 100e-9}, "expected_revision": first["revision"]},
    ).json()

    response = client.post(
        "/api/circuit/auto-layout",
        json={"expected_revision": second["revision"], "preserve_manual": False},
    )

    assert response.status_code == 200
    assert response.json()["revision"] == second["revision"] + 1
    assert all(item["layout_locked"] is False for item in response.json()["components"])
    assert len({(item["position"]["x"], item["position"]["y"]) for item in response.json()["components"]}) == len(response.json()["components"])


def test_experiment_restore_recovers_recorded_layout(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "experiment-layout.db"))
    client.post("/api/circuits/blank", json={})
    added = client.post(
        "/api/components",
        json={"type": "resistor", "params": {"resistance_ohm": 1_000}, "position": {"x": 208, "y": 224}, "expected_revision": 0},
    ).json()
    recorded = client.patch(
        "/api/components/R1/layout",
        json={"position": {"x": 464, "y": 288}, "rotation": 270, "expected_revision": added["revision"]},
    ).json()
    experiment = client.post(
        "/api/experiment-definitions",
        json={"name": "Layout snapshot", "circuit_revision": recorded["revision"]},
    ).json()
    changed = client.patch(
        "/api/components/R1/layout",
        json={"position": {"x": 640, "y": 400}, "rotation": 0, "expected_revision": recorded["revision"]},
    ).json()

    restored = client.post(f"/api/experiments/{experiment['id']}/restore", json={"expected_revision": changed["revision"]}).json()
    resistor = next(component for component in restored["components"] if component["id"] == "R1")
    assert resistor["position"] == {"x": 464.0, "y": 288.0}
    assert resistor["rotation"] == 270
