# Stage 6D-R1 report — Runtime Plugin Load Repair + Requalification

## Staged verdict

```text
Loader                 PASS
Runtime hook execution PASS
Mutation propagation   PASS
Observer ordering      runtime-before-observer
Observed marker        1
Reconciliation         PASS

Overall qualification  PASS
```

This establishes transport and integration viability only. It does
not show that runtime context improves model behaviour, and it counts
as no book evidence.

## What changed since the 6D-L FAIL

The 6D-L record stands unmodified: the intervention plugin never
loaded because the package shipped no plugin entry file, so hook
mutation semantics were not tested. The repair touched only that
boundary. The runtime package gained an entrypoint that re-exports
the frozen hook, plus an env-gated qualification trace that records
counts and outcomes (never block text) so a later probe can tell
"loaded but failed" from "never executed". Injection logic,
rendering, reconciliation, the observer, the compiler, and the ledger
path are unchanged.

The minimum observed difference that motivated the repair: the
loader resolves a plugin directory through its entry file, which the
runtime directory lacked while the working observer directory had.

## How the probe ran

A zero-model loader inspection came first: with an invalid model
name, so no request could occur, the server log resolved the runtime
entrypoint. That retired the exact 6D-L defect before any model call
was spent. One deviation from the frozen spec is recorded here: the
spec expected a setup record in that dry run, but none appeared. A
standalone check of the trace helper proved it writes correctly, so
the absence means plugin setup runs with the session rather than at
server load — the dry run's session died at model resolution before
setup. The live run then supplied the setup record, as designed by
the gate ladder. No extra model call was needed.

One live call followed in a throwaway directory with a trivial
prompt on a small local model at zero spend. The runtime was opted
in only through the child process environment. Pre-existing global
plugin state was backed up beforehand and restored afterwards,
verified by hash. Both packages deployed byte-identical to their
committed sources.

## What the gates showed

The runtime trace records setup with hook registration, then one
hook invocation reporting a successful injection with single-block
growth. The independent observer captured one valid invocation for
the same session: the expected block present exactly once, last in
the system array, byte-identical to the rendered reference, with no
unexpected runtime content and consistent whole-request integrity.
Trace session and observed session match. The model reply is noted
as diagnostic only; the verdict rests on trace plus observed
request, never on what the model said.

Ordering is therefore established by observation, not assumed from
registration: with this deployment, the runtime mutation lands
before the observer capture, so the observer sees the final
injected request. Mutation semantics are likewise established for
the tested path: assigning the assembled system array inside the
context hook persists into the invocation the observer records.

## What this does not establish

One local model, one trivial prompt, one invocation. Nothing here
speaks to task success, to other models or providers, or to the
provider wire request, which remains unobserved. The deployment used
a load-order-first directory name; whether natural ordering behaves
the same was not tested. The trace file is a qualification harness,
silent by default, and must stay out of ordinary sessions.

## Validation after the probe

Full Python suite, linter, formatter check, both Node suites, and
the earlier stage suites pass as at the freeze. The 6D-L artifact
and report verify unmodified with their FAIL verdict intact. The
qualification added no model-facing content and altered no previous
evidence.

## Consequence

The intervention boundary is now qualified for transport: selected
context rendered by the frozen pipeline can reach a live model
request and be independently verified there. Behavioural work may
now be designed — under its own frozen spec, with oracle-authored
state first — but it is not started here.
