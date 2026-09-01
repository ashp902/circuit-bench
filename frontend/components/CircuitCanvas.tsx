"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowClockwiseIcon, CornersOutIcon, MinusIcon, PlusIcon } from "@phosphor-icons/react";

import { engineering } from "@/lib/format";
import { api } from "@/lib/api";
import { getComponentDisplayName, getParameterUnit } from "@/lib/presentation";
import type { Circuit, CircuitComponent, ComponentType, ParameterValue } from "@/lib/types";

type Point = { x: number; y: number };
type PinRef = { componentId: string; pin: string };
type Direction = "left" | "right" | "top" | "bottom";
type Rotation = 0 | 90 | 180 | 270;
type PinPosition = PinRef & Point & { direction: Direction; nodeId: string | null; label: string };
type WirePath = { nodeId: string; pin: PinPosition; points: Point[]; bridges: Array<Point & { horizontal: boolean }> };

const GRID = 16;
const WORLD = { width: 920, height: 560 };
const pinNames: Record<ComponentType, string[]> = {
  resistor: ["a", "b"], capacitor: ["a", "b"], inductor: ["a", "b"], voltage_source: ["negative", "positive"], diode: ["anode", "cathode"], ideal_opamp: ["plus", "minus", "out"], ground: ["ground"],
};

