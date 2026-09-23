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
src/project_context/   domain records, fixtures, evaluation,
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
