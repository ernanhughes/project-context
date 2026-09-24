/**
 * Context Lab capture plugin for OpenCode V2 (pinned: 2.0.16).
 *
 * READ-ONLY. The session context hooks below copy the assembled
 * model-request context out and append it to a local spool. No hook
 * mutates its event. The debugger later turns these records into
 * ContextBundle + ModelInvocation views without touching live context.
 *
 * What this observes (one record per observed model request):
 * - session.hook("context"): assembled system/messages/tools/options
 *   plus session/agent/model identity, immediately before the agent
 *   model request proceeds. Primary agent-loop scope.
 * - session.hook("compaction"): checkpoint-summary request. Recorded
 *   with request_kind "compaction", filtered from primary timelines by
 *   default. event.result is NEVER set (no intervention).
 * - session.hook("generate"): transient generate calls, recorded with
 *   request_kind "generate", filtered from primary timelines by
 *   default.
 *
 * Capture stage: `opencode.v2.model_context` — the OpenCode V2 semantic
 * model-request context. This is NOT the byte-for-byte provider HTTP
 * request: protocol/provider lowering happens after this hook, and
 * provider-added material, wire representation, and cache decisions
 * remain unobserved. Reports state this explicitly.
 */

import { Plugin } from "@opencode/plugin";
import {
  appendRecord,
  assertSupportedVersion,
  buildRecord,
  captureEnabled,
  copyBlock,
  defaultSpoolDir,
  newCaptureId,
  nowIso,
} from "./capture.ts";
import type { ModelLimits, ModelRef, RequestKind } from "./schema.ts";

type Env = Record<string, string | undefined>;

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
  model: {
    get: (input: { providerID: string; modelID: string }) => Promise<{
      limit?: { context?: number; output?: number };
    } | null>;
  };
  session: {
    hook: (
      name: "context" | "compaction" | "generate",
      callback: (event: SessionContextEvent) => void | Promise<void>,
    ) => Promise<{ dispose: () => Promise<void> }>;
  };
};

const sequences = new Map<string, number>();

function nextSequence(sessionID: string): number {
  const next = (sequences.get(sessionID) ?? 0) + 1;
  sequences.set(sessionID, next);
  return next;
}

function toModelRef(raw: unknown): ModelRef | null {
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Record<string, unknown>;
  const providerID = obj["providerID"];
  const id = obj["id"] ?? obj["modelID"];
  const variant = obj["variant"];
  if (typeof providerID !== "string" && typeof id !== "string") return null;
  return {
    provider_id: typeof providerID === "string" ? providerID : null,
    id: typeof id === "string" ? id : null,
    variant: typeof variant === "string" ? variant : null,
  };
}

async function readModelLimits(
  ctx: PluginContext,
  model: { providerID: string; id: string },
): Promise<ModelLimits | null> {
  try {
    const info = await ctx.model.get({
      providerID: model.providerID,
      modelID: model.id,
    });
    const context = info?.limit?.context;
    const output = info?.limit?.output;
    if (typeof context !== "number" && typeof output !== "number") return null;
    return {
      context: typeof context === "number" ? context : null,
      output: typeof output === "number" ? output : null,
      source: "ctx.model",
    };
  } catch {
    // Model metadata unavailable at capture time: UNAVAILABLE is
    // correct. Never hard-code capacities, never infer from names.
    return null;
  }
}

export default Plugin.define({
  id: "context-debugger-capture",
  async setup(ctx) {
    const pluginCtx = ctx as unknown as PluginContext;
    assertSupportedVersion(pluginCtx.app.version);
    const env = process.env as Env;
    if (!captureEnabled(env)) return;

    const capture = async (kind: RequestKind, event: SessionContextEvent) => {
      // READ-ONLY: copy blocks out first; the event is never written.
      const system = copyBlock(event.system);
      const messages = copyBlock(event.messages);
      const tools = copyBlock(event.tools) as Record<string, unknown>;
      const options = copyBlock(event.options) as Record<string, unknown>;
      const serializeStart = performance.now();
      const capturedAt = nowIso();
      const sessionID =
        typeof event.sessionID === "string" ? event.sessionID : null;
      const model = toModelRef(event.model);
      const limits =
        model && model.provider_id && model.id
          ? await readModelLimits(pluginCtx, {
              providerID: model.provider_id,
              id: model.id,
            })
          : null;
      const record = buildRecord({
        request_kind: kind,
        session_id: sessionID,
        invocation_sequence: nextSequence(sessionID ?? "unlinked"),
        agent: typeof event.agent === "string" ? event.agent : null,
        model,
        model_limits: limits,
        system,
        messages,
        tools,
        options,
        captured_at: capturedAt,
        capture_id: newCaptureId(),
      });
      const serializeMs = performance.now() - serializeStart;
      const writeMs = appendRecord(defaultSpoolDir(env), record);
      record.timings_ms = {
        serialize: serializeMs,
        write: writeMs,
        total: serializeMs + writeMs,
      };
    };

    await pluginCtx.session.hook("context", (event) =>
      capture("context", event),
    );
    await pluginCtx.session.hook("compaction", (event) =>
      capture("compaction", event),
    );
    await pluginCtx.session.hook("generate", (event) =>
      capture("generate", event),
    );
  },
});