function snap(value: number) { return Math.round(value / GRID) * GRID; }
function pinKey(ref: PinRef) { return `${ref.componentId}:${ref.pin}`; }
function parsePinKey(value: string | undefined): PinRef | null {
  if (!value) return null;
  const [componentId, pin] = value.split(":");
  return componentId && pin ? { componentId, pin } : null;
}
function isVerticalComponent(component: CircuitComponent, circuit: Circuit) {
  if (component.type === "capacitor") return true;
  if (component.type !== "resistor") return false;
  const opamp = circuit.components.find((item) => item.type === "ideal_opamp");
  const nodes = Object.values(component.pins);
  return Boolean(opamp?.pins.minus && nodes.includes("gnd") && nodes.includes(opamp.pins.minus));
}
function isFlippedComponent(component: CircuitComponent, circuit: Circuit) {
  if (component.type !== "resistor") return false;
  const opamp = circuit.components.find((item) => item.type === "ideal_opamp");
  return Boolean(opamp?.pins.out && opamp?.pins.minus && component.pins.a === opamp.pins.out && component.pins.b === opamp.pins.minus);
}
function rotateDirection(direction: Direction, rotation: Rotation): Direction {
  const directions: Direction[] = ["top", "right", "bottom", "left"];
  return directions[(directions.indexOf(direction) + rotation / 90) % directions.length];
}
function rotatePin(pin: PinPosition, center: Point, rotation: Rotation): PinPosition {
  if (!rotation) return pin;
  const dx = pin.x - center.x; const dy = pin.y - center.y;
  if (rotation === 90) return { ...pin, x: center.x - dy, y: center.y + dx, direction: rotateDirection(pin.direction, rotation) };
  if (rotation === 180) return { ...pin, x: center.x - dx, y: center.y - dy, direction: rotateDirection(pin.direction, rotation) };
  return { ...pin, x: center.x + dy, y: center.y - dx, direction: rotateDirection(pin.direction, rotation) };
}
function defaultPositions(circuit: Circuit): Record<string, Point> {
  const positions: Record<string, Point> = {};
  const opamp = circuit.components.find((component) => component.type === "ideal_opamp");
  if (opamp) {
    positions[opamp.id] = { x: 400, y: 320 };
    circuit.components.filter((component) => component.type === "voltage_source").forEach((component, index) => { positions[component.id] = { x: 150, y: 270 + index * 120 }; });
    const feedbackNodes = new Set([opamp.pins.minus, opamp.pins.out].filter(Boolean));
    let upperIndex = 0; let lowerIndex = 0;
    circuit.components.filter((component) => component.type === "resistor").forEach((component) => {
      const nodes = Object.values(component.pins);
      const feedback = feedbackNodes.size === 2 && [...feedbackNodes].every((node) => nodes.includes(node));
      if (feedback) positions[component.id] = { x: 400, y: 170 };
      else if (nodes.includes("gnd")) positions[component.id] = { x: 290 + upperIndex++ * 180, y: 420 };
      else positions[component.id] = { x: 570 + lowerIndex++ * 150, y: 360 };
    });
    circuit.components.filter((component) => !positions[component.id]).forEach((component, index) => { positions[component.id] = { x: 620 + (index % 2) * 150, y: 300 + Math.floor(index / 2) * 130 }; });
    return positions;
  }
  const standard = { V1: { x: 170, y: 250 }, R1: { x: 400, y: 250 }, C1: { x: 640, y: 350 }, G1: { x: 640, y: 480 } };
  let automaticIndex = 0;
  circuit.components.forEach((component) => {
    const known = standard[component.id as keyof typeof standard];
    if (known) { positions[component.id] = known; return; }
    positions[component.id] = { x: 170 + (automaticIndex % 3) * 210, y: 390 + Math.floor(automaticIndex / 3) * 120 };
    automaticIndex += 1;
  });
  return positions;
}
function canonicalPositions(circuit: Circuit): Record<string, Point> {
  const positions = defaultPositions(circuit);
  circuit.components.forEach((component) => { if (component.position) positions[component.id] = component.position; });
  return positions;
}
export function componentPins(component: CircuitComponent, position: Point, vertical = false, flipped = false, rotation: Rotation = 0): PinPosition[] {
  const pair = (left: string, right: string) => [
    { componentId: component.id, pin: left, x: position.x - 58, y: position.y, direction: "left" as const, nodeId: component.pins[left] ?? null, label: left },
    { componentId: component.id, pin: right, x: position.x + 58, y: position.y, direction: "right" as const, nodeId: component.pins[right] ?? null, label: right },
  ];
  let result: PinPosition[];
  if (vertical) result = [
    { componentId: component.id, pin: pinNames[component.type][0], x: position.x, y: position.y - 58, direction: "top" as const, nodeId: component.pins[pinNames[component.type][0]] ?? null, label: pinNames[component.type][0] },
    { componentId: component.id, pin: pinNames[component.type][1], x: position.x, y: position.y + 58, direction: "bottom" as const, nodeId: component.pins[pinNames[component.type][1]] ?? null, label: pinNames[component.type][1] },
  ];
  else if (component.type === "ideal_opamp") result = [
    { componentId: component.id, pin: "plus", x: position.x - 58, y: position.y - 18, direction: "left" as const, nodeId: component.pins.plus ?? null, label: "+" },
    { componentId: component.id, pin: "minus", x: position.x - 58, y: position.y + 18, direction: "left" as const, nodeId: component.pins.minus ?? null, label: "−" },
    { componentId: component.id, pin: "out", x: position.x + 58, y: position.y, direction: "right" as const, nodeId: component.pins.out ?? null, label: "out" },
  ];
  else if (component.type === "capacitor") result = [
    { componentId: component.id, pin: "a", x: position.x, y: position.y - 58, direction: "top" as const, nodeId: component.pins.a ?? null, label: "a" },
    { componentId: component.id, pin: "b", x: position.x, y: position.y + 58, direction: "bottom" as const, nodeId: component.pins.b ?? null, label: "b" },
  ];
  else if (component.type === "ground") result = [{ componentId: component.id, pin: "ground", x: position.x, y: position.y - 21, direction: "top" as const, nodeId: "gnd", label: "GND" }];
  else result = flipped ? pair(pinNames[component.type][1], pinNames[component.type][0]) : pair(pinNames[component.type][0], pinNames[component.type][1]);
  return result.map((pin) => rotatePin(pin, position, rotation));
}
function escape(point: Point & { direction?: Direction }, distance = 40): Point {
  if (point.direction === "left") return { x: point.x - distance, y: point.y };
  if (point.direction === "right") return { x: point.x + distance, y: point.y };
  if (point.direction === "top") return { x: point.x, y: point.y - distance };
  if (point.direction === "bottom") return { x: point.x, y: point.y + distance };
  return { x: point.x, y: point.y };
}
function route(from: Point & { direction?: Direction }, to: Point & { direction?: Direction }): string {
  const start = escape(from); const end = escape(to);
  if (!from.direction) return Math.abs(from.y - to.y) < 2 ? `M ${from.x} ${from.y} H ${to.x}` : `M ${from.x} ${from.y} H ${snap((from.x + to.x) / 2)} V ${to.y} H ${to.x}`;
  if (start.x === end.x || start.y === end.y) return `M ${from.x} ${from.y} L ${start.x} ${start.y} L ${end.x} ${end.y} L ${to.x} ${to.y}`;
  if ((from.direction === "left" && to.x > from.x) || (from.direction === "right" && to.x < from.x)) {
    const detourY = Math.max(28, snap(Math.min(from.y, to.y) - 72));
    return `M ${from.x} ${from.y} L ${start.x} ${start.y} V ${detourY} H ${end.x} V ${end.y} L ${to.x} ${to.y}`;
  }
  if ((from.direction === "top" && to.y > from.y) || (from.direction === "bottom" && to.y < from.y)) {
    const detourX = Math.min(WORLD.width - 28, snap(Math.max(from.x, to.x) + 72));
    return `M ${from.x} ${from.y} L ${start.x} ${start.y} H ${detourX} V ${end.y} H ${end.x} L ${to.x} ${to.y}`;
  }
  if (from.direction === "left" || from.direction === "right") return `M ${from.x} ${from.y} L ${start.x} ${start.y} V ${end.y} H ${end.x} L ${to.x} ${to.y}`;
  return `M ${from.x} ${from.y} L ${start.x} ${start.y} H ${end.x} V ${end.y} L ${to.x} ${to.y}`;
}
function pathFromPoints(points: Point[]) { return points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" "); }
export function pathFromPointsWithBridges(points: Point[], bridges: Array<Point & { horizontal: boolean }>) {
  if (!bridges.length) return pathFromPoints(points);
  let path = `M ${points[0].x} ${points[0].y}`;
  pathSegments(points).forEach(({ from, to }) => {
    const horizontal = from.y === to.y;
    const direction = horizontal ? Math.sign(to.x - from.x) : Math.sign(to.y - from.y);
    const onSegment = bridges
      .filter((bridge) => bridge.horizontal === horizontal && (horizontal
        ? bridge.y === from.y && bridge.x > Math.min(from.x, to.x) && bridge.x < Math.max(from.x, to.x)
        : bridge.x === from.x && bridge.y > Math.min(from.y, to.y) && bridge.y < Math.max(from.y, to.y)))
      .sort((a, b) => direction * (horizontal ? a.x - b.x : a.y - b.y));
    onSegment.forEach((bridge) => {
      if (horizontal) {
        const before = bridge.x - direction * 8;
        const after = bridge.x + direction * 8;
        path += ` L ${before} ${bridge.y} Q ${bridge.x} ${bridge.y - 16} ${after} ${bridge.y}`;
      } else {
        const before = bridge.y - direction * 8;
        const after = bridge.y + direction * 8;
        path += ` L ${bridge.x} ${before} Q ${bridge.x + 16} ${bridge.y} ${bridge.x} ${after}`;
      }
    });
    path += ` L ${to.x} ${to.y}`;
  });
  return path;
}
function compactPath(points: Point[]) {
  return points.reduce<Point[]>((result, point) => {
    if (!result.length || result.at(-1)!.x !== point.x || result.at(-1)!.y !== point.y) result.push(point);
    if (result.length >= 3) {
      const [a, b, c] = result.slice(-3);
      if ((a.x === b.x && b.x === c.x) || (a.y === b.y && b.y === c.y)) result.splice(-2, 1);
    }
    return result;
  }, []);
}
function componentBox(component: CircuitComponent, position: Point, vertical = false, rotation: Rotation = 0) {
  const native = component.type === "ground" ? { width: 70, height: 42 } : component.type === "capacitor" ? { width: 44, height: 116 } : component.type === "ideal_opamp" ? { width: 116, height: 68 } : { width: 116, height: 52 };
  const baseRotation = vertical && component.type !== "capacitor" ? 90 : 0;
  const quarterTurn = (baseRotation + rotation) % 180 === 90;
  const width = quarterTurn ? native.height : native.width;
  const height = quarterTurn ? native.width : native.height;
  const margin = 22;
  return { id: component.id, left: position.x - width / 2 - margin, right: position.x + width / 2 + margin, top: position.y - height / 2 - margin, bottom: position.y + height / 2 + margin };
}
function pathSegments(points: Point[]) { return points.slice(1).map((to, index) => ({ from: points[index], to })); }
function segmentHitsBox(from: Point, to: Point, box: ReturnType<typeof componentBox>) {
  if (from.y === to.y) return from.y > box.top && from.y < box.bottom && Math.max(from.x, to.x) > box.left && Math.min(from.x, to.x) < box.right;
  return from.x > box.left && from.x < box.right && Math.max(from.y, to.y) > box.top && Math.min(from.y, to.y) < box.bottom;
}
function segmentCrossing(from: Point, to: Point, otherFrom: Point, otherTo: Point) {
  const horizontal = from.y === to.y;
  if (horizontal === (otherFrom.y === otherTo.y)) return null;
  const line = horizontal ? { from, to } : { from: otherFrom, to: otherTo };
  const upright = horizontal ? { from: otherFrom, to: otherTo } : { from, to };
  const x = upright.from.x; const y = line.from.y;
  return x > Math.min(line.from.x, line.to.x) && x < Math.max(line.from.x, line.to.x) && y > Math.min(upright.from.y, upright.to.y) && y < Math.max(upright.from.y, upright.to.y) ? { x, y } : null;
}
function segmentOverlap(from: Point, to: Point, otherFrom: Point, otherTo: Point) {
  const horizontal = from.y === to.y;
  if (horizontal !== (otherFrom.y === otherTo.y)) return false;
  if (horizontal && from.y !== otherFrom.y) return false;
  if (!horizontal && from.x !== otherFrom.x) return false;
  const firstStart = horizontal ? Math.min(from.x, to.x) : Math.min(from.y, to.y);
  const firstEnd = horizontal ? Math.max(from.x, to.x) : Math.max(from.y, to.y);
  const secondStart = horizontal ? Math.min(otherFrom.x, otherTo.x) : Math.min(otherFrom.y, otherTo.y);
  const secondEnd = horizontal ? Math.max(otherFrom.x, otherTo.x) : Math.max(otherFrom.y, otherTo.y);
  return Math.min(firstEnd, secondEnd) - Math.max(firstStart, secondStart) > 2;
}
function routeWithObstacles(pin: PinPosition, anchor: Point & { direction?: Direction }, boxes: ReturnType<typeof componentBox>[], earlier: WirePath[]): WirePath {
  const start = escape(pin); const end = escape(anchor);
  const highest = snap(Math.min(...boxes.map((box) => box.top), start.y, end.y) - 32);
  const lowest = snap(Math.max(...boxes.map((box) => box.bottom), start.y, end.y) + 32);
  const leftmost = snap(Math.min(...boxes.map((box) => box.left), start.x, end.x) - 32);
  const rightmost = snap(Math.max(...boxes.map((box) => box.right), start.x, end.x) + 32);
  const middleX = snap((start.x + end.x) / 2); const middleY = snap((start.y + end.y) / 2);
  const candidates = [
    [pin, start, { x: start.x, y: end.y }, end, anchor],
    [pin, start, { x: middleX, y: start.y }, { x: middleX, y: end.y }, end, anchor],
    [pin, start, { x: start.x, y: highest }, { x: end.x, y: highest }, end, anchor],
    [pin, start, { x: start.x, y: lowest }, { x: end.x, y: lowest }, end, anchor],
    [pin, start, { x: leftmost, y: start.y }, { x: leftmost, y: end.y }, end, anchor],
    [pin, start, { x: rightmost, y: start.y }, { x: rightmost, y: end.y }, end, anchor],
    [pin, start, { x: start.x, y: middleY }, { x: end.x, y: middleY }, end, anchor],
  ].map(compactPath);
  const otherSegments = earlier.flatMap((wire) => pathSegments(wire.points).map((segment) => ({ ...segment, nodeId: wire.nodeId })));
  const scored = candidates.map((points) => {
    const segments = pathSegments(points);
    const componentHits = segments.reduce((count, segment, index) => count + boxes.filter((box) => !(box.id === pin.componentId && (index === 0 || index === segments.length - 1)) && segmentHitsBox(segment.from, segment.to, box)).length, 0);
    const crossings = segments.reduce((count, segment) => count + otherSegments.filter((other) => other.nodeId !== pin.nodeId && segmentCrossing(segment.from, segment.to, other.from, other.to)).length, 0);
    const overlaps = segments.reduce((count, segment) => count + otherSegments.filter((other) => other.nodeId !== pin.nodeId && segmentOverlap(segment.from, segment.to, other.from, other.to)).length, 0);
    return { points, score: componentHits * 1000 + overlaps * 80 + crossings * 20 + segments.length };
  }).sort((a, b) => a.score - b.score);
  const points = scored[0].points;
  const bridges = pathSegments(points).flatMap((segment) => otherSegments.filter((other) => other.nodeId !== pin.nodeId).map((other) => segmentCrossing(segment.from, segment.to, other.from, other.to)).filter((point): point is Point => Boolean(point)).map((point) => ({ ...point, horizontal: segment.from.y === segment.to.y })));
  return { nodeId: pin.nodeId ?? "", pin, points, bridges };
}
function Symbol({ type }: { type: ComponentType }) {
  if (type === "resistor") return <svg aria-hidden className="schematic-symbol" viewBox="0 0 116 44"><path d="M0 22H18L26 10 36 34 46 10 56 34 66 10 76 34 86 10 96 22H116" /></svg>;
  if (type === "capacitor") return <svg aria-hidden className="schematic-symbol schematic-symbol--capacitor" viewBox="0 0 44 116"><path d="M22 0V45M7 45H37M7 71H37M22 71V116" /></svg>;
  if (type === "inductor") return <svg aria-hidden className="schematic-symbol" viewBox="0 0 116 44"><path d="M0 22H18C18 4 34 4 34 22C34 4 50 4 50 22C50 4 66 4 66 22C66 4 82 4 82 22H116" /></svg>;
  if (type === "voltage_source") return <svg aria-hidden className="schematic-symbol" viewBox="0 0 116 52"><path d="M0 26H34M82 26H116M34 26A24 24 0 1 1 82 26A24 24 0 1 1 34 26M58 13V27M51 20H65M51 35H65" /></svg>;
  if (type === "diode") return <svg aria-hidden className="schematic-symbol" viewBox="0 0 116 44"><path d="M0 22H35L35 7 75 22 35 37V22M75 7V37M75 22H116" /></svg>;
  if (type === "ideal_opamp") return <svg aria-hidden className="schematic-symbol" viewBox="0 0 116 68"><path d="M0 16H26M0 52H26M26 2V66L82 34 26 2M82 34H116M12 16H22M17 11V21M12 52H22" /></svg>;
  return <svg aria-hidden className="schematic-symbol schematic-symbol--ground" viewBox="0 0 70 42"><path d="M35 0V10M14 10H56M20 17H50M27 24H43" /></svg>;
}

