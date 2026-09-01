"use client";

import { useEffect, useState } from "react";

export type EngineeringUnit = { label: string; multiplier: number };
type NumericUnitInputProps = { ariaLabel: string; value: number; units: EngineeringUnit[]; onCommit: (value: number) => void; disabled?: boolean };

function closestUnit(value: number, units: EngineeringUnit[]) {
  if (value === 0) return units.find((unit) => unit.multiplier === 1) ?? units[0];
  return units.find((unit) => Math.abs(value) >= unit.multiplier) ?? units.at(-1) ?? units[0];
}

export function NumericUnitInput({ ariaLabel, value, units, onCommit, disabled = false }: NumericUnitInputProps) {
  const [unit, setUnit] = useState(() => closestUnit(value, units));
  const [displayValue, setDisplayValue] = useState(() => String(value / unit.multiplier));
  useEffect(() => { const nextUnit = closestUnit(value, units); setUnit(nextUnit); setDisplayValue(String(value / nextUnit.multiplier)); }, [value]);
  const commit = () => { const next = Number(displayValue) * unit.multiplier; if (Number.isFinite(next) && next !== value) onCommit(next); };
  return <div className="numeric-unit-input"><input aria-label={ariaLabel} disabled={disabled} inputMode="decimal" onBlur={commit} onChange={(event) => setDisplayValue(event.currentTarget.value)} type="number" value={displayValue} /><select aria-label={`${ariaLabel} unit`} disabled={disabled} onChange={(event) => { const nextUnit = units.find((item) => item.label === event.target.value) ?? unit; setUnit(nextUnit); setDisplayValue(String((Number(displayValue) * unit.multiplier) / nextUnit.multiplier)); }} value={unit.label}>{units.map((item) => <option key={item.label} value={item.label}>{item.label}</option>)}</select></div>;
}
