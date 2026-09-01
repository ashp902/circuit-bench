"use client";

import { useState } from "react";
import { MagnifyingGlassIcon } from "@phosphor-icons/react";

import { getComponentDisplayName } from "@/lib/presentation";
import type { ComponentType, ParameterValue } from "@/lib/types";

const defaults: Record<ComponentType, Record<string, ParameterValue>> = { resistor: { resistance_ohm: 1_000 }, capacitor: { capacitance_f: 100e-9 }, inductor: { inductance_h: 1e-3 }, voltage_source: { mode: "dc", voltage_v: 1 }, diode: { model: "D" }, ideal_opamp: { gain: 100_000 }, ground: {} };
const glyphs: Record<ComponentType, string> = { resistor: "R", capacitor: "C", inductor: "L", voltage_source: "V", diode: "D", ideal_opamp: "A", ground: "G" };
const groups: Array<{ name: string; types: ComponentType[] }> = [{ name: "Passive", types: ["resistor", "capacitor", "inductor"] }, { name: "Sources", types: ["voltage_source"] }, { name: "Semiconductor", types: ["diode", "ideal_opamp"] }, { name: "Utility", types: ["ground"] }];

export function ComponentTray({ allowed, onAdd }: { allowed: ComponentType[]; onAdd: (type: ComponentType, params: Record<string, ParameterValue>) => void }) {
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const matches = groups.flatMap((group) => group.types).filter((type) => allowed.includes(type) && getComponentDisplayName(type).toLowerCase().includes(query));
  return <section className="component-tray panel" aria-label="Component library">
    <div className="panel-title"><div><p className="section-kicker">Components</p><h2>Library</h2></div></div>
    <label className="component-search"><MagnifyingGlassIcon aria-hidden size={14} /><input aria-label="Search components" onChange={(event) => setSearch(event.target.value)} placeholder="Search components" value={search} /></label>
    <div className="component-groups">{matches.length ? groups.map((group) => {
      const groupMatches = group.types.filter((type) => matches.includes(type));
      if (!groupMatches.length) return null;
      return <section className="component-group" key={group.name}><h3>{group.name}</h3>{groupMatches.map((type) => <button className="component-button" draggable key={type} onClick={() => onAdd(type, defaults[type])} onDragStart={(event) => { event.dataTransfer.effectAllowed = "copy"; event.dataTransfer.setData("application/x-electronics-component", JSON.stringify({ type, params: defaults[type] })); }} title={`Add ${getComponentDisplayName(type)}`} type="button"><span className="component-glyph">{glyphs[type]}</span><span>{getComponentDisplayName(type)}</span><small aria-hidden>Drag</small></button>)}</section>;
    }) : <div className="component-search-empty"><strong>No matching components</strong><span>Try a component name such as resistor or source.</span></div>}</div>
    <p className="tray-hint">Drag onto the canvas for precise placement. Click to add near the center.</p>
  </section>;
}
