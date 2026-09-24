/**
 * Entrypoint discoverability tests (node:test, no test framework).
 *
 * Stage 6D-L failed because the runtime package shipped no plugin
 * entry file, so the OpenCode loader silently skipped the directory
 * (observed: directories resolve through `<dir>/index.ts`, single
 * `.ts` files load directly). These tests pin the discoverable shape
 * without requiring a model call:
 *
 * 1. `src/index.ts` exists and re-exports the default plugin from
 *    `./runtime.ts` (no logic moves into the entrypoint).
 * 2. `src/runtime.ts` default-exports a `Plugin.define` plugin with
 *    the frozen id and registers exactly one `context` hook through
 *    the plugin session object.
 */

import { equal, match, ok } from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

const index = readFileSync(join(srcDir, "index.ts"), "utf-8");
const runtime = readFileSync(join(srcDir, "runtime.ts"), "utf-8");

{
  // The entrypoint is a pure re-export: no hook logic, no block logic.
  equal(
    index.includes('from "./runtime.ts"'),
    true,
    "index.ts must import from ./runtime.ts",
  );
  match(index, /export\s*\{\s*default\s*\}/);
  equal(index.includes("session.hook"), false);
  equal(index.includes("event.system"), false);
}

{
  // The frozen hook keeps its loader-required shape and id.
  match(runtime, /export\s+default\s+Plugin\.define\(/);
  match(runtime, /id:\s*"context-runtime-injection"/);
  const hooks = runtime.match(/pluginCtx\.session\.hook\("context"/g) ?? [];
  equal(hooks.length, 1, "exactly one context hook registration");
  ok(
    runtime.includes('from "./trace.ts"'),
    "hook outcomes are traced for qualification",
  );
}
