from __future__ import annotations

import shutil

import pytest

from app.models.circuit import Circuit, Component, ComponentType, Constraint, Node, SimulationResult
from app.services.constraint_service import ConstraintService
from app.services.errors import CircuitError
from app.services.measurement_service import MeasurementService
from app.services.netlist_service import AcAnalysis
from app.services.simulation_service import NgspiceSimulator


def ac_result() -> SimulationResult:
    return SimulationResult(
        success=True,
        analysis="ac",
        circuit_revision=1,
        simulation_id="sim_ac",
        series={"frequency_hz": [100, 1_000, 2_000, 10_000], "output_gain_db": [0, -2, -4, -20]},
    )


def transient_result() -> SimulationResult:
    return SimulationResult(
        success=True,
        analysis="transient",
        circuit_revision=1,
        simulation_id="sim_tran",
        series={"time_s": [0, 1, 2, 3, 4, 5], "voltage_v:out": [0, 0.1, 0.5, 0.9, 1.05, 1]},
    )


def test_measures_dc_max_min_and_final_voltage() -> None:
    measurements = MeasurementService()
    operating_point = SimulationResult(
        success=True,
        analysis="operating_point",
        circuit_revision=1,
        simulation_id="sim_op",
        measurements={"voltage_v:out": 2.5},
    )

    assert measurements.measure_voltage(operating_point, "out", "dc") == 2.5
    assert measurements.measure_voltage(transient_result(), "out", "max") == 1.05
    assert measurements.measure_voltage(transient_result(), "out", "min") == 0
    assert measurements.measure_voltage(transient_result(), "out", "final") == 1


def test_interpolates_gain_at_requested_frequency() -> None:
    gain = MeasurementService().measure_gain(ac_result(), 1_500)

    assert gain == pytest.approx(-3.0)


def test_finds_first_minus_three_db_cutoff() -> None:
    cutoff = MeasurementService().measure_cutoff_frequency(ac_result())

    assert cutoff == pytest.approx(1_500)


def test_returns_none_when_cutoff_is_absent() -> None:
    result = ac_result().model_copy(update={"series": {"frequency_hz": [10, 100, 1_000], "output_gain_db": [0, -0.1, -0.5]}})

    assert MeasurementService().measure_cutoff_frequency(result) is None


def test_measures_rise_time_and_overshoot() -> None:
    measurements = MeasurementService()

    assert measurements.measure_rise_time(transient_result(), "out") == pytest.approx(2.0)
    assert measurements.measure_overshoot(transient_result(), "out") == pytest.approx(5.0)


def test_rejects_measurement_from_wrong_analysis() -> None:
    with pytest.raises(CircuitError) as error:
        MeasurementService().measure_gain(transient_result(), 1_000)

    assert error.value.code == "MEASUREMENT_UNAVAILABLE"


@pytest.mark.ngspice
@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_real_rc_simulation_measures_expected_cutoff() -> None:
    circuit = Circuit(
        id="ckt_rc_measurement",
        name="RC measurement",
        nodes=[Node(id="gnd", label="Ground"), Node(id="vin", label="Input"), Node(id="out", label="Output")],
        components=[
            Component(
                id="V1",
                type=ComponentType.VOLTAGE_SOURCE,
                params={"mode": "dc", "voltage_v": 0},
                pins={"positive": "vin", "negative": "gnd"},
            ),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "vin", "b": "out"}),
            Component(id="C1", type=ComponentType.CAPACITOR, params={"capacitance_f": 100e-9}, pins={"a": "out", "b": "gnd"}),
        ],
    )
    simulation = NgspiceSimulator(simulation_id_factory=lambda: "sim_rc").run_ac(
        circuit,
        AcAnalysis(start_hz=10, stop_hz=100_000, points_per_decade=100, input_node="vin", output_node="out"),
    )

    cutoff = MeasurementService().measure_cutoff_frequency(simulation)
    assert cutoff == pytest.approx(1_591.5, rel=0.01)
    assert cutoff is not None

    evaluation = ConstraintService().evaluate(
        [
            Constraint(id="expected_band", metric="cutoff_frequency_hz", operator="between", target=(1_400, 1_800)),
            Constraint(id="too_slow", metric="cutoff_frequency_hz", operator="<=", target=500),
        ],
        {"cutoff_frequency_hz": cutoff},
    )
    assert [result.status for result in evaluation.results] == ["PASS", "FAIL"]
