"use client";

import { useEffect, useRef, useState } from "react";
import { CaretDownIcon, PlusIcon, TrashIcon } from "@phosphor-icons/react";

import type { ChallengeSummary, SavedCircuitSummary } from "@/lib/types";

export function ChallengeSelector({ activeId, activeSavedCircuitId, activeTitle, challenges, disabled, onCreateBlank, onDeleteSaved, onLoad, onOpenSaved, savedCircuits }: { activeId: string; activeSavedCircuitId: string | null; activeTitle: string; challenges: ChallengeSummary[]; disabled: boolean; onCreateBlank: () => void; onDeleteSaved: (id: string) => void; onLoad: (id: string) => void; onOpenSaved: (id: string) => void; savedCircuits: SavedCircuitSummary[] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const active = challenges.find((challenge) => challenge.id === activeId);
  useEffect(() => {
    const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, []);
  const navigateMenu = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") { setOpen(false); root.current?.querySelector<HTMLButtonElement>(".project-switcher__trigger")?.focus(); return; }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("[role='menuitem']")];
    const index = Math.max(0, buttons.indexOf(document.activeElement as HTMLButtonElement));
    event.preventDefault();
    buttons[(index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
  };
  return <div className="project-switcher" ref={root}>
    <button aria-expanded={open} aria-haspopup="menu" className="project-switcher__trigger" disabled={disabled} onClick={() => setOpen((current) => !current)} type="button">{active?.title ?? activeTitle}<CaretDownIcon aria-hidden size={13} /></button>
    {open && <div aria-label="Circuit switcher" className="project-switcher__menu" onKeyDown={navigateMenu} role="menu">
      <button className="project-switcher__new" disabled={disabled} onClick={() => { setOpen(false); onCreateBlank(); }} role="menuitem" type="button"><PlusIcon aria-hidden size={15} />New circuit</button>
      {savedCircuits.length > 0 && <section className="project-switcher__saved">
        {savedCircuits.map((circuit) => <div className={circuit.id === activeSavedCircuitId ? "is-active" : ""} key={circuit.id}>
          <button aria-current={circuit.id === activeSavedCircuitId ? "page" : undefined} disabled={disabled} onClick={() => { setOpen(false); onOpenSaved(circuit.id); }} role="menuitem" type="button">{circuit.name}</button>
          <button aria-label={`Delete ${circuit.name}`} className="project-switcher__delete" disabled={disabled} onClick={() => onDeleteSaved(circuit.id)} title={`Delete ${circuit.name}`} type="button"><TrashIcon aria-hidden size={14} /></button>
        </div>)}
      </section>}
      <section className="project-switcher__templates">
        {challenges.map((challenge) => <button aria-current={challenge.id === activeId && activeSavedCircuitId === null ? "page" : undefined} className={challenge.id === activeId && activeSavedCircuitId === null ? "is-active" : ""} disabled={disabled} key={challenge.id} onClick={() => { setOpen(false); onLoad(challenge.id); }} role="menuitem" type="button">{challenge.title}</button>)}
      </section>
    </div>}
  </div>;
}
