from __future__ import annotations

from collections import defaultdict, deque

from app.models.circuit import Circuit, Component, ComponentType, Position


GRID = 16
MAIN_Y = 240


def _snap(value: float) -> float:
    return float(round(value / GRID) * GRID)


def _component_nodes(component: Component) -> list[str]:
    if component.type is ComponentType.GROUND:
        return ["gnd"]
    return [node for node in component.pins.values() if node]


def _preferred_input(circuit: Circuit) -> str | None:
    node_ids = {node.id for node in circuit.nodes}
    configured = circuit.metadata.get("input_node")
    if configured in node_ids:
        return configured
    for component in circuit.components:
        if component.type is ComponentType.VOLTAGE_SOURCE and component.pins.get("positive"):
            return component.pins["positive"]
    for node in circuit.nodes:
        if node.label.casefold().replace(" ", "") in {"vin", "input"}:
            return node.id
    return next((node.id for node in circuit.nodes if node.id != "gnd"), None)


def _net_ranks(circuit: Circuit) -> dict[str, int]:
    """Rank signal nets from the source without allowing ground to shortcut paths."""
    start = _preferred_input(circuit)
    if start is None:
        return {}
    neighbors: dict[str, set[str]] = defaultdict(set)
    for component in circuit.components:
        nodes = list(dict.fromkeys(node for node in _component_nodes(component) if node != "gnd"))
        for left in nodes:
            for right in nodes:
                if left != right:
                    neighbors[left].add(right)
    ranks = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for adjacent in sorted(neighbors[node]):
            if adjacent not in ranks:
                ranks[adjacent] = ranks[node] + 1
                queue.append(adjacent)
    return ranks


def _orientation(component: Component, signal_nodes: list[str], grounded: bool) -> int:
    if component.type in {ComponentType.GROUND, ComponentType.VOLTAGE_SOURCE, ComponentType.IDEAL_OPAMP}:
        return 0
    if grounded and len(signal_nodes) == 1:
        return 0 if component.type is ComponentType.CAPACITOR else 90
    return 90 if component.type is ComponentType.CAPACITOR else 0


def arrange_circuit(circuit: Circuit, *, preserve_manual: bool = True) -> Circuit:
    """Return a readable, deterministic schematic layout derived from connectivity.

    Signal flow is placed left-to-right, shunt parts below their net, feedback paths
    above the signal path, and disconnected parts in a separate staging row. Manual
    positions are obstacles when ``preserve_manual`` is requested.
    """
    arranged = circuit.model_copy(deep=True)
    ranks = _net_ranks(arranged)
    max_rank = max(ranks.values(), default=0)
    output_node = arranged.metadata.get("output_node")
    if output_node in ranks:
        max_rank = max(max_rank, ranks[output_node])

    locked = [component for component in arranged.components if preserve_manual and component.layout_locked and component.position]
    occupied: list[tuple[float, float]] = [(component.position.x, component.position.y) for component in locked if component.position]
    layer_counts: dict[tuple[str, int], int] = defaultdict(int)
    disconnected_index = 0
    opamp = next((item for item in arranged.components if item.type is ComponentType.IDEAL_OPAMP), None)
    opamp_feedback_nodes = {opamp.pins.get("minus"), opamp.pins.get("out")} - {None} if opamp else set()
    opamp_x = 240 + max(1, ranks.get(opamp.pins.get("out") or "", 1)) * 180 if opamp else None

    def available(x: float, y: float) -> Position:
        candidates = [(x, y)]
        for step in range(1, 8):
            candidates.extend([(x, y + step * 112), (x, y - step * 112), (x + step * 144, y)])
        for candidate_x, candidate_y in candidates:
            candidate_x = min(840, max(96, _snap(candidate_x)))
            candidate_y = min(480, max(96, _snap(candidate_y)))
            if all(abs(candidate_x - used_x) >= 136 or abs(candidate_y - used_y) >= 96 for used_x, used_y in occupied):
                occupied.append((candidate_x, candidate_y))
                return Position(x=candidate_x, y=candidate_y)
        position = Position(x=min(840, max(96, _snap(x))), y=min(480, max(96, _snap(y))))
        occupied.append((position.x, position.y))
        return position

    for component in arranged.components:
        if preserve_manual and component.layout_locked and component.position:
            continue
        all_nodes = list(dict.fromkeys(_component_nodes(component)))
        signal_nodes = [node for node in all_nodes if node != "gnd"]
        grounded = "gnd" in all_nodes

        if component.type is ComponentType.GROUND:
            component.position = available(200 + max_rank * 180 / 2, 464)
            component.rotation = 0
        elif component.type is ComponentType.VOLTAGE_SOURCE:
            positive = component.pins.get("positive")
            rank = ranks.get(positive or "", 0)
            component.position = available(112 + rank * 180, MAIN_Y)
            component.rotation = 0
        elif component.type is ComponentType.IDEAL_OPAMP:
            out_rank = ranks.get(component.pins.get("out") or "", 1)
            component.position = available(240 + max(1, out_rank) * 180, MAIN_Y)
            component.rotation = 0
        elif not signal_nodes or not any(node in ranks for node in signal_nodes):
            row, column = divmod(disconnected_index, 4)
            disconnected_index += 1
            component.position = available(176 + column * 176, 368 + row * 112)
            component.rotation = _orientation(component, signal_nodes, grounded)
        elif grounded and len(signal_nodes) == 1:
            rank = ranks.get(signal_nodes[0], 0)
            slot = layer_counts[("shunt", rank)]
            layer_counts[("shunt", rank)] += 1
            component.position = available(240 + rank * 180 + slot * 144, 384)
            component.rotation = _orientation(component, signal_nodes, grounded)
        else:
            node_ranks = sorted(ranks[node] for node in signal_nodes if node in ranks)
            low = node_ranks[0]
            high = node_ranks[-1]
            is_opamp_feedback = len(opamp_feedback_nodes) == 2 and opamp_feedback_nodes.issubset(signal_nodes)
            is_feedback = is_opamp_feedback or (len(node_ranks) > 1 and high - low > 1)
            lane = "feedback" if is_feedback else "signal"
            slot = layer_counts[(lane, low)]
            layer_counts[(lane, low)] += 1
            x = opamp_x if is_opamp_feedback and opamp_x is not None else 240 + ((low + high) / 2 if high != low else low + .5) * 180
            y = 112 - slot * 96 if is_feedback else MAIN_Y + slot * 112
            component.position = available(x, y)
            component.rotation = _orientation(component, signal_nodes, grounded)
        component.layout_locked = False
    return arranged
