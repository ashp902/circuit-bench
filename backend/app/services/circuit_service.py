from __future__ import annotations

from collections.abc import Mapping

from app.models.circuit import ALLOWED_PARAMETERS, Challenge, Circuit, Component, ComponentType, Node, PIN_NAMES, ParameterValue, Position
from app.services.errors import CircuitError
from app.services.layout_service import arrange_circuit


class CircuitService:
    """Revision-safe mutations over the backend's canonical circuit state."""

    def __init__(self, circuit: Circuit, challenge: Challenge) -> None:
        self._circuit = circuit
        self._challenge = challenge

    def get_circuit(self) -> Circuit:
        return self._circuit.model_copy(deep=True)

    def add_component(self, component_type: ComponentType, params: Mapping[str, ParameterValue], expected_revision: int, position: Position | None = None) -> Component:
        self._assert_revision(expected_revision)
        if component_type not in self._challenge.allowed_components:
            raise CircuitError("UNSUPPORTED_COMPONENT", f"{component_type} is not allowed in this lab.")
        if len(self._circuit.components) >= self._challenge.component_limit:
            raise CircuitError("COMPONENT_LIMIT_EXCEEDED", "The challenge component limit has been reached.")
        prefix = {ComponentType.RESISTOR: "R", ComponentType.CAPACITOR: "C", ComponentType.INDUCTOR: "L", ComponentType.VOLTAGE_SOURCE: "V", ComponentType.DIODE: "D", ComponentType.IDEAL_OPAMP: "U", ComponentType.GROUND: "G"}[component_type]
        index = len(self._circuit.components)
        component_params = {**self._default_params(component_type), **dict(params)}
        try:
            component = Component(id=self._next_id(prefix), type=component_type, params=component_params, pins={pin: None for pin in PIN_NAMES[component_type]}, position=position or Position(x=180 + (index % 4) * 180, y=220 + (index // 4) * 150), layout_locked=position is not None)
        except ValueError as error:
            raise CircuitError("INVALID_PARAMETER", str(error)) from error
        self._circuit.components.append(component)
        self._advance_revision()
        return component.model_copy(deep=True)

    @staticmethod
    def _default_params(component_type: ComponentType) -> dict[str, ParameterValue]:
        """Usable defaults let a tool add a primitive before tailoring it."""
        return {
            ComponentType.RESISTOR: {"resistance_ohm": 1_000.0},
            ComponentType.CAPACITOR: {"capacitance_f": 100e-9},
            ComponentType.INDUCTOR: {"inductance_h": 1e-3},
            ComponentType.VOLTAGE_SOURCE: {"mode": "dc", "voltage_v": 0.0},
            ComponentType.DIODE: {"model": "D"},
            ComponentType.IDEAL_OPAMP: {"gain": 100_000.0},
            ComponentType.GROUND: {},
        }[component_type]

    def create_node(self, label: str, expected_revision: int) -> Node:
        self._assert_revision(expected_revision)
        node = Node(id=self._next_id("n", [node.id for node in self._circuit.nodes]), label=label)
        self._circuit.nodes.append(node)
        self._advance_revision()
        return node.model_copy(deep=True)

    def rename_node(self, node_id: str, label: str, expected_revision: int) -> None:
        self._assert_revision(expected_revision)
        node = next((candidate for candidate in self._circuit.nodes if candidate.id == node_id), None)
        if node is None:
            raise CircuitError("NODE_NOT_FOUND", f"Node {node_id} does not exist.")
        if node_id == "gnd":
            raise CircuitError("INVALID_PARAMETER", "Ground is the fixed electrical reference and cannot be renamed.")
        node.label = label.strip()
        normalized = node.label.casefold().replace(" ", "")
        if normalized in {"vin", "input"}:
            self._circuit.metadata["input_node"] = node.id
        if normalized in {"vout", "output"}:
            self._circuit.metadata["output_node"] = node.id
        self._advance_revision()

    def set_layout(self, component_id: str, position: Position, rotation: int, expected_revision: int) -> None:
        self._assert_revision(expected_revision)
        component = self._component(component_id)
        if rotation not in {0, 90, 180, 270}:
            raise CircuitError("INVALID_PARAMETER", "Rotation must be 0, 90, 180, or 270 degrees.")
        component.position = position
        component.rotation = rotation
        component.layout_locked = True
        self._advance_revision()

    def auto_layout(self, expected_revision: int, *, preserve_manual: bool = True) -> None:
        self._assert_revision(expected_revision)
        self._circuit = arrange_circuit(self._circuit, preserve_manual=preserve_manual)
        self._advance_revision()

    def apply_auto_layout(self, *, preserve_manual: bool = True) -> None:
        """Apply layout inside another mutation without consuming another revision."""
        self._circuit = arrange_circuit(self._circuit, preserve_manual=preserve_manual)

    def connect(self, component_id: str, pin: str, node_id: str, expected_revision: int) -> None:
        self._assert_revision(expected_revision)
        component = self._component(component_id)
        if pin not in PIN_NAMES[component.type]:
            raise CircuitError("INVALID_PARAMETER", f"{pin} is not a pin on {component_id}.")
        if node_id not in {node.id for node in self._circuit.nodes}:
            raise CircuitError("NODE_NOT_FOUND", f"Node {node_id} does not exist.")
        component.pins[pin] = node_id
        self._advance_revision()

    def connect_pins(
        self,
        source_component_id: str,
        source_pin: str,
        target_component_id: str,
        target_pin: str,
        expected_revision: int,
    ) -> None:
        """Join two terminals, creating or merging a canonical electrical net.

        The persisted circuit model deliberately represents connectivity as nets.
        This method gives the editor its expected direct terminal-to-terminal
        interaction while keeping that model unchanged.
        """
        self._assert_revision(expected_revision)
        source = self._component(source_component_id)
        target = self._component(target_component_id)
        source_node = self._terminal_node(source, source_pin)
        target_node = self._terminal_node(target, target_pin)

        if source_node and target_node and source_node == target_node:
            return

        if source_node and target_node:
            retained_node, replaced_node = self._select_retained_node(source_node, target_node)
            for component in self._circuit.components:
                for pin, node_id in component.pins.items():
                    if node_id == replaced_node:
                        component.pins[pin] = retained_node
            self._circuit.nodes = [node for node in self._circuit.nodes if node.id != replaced_node]
            for key, value in tuple(self._circuit.metadata.items()):
                if value == replaced_node:
                    self._circuit.metadata[key] = retained_node
        elif source_node:
            self._assign_terminal(target, target_pin, source_node)
        elif target_node:
            self._assign_terminal(source, source_pin, target_node)
        else:
            node = Node(id=self._next_id("n", [node.id for node in self._circuit.nodes]), label=self._next_net_label())
            self._circuit.nodes.append(node)
            self._assign_terminal(source, source_pin, node.id)
            self._assign_terminal(target, target_pin, node.id)
        self._advance_revision()

    def disconnect(self, component_id: str, pin: str, expected_revision: int) -> None:
        self._assert_revision(expected_revision)
        component = self._component(component_id)
        if pin not in PIN_NAMES[component.type]:
            raise CircuitError("INVALID_PARAMETER", f"{pin} is not a pin on {component_id}.")
        component.pins[pin] = None
        self._advance_revision()

    def set_parameter(self, component_id: str, parameter: str, value: ParameterValue, expected_revision: int) -> None:
        self._assert_revision(expected_revision)
        component = self._component(component_id)
        if parameter not in ALLOWED_PARAMETERS[component.type]:
            raise CircuitError("INVALID_PARAMETER", f"{parameter} is not a parameter on {component_id}.")
        next_params = dict(component.params)
        next_params[parameter] = value
        try:
            replacement = Component(id=component.id, type=component.type, params=next_params, pins=component.pins, position=component.position, rotation=component.rotation, layout_locked=component.layout_locked)
        except ValueError as error:
            raise CircuitError("INVALID_PARAMETER", str(error)) from error
        self._circuit.components[self._circuit.components.index(component)] = replacement
        self._advance_revision()

    def remove_component(self, component_id: str, expected_revision: int) -> None:
        self._assert_revision(expected_revision)
        component = self._component(component_id)
        self._circuit.components.remove(component)
        self._advance_revision()

    def validate(self) -> list[CircuitError]:
        issues: list[CircuitError] = []
        node_ids = {node.id for node in self._circuit.nodes}
        if "gnd" not in node_ids:
            issues.append(CircuitError("NO_GROUND", "Circuit needs a gnd node."))
        for component in self._circuit.components:
            for pin in PIN_NAMES[component.type]:
                if component.pins.get(pin) is None:
                    issues.append(CircuitError("FLOATING_PIN", f"{component.id}.{pin} is not connected."))
            if component.type is ComponentType.VOLTAGE_SOURCE and component.pins.get("positive") == component.pins.get("negative"):
                issues.append(CircuitError("INVALID_CIRCUIT", f"{component.id} terminals must use different nodes."))
        return issues

    def _assert_revision(self, expected_revision: int) -> None:
        if expected_revision != self._circuit.revision:
            raise CircuitError("STALE_REVISION", f"Circuit changed since revision {expected_revision}.", "Call get_circuit and retry with the latest revision.")

    def _component(self, component_id: str) -> Component:
        for component in self._circuit.components:
            if component.id == component_id:
                return component
        raise CircuitError("COMPONENT_NOT_FOUND", f"Component {component_id} does not exist.")

    def _terminal_node(self, component: Component, pin: str) -> str | None:
        if component.type is ComponentType.GROUND and pin == "ground":
            if "gnd" not in {node.id for node in self._circuit.nodes}:
                self._circuit.nodes.append(Node(id="gnd", label="GND"))
            return "gnd"
        if pin not in PIN_NAMES[component.type]:
            raise CircuitError("INVALID_PARAMETER", f"{pin} is not a pin on {component.id}.")
        return component.pins.get(pin)

    def _assign_terminal(self, component: Component, pin: str, node_id: str) -> None:
        if component.type is ComponentType.GROUND and pin == "ground":
            return
        if pin not in PIN_NAMES[component.type]:
            raise CircuitError("INVALID_PARAMETER", f"{pin} is not a pin on {component.id}.")
        component.pins[pin] = node_id

    @staticmethod
    def _select_retained_node(source_node: str, target_node: str) -> tuple[str, str]:
        if source_node == "gnd":
            return source_node, target_node
        if target_node == "gnd":
            return target_node, source_node
        return source_node, target_node

    def _next_net_label(self) -> str:
        labels = {node.label.casefold() for node in self._circuit.nodes}
        suffix = 1
        while f"n{suffix:03d}" in labels:
            suffix += 1
        return f"N{suffix:03d}"

    def _next_id(self, prefix: str, ids: list[str] | None = None) -> str:
        existing = ids or [component.id for component in self._circuit.components]
        suffix = 1
        while f"{prefix}{suffix}" in existing:
            suffix += 1
        return f"{prefix}{suffix}"

    def _advance_revision(self) -> None:
        self._circuit.revision += 1
