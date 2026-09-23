/**
 * Read-only capture core. Pure functions plus one append-only spool writer.
 * Nothing here mutates hook input: inputs are deep-frozen by the caller
 * contract and only ever read. See tests/capture.test.ts.
 */

import { randomUUID } from "node:crypto";
import { createHash } from "node:crypto";
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  ADAPTER_VERSION,
  BRIDGE_SCHEMA_V1,
  CAPTURE_STAGE_V1,
  type BridgePayload,
  type BridgeRecord,
  type HookKind,
  type ModelRef,
} from "./schema.ts";

export const OPT_IN_ENV = "PROJECT_CONTEXT_CAPTURE";
export const SPOOL_ENV = "PROJECT_CONTEXT_SPOOL_DIR";
export const OPENCODE_VERSION = "1.18.27";
export const PLUGIN_API_VERSION = "@opencode-ai/plugin 1.18.27";
export const OBSERVER_POSITION = "last-registered";

export function captureEnabled(
  env: Record<string, string | undefined>,
): boolean {
  return env[OPT_IN_ENV] === "1";
}

export function defaultSpoolDir(
  env: Record<string, string | undefined>,
): string {
  const override = env[SPOOL_ENV];
  if (override !== undefined && override !== "") return override;
  return join(homedir(), ".local", "share", "project-context", "captures");
}

/** Canonical form for hashing: object keys sorted recursively, arrays keep
 * order (ordering is semantically relevant — never sort arrays). */
export function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (typeof value === "object" && value !== null) {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      out[key] = canonicalize((value as Record<string, unknown>)[key]);
    }
    return out;
  }
  return value;
}

export function sha256Hex(value: unknown): string {
  return createHash("sha256")
    .update(JSON.stringify(canonicalize(value)))
    .digest("hex");
}

export type RecordInput = {
  hook_kind: HookKind;
  session_id: string | null;
  agent: string | null;
  model: ModelRef | null;
  sequence_scope: string;
  sequence_index: number;
  payload: BridgePayload;
  captured_at: string;
  capture_id: string;
};

export function buildRecord(input: RecordInput): BridgeRecord {
  const integrity = sha256Hex(input.payload);
  return {
    schema: BRIDGE_SCHEMA_V1,
    capture_id: input.capture_id,
    captured_at: input.captured_at,
    capture_stage: CAPTURE_STAGE_V1,
    hook_kind: input.hook_kind,
    session_id: input.session_id,
    agent: input.agent,
    model: input.model,
    sequence_scope: input.sequence_scope,
    sequence_index: input.sequence_index,
    adapter_version: ADAPTER_VERSION,
    opencode_version: OPENCODE_VERSION,
    plugin_api_version: PLUGIN_API_VERSION,
    observer_position: OBSERVER_POSITION,
    payload: input.payload,
    integrity: { sha256: integrity },
    timings_ms: { serialize: 0, write: 0, total: 0 },
    evidence_class: "opencode_capture",
  };
}

export function spoolPath(spoolDir: string, capturedAt: string): string {
  const day = capturedAt.slice(0, 10);
  return join(spoolDir, day, "captures.jsonl");
}

/** Append one record. Returns write milliseconds. Throws on I/O failure
 * so a broken spool fails loudly instead of silently dropping evidence. */
export function appendRecord(spoolDir: string, record: BridgeRecord): number {
  const start = performance.now();
  const path = spoolPath(spoolDir, record.captured_at);
  mkdirSync(join(spoolDir, record.captured_at.slice(0, 10)), {
    recursive: true,
  });
  appendFileSync(path, JSON.stringify(record) + "\n", "utf-8");
  return performance.now() - start;
}

export function newCaptureId(): string {
  return randomUUID();
}

export function nowIso(): string {
  return new Date().toISOString();
}
