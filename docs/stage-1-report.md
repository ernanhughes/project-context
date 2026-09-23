# Stage 1 report — read-only OpenCode capture

## Baseline

- Project Context Stage 0 local commit SHA: `dccc796` (working tree was
  clean; no new commit needed).
- Installed OpenCode version: **1.18.27** (V1 API line).
- Pinned plugin package: `@opencode-ai/plugin` **1.18.27** exact
  (devDependency; type-only at runtime, zero runtime dependencies).
- TypeScript toolchain: `typescript@7.0.2`, `prettier@3.9.9`,
  `@types/node@25.0.3`, all exact; tests on Node v25.8.2 built-in
  runner; Python 3.11, pytest 9.1.1, ruff 0.16.8.
- Verification date: 2026-09-23. API surface verified against the
  installed 1.18.27 SDK types, not remembered docs.

## Target decision (重要)

The installed environment is **V1, not V2**. V1 exposes no unified
pre-dispatch assembled-context hook, so this stage implements a **pinned
V1 adapter**, not an imitation of the V2 `session.context` design. The
bridge schema already carries optional full blocks so a future V2
adapter reuses it. No pretend compatibility layer was created.

## Capture boundary

Observed (read-only): `experimental.chat.system.transform` (system
array, sessionID+model where present), `experimental.chat.messages.
transform` (message list, **no identity** — hook input is `{}`),
`chat.message` (admission inventory), `tool.execute.after` (result text
with session+call linkage; input args deliberately excluded).

NOT observed: assembled provider request (no such V1 hook), per-tool
definitions (no invocation linkage), generation settings (not context
membership), compaction (separately hooked, deferred), HTTP/WebSocket
transport (deliberately excluded: credential exposure, one-shot
streams, transport coupling), usage/cost/latency telemetry (unavailable
at this boundary; past-computation token fields on stored messages are
not transferred).

Capture stage string: `opencode.v1.pre_dispatch_partial`. Provider
lowering happens after capture; later-registered plugins may mutate
after capture (load last; assumption recorded per record).

## Files changed

- `integrations/opencode/` (new): `package.json`, `tsconfig.json`,
  `README.md`, `src/{schema,capture,index}.ts`, `tests/capture.test.ts`
  (10 tests: tsc + node:test + prettier clean).
- `src/project_context/domain/`: `provenance.py` (new
  CaptureProvenance), `items.py` (+ optional `ref`),
  `bundles.py` (+ optional `provenance`, ref threading).
  Backward-compatible: all 18 Stage 0 tests green unchanged.
- `src/project_context/opencode/` (new): `bridge.py` (schema gate,
  crash-tolerant JSONL loader), `ingest.py` (record→bundle+invocation,
  part mapping with opaque fallback, per-scope sequencing),
  `prevalence.py` (aggregates, fingerprints, structural prefix,
  export gate).
- `src/project_context/cli/main.py`: `opencode inspect|ingest`,
  `corpus prevalence [--export]`.
- `fixtures/opencode-capture-v1/primary-one-request.json`: golden
  synthetic fixture shared by TS and Python tests.
- `tests/test_opencode_capture.py`: 13 tests.
- Specs: architecture/measurement/privacy appends,
  `specs/opencode-capture-protocol.md` (new), AGENTS.md Stage 1 rules.

## Bridge schema

`project_context.opencode_capture.v1`: schema, capture_id (UUID),
captured_at, capture_stage, hook_kind, session_id?, agent?, model?,
sequence_scope/index, adapter/opencode/plugin-api versions,
observer_position, payload (one observed block only), integrity sha256
(producer-local canonical bytes), timings_ms, evidence_class
`opencode_capture`. Unknown schemas rejected loudly on both sides.

## Read-only proof

TS test snapshots hook input/output before capture and deep-equals
afterwards; adapter code paths contain no writes to hook objects
(reviewed plus tested). Overhead is measured, never assumed.

## Storage/privacy

Opt-in `PROJECT_CONTEXT_CAPTURE=1` (default disabled, tested);
spool `~/.local/share/project-context/captures/<date>/captures.jsonl`
overridable, UUID filenames, append-only with loud I/O failure;
ingester never modifies raw files; malformed trailing lines skipped and
counted; export relabels sessions and refuses content/identifier/hash/
secret markers (tested, including adversarial report).

## Ingestion

One validated record → one bundle (`opencode-<capture_id>`) + one
linked invocation. Part mapping: text by role, completed tool parts to
tool_result with call linkage, reasoning passthrough, everything else
opaque JSON (unknown-part test). Tool input args excluded by policy.
Per-scope sequence counters; unlinked scope for identity-free records.

## Metrics

Structural-only by default: sizes (bytes/chars exact, tokens
approximation-labelled), kind/source shares, session growth deltas,
within/across repetition counts, structural shared prefix with scope
refusal, tool-result and system byte shares. No tokenizer dependency:
exact bytes/chars plus approximation is the honest Stage 1 position.

## Token accounting

Bytes/chars exact; token counts via documented naive estimator marked
`approximation`; provider fields `None`. No heavy tokenizer added: no
exact tokenizer exists for arbitrary captured models, and a false exact
count is worse than none.

## Instrument overhead

Adapter records serialize/write/total milliseconds per capture;
TS tests assert presence without asserting values. No live dispatch
timings exist yet (no smoke session run); model-latency impact is
explicitly unclaimed.

## Real captures

None. A load smoke attempt (plugin copied to a scratch project,
25-second headed run) produced no conclusive evidence about plugin
loading and no capture records; no model was called and no user task
was executed. Real-trace analysis is pending the first user-activated
captured session. No results are claimed from the synthetic golden
fixture beyond schema compatibility.

Incident: during smoke-test cleanup an over-broad process stop
terminated pre-existing user OpenCode processes. No data was touched,
but the procedure was wrong; future smoke tests must never manage user
processes (rule added to AGENTS.md and the collection protocol).

## Architecture implications

Two minimal core additions, both backwards-compatible and
test-covered: `CaptureProvenance` on bundles and `ref` on items. No
other Stage 0 record changed. The V1 boundary confirms the book's
standing assumption that harness-side capture sees client assembly
only, never provider behaviour — consistent with Chapter 2's opaque
server-side spans.

## OpenCode limitations

Provider lowering after hook; plugin ordering (assumption recorded,
not verifiable); messages.transform carries no identity (parts may);
tool definitions and generation settings unobserved; compaction
separately hooked and deferred; HTTP/WebSocket excluded by design;
response/usage telemetry unavailable; per-message historical
token/cost fields deliberately not transferred.

## Privacy risks

Raw captures can contain source, conversation, tool output, system and
project instructions, and shown secrets. Mitigations: opt-in default
off, user-local git-ignored spool, UUID filenames, no raw stdout,
no uploads, args excluded from tool records, export gate with
adversarial tests. Residual risk: operator error (wrong spool dir,
shared terminal output with --show-content); documented, not solved.

## Recommended Stage 2

Collect the ~10-session ecological corpus under the collection
protocol, then run the first prevalence analysis. Do not build
interventions yet: the corpus must first confirm or refute the book's
standing predictions (tool-definition share, repetition prevalence,
growth shapes) before any mechanism earns implementation. If V2 adoption
lands in the environment, re-target the adapter to `session.context`
behind the same bridge schema instead.
