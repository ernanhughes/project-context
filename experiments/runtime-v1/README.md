# runtime-v1 — explicit injection with independent observation (design)

Status: design only until the synthetic harness validates it. No model
calls. Not book evidence under any outcome.

## Question

Can the output of the existing Context Compiler be injected through a
separate explicit runtime and independently observed at the
model-request boundary without bypassing compiler policy or modifying
the observer?

## Why structural first

A behavioural test now would confound six explanations (extraction,
ledger, activation, admission, rendering, model behaviour). The loop
below isolates the last mechanical boundary: intended injection versus
observed invocation.

```text
selected bundle → render → inject → observe → reconcile
```

## Method

Synthetic V2-shaped requests plus hand-built selected bundles. The
existing ingester serves as the observer; reconciliation compares
receipt + rendered reference against the observed record. Adversarial
cases: empty selection (no mutation), unselected leakage, duplicate
injection (idempotent), conflicting block (loud failure), tampered
post-injection records (reconciliation must fail), private-looking
unselected material (must never appear), dormant/unknown state (never
reaches the renderer by construction).

## Measurements (structural only)

Render determinism; selected-item coverage; unselected leakage;
duplication count; order preservation; epistemic-label preservation;
injection success; reconciliation success; idempotence; observer
compatibility. No composite score.

## Null and negative outcomes

- **Reconciliation fails on correct requests:** the injection model
  does not match the observed shape; fix the runtime, not the test.
- **Observer cannot ingest injected records:** the injection location
  is wrong for the capture schema; relocate explicitly.
- **Live hook shape differs:** the TypeScript skeleton is revised
  after exactly one throwaway live probe, which counts as no evidence.

## Depends on

Compiler-v1 fixtures (selection semantics), the V2 bridge schema and
ingester (observation), Stages 6A–6C (selected bundles with epistemic
payloads). Follows F4B/F10 designs; alters neither.
