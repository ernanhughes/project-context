/**
 * Read-only V2 capture core. Pure functions plus one append-only spool
 * writer. Nothing here mutates the hook event: blocks are deep-copied
 * out (JSON round-trip) and only ever read afterwards.
 *
 * Integrity rule: sha256 over the canonical JSON of the observed
 * blocks {system, messages, tools, options} only. Object keys sorted
 * recursively; arrays keep order; compact serialization with no
 * insignificant whitespace (matching Python
 * json.dumps(sort_keys=True, separators=(",", ":"))). The Python
 * ingester implements the same rule; the golden fixture keeps
 * ASCII-only content so both agree byte-for-byte.
 */

import { randomUUID } from "node:crypto";
import { createHash } from "node:crypto";
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import {
  ADAPTER_VERSION,
  BRIDGE_SCHEMA_V2,
  CAPTURE_STAGE_V2,
  type BridgeRecord,
  type ModelLimits,
  type ModelRef,
  type RequestKind,
} from "./schema.ts";

export const OPT_IN_ENV = "PROJECT_CONTEXT_CAPTURE";
export const SPOOL_ENV = "PROJECT_CONTEXT_SPOOL_DIR";
export const OPENCODE_VERSION = "2.0.16";
export const PLUGIN_API_VERSION = "@opencode/plugin 2.0.16";
export const OBSERVER_POSITION = "context-hook";
export const PLUGIN_ID = "context-debugger-capture";

/** Exact pinned OpenCode version this adapter supports. No fallback. */
export function assertSupportedVersion(runtimeVersion: unknown): void {
  const normalized =
    typeof runtimeVersion === "string" && runtimeVersion.startsWith("v")
      ? runtimeVersion.slice(1)
      : runtimeVersion;
  if (normalized !== OPENCODE_VERSION) {
    throw new Error(
      `[${PLUGIN_ID}] unsupported OpenCode version ${JSON.stringify(runtimeVersion)}; ` +
        `this adapter targets exactly ${OPENCODE_VERSION} (plugin API V2, ${PLUGIN_API_VERSION}). ` +
        `Capture disabled: migrate the adapter, do not run a compatibility layer.`,
    );
  }
}

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

/** Canonical form for hashing: object keys sorted recursively, arrays
 * keep order (ordering is semantically relevant — never sort arrays). */
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

/** Deep-copy a hook block so later hook mutations cannot alter the
 * captured record, and capture cannot alter the live event. */
export function copyBlock<T>(value: T): T {
  if (value === undefined) return value;
  return JSON.parse(JSON.stringify(value)) as T;
}

export type RecordInput = {
  request_kind: RequestKind;
  session_id: string | null;
  invocation_sequence: number;
  agent: string | null;
  model: ModelRef | null;
  model_limits: ModelLimits | null;
  system: unknown;
  messages: unknown;
  tools: Record<string, unknown>;
  options: Record<string, unknown>;
  captured_at: string;
  capture_id: string;
};

export function buildRecord(input: RecordInput): BridgeRecord {
  const observed = {
    system: input.system,
    messages: input.messages,
    tools: input.tools,
    options: input.options,
  };
  const integrity = sha256Hex(observed);
  return {
    schema: BRIDGE_SCHEMA_V2,
    capture_id: input.capture_id,
    captured_at: input.captured_at,
    capture_stage: CAPTURE_STAGE_V2,
    request_kind: input.request_kind,
    session_id: input.session_id,
    invocation_sequence: input.invocation_sequence,
    agent: input.agent,
    model: input.model,
    model_limits: input.model_limits,
    system: copyBlock(input.system),
    messages: copyBlock(input.messages),
    tools: copyBlock(input.tools),
    options: copyBlock(input.options),
    adapter_version: ADAPTER_VERSION,
    opencode_version: OPENCODE_VERSION,
    plugin_api_version: PLUGIN_API_VERSION,
    observer_position: OBSERVER_POSITION,
    integrity: { sha256: integrity },
    timings_ms: { serialize: 0, write: 0, total: 0 },
    evidence_class: "opencode_capture",
  };
}

export function spoolPath(spoolDir: string, capturedAt: string): string {
  const day = capturedAt.slice(0, 10);
  return join(spoolDir, day, "captures.jsonl");
}

/** Append one record. Returns write milliseconds. Throws on I/O
 * failure so a broken spool fails loudly instead of silently dropping
 * evidence. */
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
