# oracle-leverage-v1 fixtures (pre-run candidates)

Counterfactual coding fixtures for the frozen `oracle-leverage-v1`
experiment (see `experiments/oracle-leverage-v1/spec.md`, which is
authoritative). Each fixture pairs a small visible repository and
task — which together make one action reasonably attractive — with
latent project state, supplied only as oracle context in condition O,
that makes a different action correct.

## Status

Pre-run. No model has been executed against these fixtures, no
grader is implemented, no schedule is frozen, and no model is
pinned. The manipulated factor is supplied context content only:
N (none, runtime active with empty selection), D (matched
distractor), O (oracle minimal). Stale-context X and
compiler-selected context remain deferred.

## Layout

Each task directory holds `fixture.json` (task text, visible
default, latent state, oracle and distractor payloads, design
expectations, deterministic observable, admission evidence),
`truth.json` (evaluator-side hidden truth: required and forbidden
patterns), and `repo/` (the visible repository the model will act
in). Only `repo/` contents, the task text, and the per-condition
context enter a session; `truth.json` never does.

## Admission rules applied

Plausible visible default supported by repository evidence;
latent state absent from visible inputs (audited by static search,
including the documented datum-without-meaning exceptions);
oracle minimal and solution-free; distractor matched in size and
structure without causal content; deterministic future observable
needing no LLM judge; single manipulated factor.

## What was rejected or weakened in review

No candidate was rejected. Two trims were applied from static
review alone: distractor payloads were shortened to sit within
roughly a fifth of oracle length, and one fixture's repository
gained a visible status field so the latent consequence has a
datum to attach to. Details are in the stage report.
