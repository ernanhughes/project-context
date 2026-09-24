# Stage 6D report — Explicit Context Runtime Injection

## Purpose

Close the mechanical loop without claiming usefulness: render an
already-selected compiler bundle, inject it through a separate
explicit runtime, observe the result with the unchanged read-only
observer, and reconcile intended versus observed. Stage 6D establishes
integration, not effectiveness.

Design: `experiments/runtime-v1/` (frozen integration contract,
question, conditions, measurements, falsification). No model calls; no
behavioural run; nothing here is book evidence.

## Architecture

```text
Stage 6A:  events → LedgerState
Stage 6B:  + request → activation
Stage 6C:  + adapter → ordinary candidates → EXISTING compiler → bundle
Stage 6D:  bundle → deterministic render → explicit inject →
           InjectionReceipt → model request →
           EXISTING observer captures → reconcile
```

Permanent separation: the component that changes context is not the
component that measures context.

## Renderer

`render_bundle(bundle, RenderPolicy)`: one canonical block,
`[CONTEXT RUNTIME] … [/CONTEXT RUNTIME]`, one `[KIND]` section per
selected item in compiler order, verbatim bodies (6C epistemic tags
survive; no paraphrase, compression, or history). Empty selections
render empty. No item outside the bundle can enter by construction.

## Intervention integration

`integrations/opencode-runtime/` is a separate package owning
mutation; the observer never imports it and vice versa (pinned).
Opt-in only (`PROJECT_CONTEXT_RUNTIME=inject`); fail-safe single
write; idempotent on identical blocks; loud refusal on differing
blocks. **Hook mutation contract explicitly unverified**: assigning
the assembled system array inside `session.hook("context")` is
unconfirmed against live OpenCode 2.0.16 — no live probe was run, per
the stage constraints. The tested surface is the Python synthetic
harness; one throwaway live probe is the named next live step and
counts as no evidence.

## Injection location and opt-in

Single documented choice: append to the system array
(`system-append`, recorded in every receipt). Python `inject()`
additionally requires the literal runtime mode and refuses malformed
shapes loudly. Fresh/default setups cannot mutate.

## Receipts

`InjectionReceipt`: request/bundle/render ids, rendered digest,
candidate ids, policy id, location, pre/post digests on the
observer's own integrity basis, byte count, typed status
(injected/noop_empty/noop_idempotent/failed), failure reason. No raw
content (privacy: receipts are shareable, blocks are local-only).

## Reconciliation

`reconcile(receipt, rendered, observed)`: record validity, marker
presence, byte-exact singularity, append-order plus internal section
order, and whole-request integrity equality with the receipt. PASS
needs all; FAIL names the violated check. Non-injected receipts
reconcile as their own kind (empty demands absence + pre-integrity;
failures stand alone as not_applicable).

## Synthetic fixtures

`fixtures/runtime-v1/` (SYNTHETIC): 9 harness cases (empty, single,
pending, mixed, rejected-absent, idempotent, conflict, tampered
×4, privacy trap) over hand-built bundles and minimal V2 records,
observed through the unchanged ingester. Dormant/unknown exclusion is
structural (no candidate, no bundle) and covered at the adapter layer.

## Idempotence, failure, privacy

Second identical injection is byte-identical; differing blocks fail
unmutated; empty selections no-op; malformed inputs raise. Failures
are typed receipts, never partial writes. Private-looking unselected
strings never appear; receipts carry no content.

## Observer compatibility

Injected records validate and ingest through the existing pipeline
unchanged; the observer's read-only pins (no result-setting, no event
writes) are extended to all event fields and still hold. The observer
learns of injections only by observing them.

## No-bypass

The renderer accepts only bundles; the runtime imports no
ledger/activation/compiler packages (scan-pinned) — only domain
records and the read-only bridge hash/validator. Nothing outside the
selected bundle can be added at this layer.

## Tests

`tests/test_runtime.py`, 28 tests: determinism, empty no-op, exact
single render, unselected absence, order, epistemic survival,
metadata hygiene, digest behaviour, idempotence, conflict safety,
opt-in refusal, malformed refusal, receipt lineage, observer capture,
clean-case PASS, four tamper FAILs with named checks, privacy trap,
dormant exclusion, consumption boundaries, import hygiene, observer
read-only, TS separation, input immutability, 6A/6B/6C stability
re-verified, runtime-file truth separation, CLI demo. Plus one
passing node:test file for the TS marker helpers.

Results: 438 passing at baseline; **466 passing** at finish (28 new),
`ruff check .` clean. No historical artifacts modified; no runs
fabricated; no model calls; no live sessions.

## Measurements (structural)

Render determinism, selected coverage, zero unselected leakage,
duplication counts, order preservation, epistemic preservation,
injection success, reconciliation success, idempotence, observer
compatibility — each reported, none composited.

## What Stage 6D establishes

A selected bundle can be rendered, injected through a separate
explicit runtime, and independently verified at the model-request
boundary without bypassing compiler policy or touching the observer.

## What it does NOT establish

Task success, activation ecology, bundle optimality, ledger utility,
extraction, deployment readiness.

## Deferred and declined

6E extraction and F4B behaviour explicitly not started; F10
untouched; no live campaigns; runtime stays off for ordinary work.
The recommended next decision — oracle-state F4B before extraction —
is recorded but not taken here.

## Deviations

None structural. Exact-fit adapter budgets (C:108, D:14) are
 reaffirmed as fixture mechanics for "can lose/omit", not realistic
thresholds, and must not be inherited as meaningful values later.
