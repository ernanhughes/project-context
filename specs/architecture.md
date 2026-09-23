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

## Stage 1 — read-only OpenCode capture (V1, pinned 1.18.27)

OpenCode V1 exposes no unified pre-dispatch hook, so the adapter
observes four read-only signals, each becoming one bridge record
(`project_context.opencode_capture.v1`) in a local JSONL spool:

```text
OpenCode 1.18.27 (V1 API)
  experimental.chat.system.transform → system snapshot (session-linked)
  experimental.chat.messages.transform → message-list snapshot (unlinked)
  chat.message → admission inventory (session-linked)
  tool.execute.after → tool result, call-linked (input args excluded)
        ↓ local spool (.local/... or $PROJECT_CONTEXT_SPOOL_DIR)
  Python ingester (no mutation of raw files)
        ↓
  ContextBundle (provenance: source_type opencode_capture) + ModelInvocation
        ↓ (usage telemetry unavailable at this boundary: all None)
  prevalence analysis (aggregates only; export gated)
```

Boundary, stated once: this is **OpenCode V1 pre-dispatch partial
context**, not the assembled provider request. Provider lowering happens
after these hooks; later-registered plugins may mutate after capture
(load the adapter last); per-tool definitions, generation settings, and
compaction observation are deferred. A future V2 adapter reuses the
bridge schema with full system/messages/tools/options blocks.
