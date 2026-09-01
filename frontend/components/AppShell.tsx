import type { ReactNode } from "react";

import { Tabs } from "@/components/ui/Tabs";
import { StatusIndicator } from "@/components/ui/StatusIndicator";

export type Workspace = "workbench" | "experiments" | "reports";

export function AppShell({ activeWorkspace, children, projectControl, onWorkspaceChange, working }: { activeWorkspace: Workspace; children: ReactNode; projectControl: ReactNode; onWorkspaceChange: (workspace: Workspace) => void; working: boolean }) {
  return <main className="lab-app app-shell">
    <header className="app-header">
      <div className="app-header__identity"><span className="app-mark" aria-hidden="true">EL</span><h1>Virtual Electronics Laboratory</h1></div>
      <div className="app-header__project">{projectControl}</div>
      <div className="app-header__actions"><StatusIndicator tone={working ? "warning" : "neutral"}>{working ? "Working" : "Ready"}</StatusIndicator></div>
    </header>
    <Tabs active={activeWorkspace} ariaLabel="Main navigation" className="app-tabs" items={[{ id: "workbench", label: "Workbench" }, { id: "experiments", label: "Experiments" }, { id: "reports", label: "Reports" }]} onChange={onWorkspaceChange} />
    {children}
  </main>;
}