function StaticSymbol({ component, position }: { component: CircuitComponent; position: Point }) {
  const common = { fill: "none", stroke: "currentColor", strokeLinecap: "round" as const, strokeLinejoin: "round" as const, strokeWidth: 2 };
  const rotation = component.rotation ?? 0;
  const transform = `rotate(${rotation} ${position.x} ${position.y})`;
  if (component.type === "capacitor") return <g transform={transform}><g transform={`translate(${position.x - 22} ${position.y - 58})`}><path {...common} d="M22 0V45M7 45H37M7 71H37M22 71V116" /></g></g>;
  if (component.type === "ground") return <g transform={transform}><g transform={`translate(${position.x - 35} ${position.y - 2})`}><path {...common} d="M35 0V10M14 10H56M20 17H50M27 24H43" /></g></g>;
  const paths: Partial<Record<ComponentType, string>> = {
    resistor: "M0 22H18L26 10 36 34 46 10 56 34 66 10 76 34 86 10 96 22H116",
    inductor: "M0 22H18C18 4 34 4 34 22C34 4 50 4 50 22C50 4 66 4 66 22C66 4 82 4 82 22H116",
    voltage_source: "M0 26H34M82 26H116M34 26A24 24 0 1 1 82 26A24 24 0 1 1 34 26M58 13V27M51 20H65M51 35H65",
    diode: "M0 22H35L35 7 75 22 35 37V22M75 7V37M75 22H116",
    ideal_opamp: "M0 16H26M0 52H26M26 2V66L82 34 26 2M82 34H116M12 16H22M17 11V21M12 52H22",
  };
  return <g transform={transform}><g transform={`translate(${position.x - 58} ${position.y - (component.type === "ideal_opamp" ? 34 : component.type === "voltage_source" ? 26 : 22)})`}><path {...common} d={paths[component.type]} /></g></g>;
}

