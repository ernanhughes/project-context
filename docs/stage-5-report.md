# Stage 5 report — V2 capture migration plus Context Debugger v1

## Baseline

- Stage 4 state: committed locally (working tree clean at Stage 5
  start except for the staged migration work itself).
- Installed OpenCode version at execution time: **2.0.16** (V2 API
  line; `opencode --version` → `v2.0.16`).
- Published `@opencode/plugin` latest dist-tag at execution time:
  **2.0.16** (verified via registry; design-time expectation of 2.0.4
  superseded per the cut-over rule: target the newer single stable).
- Pinned plugin package: `@opencode/plugin` **2.0.16** exact
  (devDependency; type-only at runtime, zero runtime dependencies).
- TypeScript toolchain: `typescript@7.0.2`, `prettier@3.9.9`,
  `@types/node@25.0.3`, all exact; tests on Node v25.8.2 built-in
  runner; Python 3.11, pytest 9.1.1, ruff 0.16.6.
- Verification date: 2026-09-24. V2 hook shapes verified against the
  installed `@opencode/plugin@2.0.16` promise-type declarations
  (`SessionContext`: sessionID/model/agent/system/messages/tools/options;
  compaction and generate extend it; title does not) and the official
  V2 plugin and V1→V2 migration documentation — not remembered docs.

## Target decision

Single-target cut-over, no dual runtime. The design-time pin
(OpenCode 1.18.31, `@opencode/plugin` 2.0.4) was superseded at
execution time by the newer stable above; every pin below names the
executed versions. V1 code paths, schemas, hooks, fixtures, and tests
are retired from active use. A `BRIDGE_SCHEMA_V1` alias name and the
historical V1 fixture/reports remain for provenance; nothing active
reads them.

## Capture boundary

Observed (read-only): `session.hook("context")` — assembled
system/messages/tools/options plus session/agent/model identity and
invocation sequence, one record per observed primary model request;
`session.hook("compaction")` and `session.hook("generate")` recorded
with an explicit request kind and filtered from primary timelines by
default. Tool definitions carry description plus input schema only
(no executables). Options are observed overrides only. Model limits
come from `ctx.model` where available, else UNAVAILABLE.

NOT observed: byte-for-byte provider HTTP request, provider-added
material, wire representation, cache decisions, usage/cost/latency
telemetry (all None/UNAVAILABLE, never zero), title-generation
requests (different event shape; deferred, documented).

Capture stage string: `opencode.v2.model_context`. Version mismatch at
setup fails clearly; no fallback.

## Files changed

- `integrations/opencode/` rewritten for V2: `package.json` (0.2.0,
  `@opencode/plugin` 2.0.16), `src/{schema,capture,index}.ts`,
  `tests/capture.test.ts` (14 tests), `README.md`. V1 sources deleted
  by replacement (same paths, no V1 code remains).
- `src/project_context/domain/provenance.py`: `CaptureProvenance`
  gains optional `plugin_api_version` and `request_kind`
  (backward-compatible).
- `src/project_context/opencode/bridge.py`: V2-only validation
  (`project_context.opencode_capture.v2`), V1 rejection with a
  retirement message, canonical-integrity helper shared with tests.
- `src/project_context/opencode/ingest.py`: one V2 record → one
  bundle + one invocation; deterministic tool-definition items sorted
  by tool name; `SequenceTracker` kept as fallback ordering only.
- `src/project_context/opencode/prevalence.py`: tool definitions
  OBSERVED (role, composition, `tool_definition_stats`); V2 boundary
  wording.
- `src/project_context/debugger/` (new): `domain.py`, `analyse.py`,
  `query.py`, `doctor.py`, `report.py`. Zero model calls, zero network,
  stdlib only.
- `src/project_context/cli/main.py`: `contextlab debug
  latest|inspect|timeline|compare|explain|query|doctor` (text plus
  deterministic versioned JSON); `opencode inspect|ingest`, campaign
  defaults, and prevalence boundary moved to V2.
- `src/project_context/corpus/campaign_store.py`: request-kind
  accounting; `compaction_observed` reflects kind=compaction records.
- `fixtures/opencode-capture-v2/session-three-requests.json` (new
  golden, SYNTHETIC) plus a derived JSONL spool; generator at
  `scripts/make_v2_golden.py` (deterministic).
- `tests/test_opencode_capture.py` rewritten for V2 (21 tests);
  `tests/test_corpus_campaign.py` helpers migrated to V2;
  `tests/test_debugger.py` new (26 tests).
- Specs: `architecture.md` (Stage 5 section), `measurement-contract.md`
  (V2 boundary), `opencode-capture-protocol.md` (rewritten for V2),
  `privacy.md` (debugger boundary); `AGENTS.md` capture rules;
  `README.md` current-state section.

## V1 removal

Deleted/replaced: V1 adapter sources (`schema/capture/index.ts`
rewritten), V1 tests (rewritten), V1 bridge contract (V2-only reader),
V1 ingest mapping (replaced), V1 campaign helper shapes in tests.
Retired hooks: `experimental.chat.system.transform`,
`experimental.chat.messages.transform`, `chat.message`,
`tool.execute.after`. Retired schemas: active V1 bridge reads.
Retired fixtures: active V1 golden (file retained, unread by code).
Confirmed: no active V1 fallback, no dual-version runtime, no
`latest`-tracking dependency.

## V2 observability gains (vs Stage 1/2 gaps)

Now observed: assembled semantic system, assembled messages, tool
definitions (closes gap 2), model, agent, request overrides,
compaction requests as kind-tagged records (partially closes gap 5).
Still unobserved: provider usage/cache telemetry (gap 3),
response-side observation (gap 4), provider wire payload.

## Privacy

Raw captures remain local-only and git-ignored; debugger default
output is structural (local session ordinals, no content, no raw
identifiers, no hashes); content printing/searching requires explicit
local flags with warnings; debugger makes zero model calls and sends
nothing to the network. Pinned by 26 debugger tests plus the existing
export-gate tests.

## Validation

- 182 Python tests pass (`pytest`); `ruff check .` clean;
  `ruff format --check .` clean; `git diff --check` clean.
- 14 TypeScript tests pass (`npm test`); `tsc --noEmit` clean;
  `prettier --check .` clean.
- Deterministic double-runs of debugger JSON verified byte-identical
  (test-pinned for `debug latest`; manually repeated for all seven
  commands during development).
- TS↔Python integrity agreement verified: the golden test rebuilds all
  three records in TypeScript and byte-compares, including sha256 over
  canonical blocks.

## Real captures

None yet under V2. The first genuine session will exercise the
installed plugin path end to end; until then, all debugger output
shown anywhere is labelled synthetic-or-local and no prevalence claim
is made.

## Deliberate deferrals

Context modification of any kind, compiler insertion into live
context, automatic recommendations, TUI, semantic duplicate detection,
behavioural utility inference, provider-wire capture, title-request
capture, SQLite derived index (JSONL loading is sufficient at current
corpus sizes).
