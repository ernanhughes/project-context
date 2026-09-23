# runs/

Frozen run artifacts live here, one directory per run:

```text
runs/<experiment-id>/<run-id>/
  manifest.json
  observations.jsonl
  results.json
  README.md
```

This directory is git-ignored except for this README: run artifacts are
produced locally (or in CI) and referenced by experiment ID, run ID, and
repository commit SHA. Stage 0 commits no run artifacts.

Every artifact must validate with `runs.artifacts.validate_artifact`:
complete files, consistent manifest, no provider-evidence claims on
synthetic runs, no secret patterns. Synthetic runs are labelled
SYNTHETIC in their README and are never book evidence.
