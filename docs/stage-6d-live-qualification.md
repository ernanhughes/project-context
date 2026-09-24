# Stage 6D-L report — Live Injection Qualification

Verdict: **FAIL** (with a precisely located defect, not a vague one).

## Question asked

Whether the explicitly intervention-capable OpenCode runtime could
inject a deterministic context block into one real request such that
the independent read-only observer subsequently recorded that same
block at the model-request boundary.

## What was done

Two synthetic live calls were made in a throwaway directory with a
trivial prompt ("reply with exactly one word"), using a small local
model at zero monetary spend. Both runs completed cleanly: the model
answered, no hook error appeared, and the observer captured one valid
primary invocation per run. The runtime was opted in only through the
child process environment; ordinary sessions were never enabled, and
all pre-existing global plugin state was backed up beforehand and
restored afterwards (verified by hash).

The injected block was rendered by the frozen Stage 6D code from a
fixed synthetic marker, and deployed byte-identical to that render.
The observer package was not modified at any point.

## What the observer saw

In both runs the observer captured a valid invocation whose whole-
request integrity was internally consistent — but the expected runtime
block was absent from every observed record. Occurrence count: zero.
Nothing unexpected appeared either: no partial block, no duplicate,
no conflicting content.

The model repeating nothing of the marker is noted as diagnostic
only; the criterion was always the independently observed request,
and the observed request did not contain the block.

## Why: defect recorded before any repair

The second call existed only to distinguish hook-order semantics: the
runtime plugin directory was renamed to sort before the observer, with
its code byte-identical. The outcome did not change, which ruled out
simple load ordering.

A further zero-model dry run (an invalid model name, so no request
could occur) with debug logging then showed the actual boundary. The
server log lists every plugin it loads with its resolved entrypoint:
the observer directory resolves to its entry file, a single-file
plugin resolves directly, and the configured package resolves to its
entry file. The runtime directory appears nowhere — no load line, no
error line. It is silently skipped.

The defect: as frozen, the runtime package ships two source files and
no plugin entry file, and the loader only picks up directories
through their entry file. The intervention code therefore never
executed in either live attempt. The hook mutation contract —
whether assigning the system array inside the context hook reaches
the model invocation — remains untested, not disproven. Hook ordering
is likewise still unknown, since the runtime hook never ran.

## What did not change

No Stage 6D source file was modified to chase a pass. The observer,
the runtime, the renderer, the injector, and the reconciler are all
byte-identical to their frozen revisions. The failing boundary is in
packaging/deployment, not in the synthetic render–inject–observe–
reconcile loop, which still passes its full suite.

## Validation after the probe

Full Python suite, linter, formatter check, both Node suites, and the
earlier stage suites all pass exactly as at the freeze. The
qualification added no code to the implementation and altered no
previous evidence.

## Limitations

The live runtime emits no machine injection receipt, so acceptance
could only be evidenced by a clean run plus the independent capture.
Observation sits at the model-context hook, not the provider wire.
The probe used one local model and one trivial prompt; nothing here
speaks to behaviour, usefulness, or any other model or provider. The
frozen artifact records the final attempt's machine detail; the first
attempt's outcome (same shape: valid capture, zero occurrences) is
recorded here. This probe counts as no book evidence.

## consequence

Do not begin F4B. The next stage repairs or redesigns only the
intervention boundary — most directly, giving the runtime package a
loadable plugin entrypoint — and then re-runs this qualification
under a new spec. Until a probe passes, F4B would rest on an
unproven injection layer.
