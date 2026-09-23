# Stage 0 report — experimental substrate

## What was built

Boring-on-purpose v0 platform: frozen domain records, deterministic
fixtures with hidden truth, probe scoring, synthetic telemetry, run
artifacts with validation, corpus manifests with a publication gate, and
a minimal `contextlab` CLI. 18 tests, Ruff-clean, stdlib-only runtime.

## Structure

```text
src/project_context/
  domain/{items,bundles,invocations,evaluation,runs}.py
  domain/interventions.py      # named future kinds, zero behaviour
  telemetry.py                 # TokenCount, PriceSchedule, calculate_cost
  fixtures/{base,reference}.py # ABC + reference v1 world
  evaluation/scoring.py        # normalised exact-match probe scorer
  providers/{base,synthetic}.py# normaliser contract + deterministic fake
  corpus/manifest.py           # manifests + sanitisation gate + secret scan
  runs/artifacts.py            # writer + validator
  cli/main.py                  # fixture list/inspect (text + json)
specs/                         # architecture, measurement, experiment,
                               # evidence-model, privacy
experiments/README.md          # planned families, per-experiment convention
fixtures/synthetic/            # reference-v1 manifest (no hidden answers)
runs/README.md                 # artifact convention (artifacts git-ignored)
tests/                         # invariants, fixture behaviour, artifacts
```

## Records implemented

`ContextItem` (id, source, kind, content, position, token_count with
`approximation` provenance, authority, scope, observed_at, semantic_id);
`ContextBundle` (immutable, ordered, content-hashed, layout-traced);
`ModelInvocation` (provider/model, TokenCounts with None discipline,
latency, cost under a recorded schedule, observation_only flag);
`EvaluationObservation` + append-only `EvaluationLog`
(PASS/FAIL/INCONCLUSIVE with metric, value, evidence, evaluator);
`RunManifest` (reconstruction identity excluding timestamp);
`CorpusManifest` (content-free trace description);
`InterventionProposal` (kind + targets + reason, no apply path).

## Fixture model

Code-defined deterministic worlds: visible items render to the bundle;
probes plus oracle labels stay evaluator-side; `build()` raises if a
probe question leaks into visible text. Reference v1 ships six items and
three probes (exact rule, identifier, hypothesis status).

## Evidence model

BACKGROUND (book bibliography) / BOOK HYPOTHESIS (manuscript, awaiting
runs) / PROJECT RESULT (frozen run + SHA here) / BOOK RESULT (imported
with IDs printed). Every record carries `evidence_class`.

## Run-artifact model

`runs/<experiment>/<run>/{manifest.json, observations.jsonl,
results.json, README.md}`. Validator checks completeness, manifest
consistency, synthetic-vs-provider honesty, and secret patterns.
Stage 0 commits no artifacts.

## Privacy boundary

`.local/`, `raw-corpus/`, `private-runs/`, run directories git-ignored.
Only `approved-public` manifests pass `assert_publishable` (tests pin
refusals for raw-local and sanitised-awaiting-approval). No IDs derived
from secrets.

## CLI surface

`contextlab fixture list`, `contextlab fixture inspect <id>
[--format text|json]`. Deterministic (tested by double-run equality).
No model calls, no network.

## Tests

18 tests: ordering preservation, order-sensitive identity, hidden-truth
boundary, unavailable-metrics discipline, manifest reconstructability,
append-only evidence, publication-gate refusals, CLI determinism,
bundle immutability + no-intervention functions, JSON round-trips,
Stage-0 field discipline, fixture build/scoring, synthetic provider
marking, artifact round-trip/tamper/synthetic-honesty/secret detection.

## Deliberately deferred

PruneDecision/CompactionArtifact/FidelityRepresentation records;
prune/compact/decay/retrieve/assemble behaviour; real provider adapters
and API spend; OpenCode capture adapter (boundary documented in
`specs/architecture.md` discussion and a future stage); real corpus
traces; Context Compiler; notebooks as runners; mypy (skipped: dataclass
invariants already test-pinned; revisit if the model grows).

## Toolchain deviation

Brief preferred Python 3.12+; the build environment provides CPython
3.11, so `requires-python = ">=3.11"` with 3.12+ preferred documented in
README. No language features beyond 3.11 are used; revisit on
maintainer machines.

## Book-chapter mapping

Ch1 definitions → domain vocabulary and the not-in-context distinction.
Ch2 instrument → observation-only invocations, layout trace, token
provenance. Ch5 ladders → probe groups and recovery-style scoring
shape. Ch6 ordering → order-sensitive identity plus permutation-ready
fixtures. Ch7 classes → deliberately absent fields, documented as
earned-later. Ch9 economics → TokenCount provenance, PriceSchedule
separation, unavailable-not-zero. Ch10–12 → named intervention kinds
and fixture truth/oracle structure, zero behaviour. Capstone ladder →
`experiments/README.md` families and the v0→v10 evolution note (to be
added when Stage 1 begins).

## Unresolved design questions

1. Canonical serialisation for large bundles (JSONL vs SQLite) once real
   traces arrive.
2. Where run artifacts should live long-term if this repo must stay
   lean (releases vs LFS vs external store).
3. OpenCode adapter shape once the capture contract (message vs
   request-render interception) is verified against a pinned version.
4. Whether `reasoning_tokens` needs provider-specific substructure.
