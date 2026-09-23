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
