# Evidence model

Four evidence classes. Confusing them is the fastest way to corrupt the
book, so the repository enforces the vocabulary in code and artifacts.

## BACKGROUND RESULT

External literature or provider evidence. Lives in the book's
`research/bibliography.yaml`. Never stored as a run artifact here.

## BOOK HYPOTHESIS

A claim awaiting a project-context experiment. Lives in manuscript prose
marked as hypothesis. This repository may hold its fixture and its frozen
spec, never its result.

## PROJECT RESULT

A result produced by a frozen run in this repository. Must reference:

```text
run_id
git SHA of this repository at run time
experiment id and version
artifact paths under runs/
```

## BOOK RESULT

A project result deliberately imported into the manuscript. The prose
describes the finding in plain language; the experiment ID, run ID, and
commit SHA are resolvable from the claim through the evidence register
(`evidence/README.md`) rather than printed in the text. Nothing else in the
manuscript may be called a result.

## Labelling rule

Every bundle, manifest, artifact, and CLI report carries
`evidence_class: synthetic | provider-observed`. Validators reject
synthetic artifacts that claim provider evidence. Synthetic data is
never book evidence, no matter how realistic it looks.
