import type { ReactNode } from "react";

export function PropertyRow({ label, value, className = "" }: { label: ReactNode; value: ReactNode; className?: string }) {
  return <div className={`property-row ${className}`.trim()}><span>{label}</span><div className="property-row__value">{value}</div></div>;
}