export function StaticCircuitSchematic({ circuit }: { circuit: Circuit }) {
  const positions = canonicalPositions(circuit);
  const pins = circuit.components.flatMap((component) => componentPins(component, positions[component.id] ?? { x: 240, y: 240 }, isVerticalComponent(component, circuit), isFlippedComponent(component, circuit), component.rotation ?? 0));
  const pinsByNode = circuit.nodes.reduce<Record<string, PinPosition[]>>((groups, node) => {
    groups[node.id] = pins.filter((pin) => pin.nodeId === node.id);
    return groups;
  }, {});
  const anchors = circuit.nodes.reduce<Record<string, Point>>((result, node) => {
    const netPins = pinsByNode[node.id] ?? [];
    if (node.id === "gnd") {
      const lower = netPins.reduce<Point | null>((best, pin) => !best || pin.y > best.y ? pin : best, null);
      result[node.id] = lower ? { x: snap(lower.x), y: Math.min(WORLD.height - 54, snap(lower.y + 82)) } : { x: 570, y: 480 };
    } else if (node.id === circuit.metadata.output_node && netPins.length) {
      result[node.id] = { x: Math.max(...netPins.map((pin) => pin.x)), y: Math.min(...netPins.map((pin) => pin.y)) };
    } else if (netPins.length) {
      result[node.id] = { x: snap(netPins.reduce((sum, pin) => sum + pin.x, 0) / netPins.length), y: snap(netPins.reduce((sum, pin) => sum + pin.y, 0) / netPins.length) };
    } else {
      result[node.id] = { x: 160 + Object.keys(result).length * 120, y: 460 };
    }
    return result;
  }, {});

  return <figure className="report-schematic-static">
    <svg aria-labelledby="report-schematic-title" role="img" viewBox={`0 0 ${WORLD.width} ${WORLD.height}`}>
      <title id="report-schematic-title">{circuit.name} circuit topology</title>
      <g className="report-schematic-static__wires">
        {circuit.nodes.flatMap((node) => (pinsByNode[node.id] ?? []).map((pin) => <path d={route(pin, { ...anchors[node.id], direction: node.id === "gnd" ? "top" : undefined })} key={`${node.id}-${pinKey(pin)}`} />))}
      </g>
      <g className="report-schematic-static__nodes">
        {circuit.nodes.map((node) => <g key={node.id}><circle cx={anchors[node.id].x} cy={anchors[node.id].y} r="4" /><text x={anchors[node.id].x + 9} y={anchors[node.id].y + 18}>{node.label}</text>{node.id === "gnd" ? <path d={`M${anchors[node.id].x} ${anchors[node.id].y}v10m-16 0h32m-25 7h18m-11 7h4`} /> : null}</g>)}
      </g>
      <g className="report-schematic-static__components">
        {circuit.components.map((component) => { const position = positions[component.id] ?? { x: 240, y: 240 }; const numeric = Object.entries(component.params).find((entry): entry is [string, number] => typeof entry[1] === "number"); return <g key={component.id}><StaticSymbol component={component} position={position} /><text className="report-schematic-static__reference" textAnchor="middle" x={position.x} y={position.y - (component.type === "capacitor" ? 76 : 38)}>{component.id}</text><text className="report-schematic-static__value" textAnchor="middle" x={position.x} y={position.y - (component.type === "capacitor" ? 62 : 25)}>{numeric ? engineering(numeric[1], getParameterUnit(numeric[0])) : getComponentDisplayName(component.type)}</text></g>; })}
      </g>
    </svg>
    <figcaption>Topology rendered from the recorded circuit snapshot.</figcaption>
  </figure>;
}

