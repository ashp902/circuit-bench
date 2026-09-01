"use client";

import { TrashIcon } from "@phosphor-icons/react";

import { api } from "@/lib/api";
import { getComponentDisplayName, getParameterValueLabel } from "@/lib/presentation";
import type { Circuit, CircuitComponent, CircuitNode } from "@/lib/types";
import { type EngineeringUnit, NumericUnitInput } from "@/components/ui/NumericUnitInput";

function parameterUnits(parameter: string): EngineeringUnit[] {
  if (parameter.endsWith("_ohm")) return [{ label: "MΩ", multiplier: 1e6 }, { label: "kΩ", multiplier: 1e3 }, { label: "Ω", multiplier: 1 }];
  if (parameter.endsWith("_f")) return [{ label: "mF", multiplier: 1e-3 }, { label: "µF", multiplier: 1e-6 }, { label: "nF", multiplier: 1e-9 }, { label: "pF", multiplier: 1e-12 }];
  if (parameter.endsWith("_h")) return [{ label: "H", multiplier: 1 }, { label: "mH", multiplier: 1e-3 }, { label: "µH", multiplier: 1e-6 }];
  if (parameter.endsWith("_v")) return [{ label: "kV", multiplier: 1e3 }, { label: "V", multiplier: 1 }, { label: "mV", multiplier: 1e-3 }];
  return [{ label: "", multiplier: 1 }];
}

type Props = {
  circuit: Circuit;
  component: CircuitComponent | null;
  selectedNode?: CircuitNode | null;
  probeNodeId?: string | null;
  onDelete: (id: string) => void;
  onSetValue: (id: string, parameter: string, value: number) => void;
  onConnect: (id: string, pin: string, nodeId: string) => void;
  onDisconnect?: (id: string, pin: string) => void;
  onRenameNode?: (id: string, label: string) => void;
  onSetProbe?: (nodeId: string) => void;
};

export function PropertyInspector({ circuit, component, selectedNode, probeNodeId, onDelete, onSetValue, onConnect, onDisconnect, onRenameNode, onSetProbe }: Props) {
  const disconnect = (id: string, pin: string) => {
    if (onDisconnect) onDisconnect(id, pin);
    else void api.disconnect(id, pin, circuit.revision);
  };

  if (!component && selectedNode) {
    const terminals = circuit.components.flatMap((item) => Object.entries(item.pins).filter(([, nodeId]) => nodeId === selectedNode.id).map(([pin]) => ({ componentId: item.id, pin })));
    const isProbe = probeNodeId === selectedNode.id;
    return <aside className="inspector panel" aria-label={`${selectedNode.label} net inspector`}>
      <div className="panel-title"><div><p className="section-kicker">Inspector</p><h2>{selectedNode.label}</h2><p className="type-label">Electrical net</p></div></div>
      {selectedNode.id !== "gnd" && <section className="inspector-section"><h3>Net name</h3><input aria-label="Net name" defaultValue={selectedNode.label} onBlur={(event) => { const label = event.currentTarget.value.trim(); if (label && label !== selectedNode.label) onRenameNode?.(selectedNode.id, label); }} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }} /></section>}
      <section className="inspector-section"><h3>Measurement</h3><p className="inspector-helper">The active voltage probe determines which net is recorded by a quick simulation.</p><button className={`button button--secondary inspector-probe-button${isProbe ? " inspector-probe-button--active" : ""}`} disabled={isProbe} onClick={() => onSetProbe?.(selectedNode.id)} type="button">{isProbe ? "Active voltage probe" : "Measure voltage here"}</button></section>
      <section className="inspector-section"><h3>Connections</h3><div className="property-group">{terminals.length ? terminals.map((terminal) => <div className="property-row" key={`${terminal.componentId}.${terminal.pin}`}><span>{terminal.componentId}.{terminal.pin}</span><button onClick={() => disconnect(terminal.componentId, terminal.pin)} type="button">Disconnect</button></div>) : <p className="inspector-empty">No component terminals are attached to this net.</p>}</div></section>
    </aside>;
  }
  if (!component) return <aside className="inspector panel"><div className="panel-title"><div><p className="section-kicker">Inspector</p><h2>Select an item</h2></div></div><div className="inspector-empty"><p>Select a component, wire, or node to inspect it.</p></div></aside>;
  const numericParams = Object.entries(component.params).filter((entry): entry is [string, number] => typeof entry[1] === "number");
  return <aside className="inspector panel" aria-label={`${component.id} property inspector`}>
    <div className="panel-title"><div><p className="section-kicker">Properties</p><h2>{component.id}</h2><p className="type-label">{getComponentDisplayName(component.type)}</p></div></div>
    <section className="inspector-section" aria-label="Component values"><h3>Values</h3><div className="property-group">{numericParams.map(([parameter, value]) => <div className="property-row property-row--input" key={parameter}><span>{getParameterValueLabel(parameter)}</span><NumericUnitInput ariaLabel={`${component.id} ${getParameterValueLabel(parameter)}`} onCommit={(next) => onSetValue(component.id, parameter, next)} units={parameterUnits(parameter)} value={value} /></div>)}</div></section>
    {component.type !== "ground" && <section className="inspector-section"><h3>Measurement</h3><p className="inspector-helper">This component is the active current probe. Run a simulation to record its ngspice branch current.</p></section>}
    {Object.keys(component.pins).length > 0 && <section className="inspector-section pin-editor" aria-label="Electrical connections"><h3>Connections</h3><p className="inspector-helper">Wire terminals directly on the canvas. These controls are for reviewing or retargeting a net.</p>{Object.entries(component.pins).map(([pin, nodeId]) => <label className="pin-select" key={pin}><span>{pin}</span><select aria-label={`${component.id} ${pin} node`} onChange={(event) => { if (event.target.value) onConnect(component.id, pin, event.target.value); else if (nodeId) disconnect(component.id, pin); }} value={nodeId ?? ""}><option value="">Unconnected</option>{circuit.nodes.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select></label>)}</section>}
    <details className="advanced-properties"><summary>Advanced</summary><div className="property-row"><span>Reference</span><strong>{component.id}</strong></div><div className="property-row"><span>Type</span><strong>{component.type}</strong></div></details>
    <button className="danger-button" onClick={() => onDelete(component.id)} type="button"><TrashIcon aria-hidden size={16} />Delete component</button>
  </aside>;
}
