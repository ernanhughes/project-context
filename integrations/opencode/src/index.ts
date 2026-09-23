/**
 * Context Lab capture plugin for OpenCode V1 (pinned: 1.18.27).
 *
 * READ-ONLY. Every hook below copies data out and writes it to a local
 * spool. No hook mutates its input or output. See tests/capture.test.ts
 * for the structural no-mutation proof.
 *
 * What this observes (and does not observe):
 * - experimental.chat.system.transform: system string array, usually with
 *   sessionID + model. Closest available pre-dispatch system signal.
 * - experimental.chat.messages.transform: message list. NO session/agent/
 *   model identity in this hook (verified against @opencode-ai/plugin
 *   1.18.27 types). Recorded unlinked with the limitation stated.
 * - chat.message: admission inventory (session/agent/model + message).
 * - tool.execute.after: tool result text with session + call linkage.
 *   Input args are deliberately NOT recorded (secret-prone).
 *
 * This is "opencode.v1.pre_dispatch_partial", NOT the assembled provider
 * request. No unified pre-dispatch hook exists on V1.
 */

import type { Plugin } from "@opencode-ai/plugin";
import {
  appendRecord,
  buildRecord,
  captureEnabled,
  defaultSpoolDir,
  newCaptureId,
  nowIso,
  type RecordInput,
} from "./capture.ts";
import type { BridgeRecord, HookKind, ModelRef } from "./schema.ts";

type Env = Record<string, string | undefined>;

const sequences = new Map<string, number>();

function nextSequence(scope: string): number {
  const next = (sequences.get(scope) ?? 0) + 1;
  sequences.set(scope, next);
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

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function emit(
  env: Env,
  partial: Omit<RecordInput, "captured_at" | "capture_id">,
): BridgeRecord | null {
  if (!captureEnabled(env)) return null;
  const serializeStart = performance.now();
  const capturedAt = nowIso();
  const record = buildRecord({
    ...partial,
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
  return record;
}

export const ContextLabCapture = async (
  _ctx: unknown,
  env: Env = process.env,
) => {
  if (!captureEnabled(env)) return {};
  return {
    "experimental.chat.system.transform": async (
      input: {
        sessionID?: string;
        model?: unknown;
      },
      output: { system: unknown },
    ) => {
      const sessionID = asString(input.sessionID);
      const scope = sessionID ?? "unlinked";
      emit(env, {
        hook_kind: "system.transform" as HookKind,
        session_id: sessionID,
        agent: null,
        model: toModelRef(input.model),
        sequence_scope: scope,
        sequence_index: nextSequence(scope),
        payload: { system: output.system },
      });
    },
    "experimental.chat.messages.transform": async (
      _input: unknown,
      output: { messages: unknown },
    ) => {
      emit(env, {
        hook_kind: "messages.transform" as HookKind,
        session_id: null,
        agent: null,
        model: null,
        sequence_scope: "unlinked",
        sequence_index: nextSequence("unlinked"),
        payload: { messages: output.messages },
      });
    },
    "chat.message": async (
      input: {
        sessionID: string;
        agent?: string;
        model?: unknown;
        messageID?: string;
      },
      output: { message: unknown; parts: unknown },
    ) => {
      const scope = input.sessionID;
      emit(env, {
        hook_kind: "chat.message" as HookKind,
        session_id: scope,
        agent: asString(input.agent),
        model: toModelRef(input.model),
        sequence_scope: scope,
        sequence_index: nextSequence(scope),
        payload: {
          admission: { message: output.message, parts: output.parts },
        },
      });
    },
    "tool.execute.after": async (
      input: { tool: string; sessionID: string; callID: string },
      output: { title: unknown; output: unknown; metadata: unknown },
    ) => {
      const scope = input.sessionID;
      emit(env, {
        hook_kind: "tool.execute.after" as HookKind,
        session_id: scope,
        agent: null,
        model: null,
        sequence_scope: scope,
        sequence_index: nextSequence(scope),
        payload: {
          tool_result: {
            tool: input.tool,
            callID: input.callID,
            title: output.title,
            output: output.output,
            metadata: output.metadata,
          },
        },
      });
    },
  };
};

export const ContextLabCapturePlugin: Plugin = ContextLabCapture as Plugin;
