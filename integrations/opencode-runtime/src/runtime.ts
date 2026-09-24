/**
 * Context Lab intervention runtime for OpenCode V2 (pinned: 2.0.16).
 *
 * UNVERIFIED HOOK CONTRACT — READ BEFORE USE.
 *
 * The tested 6D surface is the Python synthetic harness
 * (`src/project_context/runtime/`, `fixtures/runtime-v1/`), which
 * proves render → inject → observe → reconcile structurally. This
 * TypeScript file prepares the live intervention shape but has NEVER
 * run against a real OpenCode session: whether assigning the assembled
 * `system` array inside `session.hook("context")` actually alters the
 * model request is UNCONFIRMED. Do not install this plugin for
 * ordinary work. Do not cite it as evidence. A single throwaway live
 * probe is the explicit next step if hook validation is required.
 *
 * Opt-in only: without PROJECT_CONTEXT_RUNTIME=inject this plugin
 * registers no hooks and changes nothing. The rendered block is read
 * from the file named by PROJECT_CONTEXT_RUNTIME_BLOCK.
 *
 * Fail-safe: the new system array is built first and assigned once;
 * any error leaves the event untouched (no partial writes). A
 * differing pre-existing runtime block refuses with an error instead
 * of stacking payloads; an identical block is a no-op.
 */

import { Plugin } from "@opencode/plugin";
import { findExactBlock, findRuntimeBlocks } from "./blocks.ts";
import { readFileSync } from "node:fs";

type SessionContextEvent = {
  sessionID: string;
  agent: string;
  model: { providerID: string; id: string; variant?: string };
  system: unknown;
  messages: unknown;
  tools: Record<string, { description: string; input: unknown }>;
  options: Record<string, unknown>;
};

type PluginContext = {
  app: { version: string };
  session: {
    hook: (
      name: "context",
      callback: (event: SessionContextEvent) => void | Promise<void>,
    ) => Promise<{ dispose: () => Promise<void> }>;
  };
};

function loadBlock(path: string | undefined): string {
  if (!path) throw new Error("PROJECT_CONTEXT_RUNTIME_BLOCK is not set");
  const text = readFileSync(path, "utf-8");
  if (!text.includes("[CONTEXT RUNTIME]")) {
    throw new Error("rendered block lacks runtime markers; refusing");
  }
  return text;
}

export default Plugin.define({
  id: "context-runtime-injection",
  async setup(ctx) {
    if (process.env["PROJECT_CONTEXT_RUNTIME"] !== "inject") return;
    const pluginCtx = ctx as unknown as PluginContext;
    const blockPath = process.env["PROJECT_CONTEXT_RUNTIME_BLOCK"];
    await pluginCtx.session.hook("context", (_event) => {
      const event = _event;
      const text = loadBlock(blockPath);
      if (!Array.isArray(event.system)) {
        throw new Error("unsupported request shape: system is not an array");
      }
      const marked = findRuntimeBlocks(event.system);
      if (marked.length > 0) {
        if (findExactBlock(event.system, text) >= 0) return; // idempotent
        throw new Error("injection_conflict: a different runtime block is present");
      }
      const next = [...event.system, { type: "text", text }];
      event.system = next;
    });
  },
});
