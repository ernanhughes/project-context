# Frozen probe spec: runtime-live-6dr1 (Stage 6D-R1 requalification)

Requalification after the Stage 6D-L clean FAIL. Nothing in the 6D-L
record is rewritten: `evidence/qualifications/runtime-live-6dl.json`,
`docs/stage-6d-live-qualification.md`, and `experiments/runtime-live-6dl/`
stay immutable, and their conclusion stands (the intervention plugin
never loaded, so hook mutation semantics were not tested).

Status: **spec frozen, no live call made under it yet.**

## Repair under test

One minimal repair, committed separately before this spec: the
runtime package gained a loader entrypoint (`src/index.ts`, a pure
re-export of the frozen hook) and an env-gated qualification trace
(`src/trace.ts` plus trace call sites in `src/runtime.ts`; injection
semantics unchanged). Renderer, injector, reconciler, observer,
compiler, ledger, activation, and adapter are untouched.

Recorded minimum difference between the working observer package and
the failing runtime package: the loader resolves a plugin directory
through its entry file, observed as `entrypoint=.../index.ts` in the
server log; the runtime directory shipped no such file and was
silently skipped.

## Questions (kept separate in the result)

- Q1 loader: can OpenCode discover and execute the intervention
  plugin through the supported entrypoint mechanism?
- Q2 injection: once the plugin demonstrably executes, does the
  Stage 6D runtime mutation reach the model invocation observed
  independently by the read-only observer?

## Synthetic payload (deterministic, fixed here)

Same marker as 6D-L for comparability (`ORANGE-QUARTZ-731`), new
bundle identity. Built by the probe script from these exact values
through the frozen Stage 6D render code (policy `runtime-render-v1`):

- bundle id: `rt-live-probe-6dr1`
- item id: `live-probe-item-r1-001`, source `ledger`, kind
  `test_constraint`, content (exact, three lines):

```text
RUNTIME-LIVE-PROBE-6D-R1
For this synthetic qualification request only,
the marker value is ORANGE-QUARTZ-731.
```

Injection location: `system-append`. No secrets, paths, user data,
repository facts, commit IDs, or task answers.

## Synthetic task (transport only, deliberately trivial)

Prompt (exact): `Reply with exactly the word READY and nothing else.`
The model response is diagnostic only, never the criterion.

## Live-call policy

- Phase A (zero-model loader probe) first: an invalid model name, so
  no request can occur, with debug logging. PASS requires the server
  log to resolve the runtime entrypoint plus a trace setup record
  with hook registration. If Phase A fails: STOP, no model request,
  loader FAIL.
- Phase B only if Phase A passes. Target: **1 actual model
  invocation**, cap **2 total**; a second call only to distinguish
  hook semantics, with the reason recorded first.
- Model: small local model at zero spend, as in 6D-L.

## Throwaway environment and opt-in

Fresh temp directory with only a synthetic marker file; probe spool
and trace directories under temp, wired only through child-process
environment (`PROJECT_CONTEXT_SPOOL_DIR`,
`PROJECT_CONTEXT_RUNTIME=inject`,
`PROJECT_CONTEXT_RUNTIME_BLOCK`,
`PROJECT_CONTEXT_RUNTIME_TRACE_DIR`). The runtime stays disabled by
default everywhere else. Pre-existing global plugin state is backed
up before and restored after (hash-verified).

## Deployment (observer independence preserved)

The observer is not modified. Both packages deploy byte-identical to
their committed sources (hashes recorded); the runtime deploys with
its new entrypoint and trace files. The observer learns of any
injection only by observing the invocation. The trace file is
qualification-local (counts and outcomes only, never block text) and
is never committed.

## Gate ladder (overall PASS needs every gate)

1. loader: entrypoint resolved, plugin initialised, hook registered;
2. execution: hook invoked, qualification mode recognised, block
   available, inject path executed (per trace outcomes);
3. mutation: trace reports `injected` with single-block growth;
4. observation: observer capture carries the marker exactly once, last;
5. reconciliation: receipt-equivalent ↔ observed invocation PASS.

Ordering (`runtime-before-observer` versus
`observer-before-runtime-or-nonpersistent` versus `unknown`) is
inferred from trace plus capture, never from registration order
alone. If the plugin loads and runs but the marker does not persist,
STOP at that boundary: loader PASS, execution PASS, mutation FAIL.

## Fail-safe rule

No monkey-patching the observer, no rewriting internal OpenCode
files, no network interception, no provider-client replacement, no
unrelated hook modification. If no clean supported mutation boundary
appears, report exactly that.

## Privacy

Artifacts carry digests, counts, booleans, and outcome summaries
only. Server-log text and trace content stay local and are never
embedded. All probe input is synthetic. Nothing is published
automatically.
