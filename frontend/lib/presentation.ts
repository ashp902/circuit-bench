import type { ComponentType, ExperimentCriterion } from "@/lib/types";

export const componentDisplayNames: Record<ComponentType, string> = {
  resistor: "Resistor",
  capacitor: "Capacitor",
  inductor: "Inductor",
  voltage_source: "Voltage Source",
  diode: "Diode",
  ideal_opamp: "Ideal Op-Amp",
  ground: "Ground",
};

const parameterNames: Record<string, string> = {
  resistance_ohm: "Resistance",
  capacitance_f: "Capacitance",
  inductance_h: "Inductance",
  voltage_v: "Voltage",
  frequency_hz: "Frequency",
  gain: "Gain",
};

const measurementNames: Record<string, string> = {
  "voltage:out": "Output Voltage",
  "voltage:vout": "Output Voltage",
  "voltage:vin": "Input Voltage",
  output_voltage: "Output Voltage",
  "Output Voltage": "Output Voltage",
  ac_gain: "AC Gain",
  "AC Gain": "AC Gain",
  cutoff_frequency_hz: "Cutoff Frequency",
  "Cutoff Frequency Hz": "Cutoff Frequency",
};

const unitScales = [
  { threshold: 1e9, divisor: 1e9, prefix: "G" },
  { threshold: 1e6, divisor: 1e6, prefix: "M" },
  { threshold: 1e3, divisor: 1e3, prefix: "k" },
  { threshold: 1, divisor: 1, prefix: "" },
  { threshold: 1e-3, divisor: 1e-3, prefix: "m" },
  { threshold: 1e-6, divisor: 1e-6, prefix: "µ" },
  { threshold: 1e-9, divisor: 1e-9, prefix: "n" },
  { threshold: 0, divisor: 1e-12, prefix: "p" },
] as const;

export function getComponentDisplayName(type: ComponentType) {
  return componentDisplayNames[type];
}

export function getParameterDisplayName(componentId: string, parameter: string) {
  if (componentId === "V1" && parameter === "voltage_v") return "Input Voltage";
  const parameterName = parameterNames[parameter] ?? parameter.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
  return `${componentId} ${parameterName}`;
}

export function getParameterReferenceLabel(componentId: string, parameter: string) {
  const name = getParameterDisplayName(componentId, parameter);
  return name === "Input Voltage" ? `${name} · ${componentId}` : name;
}

export function getParameterValueLabel(parameter: string) {
  return parameterNames[parameter] ?? parameter.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function getMeasurementDisplayName(metric: string) {
  if (metric.startsWith("current_a:")) return `${metric.slice("current_a:".length)} Current`;
  if (metric.startsWith("current_magnitude_a:")) return `${metric.slice("current_magnitude_a:".length)} Current Magnitude`;
  if (metric.startsWith("Branch Current:")) return `${metric.slice("Branch Current:".length)} Current`;
  if (metric.startsWith("voltage_v:")) {
    const node = metric.slice("voltage_v:".length);
    if (node === "out" || node === "vout") return "Output Voltage";
    if (node === "in" || node === "vin") return "Input Voltage";
    return `${node.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase())} Voltage`;
  }
  return measurementNames[metric] ?? metric.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function getMeasurementUnit(metric: string) {
  if (metric.startsWith("current_a:") || metric.startsWith("current_magnitude_a:") || metric.startsWith("Branch Current:")) return "A";
  if (metric.startsWith("voltage_v:") || metric === "Output Voltage" || metric === "output_voltage") return "V";
  if (metric.includes("gain") || metric === "AC Gain") return "dB";
  if (metric === "cutoff_frequency_hz" || metric === "Cutoff Frequency Hz") return "Hz";
  return "";
}

export function formatCriterionDefinition(criterion: ExperimentCriterion) {
  const unit = getMeasurementUnit(criterion.metric);
  if (criterion.operator === "between" && Array.isArray(criterion.target)) return `${formatEngineeringValue(criterion.target[0], unit)} to ${formatEngineeringValue(criterion.target[1], unit)}`;
  if (criterion.operator === "approximately") return `${formatEngineeringValue(Number(criterion.target), unit)} ± ${formatEngineeringValue(criterion.tolerance ?? 0, unit)}`;
  return `${criterion.operator === ">=" ? "minimum" : "maximum"} ${formatEngineeringValue(Number(criterion.target), unit)}`;
}

export function getParameterUnit(parameter: string) {
  if (parameter.endsWith("_ohm")) return "Ω";
  if (parameter.endsWith("_f")) return "F";
  if (parameter.endsWith("_h")) return "H";
  if (parameter.endsWith("_hz")) return "Hz";
  if (parameter.endsWith("_s")) return "s";
  if (parameter.endsWith("_v")) return "V";
  return "";
}

export function formatEngineeringValue(value: number, unit = "", significantDigits = 3): string {
  if (!Number.isFinite(value)) return "Not available";
  if (value === 0) return `0 ${unit}`.trim();
  const scale = unitScales.find((item) => Math.abs(value) >= item.threshold) ?? unitScales.at(-1)!;
  const scaled = value / scale.divisor;
  const decimalPlaces = Math.max(0, significantDigits - 1 - Math.floor(Math.log10(Math.abs(scaled))));
  const formatted = scaled.toLocaleString(undefined, unit ? { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces } : { maximumFractionDigits: decimalPlaces });
  return `${formatted} ${scale.prefix}${unit}`.trim();
}

export function formatExperimentType(type?: string) {
  if (!type) return "Manual";
  return type.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatExecutionStatus(status?: string) {
  const labels: Record<string, string> = {
    draft: "Draft",
    ready: "Ready",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    interrupted: "Stopped",
    paused: "Paused",
  };
  return labels[status ?? ""] ?? "Draft";
}

export function formatResultStatus(status?: string) {
  const labels: Record<string, string> = {
    PASS: "Pass",
    FAIL: "Fail",
    COMPLETED: "Completed",
    FAILED: "Simulation Error",
    SKIPPED: "Skipped",
    NOT_EVALUATED: "Not Evaluated",
  };
  return labels[status ?? ""] ?? "Not Available";
}
