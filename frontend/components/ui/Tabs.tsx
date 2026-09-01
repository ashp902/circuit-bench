import type { ReactNode } from "react";

export type TabItem<T extends string> = { id: T; label: ReactNode };

export function Tabs<T extends string>({ active, ariaLabel, items, onChange, className = "" }: { active: T; ariaLabel: string; items: TabItem<T>[]; onChange: (id: T) => void; className?: string }) {
  return <nav aria-label={ariaLabel} className={`tabs ${className}`.trim()} onKeyDown={(event) => { if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return; const current = items.findIndex((item) => item.id === active); const offset = event.key === "ArrowRight" ? 1 : -1; const next = items[(current + offset + items.length) % items.length]; event.preventDefault(); onChange(next.id); event.currentTarget.querySelectorAll<HTMLButtonElement>("button")[items.findIndex((item) => item.id === next.id)]?.focus(); }}>{items.map((item) => <button aria-current={active === item.id ? "page" : undefined} className={active === item.id ? "is-active" : ""} key={item.id} onClick={() => onChange(item.id)} type="button">{item.label}</button>)}</nav>;
}