export function CircuitCanvas({ circuit, selectedComponentId, selectedNodeId, invalidPins, onAddComponent, onConnectPins, onConnectToNode, onSetLayout, onSelectComponent, onSelectNode, onClearSelection }: {
  circuit: Circuit;
  selectedComponentId: string | null;
  selectedNodeId: string | null;
  invalidPins: string[];
  onAddComponent: (type: ComponentType, params: Record<string, ParameterValue>, point: Point) => Promise<Circuit | null>;
  onConnectPins: (source: PinRef, target: PinRef) => void;
  onConnectToNode: (source: PinRef, nodeId: string) => void;
  onSetLayout: (componentId: string, position: Point, rotation: Rotation) => void;
  onSelectComponent: (componentId: string) => void;
  onSelectNode: (nodeId: string) => void;
  onClearSelection: () => void;
}) {
  const canvas = useRef<HTMLDivElement>(null);
  const [positions, setPositions] = useState<Record<string, Point>>(() => canonicalPositions(circuit));
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 });
  const [nodePositions, setNodePositions] = useState<Record<string, Point>>({});
  const [rotations, setRotations] = useState<Record<string, Rotation>>(() => Object.fromEntries(circuit.components.map((component) => [component.id, component.rotation ?? 0])));
  const [layoutEpoch, setLayoutEpoch] = useState(0);
  const [arranging, setArranging] = useState(false);
  const [dragging, setDragging] = useState<{ kind: "component" | "node"; id: string; offset: Point } | null>(null);
  const nodeDrag = useRef<{ id: string; offset: Point } | null>(null);
  const [panning, setPanning] = useState<{ pointer: Point; pan: Point } | null>(null);
  const [wiring, setWiring] = useState<{ source: PinRef; point: Point; hover: PinRef | null } | null>(null);
  const positionsRef = useRef(positions);
  const nodePositionsRef = useRef(nodePositions);
  const componentIdsRef = useRef(circuit.components.map((component) => component.id));

  useEffect(() => { positionsRef.current = positions; }, [positions]);
  useEffect(() => { nodePositionsRef.current = nodePositions; }, [nodePositions]);
  useEffect(() => { componentIdsRef.current = circuit.components.map((component) => component.id); }, [circuit.components]);

  useEffect(() => {
    setPositions(canonicalPositions(circuit));
    setRotations(Object.fromEntries(circuit.components.map((component) => [component.id, component.rotation ?? 0])));
    setLayoutEpoch((value) => value + 1);
  }, [circuit.id, circuit.revision]);

  const toWorld = (clientX: number, clientY: number): Point => {
    const rect = canvas.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: (clientX - rect.left - pan.x) / zoom, y: (clientY - rect.top - pan.y) / zoom };
  };
  const fitSchematic = useCallback(() => {
    const rect = canvas.current?.getBoundingClientRect();
    if (!rect) return;
    const layout = positionsRef.current;
    const points = [
      ...componentIdsRef.current.map((id) => layout[id] ?? { x: 240, y: 240 }),
      ...Object.values(nodePositionsRef.current),
    ];
    if (!points.length) { setZoom(1); setPan({ x: 0, y: 0 }); return; }
    const minX = Math.min(...points.map((point) => point.x)) - 92;
    const maxX = Math.max(...points.map((point) => point.x)) + 92;
    const minY = Math.min(...points.map((point) => point.y)) - 90;
    const maxY = Math.max(...points.map((point) => point.y)) + 116;
    const width = Math.max(maxX - minX, 180);
    const height = Math.max(maxY - minY, 160);
    const nextZoom = Math.max(.7, Math.min(1.25, (rect.width - 96) / width, (rect.height - 88) / height));
    setZoom(nextZoom);
    setPan({ x: Math.round((rect.width - width * nextZoom) / 2 - minX * nextZoom), y: Math.round((rect.height - height * nextZoom) / 2 - minY * nextZoom) });
  }, []);
  useEffect(() => {
    const frame = window.requestAnimationFrame(fitSchematic);
    return () => window.cancelAnimationFrame(frame);
  }, [circuit.id, fitSchematic, layoutEpoch]);
  const pins = useMemo(() => circuit.components.flatMap((component) => componentPins(component, positions[component.id] ?? { x: 240, y: 240 }, isVerticalComponent(component, circuit), isFlippedComponent(component, circuit), rotations[component.id] ?? 0)), [circuit, positions, rotations]);
  const pinsByNode = useMemo(() => circuit.nodes.reduce<Record<string, PinPosition[]>>((groups, node) => { groups[node.id] = pins.filter((pin) => pin.nodeId === node.id); return groups; }, {}), [circuit.nodes, pins]);
  const calculatedAnchors = useMemo(() => {
    const opamp = circuit.components.find((component) => component.type === "ideal_opamp");
    const opampPosition = opamp ? positions[opamp.id] : null;
    const source = circuit.components.find((component) => component.type === "voltage_source");
    const sourcePosition = source ? positions[source.id] : null;
    return circuit.nodes.reduce<Record<string, Point>>((result, node) => {
    const netPins = pinsByNode[node.id] ?? [];
    if (opamp && opampPosition && node.id === opamp.pins.plus) {
      const sourcePin = netPins.find((pin) => pin.componentId === source?.id);
      result[node.id] = { x: snap(((sourcePin?.x ?? opampPosition.x - 180) + (opampPosition.x - 58)) / 2), y: opampPosition.y - 18 };
    } else if (opamp && opampPosition && node.id === opamp.pins.minus) {
      result[node.id] = { x: snap(opampPosition.x - 112), y: opampPosition.y + 18 };
    } else if (opamp && opampPosition && node.id === opamp.pins.out) {
      result[node.id] = { x: snap(opampPosition.x + 132), y: opampPosition.y };
    } else if (node.id === "gnd") {
      if (opamp && sourcePosition) {
        const groundedVertical = circuit.components.find((component) => isVerticalComponent(component, circuit) && Object.values(component.pins).includes("gnd"));
        const groundedPosition = groundedVertical ? positions[groundedVertical.id] : null;
        result[node.id] = groundedPosition ? { x: groundedPosition.x, y: groundedPosition.y + 96 } : { x: sourcePosition.x, y: snap(Math.max(sourcePosition.y + 150, opampPosition?.y ? opampPosition.y + 130 : 450)) };
      }
      else {
      const lower = netPins.reduce<Point | null>((best, pin) => !best || pin.y > best.y ? pin : best, null);
      result[node.id] = lower ? { x: snap(lower.x), y: Math.min(WORLD.height - 54, snap(lower.y + 82)) } : { x: 570, y: 480 };
      }
    } else if (node.id === circuit.metadata.output_node && netPins.length) {
      result[node.id] = { x: Math.max(...netPins.map((pin) => pin.x)), y: Math.min(...netPins.map((pin) => pin.y)) };
    } else if (netPins.length) {
      result[node.id] = { x: snap(netPins.reduce((sum, pin) => sum + pin.x, 0) / netPins.length), y: snap(netPins.reduce((sum, pin) => sum + pin.y, 0) / netPins.length) };
    } else result[node.id] = { x: 160 + (Object.keys(result).length * 120), y: 460 };
    return result;
  }, {});
  }, [circuit.components, circuit.metadata.output_node, circuit.nodes, pinsByNode, positions]);
  const anchors = useMemo(() => circuit.nodes.reduce<Record<string, Point>>((result, node) => ({ ...result, [node.id]: nodePositions[node.id] ?? calculatedAnchors[node.id] }), {}), [calculatedAnchors, circuit.nodes, nodePositions]);
  const wirePaths = useMemo(() => {
    const boxes = circuit.components.map((component) => componentBox(component, positions[component.id] ?? { x: 240, y: 240 }, isVerticalComponent(component, circuit), rotations[component.id] ?? 0));
    const result: WirePath[] = [];
    circuit.nodes.forEach((node) => (pinsByNode[node.id] ?? []).forEach((pin) => {
      result.push(routeWithObstacles(pin, { ...anchors[node.id], direction: node.id === "gnd" ? "top" : undefined }, boxes, result));
    }));
    return result;
  }, [anchors, circuit.components, circuit.nodes, pinsByNode, positions, rotations]);
  const selectedComponent = circuit.components.find((component) => component.id === selectedComponentId) ?? null;
  const highlightedNodes = new Set([selectedNodeId, ...(selectedComponent ? Object.values(selectedComponent.pins).filter((value): value is string => Boolean(value)) : [])]);
  const rotateComponent = useCallback((componentId: string) => {
    const nextRotation = (((rotations[componentId] ?? 0) + 90) % 360) as Rotation;
    setRotations((current) => ({ ...current, [componentId]: nextRotation }));
    onSetLayout(componentId, positionsRef.current[componentId], nextRotation);
  }, [onSetLayout, rotations]);

  useEffect(() => {
    const rotateSelected = (event: KeyboardEvent) => {
      if (!selectedComponentId || event.key.toLowerCase() !== "r" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, select, textarea, [contenteditable='true']")) return;
      event.preventDefault();
      rotateComponent(selectedComponentId);
    };
    window.addEventListener("keydown", rotateSelected);
    return () => window.removeEventListener("keydown", rotateSelected);
  }, [rotateComponent, selectedComponentId]);

  useEffect(() => {
    if (!dragging && !panning && !wiring) return;
    const move = (event: PointerEvent) => {
      if (dragging) {
        const point = toWorld(event.clientX, event.clientY);
        const next = { x: snap(point.x - dragging.offset.x), y: snap(point.y - dragging.offset.y) };
        if (dragging.kind === "component") { positionsRef.current = { ...positionsRef.current, [dragging.id]: next }; setPositions(positionsRef.current); }
        else setNodePositions((current) => ({ ...current, [dragging.id]: next }));
      }
      if (panning) setPan({ x: panning.pan.x + event.clientX - panning.pointer.x, y: panning.pan.y + event.clientY - panning.pointer.y });
      if (wiring) {
        const target = (document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null)?.closest<HTMLElement>("[data-pin-key]");
        setWiring((current) => current ? { ...current, point: toWorld(event.clientX, event.clientY), hover: parsePinKey(target?.dataset.pinKey) } : null);
      }
    };
    const end = (event: PointerEvent) => {
      if (dragging?.kind === "component") onSetLayout(dragging.id, positionsRef.current[dragging.id], rotations[dragging.id] ?? 0);
      if (wiring) {
        const element = document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null;
        const pinTarget = element?.closest<HTMLElement>("[data-pin-key]");
        const nodeTarget = element?.closest<HTMLElement>("[data-node-id]");
        const targetPin = parsePinKey(pinTarget?.dataset.pinKey);
        const targetNode = nodeTarget?.dataset.nodeId;
        if (targetPin && pinKey(targetPin) !== pinKey(wiring.source)) onConnectPins(wiring.source, targetPin);
        if (targetNode) onConnectToNode(wiring.source, targetNode);
      }
      setDragging(null); setPanning(null); setWiring(null);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); };
  }, [dragging, onSetLayout, panning, rotations, wiring]);

  const startMove = (event: React.PointerEvent, component: CircuitComponent) => {
    if ((event.target as HTMLElement).closest("[data-pin-key]")) return;
    event.preventDefault();
    onSelectComponent(component.id);
    const point = toWorld(event.clientX, event.clientY); const position = positions[component.id];
    setDragging({ kind: "component", id: component.id, offset: { x: point.x - position.x, y: point.y - position.y } });
  };
  const startNodeMove = (event: React.PointerEvent, nodeId: string) => {
    event.preventDefault(); event.stopPropagation();
    onSelectNode(nodeId);
    const point = toWorld(event.clientX, event.clientY); const position = anchors[nodeId];
    nodeDrag.current = { id: nodeId, offset: { x: point.x - position.x, y: point.y - position.y } };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveNode = (event: React.PointerEvent) => {
    if (!nodeDrag.current) return;
    const point = toWorld(event.clientX, event.clientY);
    setNodePositions((current) => ({ ...current, [nodeDrag.current!.id]: { x: snap(point.x - nodeDrag.current!.offset.x), y: snap(point.y - nodeDrag.current!.offset.y) } }));
  };
  const finishNodeMove = (event: React.PointerEvent) => {
    if (!nodeDrag.current) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    nodeDrag.current = null;
  };
  const startWire = (event: React.PointerEvent, source: PinRef) => {
    event.preventDefault(); event.stopPropagation();
    onSelectComponent(source.componentId);
    setWiring({ source, point: toWorld(event.clientX, event.clientY), hover: null });
  };
  const drop = async (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const raw = event.dataTransfer.getData("application/x-electronics-component");
    if (!raw) return;
    const { type, params } = JSON.parse(raw) as { type: ComponentType; params: Record<string, ParameterValue> };
    const point = toWorld(event.clientX, event.clientY);
    const updated = await onAddComponent(type, params, point);
    const added = updated?.components.find((component) => !circuit.components.some((current) => current.id === component.id));
    if (added) setPositions((current) => ({ ...current, [added.id]: added.position ?? { x: snap(point.x), y: snap(point.y) } }));
  };
  const previewStart = wiring ? pins.find((pin) => pinKey(pin) === pinKey(wiring.source)) : null;
  const autoArrange = async () => {
    setArranging(true);
    try {
      const updated = await api.autoLayoutCircuit(circuit.revision, false);
      setPositions(canonicalPositions(updated));
      setRotations(Object.fromEntries(updated.components.map((component) => [component.id, component.rotation ?? 0])));
      setLayoutEpoch((value) => value + 1);
      window.dispatchEvent(new CustomEvent("circuit-layout-changed", { detail: { before: circuit, after: updated } }));
    } catch (reason) {
      window.dispatchEvent(new CustomEvent("circuit-layout-error", { detail: reason instanceof Error ? reason.message : "Could not arrange the circuit." }));
    } finally {
      setArranging(false);
    }
  };

  return <section className="canvas-panel panel" aria-label="Circuit canvas">
    <div className="canvas-heading"><div><p className="section-kicker">Circuit</p><span>{circuit.name}</span></div><div className="canvas-heading__actions"><span className="canvas-note">Drag empty space to pan. Drag parts or named nodes to move.</span><button disabled={arranging || circuit.components.length < 2} onClick={() => void autoArrange()} title="Arrange components from circuit connectivity" type="button">{arranging ? "Arranging…" : "Auto arrange"}</button></div></div>
    <div className="canvas" onDragOver={(event) => event.preventDefault()} onDrop={drop} onPointerDown={(event) => { const target = event.target as HTMLElement; if (!target.closest("button, .schematic-component, .schematic-net, [data-pin-key]")) { onClearSelection(); event.currentTarget.setPointerCapture(event.pointerId); setPanning({ pointer: { x: event.clientX, y: event.clientY }, pan }); } }} ref={canvas} role="application" aria-label={`${circuit.name} schematic editor`}>
      <svg aria-hidden className="schematic-grid" viewBox={`0 0 ${WORLD.width} ${WORLD.height}`}><defs><pattern height={GRID} id="workbench-grid" patternUnits="userSpaceOnUse" width={GRID}><circle cx="1" cy="1" fill="currentColor" r="0.65" /></pattern></defs><rect fill="url(#workbench-grid)" height="100%" width="100%" /></svg>
      <div className="schematic-world" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
        <svg className="schematic-wires" height={WORLD.height} viewBox={`0 0 ${WORLD.width} ${WORLD.height}`} width={WORLD.width}>
          {circuit.nodes.map((node) => {
            const netPins = pinsByNode[node.id] ?? []; const anchor = anchors[node.id]; const highlighted = highlightedNodes.has(node.id); const paths = wirePaths.filter((wire) => wire.nodeId === node.id);
            return <g aria-label={`${node.label} net`} className={`schematic-net ${highlighted ? "schematic-net--selected" : ""}`} key={node.id} onClick={() => onSelectNode(node.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectNode(node.id); } }} role="button" tabIndex={0}>
              {paths.map((wire) => <path d={pathFromPointsWithBridges(wire.points, wire.bridges)} key={pinKey(wire.pin)} />)}
              {netPins.length > 1 && <circle className="net-junction" cx={anchor.x} cy={anchor.y} r="3.5" />}
            </g>;
          })}
          {wiring && previewStart && <path className="schematic-preview-wire" d={route(previewStart, wiring.point)} />}
        </svg>
        {circuit.nodes.map((node) => {
          const anchor = anchors[node.id]; const selected = selectedNodeId === node.id;
          return <button className={`net-label ${selected ? "net-label--selected" : ""} ${node.id === "gnd" ? "net-label--ground" : ""}`} data-node-id={node.id} key={node.id} onClick={() => onSelectNode(node.id)} onPointerDown={(event) => startNodeMove(event, node.id)} onPointerMove={moveNode} onPointerUp={finishNodeMove} style={{ left: anchor.x, top: anchor.y }} type="button">{node.id === "gnd" && <svg aria-hidden className="ground-symbol" viewBox="0 0 36 28"><path d="M18 0V7M3 7H33M8 13H28M13 19H23" /></svg>}<span>{node.label}</span>{selected && <b>V</b>}</button>;
        })}
        {circuit.components.map((component) => {
          const position = positions[component.id] ?? { x: 240, y: 240 }; const selected = component.id === selectedComponentId; const vertical = isVerticalComponent(component, circuit); const rotation = rotations[component.id] ?? 0; const symbolRotation = (vertical && component.type !== "capacitor" ? 90 : 0) + rotation;
          const numeric = Object.entries(component.params).find((entry): entry is [string, number] => typeof entry[1] === "number");
          return <div aria-label={`${component.id} ${getComponentDisplayName(component.type)}`} className={`schematic-component schematic-component--${component.type} ${vertical ? "schematic-component--vertical" : ""} ${selected ? "schematic-component--selected" : ""}`} key={component.id} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectComponent(component.id); } }} onPointerDown={(event) => startMove(event, component)} role="button" style={{ left: position.x, top: position.y }} tabIndex={0}>
            <span className="schematic-component__meta"><strong>{component.id}</strong><span>{numeric ? engineering(numeric[1], getParameterUnit(numeric[0])) : getComponentDisplayName(component.type)}</span></span>
            <span className="schematic-component__symbol-wrap" style={{ transform: `rotate(${symbolRotation}deg)` }}><Symbol type={component.type} /></span>
            {selected && <button aria-label={`Rotate ${component.id} clockwise`} className="schematic-component__rotate" onClick={() => rotateComponent(component.id)} onPointerDown={(event) => { event.preventDefault(); event.stopPropagation(); }} title="Rotate clockwise (R)" type="button"><ArrowClockwiseIcon aria-hidden size={15} /></button>}
            {componentPins(component, position, vertical, isFlippedComponent(component, circuit), rotation).map((pin) => {
              const key = pinKey(pin); const compatible = Boolean(wiring && pinKey(wiring.source) !== key); const active = selected || highlightedNodes.has(pin.nodeId ?? "") || (wiring?.hover && pinKey(wiring.hover) === key) || (wiring?.source && pinKey(wiring.source) === key) || compatible;
              const polarity = component.type === "voltage_source" ? pin.pin === "positive" ? "+" : pin.pin === "negative" ? "−" : null : null;
              return <button aria-label={`${component.id} ${pin.label} terminal`} className={`schematic-pin ${active ? "schematic-pin--visible" : ""} ${compatible ? "schematic-pin--compatible" : ""} ${invalidPins.includes(key) ? "schematic-pin--invalid" : ""} ${polarity ? "schematic-pin--polarized" : ""}`} data-direction={pin.direction} data-pin-key={key} key={key} onPointerDown={(event) => startWire(event, pin)} style={{ left: pin.x - position.x + 71, top: pin.y - position.y + 71 }} type="button"><span aria-hidden className="schematic-pin__target" />{polarity && <b aria-hidden className="schematic-pin__polarity">{polarity}</b>}</button>;
            })}
          </div>;
        })}
      </div>
      <div className="canvas-controls" aria-label="Canvas view controls"><button aria-label="Zoom in" disabled={zoom >= 1.35} onClick={() => setZoom((value) => Math.min(1.35, value + .1))} title="Zoom in" type="button"><PlusIcon aria-hidden size={15} /></button><button aria-label="Zoom out" disabled={zoom <= .7} onClick={() => setZoom((value) => Math.max(.7, value - .1))} title="Zoom out" type="button"><MinusIcon aria-hidden size={15} /></button><button aria-label="Fit schematic" onClick={fitSchematic} title="Fit schematic" type="button"><CornersOutIcon aria-hidden size={15} /></button></div>
    </div>
  </section>;
}
