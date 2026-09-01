"""The three public challenge starting states.

Known-good circuits deliberately live in tests, never in this catalog or a
production endpoint.  The catalog only contains what a human or an agent is
allowed to inspect and edit.
"""

from __future__ import annotations

from app.models.circuit import Challenge, Circuit, Component, ComponentType, Constraint, Node


ALL_MVP_COMPONENTS = {
    ComponentType.RESISTOR,
    ComponentType.CAPACITOR,
    ComponentType.INDUCTOR,
    ComponentType.VOLTAGE_SOURCE,
    ComponentType.DIODE,
    ComponentType.IDEAL_OPAMP,
    ComponentType.GROUND,
}


def _nodes(*values: tuple[str, str]) -> list[Node]:
    return [Node(id=node_id, label=label) for node_id, label in values]


def filter_design() -> tuple[Challenge, Circuit]:
    challenge = Challenge(
        id="challenge_filter_01",
        title="Filter Design",
        description="Pass the useful 500 Hz band while strongly rejecting 10 kHz noise. Keep it to six components and ten real simulations.",
        component_limit=6,
        allowed_components={ComponentType.RESISTOR, ComponentType.CAPACITOR, ComponentType.VOLTAGE_SOURCE, ComponentType.GROUND},
        constraints=[
            Constraint(id="passband", metric="gain_db_at_500hz", operator=">=", target=-1),
            Constraint(id="noise_rejection", metric="gain_db_at_10000hz", operator="<=", target=-30),
        ],
    )
    circuit = Circuit(
        id="ckt_filter_01",
        name="Filter Design — starting point",
        nodes=_nodes(("gnd", "Ground"), ("vin", "Input"), ("out", "Output")),
        components=[
            Component(id="V1", type=ComponentType.VOLTAGE_SOURCE, params={"mode": "dc", "voltage_v": 0}, pins={"positive": "vin", "negative": "gnd"}),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "vin", "b": "out"}),
            Component(id="C1", type=ComponentType.CAPACITOR, params={"capacitance_f": 100e-9}, pins={"a": "out", "b": "gnd"}),
        ],
        metadata={"input_node": "vin", "output_node": "out", "prompt": "Design the simplest circuit you can that loses less than 1 dB at 500 Hz and attenuates 10 kHz by at least 30 dB."},
    )
    return challenge, circuit


def sensor_interface() -> tuple[Challenge, Circuit]:
    challenge = Challenge(
        id="challenge_sensor_01",
        title="Sensor Interface",
        description="Make a weak, noisy 10 Hz sensor signal useful and safe for a 3.3 V ADC. Preserve low-frequency gain, reject 10 kHz noise, and stay within ten components.",
        component_limit=10,
        allowed_components=ALL_MVP_COMPONENTS,
        constraints=[
            Constraint(id="useful_gain", metric="gain_db_at_10hz", operator=">=", target=19),
            Constraint(id="hf_rejection", metric="gain_db_at_10000hz", operator="<=", target=-10),
            Constraint(id="adc_safe", metric="max_output_voltage_v", operator="<=", target=3.3),
            Constraint(id="response", metric="rise_time_s", operator="<=", target=0.025),
        ],
    )
    circuit = Circuit(
        id="ckt_sensor_01",
        name="Sensor Interface — starting point",
        nodes=_nodes(("gnd", "Ground"), ("sensor", "Sensor"), ("out", "ADC output")),
        components=[
            Component(id="V1", type=ComponentType.VOLTAGE_SOURCE, params={"mode": "sine", "offset_v": 0, "amplitude_v": 0.1, "frequency_hz": 10}, pins={"positive": "sensor", "negative": "gnd"}),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 10_000}, pins={"a": "sensor", "b": "out"}),
            Component(id="C1", type=ComponentType.CAPACITOR, params={"capacitance_f": 100e-9}, pins={"a": "out", "b": "gnd"}),
        ],
        metadata={"input_node": "sensor", "output_node": "out", "prompt": "Make this sensor signal safe and useful for the 3.3 V ADC. Keep the useful slow signal, reduce high-frequency noise, and use no more than ten components."},
    )
    return challenge, circuit


def debug_amplifier() -> tuple[Challenge, Circuit]:
    challenge = Challenge(
        id="challenge_debug_01",
        title="Debug Amplifier",
        description="This non-inverting amplifier produces too much output from a 100 mV input. Diagnose the gain error and repair it without losing useful amplification.",
        component_limit=7,
        allowed_components=ALL_MVP_COMPONENTS,
        constraints=[
            Constraint(id="minimum_gain", metric="gain_db_at_10hz", operator=">=", target=18),
            Constraint(id="output_range", metric="max_output_voltage_v", operator="<=", target=1.5),
        ],
    )
    circuit = Circuit(
        id="ckt_debug_01",
        name="Debug Amplifier — excessive feedback gain",
        nodes=_nodes(("gnd", "Ground"), ("vin", "100 mV input"), ("minus", "Feedback"), ("out", "Output")),
        components=[
            Component(id="V1", type=ComponentType.VOLTAGE_SOURCE, params={"mode": "sine", "offset_v": 0, "amplitude_v": 0.1, "frequency_hz": 10}, pins={"positive": "vin", "negative": "gnd"}),
            Component(id="U1", type=ComponentType.IDEAL_OPAMP, params={"gain": 100_000}, pins={"plus": "vin", "minus": "minus", "out": "out"}),
            Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000}, pins={"a": "minus", "b": "gnd"}),
            Component(id="R2", type=ComponentType.RESISTOR, params={"resistance_ohm": 39_000}, pins={"a": "out", "b": "minus"}),
        ],
        metadata={"input_node": "vin", "output_node": "out", "prompt": "This amplifier should produce about 1 V from a 100 mV input, but the output is over range. Find the cause and fix it without reducing gain below 8."},
    )
    return challenge, circuit


_FACTORIES = {"challenge_filter_01": filter_design, "challenge_sensor_01": sensor_interface, "challenge_debug_01": debug_amplifier}


def list_challenges() -> list[Challenge]:
    return [factory()[0] for factory in _FACTORIES.values()]


def load_challenge(challenge_id: str) -> tuple[Challenge, Circuit] | None:
    factory = _FACTORIES.get(challenge_id)
    return factory() if factory else None


def blank_circuit(name: str = "Untitled Circuit") -> tuple[Challenge, Circuit]:
    """Create the same unconstrained blank lab for the human UI and WebMCP."""
    title = name.strip() or "Untitled Circuit"
    challenge = Challenge(
        id="custom_blank",
        title=title,
        description="Build a circuit from scratch, then validate and simulate it.",
        component_limit=1_000,
        allowed_components=ALL_MVP_COMPONENTS,
        constraints=[],
    )
    circuit = Circuit(
        id="ckt_custom_blank",
        name=title,
        nodes=_nodes(("gnd", "Ground")),
        metadata={},
    )
    return challenge, circuit
