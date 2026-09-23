# Measurement contract — Context Lab v0

Every measurement recorded by this repository states, at minimum:

1. **What was measured**: metric name plus the exact record and field.
2. **How**: instrument or procedure version (evaluator id, e.g.
   `project_context.scoring.exact_match.v1`).
3. **Provenance of numbers**: `provider`, `local-tokenizer`,
   `approximation`, or `unavailable` — per value, never per report.
4. **What is missing**: unobserved components listed, not zero-filled.
5. **Evidence class**: `synthetic` or `provider-observed`, on the bundle,
   the manifest, and the artifact.

## Rules

- Token estimates from `estimate_tokens` are labelled `approximation` at
  creation and must never be stored as provider telemetry.
- Cost is always computed from an explicit `PriceSchedule` version recorded
  alongside the result. Recompute historical costs only under the schedule
  that applied at the time.
- Latency, cache reads/writes, and reasoning tokens default to unavailable.
- Evaluation verdicts (PASS/FAIL/INCONCLUSIVE) require stated evidence; a
  verdict without an evidence string is invalid.
- No measurement may silently mutate the record it measures. Analysis
  layers append; raw observations are never rewritten.

## Stage 1: OpenCode pre-dispatch partial capture

Observed at the hook (V1 experimental transforms, admission, tool-after):

```text
system structure, message order and parts, tool results with call linkage,
session/agent/model identity where the hook carries it, hook-time ordering
```

Exact local measurements (no model, no network):

```text
bytes, characters, item counts, content equality via local fingerprints,
structural prefix equality within one session scope
```

Derived or estimated (labelled as such):

```text
local token estimate (approximation), repetition classifications,
stable-prefix ratios, growth deltas
```

Unavailable at this boundary unless separately observed (stay None,
never zero):

```text
provider cache hits, wire payload bytes, provider-added prompt material,
final resolved model defaults, provider usage and cost, response latency
```

Assistant-message token/cost fields visible inside stored history describe
past computations, never the current invocation; the ingester does not
transfer them into invocation telemetry.
