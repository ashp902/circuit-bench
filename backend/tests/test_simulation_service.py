from __future__ import annotations

import math
import shutil

import pytest

from app.models.circuit import Circuit, Component, ComponentType, Node
from app.services.netlist_service import AcAnalysis, NetlistService, TransientAnalysis
from app.services.simulation_service import NgspiceSimulator


pytestmark = [pytest.mark.ngspice, pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")]


def divider_circuit() -> Circuit:
    return Circuit(
        id="ckt_divider",
        revision=3,
        name="Voltage divider",
        nodes=[Node(id="gnd", label="Ground"), Node(id="vin", label="Input"), Node(id="out", label="Output")],
        components=[
            Component(
                id="V1",
                type=ComponentType.VOLTAGE_SOURCE,
                params={"mode": "dc", "voltage_v": 5},
                pins={"positive": "vin", "negative": "gnd"},
            ),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "vin", "b": "out"}),
            Component(id="R2", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "out", "b": "gnd"}),
        ],
    )


def rc_circuit(*, pulse: bool, capacitance_f: float) -> Circuit:
    source_params: dict[str, float | str] = {"mode": "dc", "voltage_v": 0}
    if pulse:
        source_params = {
            "mode": "pulse",
            "initial_v": 0,
            "pulsed_v": 1,
            "delay_s": 0,
            "rise_time_s": 1e-6,
            "fall_time_s": 1e-6,
            "pulse_width_s": 0.1,
            "period_s": 0.2,
        }
    return Circuit(
        id="ckt_rc",
        revision=4,
        name="RC low pass",
        nodes=[Node(id="gnd", label="Ground"), Node(id="vin", label="Input"), Node(id="out", label="Output")],
        components=[
            Component(id="V1", type=ComponentType.VOLTAGE_SOURCE, params=source_params, pins={"positive": "vin", "negative": "gnd"}),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "vin", "b": "out"}),
            Component(id="C1", type=ComponentType.CAPACITOR, params={"capacitance_f": capacitance_f}, pins={"a": "out", "b": "gnd"}),
        ],
        metadata={"input_node": "vin", "output_node": "out"},
    )


def simulator() -> NgspiceSimulator:
    return NgspiceSimulator(simulation_id_factory=lambda: "sim_test")


def test_netlist_is_deterministic_and_maps_ground_to_zero() -> None:
    generated = NetlistService().build_operating_point(divider_circuit(), ["out"])

    assert "V1 vin 0 DC 5 AC 1" in generated
    assert generated.index("R1 vin out 1000") < generated.index("R2 out 0 1000")
    assert generated.endswith(".end\n")


def test_operating_point_from_circuit_json_returns_divider_voltage() -> None:
    result = simulator().run_operating_point(divider_circuit(), ["out"])

    assert result.success is True
    assert result.simulation_id == "sim_test"
    assert result.measurements["voltage_v:out"] == pytest.approx(2.5, abs=0.01)


def test_operating_point_records_actual_ngspice_branch_current() -> None:
    result = simulator().run_operating_point(divider_circuit(), ["out"], ["R1"])

    assert result.success is True
    assert result.measurements["current_a:R1"] == pytest.approx(0.0025, abs=1e-6)


def test_ac_analysis_from_circuit_json_finds_expected_rc_cutoff() -> None:
    analysis = AcAnalysis(start_hz=10, stop_hz=100_000, points_per_decade=100, input_node="vin", output_node="out")

    result = simulator().run_ac(rc_circuit(pulse=False, capacitance_f=100e-9), analysis)

    assert result.success is True
    gains = result.series["output_gain_db"]
    frequencies = result.series["frequency_hz"]
    cutoff_index = min(range(len(gains)), key=lambda index: abs(gains[index] + 3.0103))
    assert frequencies[cutoff_index] == pytest.approx(1_591.5, rel=0.03)
    assert gains[0] == pytest.approx(0, abs=0.05)
    assert result.series["output_phase_deg"][cutoff_index] == pytest.approx(-45, abs=2)
    assert result.series["output_phase_deg"][0] == pytest.approx(0, abs=1)
    assert result.series["output_phase_deg"][-1] < -80


def test_transient_analysis_from_circuit_json_has_positive_rise_time() -> None:
    analysis = TransientAnalysis(duration_s=0.01, time_step_s=10e-6, output_nodes=("out",))

    result = simulator().run_transient(rc_circuit(pulse=True, capacitance_f=1e-6), analysis)

    assert result.success is True
    times = result.series["time_s"]
    output = result.series["voltage_v:out"]
    time_10 = next(time for time, value in zip(times, output) if value >= 0.1)
    time_90 = next(time for time, value in zip(times, output) if value >= 0.9)
    assert math.isfinite(time_90 - time_10)
    assert time_90 - time_10 > 0
    assert output[-1] > 0.99
