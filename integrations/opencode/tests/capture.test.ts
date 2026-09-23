/**
 * Stage 1 invariant tests (node:test, no dependencies).
 * Run: npm test
 *
 * 1. disabled flag produces no raw file
 * 2. enabled flag emits one versioned record
 * 3. hook input structurally unchanged by capture
 * 4. system/message/tool order preserved
 * 5. unknown part survives without silent deletion
 * 6. spool defaults to user-local path, overridable per request
 * 7. overhead measurement does not alter the event
 * 8. golden fixture: builder output matches committed expectations
 * 9. schema validator accepts good records, rejects bad ones
 */

import { deepEqual, equal, ok } from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  appendRecord,
  buildRecord,
  captureEnabled,
  defaultSpoolDir,
  sha256Hex,
  type RecordInput,
} from "../src/capture.ts";
import { ContextLabCapture } from "../src/index.ts";
import { BRIDGE_SCHEMA_V1, validateBridgeRecord } from "../src/schema.ts";
import golden from "../../../fixtures/opencode-capture-v1/primary-one-request.json" with { type: "json" };

function tmpSpool(): string {
  return mkdtempSync(join(tmpdir(), "ctxlab-spool-"));
}

function envFor(spool: string): Record<string, string> {
  return { PROJECT_CONTEXT_CAPTURE: "1", PROJECT_CONTEXT_SPOOL_DIR: spool };
}

test("disabled flag produces no raw file", async () => {
  const spool = tmpSpool();
  const hooks = await ContextLabCapture(
    {},
    { PROJECT_CONTEXT_SPOOL_DIR: spool },
  );
  equal(Object.keys(hooks).length, 0);
  equal(existsSync(join(spool, "2099-01-01", "captures.jsonl")), false);
  rmSync(spool, { recursive: true, force: true });
});

test("enabled flag emits one versioned record", async () => {
  const spool = tmpSpool();
  const hooks = (await ContextLabCapture({}, envFor(spool))) as Record<
    string,
    (input: unknown, output: unknown) => Promise<void>
  >;
  ok(typeof hooks["experimental.chat.system.transform"] === "function");
  await hooks["experimental.chat.system.transform"](
    { sessionID: "ses-1", model: { providerID: "p", id: "m" } },
    { system: ["alpha", "beta"] },
  );
  const day = new Date().toISOString().slice(0, 10);
  const raw = readFileSync(join(spool, day, "captures.jsonl"), "utf-8");
  const lines = raw.trim().split("\n");
  equal(lines.length, 1);
  const record = JSON.parse(lines[0]) as Record<string, unknown>;
  equal(record["schema"], BRIDGE_SCHEMA_V1);
  equal(record["hook_kind"], "system.transform");
  rmSync(spool, { recursive: true, force: true });
});

test("hook input structurally unchanged by capture", async () => {
  const spool = tmpSpool();
  const hooks = (await ContextLabCapture({}, envFor(spool))) as Record<
    string,
    (input: unknown, output: unknown) => Promise<void>
  >;
  const input = { sessionID: "ses-9", model: { providerID: "p", id: "m" } };
  const output = { system: ["one", "two"] };
  const before = JSON.stringify({ input, output });
  await hooks["experimental.chat.system.transform"](input, output);
  equal(JSON.stringify({ input, output }), before);
  rmSync(spool, { recursive: true, force: true });
});

test("order preserved and unknown part survives", () => {
  const messages = [
    { info: { id: "m1" }, parts: [{ id: "p1", type: "text", text: "first" }] },
    {
      info: { id: "m2" },
      parts: [
        { id: "p2", type: "weird-future-part", blob: [3, 1, 2] },
        { id: "p3", type: "text", text: "second" },
      ],
    },
  ];
  const record = buildRecord({
    hook_kind: "messages.transform",
    session_id: null,
    agent: null,
    model: null,
    sequence_scope: "unlinked",
    sequence_index: 1,
    payload: { messages },
    captured_at: "2026-09-23T00:00:00.000Z",
    capture_id: "cap-order-1",
  });
  const payload = record.payload as {
    messages: Array<{ parts: Array<{ id: string }> }>;
  };
  deepEqual(
    payload.messages.flatMap((m) => m.parts.map((p) => p.id)),
    ["p1", "p2", "p3"],
  );
  ok(JSON.stringify(record).includes("weird-future-part"));
});

