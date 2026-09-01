"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { WebMCPDefinition } from "@/lib/types";

type ToolRegistration = { name: string; description: string; inputSchema: Record<string, unknown>; annotations?: { readOnlyHint?: boolean }; execute: (input: Record<string, unknown>) => Promise<unknown> };
type ModelContext = { registerTool: (tool: ToolRegistration) => Promise<void>; getTools?: () => Promise<unknown> | unknown };
declare global { interface Document { modelContext?: ModelContext; } interface Navigator { modelContext?: ModelContext; } }

export type WebMCPStatus = "registering" | "available" | "unsupported" | "error";
type Registration = { name: string; status: "SUCCESS" | "FAILED"; error?: { name: string; message: string } };
export type WebMCPDiagnostics = {
  enabled: boolean; documentModelContext: boolean; navigatorModelContext: boolean; registerTool: boolean;
  backend: { status: "not attempted" | "success" | "failed"; toolCount: number; error?: { name: string; message: string } };
  registrations: Registration[]; registeredTools?: { count: number; names: string[]; error?: { name: string; message: string } };
  overall: "WebMCP unavailable in browser" | "backend tools unavailable" | "registration failed" | "registered successfully" | "checking";
};

// Diagnostics are intentionally disabled in all environments. Keep the
// registration/integration logic active, but do not expose the developer
// diagnostics panel in the laboratory UI.
const diagnosticsEnabled = false;
const initialDiagnostics: WebMCPDiagnostics = { enabled: diagnosticsEnabled, documentModelContext: false, navigatorModelContext: false, registerTool: false, backend: { status: "not attempted", toolCount: 0 }, registrations: [], overall: "checking" };
const errorDetails = (error: unknown) => error instanceof Error ? { name: error.name, message: error.message } : { name: "Error", message: String(error) };
const validJsonSchema = (value: unknown): value is Record<string, unknown> => { if (!value || typeof value !== "object" || Array.isArray(value)) return false; try { JSON.stringify(value); return true; } catch { return false; } };
const registeredNames = (tools: unknown): string[] => Array.isArray(tools) ? tools.flatMap((tool) => tool && typeof tool === "object" && typeof (tool as { name?: unknown }).name === "string" ? [(tool as { name: string }).name] : []) : [];

export function useWebMCP(): { status: WebMCPStatus; diagnostics: WebMCPDiagnostics } {
  const [status, setStatus] = useState<WebMCPStatus>("registering");
  const [diagnostics, setDiagnostics] = useState<WebMCPDiagnostics>(initialDiagnostics);
  const attempted = useRef(false);
  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;
    let cancelled = false;
    const documentContext = document.modelContext;
    const navigatorContext = navigator.modelContext;
    const modelContext = documentContext ?? navigatorContext;
    const contextSnapshot = { documentModelContext: Boolean(documentContext), navigatorModelContext: Boolean(navigatorContext), registerTool: typeof modelContext?.registerTool === "function" };
    const update = (next: Partial<WebMCPDiagnostics>) => { if (!cancelled) setDiagnostics((current) => ({ ...current, ...next })); };
    update(contextSnapshot);
    if (!modelContext || typeof modelContext.registerTool !== "function") { setStatus("unsupported"); update({ backend: { status: "not attempted", toolCount: 0, error: { name: "WebMCPUnavailable", message: "Tool endpoint was not requested because the browser exposes no native modelContext." } }, overall: "WebMCP unavailable in browser" }); return () => { cancelled = true; }; }
    void (async () => {
      let definitions: WebMCPDefinition[];
      try { definitions = await api.getWebMCPTools(); update({ backend: { status: "success", toolCount: definitions.length } }); }
      catch (error) { const details = errorDetails(error); setStatus("error"); update({ backend: { status: "failed", toolCount: 0, error: details }, overall: "backend tools unavailable" }); return; }
      const names = new Set<string>(); const registrations: Registration[] = [];
      for (const definition of definitions) {
        const name = typeof definition.name === "string" ? definition.name.trim() : "";
        const description = typeof definition.description === "string" ? definition.description.trim() : "";
        const validationError = !name ? "Tool name must be non-empty." : names.has(name) ? "Tool name must be unique." : !description ? "Tool description must be non-empty." : !validJsonSchema(definition.input_schema) ? "inputSchema must be a JSON Schema object." : null;
        names.add(name);
        if (validationError) { registrations.push({ name: name || "(missing name)", status: "FAILED", error: { name: "ValidationError", message: validationError } }); update({ registrations: [...registrations] }); continue; }
        try {
          await modelContext.registerTool({ name, description, inputSchema: definition.input_schema, annotations: { readOnlyHint: definition.read_only }, async execute(input) { return api.invokeWebMCP(name, input); } });
          registrations.push({ name, status: "SUCCESS" });
        } catch (error) { registrations.push({ name, status: "FAILED", error: errorDetails(error) }); }
        update({ registrations: [...registrations] });
      }
      let toolsResult: WebMCPDiagnostics["registeredTools"];
      if (typeof modelContext.getTools === "function") {
        try { const tools = await modelContext.getTools(); const namesAfterRegistration = registeredNames(tools); toolsResult = { count: namesAfterRegistration.length, names: namesAfterRegistration }; }
        catch (error) { toolsResult = { count: 0, names: [], error: errorDetails(error) }; }
      }
      const hasFailures = registrations.some((registration) => registration.status === "FAILED");
      setStatus(hasFailures ? "error" : "available");
      update({ registeredTools: toolsResult, overall: hasFailures ? "registration failed" : "registered successfully" });
    })();
    return () => { cancelled = true; };
  }, []);
  return { status, diagnostics };
}
