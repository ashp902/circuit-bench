"use client";

import type { WebMCPDiagnostics as Diagnostics } from "@/lib/useWebMCP";

export function WebMCPDiagnostics({ diagnostics }: { diagnostics: Diagnostics }) {
  if (!diagnostics.enabled) return null;
  return <aside aria-label="WebMCP diagnostics" className="webmcp-diagnostics">
    <header><span>Developer diagnostics</span><strong>{diagnostics.overall}</strong></header>
    <dl><div><dt>document.modelContext</dt><dd>{String(diagnostics.documentModelContext)}</dd></div><div><dt>navigator.modelContext fallback</dt><dd>{String(diagnostics.navigatorModelContext)}</dd></div><div><dt>registerTool</dt><dd>{String(diagnostics.registerTool)}</dd></div><div><dt>Backend tools</dt><dd>{diagnostics.backend.status} ({diagnostics.backend.toolCount})</dd></div></dl>
    {diagnostics.backend.error && <p className="webmcp-diagnostics__error">{diagnostics.backend.error.name}: {diagnostics.backend.error.message}</p>}
    <section><h2>Registration attempts</h2>{diagnostics.registrations.length ? <ul>{diagnostics.registrations.map((registration, index) => <li key={`${registration.name}-${index}`}><b>{registration.name}</b><span className={registration.status === "SUCCESS" ? "webmcp-diagnostics__success" : "webmcp-diagnostics__error"}>{registration.status}{registration.error ? `: ${registration.error.name}: ${registration.error.message}` : ""}</span></li>)}</ul> : <p>Waiting for registration.</p>}</section>
    {diagnostics.registeredTools && <section><h2>Browser registered tools ({diagnostics.registeredTools.count})</h2>{diagnostics.registeredTools.error ? <p className="webmcp-diagnostics__error">{diagnostics.registeredTools.error.name}: {diagnostics.registeredTools.error.message}</p> : <p>{diagnostics.registeredTools.names.join(", ") || "No tool names returned."}</p>}</section>}
  </aside>;
}
