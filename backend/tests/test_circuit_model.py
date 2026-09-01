from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.circuit import Challenge, Circuit, Component, ComponentType, Node
from app.services.circuit_service import CircuitService
from app.services.errors import CircuitError


def make_service(component_limit: int = 4) -> CircuitService:
    circuit = Circuit(id="ckt_test", name="Test circuit", nodes=[Node(id="gnd", label="Ground")])
    challenge = Challenge(
        id="challenge_test",
        title="Test",
        description="Test challenge",
        component_limit=component_limit,
    )
    return CircuitService(circuit, challenge)


def test_add_resistor_assigns_deterministic_id_and_revision() -> None:
    service = make_service()

    resistor = service.add_component(ComponentType.RESISTOR, {"resistance_ohm": 1_000}, expected_revision=0)

    assert resistor.id == "R1"
    assert service.get_circuit().revision == 1


def test_invalid_resistance_is_rejected() -> None:
    with pytest.raises(ValidationError, match="resistance_ohm"):
        Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 0})


def test_connects_component_pin_to_existing_node() -> None:
    service = make_service()
    resistor = service.add_component(ComponentType.RESISTOR, {"resistance_ohm": 1_000}, 0)
    output = service.create_node("Output", 1)

    service.connect(resistor.id, "a", output.id, 2)

    assert service.get_circuit().components[0].pins["a"] == output.id


def test_connects_two_component_pins_by_creating_and_reusing_a_net() -> None:
    service = make_service()
    resistor = service.add_component(ComponentType.RESISTOR, {"resistance_ohm": 1_000}, 0)
    capacitor = service.add_component(ComponentType.CAPACITOR, {"capacitance_f": 100e-9}, 1)

    service.connect_pins(resistor.id, "b", capacitor.id, "a", 2)

    circuit = service.get_circuit()
    assert circuit.components[0].pins["b"] == "n1"
    assert circuit.components[1].pins["a"] == "n1"
    assert next(node for node in circuit.nodes if node.id == "n1").label == "N001"


def test_connecting_to_ground_component_uses_the_ground_net() -> None:
    service = make_service()
    capacitor = service.add_component(ComponentType.CAPACITOR, {"capacitance_f": 100e-9}, 0)
    ground = service.add_component(ComponentType.GROUND, {}, 1)

    service.connect_pins(capacitor.id, "b", ground.id, "ground", 2)

    assert service.get_circuit().components[0].pins["b"] == "gnd"


def test_duplicate_component_ids_are_rejected() -> None:
    resistor = Component(id="R1", type=ComponentType.RESISTOR, params={"resistance_ohm": 1_000})
    with pytest.raises(ValidationError, match="unique"):
        Circuit(id="ckt", name="duplicate", components=[resistor, resistor])


def test_stale_revision_is_rejected() -> None:
    service = make_service()
    service.add_component(ComponentType.RESISTOR, {"resistance_ohm": 1_000}, 0)

    with pytest.raises(CircuitError, match="Circuit changed") as error:
        service.add_component(ComponentType.CAPACITOR, {"capacitance_f": 1e-9}, 0)

    assert error.value.code == "STALE_REVISION"


def test_component_limit_is_rejected() -> None:
    service = make_service(component_limit=1)
    service.add_component(ComponentType.RESISTOR, {"resistance_ohm": 1_000}, 0)

    with pytest.raises(CircuitError) as error:
        service.add_component(ComponentType.CAPACITOR, {"capacitance_f": 1e-9}, 1)

    assert error.value.code == "COMPONENT_LIMIT_EXCEEDED"


def test_missing_ground_is_reported() -> None:
    service = CircuitService(
        Circuit(id="ckt", name="missing ground"),
        Challenge(id="challenge", title="Test", description="Test", component_limit=2),
    )

    assert [issue.code for issue in service.validate()] == ["NO_GROUND"]


def test_floating_pin_is_reported() -> None:
    service = make_service()
    service.add_component(ComponentType.RESISTOR, {"resistance_ohm": 1_000}, 0)

    issues = service.validate()

    assert [issue.code for issue in issues] == ["FLOATING_PIN", "FLOATING_PIN"]
