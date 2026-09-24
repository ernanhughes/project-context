/**
 * Stage 5 invariant tests (node:test, no test framework).
 * Run: npm test
 *
 * 1. disabled flag registers no hooks and writes no file
 * 2. wrong OpenCode version fails clearly (no fallback)
 * 3. enabled context hook emits one versioned V2 record
 * 4. hook event structurally unchanged by capture (read-only proof)
 * 5. system/messages/tools/options captured together; tool definitions
 *    carry description plus input schema only (no executables)
 * 6. compaction hook records kind=compaction and never sets result
 * 7. order preserved across system and message blocks
 * 8. spool defaults to user-local path, overridable per request
 * 9. golden fixture: builder output matches committed expectations
 * 10. schema validator accepts good records, rejects V1 and bad ones
 * 11. canonical hash is order-sensitive for arrays, order-free for keys
 * 12. appendRecord fails loudly on bad paths
 */

import { deepEqual, equal, ok } from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import plugin from "../src/index.ts";
import {
  appendRecord,
  assertSupportedVersion,
  buildRecord,
  captureEnabled,
  copyBlock,
  defaultSpoolDir,
  sha256Hex,
  type RecordInput,
} from "../src/capture.ts";
import {
  BRIDGE_SCHEMA_V2,
  CAPTURE_STAGE_V2,
  validateBridgeRecord,
} from "../src/schema.ts";
import golden from "../../../fixtures/opencode-capture-v2/session-three-requests.json" with { type: "json" };

function tmpSpool(): string {
  return mkdtempSync(join(tmpdir(), "ctxlab-spool-"));
}

type HookFn = (event: Record<string, unknown>) => Promise<void> | void;

type ListedModel = {
  id: string;
  modelID: string;
  providerID: string;
  limit?: { context?: number; input?: number; output?: number };
};

// Mirrors the real 2.0.16 context: `ctx.model.list()` returns `{ location, data }`, and there
// is no `ctx.model.get`. (An earlier version of this fake had `get`, which does not exist.)
function fakeContext(
  spool: string,
  models: ListedModel[] = [],
  listFails = false,
) {
  const hooks = new Map<string, HookFn>();
  return {
    hooks,
    ctx: {
      app: { version: "2.0.16" },
      model: {
        list: async () => {
          if (listFails) throw new Error("model registry unavailable");
          return { location: { directory: spool }, data: models };
        },
      },
      session: {
        hook: async (name: string, callback: HookFn) => {
          hooks.set(name, callback);
          return { dispose: async () => {} };
        },
      },
    },
  };
}

function withEnv(
  spool: string,
  fn: () => Promise<void> | void,
): Promise<void> | void {
  const prevCapture = process.env["PROJECT_CONTEXT_CAPTURE"];
  const prevSpool = process.env["PROJECT_CONTEXT_SPOOL_DIR"];
  process.env["PROJECT_CONTEXT_CAPTURE"] = "1";
  process.env["PROJECT_CONTEXT_SPOOL_DIR"] = spool;
  const restore = () => {
    if (prevCapture === undefined)
      delete process.env["PROJECT_CONTEXT_CAPTURE"];
    else process.env["PROJECT_CONTEXT_CAPTURE"] = prevCapture;
    if (prevSpool === undefined)
      delete process.env["PROJECT_CONTEXT_SPOOL_DIR"];
    else process.env["PROJECT_CONTEXT_SPOOL_DIR"] = prevSpool;
  };
  const done = (error?: unknown) => {
    restore();
    if (error) throw error;
  };
  try {
    const result = fn();
    if (result instanceof Promise) {
      return result.then(
        () => done(),
        (error: unknown) => done(error),
      );
    }
    done();
  } catch (error) {
    done(error);
  }
}

function sampleEvent() {
  return {
    sessionID: "ses-1",
    agent: "build",
    model: { providerID: "p", id: "m" },
    system: [{ type: "text", text: "alpha" }],
    // The real 2.0.16 shape: role plus a content list. Tool calls and results are parts.
    messages: [
      {
        id: "m1",
        role: "user",
        content: [{ type: "text", text: "first" }],
        metadata: {},
      },
      {
        id: "m2",
        role: "assistant",
        content: [
          { type: "reasoning", text: "thinking", providerMetadata: {} },
          {
            type: "tool-call",
            id: "call-1",
            name: "read",
            input: { path: "a.txt" },
            providerExecuted: false,
          },
        ],
      },
      {
        role: "tool",
        content: [
          {
            type: "tool-result",
            id: "call-1",
            name: "read",
            result: { type: "text", value: "contents" },
            providerExecuted: false,
          },
        ],
      },
    ],
    tools: {
      read: {
        description: "Read a file.",
        input: { type: "object", properties: {} },
      },
    },
    options: { temperature: 0.2 },
  };
}

