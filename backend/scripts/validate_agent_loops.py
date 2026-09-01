"""Repeatable WebMCP reliability rehearsal for the three challenge templates.

This is a test harness, not a production solver: it calls the same primitive
WebMCP operations available to an agent and never exposes a design endpoint.
It records whether each prescribed agent workflow reached a simulator-backed
constraint pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from time import perf_counter

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.repository import LabRepository
from app.services.challenge_catalog import debug_amplifier, filter_design, sensor_interface
from app.services.lab_service import LabService
from app.webmcp.tools import WebMCPToolRegistry


@dataclass(frozen=True)
class LoopRecord:
    challenge_id: str
    passed: bool
    simulations_run: int
    invalid_actions: int
    simulator_failures: int
    elapsed_ms: float


def _revision(tools: WebMCPToolRegistry) -> int:
    return tools.invoke("get_circuit", {}).revision  # type: ignore[union-attr]


def _call(tools: WebMCPToolRegistry, name: str, arguments: dict[str, object]) -> object:
    return tools.invoke(name, arguments)


def _add(tools: WebMCPToolRegistry, component_type: str, params: dict[str, object]):
    result = _call(tools, "add_component", {"type": component_type, "params": params, "expected_revision": _revision(tools)})
    return result["component"]  # type: ignore[index]


def _node(tools: WebMCPToolRegistry, label: str):
    result = _call(tools, "create_node", {"label": label, "expected_revision": _revision(tools)})
    return result["node"]  # type: ignore[index]


def _connect(tools: WebMCPToolRegistry, component_id: str, pin: str, node_id: str) -> None:
    _call(tools, "connect", {"component_id": component_id, "pin": pin, "node_id": node_id, "expected_revision": _revision(tools)})


def _set(tools: WebMCPToolRegistry, component_id: str, parameter: str, value: object) -> None:
    _call(tools, "set_component_value", {"component_id": component_id, "parameter": parameter, "value": value, "expected_revision": _revision(tools)})


def _prepare_filter(tools: WebMCPToolRegistry) -> tuple[str, list[str]]:
    stage = _node(tools, "Filter stage").id
    _connect(tools, "R1", "b", stage)
    _connect(tools, "C1", "a", stage)
    _set(tools, "R1", "resistance_ohm", 100)
    _set(tools, "C1", "capacitance_f", 1e-6)
    resistor = _add(tools, "resistor", {"resistance_ohm": 10_000})
    _connect(tools, resistor.id, "a", stage)
    _connect(tools, resistor.id, "b", "out")
    capacitor = _add(tools, "capacitor", {"capacitance_f": 10e-9})
    _connect(tools, capacitor.id, "a", "out")
    _connect(tools, capacitor.id, "b", "gnd")
    ac = _call(tools, "run_ac_analysis", {"start_hz": 10, "stop_hz": 100_000, "points_per_decade": 100, "input_node": "vin", "output_node": "out"})
    return "Filter response is inside both passband and rejection limits.", [ac["simulation_id"]]  # type: ignore[index]


def _prepare_sensor(tools: WebMCPToolRegistry) -> tuple[str, list[str]]:
    filtered = _node(tools, "Filtered sensor").id
    feedback = _node(tools, "Feedback").id
    _connect(tools, "R1", "b", filtered)
    _connect(tools, "C1", "a", filtered)
    _set(tools, "R1", "resistance_ohm", 1_000)
    _set(tools, "C1", "capacitance_f", 560e-9)
    opamp = _add(tools, "ideal_opamp", {"gain": 100_000})
    _connect(tools, opamp.id, "plus", filtered)
    _connect(tools, opamp.id, "minus", feedback)
    _connect(tools, opamp.id, "out", "out")
    ground_resistor = _add(tools, "resistor", {"resistance_ohm": 1_000})
    _connect(tools, ground_resistor.id, "a", feedback)
    _connect(tools, ground_resistor.id, "b", "gnd")
    feedback_resistor = _add(tools, "resistor", {"resistance_ohm": 9_000})
    _connect(tools, feedback_resistor.id, "a", "out")
    _connect(tools, feedback_resistor.id, "b", feedback)
    ac = _call(tools, "run_ac_analysis", {"start_hz": 10, "stop_hz": 100_000, "points_per_decade": 100, "input_node": "sensor", "output_node": "out"})
    transient = _call(tools, "run_transient", {"duration_s": 0.05, "time_step_s": 0.00001, "output_nodes": ["out"]})
    return "Filtered non-inverting stage meets gain, noise rejection, ADC range, and response limits.", [ac["simulation_id"], transient["simulation_id"]]  # type: ignore[index]


def _prepare_debug(tools: WebMCPToolRegistry) -> tuple[str, list[str]]:
    _set(tools, "R2", "resistance_ohm", 9_000)
    ac = _call(tools, "run_ac_analysis", {"start_hz": 10, "stop_hz": 100_000, "points_per_decade": 100, "input_node": "vin", "output_node": "out"})
    transient = _call(tools, "run_transient", {"duration_s": 0.05, "time_step_s": 0.00001, "output_nodes": ["out"]})
    return "Reducing feedback resistance restores roughly 10x gain without an over-range output.", [ac["simulation_id"], transient["simulation_id"]]  # type: ignore[index]


def rehearse(challenge_id: str, database_path: Path) -> LoopRecord:
    factories = {"challenge_filter_01": filter_design, "challenge_sensor_01": sensor_interface, "challenge_debug_01": debug_amplifier}
    starters = {"challenge_filter_01": _prepare_filter, "challenge_sensor_01": _prepare_sensor, "challenge_debug_01": _prepare_debug}
    challenge, circuit = factories[challenge_id]()
    repository = LabRepository(database_path)
    repository.initialize(challenge, circuit)
    labs = LabService(repository)
    tools = WebMCPToolRegistry(labs)
    started = perf_counter()
    _conclusion, simulation_ids = starters[challenge_id](tools)
    evaluation = _call(tools, "evaluate_constraints", {"simulation_ids": simulation_ids})
    passed = evaluation["evaluation"].all_pass  # type: ignore[index]
    return LoopRecord(
        challenge_id=challenge_id,
        passed=passed,
        simulations_run=len(simulation_ids),
        invalid_actions=0,
        simulator_failures=0,
        elapsed_ms=(perf_counter() - started) * 1_000,
    )


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        for challenge in ("challenge_filter_01", "challenge_sensor_01", "challenge_debug_01"):
            report = rehearse(challenge, Path(directory) / f"{challenge}.db")
            print(report)
