# Frozen probe spec: runtime-live-6dl (Stage 6D-L)

Live injection qualification for the Stage 6D OpenCode runtime
integration. This spec is frozen before the probe runs; the outcome is
recorded separately in `evidence/qualifications/runtime-live-6dl.json`
and reported in `docs/stage-6d-live-qualification.md`.

Status: **spec frozen, no live call made under it yet.**

## Qualification question

> Can the explicitly intervention-capable OpenCode runtime inject a
> deterministic context block into one real request such that the
> independent read-only observer subsequently records that same block
> at the model-request boundary?

A PASS establishes live integration viability only. It does not
establish behavioural usefulness, and it counts as no book evidence.

## Non-goals (explicitly out of scope)

- Stage 6E extraction. F4B behaviour. Automatic anything.
- Task success, instruction following, reasoning quality, recall.
- Turning the runtime on for ordinary work.

## Synthetic payload (deterministic, fixed here)

Selected bundle: `rt-live-probe-6dl`, one item, built by the probe
script from these exact values through the frozen Stage 6D domain and
render code (`src/project_context/runtime/render.py`,
policy `runtime-render-v1`):

- item id: `live-probe-item-001`
- item source: `ledger`
- item kind: `test_constraint`
- item content (exact, three lines):

```text
RUNTIME-LIVE-PROBE-6D-L
For this synthetic qualification request only,
the marker value is ORANGE-QUARTZ-731.
```

Expected rendered block (exact, five lines):

```text
[CONTEXT RUNTIME]
[TEST CONSTRAINT]
RUNTIME-LIVE-PROBE-6D-L
For this synthetic qualification request only,
the marker value is ORANGE-QUARTZ-731.
[/CONTEXT RUNTIME]
```

Expected marker: `ORANGE-QUARTZ-731`.
Injection location: `system-append` (single documented choice).
The block contains no secrets, paths, user data, repository facts,
commit IDs, or task answers.

## Synthetic task (transport only, deliberately trivial)

Prompt (exact):

```text
Reply with exactly the word READY and nothing else.
```

No files to read, no tools needed, no meaningful coding work. The
model response is diagnostic only and is never the qualification
criterion. The authoritative evidence is the independently observed
request (receipt ↔ observed invocation, never "the model says it
saw it").

## Live-call policy

- Target: **1 actual model invocation.**
- Cap: **2 live calls total.** A second call is permitted only to
  distinguish hook semantics (e.g. hook ordering), with the reason
  recorded before the call is made. No accumulation of evidence.
- Model: the cheapest OpenAI-compatible mini model reachable through
  ambient authentication. Model identity is recorded as observed in
  the capture, never asserted from the request name.
- If the integration fails before a model request occurs, diagnose
  structurally and stop.

## Throwaway environment

- Fresh directory under the system temp area, containing only a
  synthetic marker file. No book manuscript, no project data, no
  credentials, no personal information.
- Probe spool directory under the system temp area, used only through
  `PROJECT_CONTEXT_SPOOL_DIR` in the child process environment. The
  real capture spool is untouched.
- `PROJECT_CONTEXT_RUNTIME=inject` and
  `PROJECT_CONTEXT_RUNTIME_BLOCK=<rendered block file>` are set only
  in the child process environment. The runtime remains disabled by
  default everywhere else.

## Deployment (observer independence preserved)

- `integrations/opencode/` (the read-only observer) is not modified.
  The deployed observer copy is the frozen Stage 6D source,
  hash-recorded in the artifact.
- `integrations/opencode-runtime/` (the intervention surface) is
  deployed byte-identical to the frozen Stage 6D source,
  hash-recorded in the artifact. No probe-specific edits.
- Pre-existing global plugin state is backed up before the probe and
  restored afterwards (leave-no-trace for ordinary work).
- The observer learns of the injection only by observing the actual
  invocation. Any direct injection-to-observer signalling invalidates
  the probe.
- The TypeScript runtime emits no injection receipt; acceptance is
  evidenced by a clean run (exit 0, model response produced, no hook
  error) plus the independent capture. The absence of a machine
  receipt on the live path is recorded as a limitation.

## Pre-flight checklist (mechanical, all required before the call)

- runtime opt-in absent from the parent environment (default-off
  proven), set only for the probe child process;
- observer source unmodified in git; deployed hashes recorded;
- runtime source unmodified in git; deployed byte-identical;
- throwaway directory active and containing only synthetic material;
- rendered block written with exact bytes; digest known;
- probe spool inventory snapshotted (only appended bytes qualify);
- ordinary user/project data absent from every probe input.

## What to capture (digests in the artifact, raw records local-only)

- selected bundle id and digest;
- rendered block text (synthetic, publishable) and digest;
- injection location;
- run outcome: exit code, hook-error absence, model-response digest;
- every new observed invocation: record validity, marker occurrence
  count, byte-identity, placement, whole-request integrity;
- OpenCode version, plugin package versions, deployed file hashes,
  repository revision.

Raw spool records stay under the temp probe directory (never
committed). The artifact carries digests, counts, and the verdict.

## PASS criteria (all required; otherwise FAIL, never PARTIAL)

- runtime opted in explicitly for the probe child only;
- live run completed without a hook error;
- the independent observer captured the invocation(s);
- the expected runtime block is present in every new primary
  (`context`-kind) observed record;
- the block is byte-identical to the rendered reference;
- it appears exactly once per record;
- it is the last system block (append order) with internal section
  order preserved;
- no unexpected runtime content appears;
- whole-request integrity is internally consistent.

## Fail-safe rule

If the live OpenCode API does not provide a clean supported mutation
boundary: stop. No monkey-patching the observer, no rewriting
internal OpenCode files, no network interception, no provider-client
replacement, no unrelated hook modification. Report that the current
integration does not expose a validated supported intervention
boundary through the mechanism tested.

## Privacy

The artifact is scanned before it is written: no secret-like tokens,
no filesystem paths, no user or account names, no repository facts.
The probe is publishable by construction because all input is
synthetic. Nothing is published automatically.
