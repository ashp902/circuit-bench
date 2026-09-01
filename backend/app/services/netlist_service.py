from __future__ import annotations

from dataclasses import dataclass

from app.models.circuit import Circuit, Component, ComponentType, PIN_NAMES
from app.services.errors import CircuitError


@dataclass(frozen=True, slots=True)
class AcAnalysis:
    start_hz: float
    stop_hz: float
    points_per_decade: int
    input_node: str
    output_node: str


@dataclass(frozen=True, slots=True)
class TransientAnalysis:
    duration_s: float
    time_step_s: float
    output_nodes: tuple[str, ...]


class NetlistService:
    """Translate validated circuit models into deterministic ngspice input."""

    result_filename = "results.dat"

    def build_operating_point(self, circuit: Circuit, output_nodes: list[str], current_components: list[str] | None = None) -> str:
        self._validate(circuit, output_nodes)
        commands = ["op", f"wrdata {self.result_filename} {self._vectors(output_nodes)} {self._current_vectors(circuit, current_components or [])}".strip()]
        return self._render(circuit, commands, current_components or [])

    def build_ac(self, circuit: Circuit, analysis: AcAnalysis, current_components: list[str] | None = None) -> str:
        self._validate(circuit, [analysis.input_node, analysis.output_node])
        if analysis.start_hz <= 0 or analysis.stop_hz <= analysis.start_hz:
            raise CircuitError("INVALID_PARAMETER", "AC frequency range must be positive and increasing.")
        if not 1 <= analysis.points_per_decade <= 1_000:
            raise CircuitError("INVALID_PARAMETER", "points_per_decade must be between 1 and 1000.")
        commands = [
            f"ac dec {analysis.points_per_decade} {self._number(analysis.start_hz)} {self._number(analysis.stop_hz)}",
            f"wrdata {self.result_filename} v({self._node(analysis.input_node)}) v({self._node(analysis.output_node)}) {self._current_vectors(circuit, current_components or [])}".strip(),
        ]
        return self._render(circuit, commands, current_components or [])

    def build_transient(self, circuit: Circuit, analysis: TransientAnalysis, current_components: list[str] | None = None) -> str:
        self._validate(circuit, list(analysis.output_nodes))
        if analysis.time_step_s <= 0 or analysis.duration_s <= analysis.time_step_s:
            raise CircuitError("INVALID_PARAMETER", "Transient duration must exceed its positive time step.")
        commands = [
            f"tran {self._number(analysis.time_step_s)} {self._number(analysis.duration_s)}",
            f"wrdata {self.result_filename} {self._vectors(list(analysis.output_nodes))} {self._current_vectors(circuit, current_components or [])}".strip(),
        ]
        return self._render(circuit, commands, current_components or [])

    def _render(self, circuit: Circuit, commands: list[str], current_components: list[str]) -> str:
        lines = [f"* generated circuit: {circuit.name}"]
        requested = set(current_components)
        for component in sorted(circuit.components, key=lambda item: item.id):
            if component.id in requested:
                primary_pin = {
                    ComponentType.RESISTOR: "a", ComponentType.CAPACITOR: "a", ComponentType.INDUCTOR: "a",
                    ComponentType.VOLTAGE_SOURCE: "positive", ComponentType.DIODE: "anode", ComponentType.IDEAL_OPAMP: "out",
                }.get(component.type)
                if primary_pin is None:
                    raise CircuitError("INVALID_PARAMETER", f"{component.id} does not expose a measurable branch current.")
                original_node = self._pin(component.pins, primary_pin)
                sense_node = f"sense_{component.id.lower()}"
                lines.append(f"VMEAS{component.id} {original_node} {sense_node} 0")
                lines.append(self._component_line(component, {primary_pin: sense_node}))
            else:
                lines.append(self._component_line(component))
        if any(component.type is ComponentType.DIODE for component in circuit.components):
            lines.append(".model DDEFAULT D(Is=1e-14 N=1)")
        lines.extend([".control", "set wr_vecnames", "set wr_singlescale", *commands, "quit", ".endc", ".end", ""])
        return "\n".join(line for line in lines if line) + "\n"

    def _component_line(self, component: Component, pin_overrides: dict[str, str] | None = None) -> str:
        pins = {**component.pins, **(pin_overrides or {})}
        params = component.params
        if component.type is ComponentType.GROUND:
            return ""
        if component.type is ComponentType.RESISTOR:
            return f"{component.id} {self._pin(pins, 'a')} {self._pin(pins, 'b')} {self._number(params['resistance_ohm'])}"
        if component.type is ComponentType.CAPACITOR:
            return f"{component.id} {self._pin(pins, 'a')} {self._pin(pins, 'b')} {self._number(params['capacitance_f'])}"
        if component.type is ComponentType.INDUCTOR:
            return f"{component.id} {self._pin(pins, 'a')} {self._pin(pins, 'b')} {self._number(params['inductance_h'])}"
        if component.type is ComponentType.VOLTAGE_SOURCE:
            return self._voltage_source_line(component, pins)
        if component.type is ComponentType.DIODE:
            return f"D{component.id} {self._pin(pins, 'anode')} {self._pin(pins, 'cathode')} DDEFAULT"
        if component.type is ComponentType.IDEAL_OPAMP:
            gain = self._number(params.get("gain", 100_000))
            return f"E{component.id} {self._pin(pins, 'out')} 0 {self._pin(pins, 'plus')} {self._pin(pins, 'minus')} {gain}"
        raise CircuitError("UNSUPPORTED_COMPONENT", f"Netlist generation does not yet support {component.type.value}.")

    def _voltage_source_line(self, component: Component, pins: dict[str, str | None] | None = None) -> str:
        params = component.params
        source_pins = pins or component.pins
        prefix = f"{component.id} {self._pin(source_pins, 'positive')} {self._pin(source_pins, 'negative')}"
        mode = params.get("mode", "dc")
        if mode == "sine":
            source = "SIN({} {} {})".format(
                self._number(params.get("offset_v", 0)),
                self._number(params.get("amplitude_v", 1)),
                self._number(params.get("frequency_hz", 1)),
            )
        elif mode == "pulse":
            source = "PULSE({} {} {} {} {} {} {})".format(
                self._number(params.get("initial_v", 0)),
                self._number(params.get("pulsed_v", 1)),
                self._number(params.get("delay_s", 0)),
                self._number(params.get("rise_time_s", 1e-6)),
                self._number(params.get("fall_time_s", 1e-6)),
                self._number(params.get("pulse_width_s", 1)),
                self._number(params.get("period_s", 2)),
            )
        else:
            source = f"DC {self._number(params.get('voltage_v', 0))}"
        return f"{prefix} {source} AC 1"

    def _validate(self, circuit: Circuit, output_nodes: list[str]) -> None:
        node_ids = {node.id for node in circuit.nodes}
        if "gnd" not in node_ids:
            raise CircuitError("NO_GROUND", "Circuit needs a gnd node before simulation.")
        unknown_outputs = set(output_nodes).difference(node_ids)
        if unknown_outputs:
            raise CircuitError("NODE_NOT_FOUND", f"Unknown output nodes: {sorted(unknown_outputs)}")
        for component in circuit.components:
            for pin in PIN_NAMES[component.type]:
                node_id = component.pins.get(pin)
                if node_id is None:
                    raise CircuitError("FLOATING_PIN", f"{component.id}.{pin} is not connected.")
                if node_id not in node_ids:
                    raise CircuitError("NODE_NOT_FOUND", f"{component.id}.{pin} uses unknown node {node_id}.")

    def _pin(self, pins: dict[str, str | None], pin: str) -> str:
        node_id = pins.get(pin)
        if node_id is None:
            raise CircuitError("FLOATING_PIN", f"Pin {pin} is not connected.")
        return self._node(node_id)

    @staticmethod
    def _node(node_id: str) -> str:
        return "0" if node_id == "gnd" else node_id

    def _vectors(self, nodes: list[str]) -> str:
        return " ".join(f"v({self._node(node)})" for node in nodes)

    def _current_vectors(self, circuit: Circuit, component_ids: list[str]) -> str:
        components = {component.id: component for component in circuit.components}
        vectors: list[str] = []
        for component_id in component_ids:
            component = components.get(component_id)
            if component is None:
                raise CircuitError("COMPONENT_NOT_FOUND", f"Component {component_id} does not exist.")
            if component.type is ComponentType.GROUND:
                raise CircuitError("INVALID_PARAMETER", "Ground does not expose a branch current.")
            vectors.append(f"i(vmeas{component.id.lower()})")
        return " ".join(vectors)

    @staticmethod
    def _number(value: object) -> str:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise CircuitError("INVALID_PARAMETER", f"Expected numeric SPICE value, got {value!r}.")
        return format(float(value), ".12g")