test("disabled flag registers no hooks and writes no file", async () => {
  const spool = tmpSpool();
  const { hooks, ctx } = fakeContext(spool);
  const prevCapture = process.env["PROJECT_CONTEXT_CAPTURE"];
  delete process.env["PROJECT_CONTEXT_CAPTURE"];
  try {
    await plugin.setup(ctx as never);
  } finally {
    if (prevCapture !== undefined)
      process.env["PROJECT_CONTEXT_CAPTURE"] = prevCapture;
  }
  equal(hooks.size, 0);
  equal(existsSync(join(spool, "2099-01-01", "captures.jsonl")), false);
  rmSync(spool, { recursive: true, force: true });
});

test("wrong OpenCode version fails clearly", () => {
  let message = "";
  try {
    assertSupportedVersion("1.18.27");
  } catch (error) {
    message = String(error);
  }
  ok(message.includes("unsupported OpenCode version"));
  ok(message.includes("2.0.16"));
});

test("enabled context hook emits one versioned V2 record", async () => {
  const spool = tmpSpool();
  const { hooks, ctx } = fakeContext(spool);
  await withEnv(spool, async () => {
    await plugin.setup(ctx as never);
    const context = hooks.get("context");
    ok(typeof context === "function");
    await context(sampleEvent());
  });
  const day = new Date().toISOString().slice(0, 10);
  const raw = readFileSync(join(spool, day, "captures.jsonl"), "utf-8");
  const lines = raw.trim().split("\n");
  equal(lines.length, 1);
  const record = JSON.parse(lines[0]) as Record<string, unknown>;
  equal(record["schema"], BRIDGE_SCHEMA_V2);
  equal(record["capture_stage"], CAPTURE_STAGE_V2);
  equal(record["request_kind"], "context");
  equal(record["session_id"], "ses-1");
  rmSync(spool, { recursive: true, force: true });
});

test("hook event structurally unchanged by capture", async () => {
  const spool = tmpSpool();
  const { hooks, ctx } = fakeContext(spool);
  await withEnv(spool, async () => {
    await plugin.setup(ctx as never);
    const event = sampleEvent();
    const before = JSON.stringify(event);
    await hooks.get("context")!(event);
    equal(JSON.stringify(event), before);
  });
  rmSync(spool, { recursive: true, force: true });
});

test("tool definitions captured without executables", () => {
  const record = buildRecord({
    request_kind: "context",
    session_id: "ses-9",
    invocation_sequence: 1,
    agent: "build",
    model: { provider_id: "p", id: "m", variant: null },
    model_limits: null,
    system: [{ type: "text", text: "sys" }],
    messages: [],
    tools: {
      read: { description: "Read.", input: { type: "object" } },
      bash: { description: "Run.", input: { type: "object" } },
    },
    options: {},
    captured_at: "2026-09-24T00:00:00.000Z",
    capture_id: "cap-tools-1",
  });
  deepEqual(Object.keys(record.tools).sort(), ["bash", "read"]);
  ok(!JSON.stringify(record.tools).includes("execute"));
  ok(JSON.stringify(record.tools).includes("Read."));
});

test("compaction hook records kind and never sets result", async () => {
  const spool = tmpSpool();
  const { hooks, ctx } = fakeContext(spool);
  await withEnv(spool, async () => {
    await plugin.setup(ctx as never);
    const event = sampleEvent();
    await hooks.get("compaction")!(event);
    ok(!("result" in event), "capture must never set event.result");
  });
  const day = new Date().toISOString().slice(0, 10);
  const raw = readFileSync(join(spool, day, "captures.jsonl"), "utf-8");
  const record = JSON.parse(raw.trim().split("\n")[0]) as Record<
    string,
    unknown
  >;
  equal(record["request_kind"], "compaction");
  rmSync(spool, { recursive: true, force: true });
});

test("order preserved across system and message blocks", () => {
  const record = buildRecord({
    request_kind: "context",
    session_id: "s",
    invocation_sequence: 1,
    agent: "build",
    model: null,
    model_limits: null,
    system: [
      { type: "text", text: "first" },
      { type: "text", text: "second" },
    ],
    messages: [
      { info: { id: "m1" }, parts: [{ id: "p1" }] },
      { info: { id: "m2" }, parts: [{ id: "p2" }, { id: "p3" }] },
    ],
    tools: {},
    options: {},
    captured_at: "2026-09-24T00:00:00.000Z",
    capture_id: "cap-order-1",
  });
  const system = record.system as Array<{ text: string }>;
  deepEqual(
    system.map((s) => s.text),
    ["first", "second"],
  );
  const messages = record.messages as Array<{ parts: Array<{ id: string }> }>;
  deepEqual(
    messages.flatMap((m) => m.parts.map((p) => p.id)),
    ["p1", "p2", "p3"],
  );
});

