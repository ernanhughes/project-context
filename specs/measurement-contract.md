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
## Stage 5: OpenCode V2 model-context capture

Observed at the session context hook (V2 assembled request, primary
agent-loop scope unless a kind filter says otherwise):

```text
assembled system structure, message order and parts, tool definitions
(description plus input schema, sorted deterministically), tool results
with call linkage, session/agent/model identity, invocation sequence,
observed request overrides, declared model limits where the API yields
them (else UNAVAILABLE)
```

Exact local measurements (no model, no network):

```text
bytes, characters, item counts, content equality via local fingerprints,
structural prefix equality within one session scope, tool-definition
counts/bytes/share/stability, per-category composition
```

Derived or estimated (labelled as such):

```text
local token estimate (approximation), repetition classifications,
stable-prefix ratios, growth deltas, deterministic doctor observations
under debugger-doctor-policy-v1 (magnitude only, never harm/utility)
```

Unavailable at this boundary unless separately observed (stay None or
UNAVAILABLE, never zero):

```text
provider cache hits, wire payload bytes, provider-added prompt material,
complete effective provider configuration, provider usage and cost,
response latency
```

The debugger's request `options` are observed overrides: an empty
object means no overrides were observed, never that no model defaults
exist. Deleting or omitting an override falls back to configured
defaults; the debugger must not present overrides as the resolved
configuration.

## Shared measurement vocabulary

Several chapters proposed overlapping measurements. This section defines each once.
Chapters and experiments use these terms and these definitions, and add none
without adding it here.

Three rules govern all of them:

- **Dimensions stay separate.** There is no composite "context quality" score. A
  later analysis may justify combining dimensions, but only by stating why in its
  own preregistration.
- **Every value carries its provenance** (`provider`, `local-tokenizer`,
  `approximation`, `unavailable`), and `unavailable` is never zero.
- **Every rate reports its denominator**, and per-task outcomes are kept beside any
  aggregate.

### Behaviour

Scored by deterministic graders over a parsed, schema-constrained action. No
model judges any of these.

| Term | Definition | Existing metric |
|---|---|---|
| task success | 1 when every graded field of the action equals the fixture's correct value, else 0. Partial credit only where the grader defines an objective per-field score in advance | `*:task_score` |
| constraint adherence | fraction of the fixture's declared constraints the action does not violate; the per-constraint booleans are kept | family-specific |
| harmful action | the action is in the fixture's forbidden set. Harm is defined by the fixture, never inferred | `*:harmful_action` |
| unsupported claim | a value in the action that appears in no admitted item and not in the task text (exact match) | new |
| abstention | the action is the fixture's abstain action | action name |
| evidence use | the action contains the decisive value, and the decisive item was admitted. It is **not** influence: influence is shown only by a remove-and-restore pair | new |
| parse success | the response parsed under the frozen schema. Unparseable output is recorded, never repaired | `*:parse_success` |

### Context

Computed from the rendered bundle and the decision trace.

| Term | Definition |
|---|---|
| rendered tokens | tokens in the exact rendered bundle, with provenance |
| tokens by source | rendered tokens grouped by source kind and item kind |
| duplicate tokens | tokens in an item whose bytes are identical to an earlier item in the same bundle or the previous request |
| stable prefix | number of leading items (and tokens) identical to the previous request in the same session |
| admitted, dropped, transformed | item ids in each state, from the decision trace |
| item fidelity | the representation an item was rendered in: full, dense, compact, anchor, reference |
| evidence position | position of the decisive item as a fraction of rendered tokens (0 first, 1 last) |
| bundle digest | digest of the exact rendered bytes |

### Information survival

Measured before behaviour, so that "destroyed" and "not used" can be told apart.

| Term | Definition |
|---|---|
| exact requirement retained | each fixture requirement that must be exact appears verbatim in the rendered bundle |
| semantic requirement retained | the fixture's probe questions about it, answerable only from the bundle, are answered correctly. Deterministic where possible, otherwise a frozen rubric with a blinded evaluator, never the reader being tested |
| critical evidence recoverable | its pointer resolves, to the right version, with intact bytes |
| provenance retained | the claim is rendered with its source and status attached |
| rationale retained | a probe asking why a decision was made is answerable from the bundle |

### Economics and runtime

| Term | Definition |
|---|---|
| input, output tokens | as reported by the provider or local server |
| cache write, read, miss tokens | as reported by the provider, where exposed |
| latency, time to first token | wall-clock, where the interface exposes them |
| provider cost | computed from an explicit price schedule version recorded with the result |
| local compute | wall-clock seconds and the device class, for local models |
| call count | model calls made, including retries |

### Naming

New metrics use `<family>:<term>` in `EvaluationObservation.metric`, matching the
existing `hold_release:task_score` style, where the term is one of the names
above.

## Repetition, and what is not observed

Two quantities are easy to confuse and are kept apart everywhere they appear.

| Term | Definition |
|---|---|
| carry-over | material legitimately re-supplied across requests: a part the previous request already held, matched part for part. Expected in any session; never called redundant |
| redundant payload | the same tool output appearing more than once inside one request (identical bytes, at least 32 bytes). A second copy of something the previous request held once is new material, not carry-over |

A smaller number of repeated bytes is not evidence of lower cost, and repeated bytes are not
evidence of harm. Only the second is a candidate for later experiments.

`UNOBSERVED` marks a quantity the instrument cannot determine. It is never converted to zero, and
an aggregate states how many sessions it used and how many were unobserved. A session that exposes
no tool-definition material has an unobserved definition share, not a zero one. Values read from
the harness's own record after the fact are labelled JOINED and are used only when they line up
with the capture request for request. Any stable-prefix figure rests on an assumed render order,
which is stored with it and labelled a proxy; it can route a cache experiment but says nothing
about provider caching by itself. Full definitions: `specs/f1-capture-completeness.md`.
