/**
 * Bridge schema shared with the Python ingester. The single source of
 * truth for field names is fixtures/opencode-capture-v1/; this module
 * mirrors it. Unknown schema versions must be rejected loudly, never
 * coerced (see validateBridgeRecord).
 */

export const BRIDGE_SCHEMA_V1 = "project_context.opencode_capture.v1";

export const ADAPTER_VERSION = "0.1.0";

/** V1 observation boundary. NOT the assembled provider request. */
export const CAPTURE_STAGE_V1 = "opencode.v1.pre_dispatch_partial";

export type HookKind =
  | "system.transform"
  | "messages.transform"
  | "chat.message"
  | "tool.execute.after";

export type ModelRef = {
  provider_id: string | null;
  id: string | null;
  variant: string | null;
};

export type BridgePayload = {
  system?: unknown;
  messages?: unknown;
  admission?: unknown;
  tool_result?: unknown;
};

export type BridgeRecord = {
  schema: string;
  capture_id: string;
  captured_at: string;
  capture_stage: string;
  hook_kind: HookKind;
  session_id: string | null;
  agent: string | null;
  model: ModelRef | null;
  sequence_scope: string;
  sequence_index: number;
  adapter_version: string;
  opencode_version: string;
  plugin_api_version: string;
  observer_position: string;
  payload: BridgePayload;
  integrity: { sha256: string };
  timings_ms: { serialize: number; write: number; total: number };
  evidence_class: "opencode_capture";
};

export function validateBridgeRecord(record: unknown): string[] {
  const errors: string[] = [];
  if (typeof record !== "object" || record === null) {
    return ["record is not an object"];
  }
  const rec = record as Record<string, unknown>;
  if (rec["schema"] !== BRIDGE_SCHEMA_V1) {
    errors.push(`unsupported schema: ${String(rec["schema"])}`);
    return errors;
  }
  for (const key of [
    "capture_id",
    "captured_at",
    "capture_stage",
    "hook_kind",
    "sequence_scope",
    "payload",
    "integrity",
  ]) {
    if (!(key in rec)) errors.push(`missing key: ${key}`);
  }
  const payload = rec["payload"];
  if (typeof payload !== "object" || payload === null) {
    errors.push("payload is not an object");
  }
  return errors;
}