test("spool default is user-local and overridable", () => {
  const def = defaultSpoolDir({});
  ok(def.includes(".local"), `default spool not user-local: ${def}`);
  ok(
    def.includes("project-context"),
    `default spool missing product dir: ${def}`,
  );
  equal(defaultSpoolDir({ PROJECT_CONTEXT_SPOOL_DIR: "/tmp/x" }), "/tmp/x");
});

test("golden fixture matches builder output", () => {
  const gold = golden as {
    inputs: RecordInput[];
    records: Array<Record<string, unknown>>;
  };
  equal(gold.inputs.length, gold.records.length);
  for (let i = 0; i < gold.inputs.length; i++) {
    const built = buildRecord(gold.inputs[i]) as unknown as Record<
      string,
      unknown
    >;
    const expected = { ...gold.records[i] };
    delete built["timings_ms"];
    delete expected["timings_ms"];
    deepEqual(built, expected, `golden case ${i} diverged`);
  }
});

test("schema validator accepts good records, rejects bad ones", () => {
  const gold = golden as { records: Array<Record<string, unknown>> };
  for (const record of gold.records) {
    deepEqual(validateBridgeRecord(record), []);
  }
  deepEqual(
    validateBridgeRecord({ schema: "project_context.opencode_capture.v9" }),
    ["unsupported schema: project_context.opencode_capture.v9"],
  );
  deepEqual(validateBridgeRecord({ schema: BRIDGE_SCHEMA_V1 }), [
    "missing key: capture_id",
    "missing key: captured_at",
    "missing key: capture_stage",
    "missing key: hook_kind",
    "missing key: sequence_scope",
    "missing key: payload",
    "missing key: integrity",
    "payload is not an object",
  ]);
});

test("canonical hash is order-sensitive for arrays, order-free for keys", () => {
  const a = sha256Hex({ x: 1, y: [1, 2] });
  const b = sha256Hex({ y: [1, 2], x: 1 });
  const c = sha256Hex({ x: 1, y: [2, 1] });
  equal(a, b);
  ok(a !== c);
});

test("captureEnabled honours only explicit opt-in", () => {
  equal(captureEnabled({}), false);
  equal(captureEnabled({ PROJECT_CONTEXT_CAPTURE: "0" }), false);
  equal(captureEnabled({ PROJECT_CONTEXT_CAPTURE: "yes" }), false);
  equal(captureEnabled({ PROJECT_CONTEXT_CAPTURE: "1" }), true);
});

test("appendRecord fails loudly on bad paths", async () => {
  const base = tmpSpool();
  const blocker = join(base, "blocker.txt");
  await import("node:fs/promises").then((fs) => fs.writeFile(blocker, "x"));
  const record = buildRecord({
    hook_kind: "system.transform",
    session_id: null,
    agent: null,
    model: null,
    sequence_scope: "unlinked",
    sequence_index: 1,
    payload: { system: ["x"] },
    captured_at: "2026-09-23T00:00:00.000Z",
    capture_id: "cap-fail-1",
  });
  let threw = false;
  try {
    // A regular file in place of the spool directory cannot be descended
    // into; the write must throw, not silently drop evidence.
    appendRecord(join(blocker, "2026-09-23"), record);
  } catch {
    threw = true;
  }
  ok(threw, "spool failure must throw, not silently drop evidence");
  rmSync(base, { recursive: true, force: true });
});
