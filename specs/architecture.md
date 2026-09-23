# Architecture — Context Lab v0 (Stage 0)

Stage: observation substrate. No interventions exist.

## Records

| Record | Module | Meaning |
|---|---|---|
| `ContextItem` | `domain/items.py` | One identifiable unit of a bundle. Frozen. Later-earned fields (retention_class, recoverability, exactness, freshness, groups) deliberately absent. |
| `ContextBundle` | `domain/bundles.py` | One rendered context for one invocation. Immutable, order-preserving, content-hashed. |
| `ModelInvocation` | `domain/invocations.py` | Actual execution: provider, model, telemetry, cost. Unavailable stays `None`. |
| `EvaluationObservation` | `domain/evaluation.py` | PASS/FAIL/INCONCLUSIVE evidence with metric, value, evidence, evaluator. Append-only via `EvaluationLog`. |
| `RunManifest` | `domain/runs.py` | Reconstruction identity (timestamp excluded). |
| `CorpusManifest` | `corpus/manifest.py` | Describes a real trace without containing it. Publication gated. |
| `InterventionProposal` | `domain/interventions.py` | Named future kinds only. No behaviour. |

## Identity rules

- Live captured records: UUIDs.
- Deterministic fixture entities: stable IDs (`rule-001`, bundles named
  `<fixture>-<version>`); reconstruction via `content_hash()`.
- `id` = representation instance; `semantic_id` = underlying information
  (reserved for Chapters 11–12). Neither is ever derived from secret content.

## Flow

```text
Fixture / captured invocation
        ↓
ContextBundle (frozen, ordered, hashed)
        ↓
ModelInvocation (telemetry, cost under a recorded schedule)
        ↓
Observation (append-only log)
        ↓
Evaluation (probe scoring against hidden truth)
        ↓
Frozen Run (manifest + observations + results + README)
```

## Telemetry

`telemetry.TokenCount(value, source)` where source is one of
`provider`, `local-tokenizer`, `approximation`, `unavailable`.
`calculate_cost()` is a pure function of usage plus a versioned
`PriceSchedule`. Stage 0 ships only `synthetic-price-schedule-v1`.

## What is explicitly not here (Stage 0)

PruneDecision, CompactionArtifact, FidelityRepresentation records;
`prune()`, `compact()`, `decay()`, `retrieve()`, `assemble()` behaviour;
real provider adapters; OpenCode capture adapter; Context Compiler.
See `docs/stage-0-report.md` for the deferred list.