test("copyBlock isolates later mutations", () => {
  const tools = { read: { description: "R", input: {} } };
  const copied = copyBlock(tools);
  (tools as Record<string, unknown>)["write"] = { description: "W" };
  deepEqual(Object.keys(copied), ["read"]);
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
  equal(gold.inputs.length, 3);
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

test("schema validator accepts good records, rejects V1 and bad ones", () => {
  const gold = golden as { records: Array<Record<string, unknown>> };
  for (const record of gold.records) {
    deepEqual(validateBridgeRecord(record), []);
  }
  deepEqual(
    validateBridgeRecord({ schema: "project_context.opencode_capture.v1" }),
    ["unsupported schema: V1 capture retired; re-capture under V2"],
  );
  deepEqual(validateBridgeRecord({ schema: BRIDGE_SCHEMA_V2 }), [
    "missing key: capture_id",
    "missing key: captured_at",
    "missing key: capture_stage",
    "missing key: request_kind",
    "missing key: session_id",
    "missing key: invocation_sequence",
    "missing key: agent",
    "missing key: model",
    "missing key: system",
    "missing key: messages",
    "missing key: tools",
    "missing key: options",
    "missing key: integrity",
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
    request_kind: "context",
    session_id: null,
    invocation_sequence: 1,
    agent: null,
    model: null,
    model_limits: null,
    system: ["x"],
    messages: [],
    tools: {},
    options: {},
    captured_at: "2026-09-24T00:00:00.000Z",
    capture_id: "cap-fail-1",
  });
  let threw = false;
  try {
    appendRecord(join(blocker, "2026-09-24"), record);
  } catch {
    threw = true;
  }
  ok(threw, "spool failure must throw, not silently drop evidence");
  rmSync(base, { recursive: true, force: true });
});

test("model limits come from ctx.model.list, including the input limit", async () => {
  const spool = tmpSpool();
  const { hooks, ctx } = fakeContext(spool, [
    {
      id: "other",
      modelID: "other",
      providerID: "p",
      limit: { context: 1, output: 1 },
    },
    {
      id: "m",
      modelID: "m",
      providerID: "p",
      limit: { context: 1050000, input: 922000, output: 128000 },
    },
  ]);
  await withEnv(spool, async () => {
    await plugin.setup(ctx as never);
    await hooks.get("context")!(sampleEvent());
  });
  const day = new Date().toISOString().slice(0, 10);
  const record = JSON.parse(
    readFileSync(join(spool, day, "captures.jsonl"), "utf-8").trim(),
  );
  deepEqual(record.model_limits, {
    context: 1050000,
    input: 922000,
    output: 128000,
    source: "ctx.model.list",
  });
  rmSync(spool, { recursive: true, force: true });
});

test("an unknown model, or a failing registry, leaves the limit unobserved", async () => {
  for (const [models, fails] of [
    [[], false],
    [
      [
        {
          id: "zzz",
          modelID: "zzz",
          providerID: "p",
          limit: { context: 5 },
        },
      ],
      false,
    ],
    [[], true],
  ] as const) {
    const spool = tmpSpool();
    const { hooks, ctx } = fakeContext(spool, [...models], fails);
    await withEnv(spool, async () => {
      await plugin.setup(ctx as never);
      await hooks.get("context")!(sampleEvent());
    });
    const day = new Date().toISOString().slice(0, 10);
    const record = JSON.parse(
      readFileSync(join(spool, day, "captures.jsonl"), "utf-8").trim(),
    );
    equal(record.model_limits, null);
    equal(record.invocation_sequence, 1); // capture still happened
    rmSync(spool, { recursive: true, force: true });
  }
});

test("a restarted plugin continues the session's sequence instead of restarting at 1", async () => {
  const spool = tmpSpool();
  const numbers: number[] = [];
  for (let process_ = 0; process_ < 3; process_++) {
    const { hooks, ctx } = fakeContext(spool); // a fresh plugin instance, as after a restart
    await withEnv(spool, async () => {
      await plugin.setup(ctx as never);
      await hooks.get("context")!(sampleEvent());
      await hooks.get("context")!(sampleEvent());
    });
  }
  const day = new Date().toISOString().slice(0, 10);
  for (const line of readFileSync(join(spool, day, "captures.jsonl"), "utf-8")
    .trim()
    .split("\n"))
    numbers.push(JSON.parse(line).invocation_sequence);
  deepEqual(numbers, [1, 2, 3, 4, 5, 6]);
  rmSync(spool, { recursive: true, force: true });
});
