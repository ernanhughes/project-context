# Experiments

Each experiment is independently runnable with a frozen spec before any
run. Stage 0 defines the convention only; no experiment implementations
live here yet.

Planned families (book chapters in parentheses):

```text
ch04 budget pressure (fixed evidence + growing irrelevant context)
ch05 degradation/distractors (evidence families + position)
ch06 ordering (frozen-bundle permutations)
ch07 retention (typed policies vs uniform treatment)
ch08 long-context architecture (native vs extended regimes)
ch09 prompt caching (stable prefix, mutation, TTL)
ch10 pruning (one mechanism at a time + oracle)
ch11 compaction (typed survival, repeated rounds, hidden probes)
ch12 progressive fidelity (tier quality, decay schedules)
...
```

Per-experiment convention (to be enforced from the first implementation):

```text
experiments/<family>/
  README.md        question, hypothesis, status
  spec.yaml        frozen contract (see specs/experiment-contract.md)
  fixtures/        fixture references or constructors
  analysis/        scripts that read frozen runs, never live state
```

Experiment-specific code stays here. Generally useful capabilities
graduate to `src/project_context/` only after surviving an experiment.
