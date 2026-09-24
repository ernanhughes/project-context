# project-context

Experimental and implementation companion to
[`ernanhughes/context`](https://github.com/ernanhughes/context), the book
*Context From First Principles — Engineering What an AI Gets to Know*.

The book repository owns exposition: manuscript, hypotheses, experiment
specifications, interpretation. **This repository owns executable
evidence**: the Context Lab instrument, deterministic fixtures, corpus
tooling, experiment runners, evaluation, telemetry adapters, and frozen
run artifacts.

```text
book hypothesis → experiment spec → implementation here
→ frozen run → artifact + commit SHA → book result
```

A statement becomes a **book result** only when backed by a reproducible
frozen run artifact in this repository. See `specs/evidence-model.md`.

## Stage 0 scope (current)

Deliberately boring experimental substrate. Implemented:

- frozen domain records (`ContextItem`, `ContextBundle`,
  `ModelInvocation`, `EvaluationObservation`, `RunManifest`,
  `CorpusManifest`) with schema versions and JSON round-trips;
- token/cost accounting with provenance separation and a synthetic price
  schedule (no real money, no real API calls);
- deterministic reference fixture with hidden ground truth and probe
  scoring, plus a hidden-truth boundary test;
- run-artifact writer and validator under `runs/`;
- `contextlab fixture inspect` CLI proving fixture → bundle →
  measurement → deterministic report;
- 18 invariant tests (`pytest`), Ruff-clean.

Explicitly **not implemented**: pruning, compaction, progressive
fidelity, retrieval, memory, authority resolution, assembly, the Context
Compiler, real provider adapters, the OpenCode capture adapter, real
corpus traces. See `docs/stage-0-report.md` for the deferred list and
`specs/architecture.md` for the record map.

## Stage 3 scope (current)

Deterministic synthetic Context Compiler (book Chapter 22 contract).
Implemented:

- versioned compiler records (`ContextCandidate`, `ContextRequest`,
  `CompilerPolicy`, `DecisionTrace`, `CompileFailure`) in
  `src/project_context/compiler/`, reusing `ContextItem`/`ContextBundle`
  without modifying them;
- staged deterministic assembly: hard eligibility gates, legal
  representation alternatives with mutual exclusion, dependency closure
  with shared-cost accounting, required groups, band-ordered budgeted
  admission with coverage, deterministic ordering, exact-render
  validation with discretionary-only repair, explicit `CompileFailure`;
- hidden evaluator truth, oracle ceiling, and bundle-quality evaluator
  under `src/project_context/evaluation/` (production compiler cannot
  import them; tests pin the direction);
- `fixtures/compiler-v1/` (14 synthetic fixtures incl. the seven
  required traps) and `experiments/compiler-v1/` (frozen spec, fixed
  weights, versioned policy);
- `contextlab compiler fixtures|inspect|run|validate-run` CLI;
- frozen local runs under `.local/runs/` (git-ignored; PROJECT RESULT,
  never book evidence until promoted).

Explicitly **not implemented**: models, network calls, learned rankers,
retrieval/memory/artifact systems, ecological corpus dependence,
behavioural evaluation (Chapter 23 owns it). See `docs/stage-3-report.md`.

## Stage 4 scope (current)

Matched behavioural evaluation of frozen compiler bundles (book
Chapter 23 contract). Implemented:

- narrow reader abstraction (`ReaderAdapter` protocol) with a scripted
  offline `FakeReader` and one stdlib-HTTP OpenAI-compatible adapter;
- frozen prompt wrapper, deterministic parser, per-family deterministic
  graders, and one minimal `BehaviorRecord` linkage record reusing
  `ModelInvocation`/`EvaluationObservation`/`RunManifest`;
- `fixtures/compiler-behavior-v1/` (5 compiler-derived tasks + 1
  calibration task, hidden truth, frozen interventions) with run-001
  bundles consumed immutably under digest verification;
- `experiments/compiler-behavior-v1/` (frozen spec, seeded schedule,
  fixed readers/decoding, spend guard);
- `contextlab behavior fixtures|inspect|plan|dry-run|run|validate-run|canary`
  CLI with resume, retry, and byte-identical restoration guarantees.

Explicitly **not implemented**: behavioural conclusions (pending the
frozen live run), multi-reader averaging, agent-harness readers,
ecological prevalence. See `docs/stage-4-report.md`.

## Stage 5 scope (current)

Local, read-only Context Debugger over OpenCode V2 model context (book
Chapters 1–2, 4, 6, 9–13, 17 observation surface). Implemented:

- V2 capture adapter (`integrations/opencode` 0.2.0) pinned to
  OpenCode **2.0.16**, V2 plugin API, `@opencode/plugin` **2.0.16**
  exact: one `project_context.opencode_capture.v2` record per observed
  model request at `session.hook("context")` (plus kind-tagged
  compaction/generate records), with assembled system/messages, tool
  definitions (description plus input schema only), model/agent
  identity, observed request overrides, and declared model limits where
  the API yields them. V1 retired: rejected, never coerced.
- `src/project_context/debugger/`: immutable views, deterministic
  structural analysis (composition, timeline, compare, recurrence,
  stable prefix, tool-surface change), deterministic queries (no LLM),
  and a doctor producing magnitude-only observations under versioned
  thresholds (`debugger-doctor-policy-v1`).
- `contextlab debug latest|inspect|timeline|compare|explain|query|doctor`
  CLI with deterministic text and versioned JSON output, structural by
  default, raw content only under explicit local flags.
- V2 golden fixture (`fixtures/opencode-capture-v2/`, SYNTHETIC)
  shared by TypeScript and Python tests.

Explicitly **not implemented**: pruning, rewriting, compression,
reordering, tool filtering, automatic optimisation or recommendations,
compiler insertion into live context, TUI, semantic duplicate
detection, behavioural utility inference, provider-wire capture. The
debugger observes; it changes nothing. See `docs/stage-5-report.md`.

## Stage 6A scope (current)

Deterministic Context Ledger: typed durable state with lifecycle,
provenance, contradiction/supersession relationships, and
append-only history (F4B design). Implemented:

- `src/project_context/ledger/`: frozen `LedgerItem`/`LedgerEvent`
  records with schema versions and strict JSON round-trips, explicit
  lifecycle transitions (terminal states never silently reopen),
  verification recording (never performing), typed relationships,
  boring JSONL store, and pure `project(events) -> LedgerState`
  projection with explainable lineage and a replay digest;
- `fixtures/ledger-v1/` (SYNTHETIC): 13 items over 24 events covering
  obligations, a user constraint, decision supersession, failed
  verification, an unresolved failure, dependency satisfaction,
  irrelevant-but-valid state, expiry, and contradiction; expected
  state in `ledger-v1.truth.json` (tests only, never runtime);
- `contextlab ledger inspect|history|validate|replay` CLI;
- `tests/test_ledger.py` (31 tests) pinning determinism, lifecycle
  legality, provenance, hidden-truth separation, and the compiler /
  OpenCode boundaries.

Explicitly **not implemented**: activation, retrieval, compiler
admission, live injection, automatic extraction, model calls. The
ledger persists state; it admits nothing to context. Live stores live
under `.local/ledger/` (git-ignored). See `docs/stage-6a-report.md`.

## Evidence manifests

Runs the book cites are published byte for byte under `evidence/runs/` and
pinned in `evidence/manifests/` by artifact digest and recomputed headline
numbers; `python scripts/evidence_manifest.py --verify` checks them on a fresh
clone. `evidence/README.md` is the register that maps each finding in the book
to its evidence.

## Setup

Requires Python 3.11+ (3.12+ preferred) and [`uv`](https://docs.astral.sh/uv/).

```bash
uv venv
uv pip install -e ".[dev]"
pytest
ruff check .
contextlab fixture inspect reference
```

## Layout

```text
src/project_context/   domain records, compiler, fixtures, evaluation,
                       providers, corpus manifests, run artifacts, CLI
experiments/           per-experiment specs and runners (convention only)
fixtures/              committed synthetic fixture manifests
runs/                  frozen artifacts (git-ignored except README)
specs/                 architecture, contracts, evidence model, privacy
tests/                 invariant and behaviour tests
docs/                  stage reports
```

## Privacy

Public repository. Raw sessions, credentials, private code, and personal
data are never committed. See `specs/privacy.md`. Local-only paths
(`.local/`, `raw-corpus/`, `private-runs/`, run directories) are
git-ignored; publication requires explicit sanitisation plus human
approval recorded on the corpus manifest.

## Licence

Apache-2.0. See `LICENSE`. Studied third-party mechanisms (notably DCP,
AGPL-3.0) are never copied into this repository; see `AGENTS.md`.
