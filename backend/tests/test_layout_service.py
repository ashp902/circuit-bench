from app.models.circuit import Circuit, Component, ComponentType, Node, Position
from app.services.layout_service import arrange_circuit


def component(identifier: str, kind: ComponentType, pins: dict[str, str | None], *, locked: bool = False, position: Position | None = None) -> Component:
    params = {
        ComponentType.RESISTOR: {"resistance_ohm": 1_000.0},
        ComponentType.CAPACITOR: {"capacitance_f": 100e-9},
        ComponentType.VOLTAGE_SOURCE: {"mode": "dc", "voltage_v": 1.0},
        ComponentType.IDEAL_OPAMP: {"gain": 100_000.0},
        ComponentType.GROUND: {},
    }[kind]
    return Component(id=identifier, type=kind, params=params, pins=pins, position=position, layout_locked=locked)


def test_rc_low_pass_is_arranged_as_a_readable_signal_path() -> None:
    circuit = Circuit(
        id="rc",
        name="RC low-pass",
        nodes=[Node(id="gnd", label="GND"), Node(id="vin", label="VIN"), Node(id="vout", label="VOUT")],
        metadata={"input_node": "vin", "output_node": "vout"},
        components=[
            component("G1", ComponentType.GROUND, {}),
            component("V1", ComponentType.VOLTAGE_SOURCE, {"positive": "vin", "negative": "gnd"}),
            component("R1", ComponentType.RESISTOR, {"a": "vin", "b": "vout"}),
            component("C1", ComponentType.CAPACITOR, {"a": "vout", "b": "gnd"}),
        ],
    )

    arranged = arrange_circuit(circuit, preserve_manual=False)
    by_id = {item.id: item for item in arranged.components}

    assert by_id["V1"].position.x < by_id["R1"].position.x < by_id["C1"].position.x
    assert by_id["V1"].position.y == by_id["R1"].position.y
    assert by_id["C1"].position.y > by_id["R1"].position.y
    assert by_id["C1"].rotation == 0
    assert len({(item.position.x, item.position.y) for item in arranged.components}) == 4


def test_two_stage_filter_staggers_shunts_below_their_signal_nodes() -> None:
    circuit = Circuit(
        id="two_stage",
        name="Two-stage filter",
        nodes=[Node(id="gnd", label="GND"), Node(id="vin", label="VIN"), Node(id="n1", label="N1"), Node(id="vout", label="VOUT")],
        metadata={"input_node": "vin", "output_node": "vout"},
        components=[
            component("V1", ComponentType.VOLTAGE_SOURCE, {"positive": "vin", "negative": "gnd"}),
            component("R1", ComponentType.RESISTOR, {"a": "vin", "b": "n1"}),
            component("C1", ComponentType.CAPACITOR, {"a": "n1", "b": "gnd"}),
            component("R2", ComponentType.RESISTOR, {"a": "n1", "b": "vout"}),
            component("C2", ComponentType.CAPACITOR, {"a": "vout", "b": "gnd"}),
            component("G1", ComponentType.GROUND, {}),
        ],
    )

    arranged = arrange_circuit(circuit, preserve_manual=False)
    by_id = {item.id: item for item in arranged.components}

    assert by_id["R1"].position.x < by_id["R2"].position.x
    assert by_id["C1"].position.x < by_id["C2"].position.x
    assert by_id["C1"].position.y > by_id["R1"].position.y
    assert by_id["C2"].position.y > by_id["R2"].position.y


def test_manual_positions_are_preserved_but_full_arrange_can_move_them() -> None:
    manual = Position(x=736, y=112)
    circuit = Circuit(
        id="locked",
        name="Locked layout",
        nodes=[Node(id="gnd", label="GND"), Node(id="vin", label="VIN"), Node(id="out", label="OUT")],
        metadata={"input_node": "vin", "output_node": "out"},
        components=[
            component("V1", ComponentType.VOLTAGE_SOURCE, {"positive": "vin", "negative": "gnd"}),
            component("R1", ComponentType.RESISTOR, {"a": "vin", "b": "out"}, locked=True, position=manual),
            component("G1", ComponentType.GROUND, {}),
        ],
    )

    preserved = arrange_circuit(circuit, preserve_manual=True)
    rearranged = arrange_circuit(circuit, preserve_manual=False)

    assert next(item for item in preserved.components if item.id == "R1").position == manual
    assert next(item for item in rearranged.components if item.id == "R1").position != manual


def test_opamp_feedback_is_placed_above_the_signal_path() -> None:
    circuit = Circuit(
        id="amplifier",
        name="Amplifier",
        nodes=[Node(id="gnd", label="GND"), Node(id="vin", label="VIN"), Node(id="feedback", label="Feedback"), Node(id="vout", label="VOUT")],
        metadata={"input_node": "vin", "output_node": "vout"},
        components=[
            component("V1", ComponentType.VOLTAGE_SOURCE, {"positive": "vin", "negative": "gnd"}),
            component("U1", ComponentType.IDEAL_OPAMP, {"plus": "vin", "minus": "feedback", "out": "vout"}),
            component("R1", ComponentType.RESISTOR, {"a": "vout", "b": "feedback"}),
            component("R2", ComponentType.RESISTOR, {"a": "feedback", "b": "gnd"}),
            component("G1", ComponentType.GROUND, {}),
        ],
    )

    arranged = arrange_circuit(circuit, preserve_manual=False)
    by_id = {item.id: item for item in arranged.components}

    assert by_id["R1"].position.y < by_id["U1"].position.y
    assert by_id["R2"].position.y > by_id["U1"].position.y
    assert abs(by_id["R1"].position.x - by_id["U1"].position.x) <= 16
