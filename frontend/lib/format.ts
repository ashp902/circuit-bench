import type { ComponentType, Constraint } from "@/lib/types";
import { componentDisplayNames, formatEngineeringValue, getParameterValueLabel } from "@/lib/presentation";

export const componentLabel: Record<ComponentType, string> = componentDisplayNames;

export function engineering(value: number, unit = ""): string {
  return formatEngineeringValue(value, unit);
}

export function constraintText(constraint: Constraint): string {
  const target = Array.isArray(constraint.target) ? `${constraint.target[0]} - ${constraint.target[1]}` : constraint.target;
  return `${getParameterValueLabel(constraint.metric)} ${constraint.operator} ${target}`;
}
