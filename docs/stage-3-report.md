# Stage 3 report — deterministic synthetic Context Compiler

## Baseline

- Stage 0 SHA: `dccc796`. Stage 1 SHA: `ad8850e`. Stage 2 SHA: `07f6813`.
- Stage 3 implementation commit: `ec642dc` ("Implement deterministic
  synthetic context compiler"), local, unpushed — like all prior stages.
- Frozen run executed on the clean `ec642dc` tree; no other repository
  touched (book repository untouched throughout).
- Python via project `.venv` (3.x, stdlib-only runtime: no third-party
  dependencies in `pyproject.toml`); pytest 8+, ruff clean;
  TypeScript adapter untouched (tsc + prettier green).

## Scope

Implemented: the smallest deterministic synthetic compiler for the book
Chapter 22 contract — versioned candidate/request/policy/trace/failure
records, staged assembly with hard gates, representation alternatives,
dependency closure, required groups, budgeted admission, deterministic
ordering, exact-render validation with repair, explicit compile
failures, hidden evaluator truth with oracle ceiling, six-strategy
baselines, bundle-quality evaluator, 14-fixture synthetic suite,
`contextlab compiler` CLI, one frozen local run.

Deliberately excluded: models and model calls of any kind, network,
learned rankers or scorers, retrieval/memory/artifact/scope/freshness
subsystems (fixtures supply pre-resolved eligibility states), provider
telemetry and cost, ecological corpus dependence, behavioural
evaluation, capstone orchestration, OpenCode capture changes (V1
adapter untouched; Stage 1/2 tests green).

## Domain changes

No existing record was modified. `ContextItem`/`ContextBundle` and all
Stage 0–2 schemas are byte-compatible (all prior tests green
unchanged). New records, all frozen dataclasses with schema versions
and JSON round-trips:

- `project_context.context_candidate.v1` (`compiler/domain.py`): one
  representation option over an immutable content identity plus
  compiler-visible metadata only (requirement band, order role,
  scope/freshness/authority eligibility with reasons, form/floor ranks,
  dependencies, group, coverage keys, relevance, default-form flag).
- `project_context.context_request.v1`: compilation inputs (budgets,
  explicit required IDs, active scope, policy version, fixed timestamp).
- `project_context.compiler_policy.v1` (`compiler/policy.py`): single
  immutable policy (relevance threshold, cheapest-legal mandatory form,
  role order, repair mode).
- `project_context.decision_trace.v1`: terminal decision per record
  (7 states) with reason codes, evidence, marginal cost, budget
  before/after, position.
- `project_context.compile_failure.v1`: reason code, blocking IDs in
  deterministic order, budget state, diagnostics.
- `project_context.compilation_result.v1`: success/failure envelope
  referencing bundle identity (bundle travels as `ContextBundle`).

## Compiler contract

```text
ContextRequest + ContextCandidate[] + CompilerPolicy + budget
  → (ContextBundle + DecisionTrace) | (CompileFailure + DecisionTrace)
```

`compile_context(request, candidates, policy)` is pure: no file IO, no
clock, no randomness, no network, no models; inputs never mutated
(tested); identical inputs yield identical outputs (tested, including
across separate frozen runs).

## Deterministic stages

Validate (duplicates, unknown deps, negative counts, mixed-band
groups) → required-source existence → hard gates → mandatory cheapest
legal forms → required units → preferred/discretionary greedy (earn
rule + coverage) → alternative closeout → role-ordered layout →
exact render → discretionary-only repair → post-compile validation →
trace + bundle-or-failure. Policy/request version match enforced.

## Hard eligibility

Scope, freshness, authority flags plus representation floor checked per
record before any other consideration. Rejections are terminal with
preserved reason evidence. The highest-relevance record in the suite
(`scope-out`, 0.99) is never admitted (tested).

## Representation alternatives

One content identity, many records; at most one admitted (tested).
Floors enforced (`form_rank >= min_rank`); a mandatory identity with
only sub-floor forms fails `NO_LEGAL_REPRESENTATION` (tested).
Composite `anchor+reference` works as a single record with its resolver
dependency (tested on dependency-trap). Cheapest fitting legal form
wins within mandatory/required bands (documented policy, not oracle
knowledge — under-fidelity vs the hidden minimum is recorded
descriptively).

## Dependency closure

DFS with visited sets (cycles terminate; tested). Costs counted once
per record (tested exact: shared resolver emitted once, bundle tokens
recomputed independently in tests). Missing dependency IDs are
configuration errors (`ValueError`); ineligible dependencies block
parents (`UNSATISFIED_DEPENDENCY` for mandatory/required, rejection
otherwise). Dependents never revive rejected dependencies.

## Priority/budget policy

`MANDATORY > REQUIRED > PREFERRED > DISCRETIONARY`; request-required
IDs upgrade to REQUIRED. Mandatory/required admit-or-fail; preferred/
discretionary admit only when fitting AND (relevance ≥ 0.3 OR new
coverage). Coverage keys are fixture-declared task requirements, never
oracle labels. Budget is a ceiling: roomy regimes leave thousands of
tokens slack (tested: 2,735 on budget-slack roomy).

## Ordering/rendering

Frozen role order (instruction, task, state, evidence, support, tool)
with candidate_id tiebreak. Render = content plus deterministic
source/kind decoration, separators, and a request/policy header block;
token counts fixture-declared with exact render validation. Overruns
repair by dropping last-admitted discretionary units (whole groups),
recomputing, rerendering — mandatory/required/dependencies/floors
never move (tested on rendered-overflow tight: discretionary dropped,
mandatory kept, `repair-drop` traced).

## Validation

Every emitted bundle satisfies: rendered cost within budget, layout
trace equals item order, all items admitted, floors/closures/groups
intact. Any violation returns failure instead of a bundle.

## CompileFailure

`INSUFFICIENT_BUDGET` (mandatory overflow tight/medium),
`UNSATISFIED_DEPENDENCY`, `NO_LEGAL_REPRESENTATION`,
`UNRESOLVED_REQUIRED_GROUP`, `REQUIRED_SOURCE_UNAVAILABLE`,
`REQUIRED_INELIGIBLE` (implemented; untriggered by current fixtures).
Deterministic codes, blocking IDs, diagnostics (equality tested).

## DecisionTrace

Terminal state for every considered record, candidate_id ordered;
inclusion and exclusion both carry reason codes plus gate evidence.
Partial traces accompany failures.

## Fixtures

14 committed synthetic fixtures under `fixtures/compiler-v1/`
(manifest v1, token_mode `fixture-declared-counts`, per-fixture
tight/medium/roomy budgets, per-budget expected outcomes). The seven
required traps plus representation alternatives, shared dependency,
required-unavailable, no-legal-representation, dependency cycle,
rendered overflow, and a heterogeneous pool. Token counts are
stipulated cost-regime inputs, not measurements — documented in the
manifest and builder. Two pre-registration records are kept in
`build_fixtures.py` (oracle-feasibility budget fix; group-
discrimination calibration); both predate the frozen run and neither
consults strategy outcomes.

## Baselines

dump/truncate, relevance top-k, fixed-weight greedy (weights frozen in
`experiments/compiler-v1/weights.json`, recorded in run artifacts),
hard-gated greedy, staged compiler, evaluator-only oracle (hidden
truth, same hard constraints, minimum sufficient forms). Oracle lives
under evaluation code; an import-direction test forbids production use.

## Evaluation

Per (fixture, strategy, budget): budget compliance, status correctness
vs per-budget expectation, must/should recall with exact denominators,
precision, distractor/harmful/illegal admissions, six violation
classes, rendered tokens, slack, under/over admission, oracle token and
recall gaps. No aggregate score. One observation per combination in
`observations.jsonl` (status verdict with evidence); full tables in
`results.json`; per-combination records plus complete traces in
`compilation.jsonl`.

## Frozen run

- experiment ID: `compiler-v1`, version `1`
- run ID: `run-001`
- git SHA: `ec642dc` (clean tree at run time)
- fixture version: `1`, policy: `compiler-policy-v1`
- location: `.local/runs/compiler-v1/run-001/` (git-ignored, local only)
- validation: `validate_artifact` clean; rerun byte-identical
  (`compilation.jsonl`, `results.json`) across two executions
- evidence grade: PROJECT RESULT (synthetic). Not a book result; book
  untouched.

## Results (252 combinations: 14 fixtures × 6 strategies × 3 budgets)

Status-correct (bundle/failure matching per-budget expectation):

```text
dump 34/42   topk 34/42   weighted 34/42
gated 34/42  staged 42/42   oracle 42/42
```

Violation totals across all 42 combos per strategy:

```text
strategy  dep  group floor distr scope fresh auth
dump        1    0     3     18     5      4      0
topk        1    1     3     18     6      6      0
weighted    1    0     3     17     6      6      0
gated       1    1     0      9     0      0      0
staged      0    0     0      5     0      0      0
oracle      0    0     0      0     0      0      0
```

Staged specifics: must_recall 1.0 on every feasible combination;
zero illegal admissions of any class; expected failures with exact
reason codes (overflow tight/medium, ghost source, sub-floor form);
roomy slack up to 2,735 tokens with distractors left out; harmful
admissions 2 (heterogeneous medium/roomy admit the eligible
0.55-relevance misleading note — honest over-admission, visible in the
trace, counted against staged, not hidden); under-fidelity vs the
hidden minimum recorded on representation-alternatives (anchor chosen,
compact sufficient). Oracle token gaps vs staged range −210 to +676
(mean +51): staged spends more where distractors fit (uncertainty
price) and less where the oracle's minima exceed staged minima.

Headline mechanism reads:

- H1 (gates): earned. Weighted/top-k/dump admit 12–15 illegal items
  and 30 combined scope/freshness/floor violations; staged admits none.
  Gated (gates without staging) still breaks a required group and a
  dependency and misses stale-cheap must-evidence (0.667 vs 1.0).
- H2 (dependency costing): earned. Staged commits resolver closures
  with exact shared accounting; gated/top-k admit the cheap reference
  without its resolver (dependency violations).
- H3 (representation alternatives): earned descriptively. Cheapest
  legal forms reduce cost under floors; the anchor-vs-compact gap is
  measured as under-fidelity rather than hidden.
- H4 (explicit failure): earned. All expected failures fire with exact
  codes; always-bundle baselines fail these cases by construction.
- H5 (slack): earned. Roomy regimes leave large positive slack with
  low-relevance distractors rejected by the earn rule.

Falsification notes (no mechanism deleted yet, but recorded): required
groups discriminate only via the qualification trap (conflict groups
never break under these baselines — the mechanism is verified present
and correct, but its differential value rests on one fixture);
dependency costing matters only where fixtures attach expensive
dependencies; representation choice is cheapest-legal rather than
sufficiency-aware by documented policy. A future fixture set that
removes any of these differentials must delete the corresponding
machinery per the standing rule.

## Limitations

Synthetic fixtures with stipulated costs; no model behaviour measured;
no real corpus (genuine sessions still 0); fixture-supplied relevance
and pre-resolved authority/freshness/scope states; single policy
version exercised (backtest path exists via `--policy` but unexercised);
no live cost/latency/provider telemetry; token counts are declared
inputs, not tokenizer measurements; small pools (≤14 records).

## Chapter 23 handoff

The evaluation chapter now has: 252 frozen bundle/trace outcomes with
per-dimension quality labels, an oracle ceiling with measured gaps, six
ablation-ready strategies, and exact-failure cases — all reproducible
from commit `ec642dc` plus run `run-001`. What still requires a model:
whether legal, budgeted, traced bundles change downstream behaviour,
and whether the bundle-quality dimensions predict that change. Nothing
in this report answers those questions.

## Validation

- 121 tests pass (47 pre-existing + 74 new), ruff check/format clean,
  `git diff --check` clean, tsc + prettier green (TS untouched).
- Import-direction test (compiler never imports evaluation), oracle-
  identifier scan, no-model/network/clock/random import scan, hidden-
  truth presence-independence test, strict-loader tests, determinism
  tests (in-suite, cross-run byte equality, CLI determinism test).
- CLI exercised end to end: fixtures, inspect (text+json), run,
  validate-run.
- Process-safety scan green; no OpenCode process management; no
  ecological corpus dependence (suite runs with zero genuine sessions).
- Frozen run `run-001` validates clean; rerun byte-identical.
