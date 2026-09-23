# Stage 4 report — matched compiler-behavior evaluation

## Baseline

- Stage 3 implementation commit: `ec642dc9c15e3822506dbc93e03db7667e297921`
  ("Implement deterministic synthetic context compiler"), local, unpushed.
- Stage 4 implementation commits, all local, unpushed:
  - `9d56ef6` — matched compiler behavior evaluation
  - `7585e04` — reader endpoint root to OpenAI-compatible `/v1`
  - `ea84a2e` — reader selection (qwen3.5 retired after contract failure)
  - `b49b065` — prompt wrapper v1→v2 after run-001 pilot
  - `ea95e78` — JSON-schema-enum decoding after run-002 parse failure
- HEAD: `ea95e78f9eec66f8cdbf5f7d4a16d9a024417abe` (frozen Stage 4
  implementation SHA). Working tree clean at run time; book repository
  untouched throughout.
- Python via project `.venv` (stdlib-only runtime; no third-party
  dependencies in `pyproject.toml`); 148 tests pass; ruff check and
  format clean; `git diff --check` clean.

## Scope

Implemented: the smallest matched behaviour loop over frozen compiler
bundles — re-rendered primary bundles with digest verification against
`compiler-v1/run-001`, explicit remove/restore/volume/wrong-context
surgery for interventional bundles, one fixed local reader per case
(isolated single-shot calls, no tools/retrieval/memory/history),
JSON-schema-enum constrained decoding, deterministic never-repair
action parsing, deterministic per-family grading without any LLM judge,
frozen local runs with manifests, CLI validation of all three artifacts.

Deliberately excluded: model selection beyond the two pinned local
readers, prompt/behaviour tuning after first genuine output, grader or
budget or intervention changes after reader output, ecological corpus
dependence (genuine sessions remain 0), cost telemetry (no price
schedule configured), reasoning-trace telemetry (unavailable from the
endpoint and recorded as such), cross-reader averaging or ranking,
production or deployment claims.

## Frozen upstream provenance

Every B1–BO condition traces back to:

```text
compiler-v1
run-001
commit ec642dc9c15e3822506dbc93e03db7667e297921
policy compiler-policy-v1
fixture v1
```

recorded in `fixtures/compiler-behavior-v1/manifest.json`
(`compiler_source`) and re-verified at every condition build:
`BundleSource.bundle_for()` re-renders the primary bundle from the
frozen run-001 trace and refuses digest mismatches against the recorded
bundle id and content hash (test-pinned; tamper stops the condition).
Derived bundles (`MA/MR/MT/MW`) carry new identities of the form
`{parent}::{intervention}` with parent linkage, never silent
recompiles; MR restores byte-identically (digest equality test-pinned).

The evidence chain reads:

```text
compiler-v1 candidate pool
        ↓
compiler-v1/run-001 (ec642dc)
        ↓
exact frozen ContextBundle (digest-verified re-render)
        ↓
compiler-behavior-v1 condition (B0–BO ladder, M-series surgery)
        ↓
one isolated reader invocation (mistral-small:latest, temp 0)
        ↓
structured action (JSON-schema-enum, never repaired)
        ↓
deterministic grader (per-family pure function, no LLM judge)
```

## Pilot history (harness pilots, not behavioural evidence)

`run-001` and `run-002` are not behavioural evidence and are never
merged into canonical aggregates.

```text
run-001 pilot (@ea84a2e, fixture v1, prompt behavior-prompt-v1)
→ 0/54 parseable responses (54/54 parse-failure, verified from artifact)

run-002 pilot (@b49b065, fixture v2, prompt behavior-prompt-v2)
→ 0/54 parseable responses (54/54 parse-failure, verified from artifact)

JSON-schema-enum decoding frozen (@ea95e78)

run-003 (@ea95e78, fixture v2, json-schema-enum constraint)
→ canonical primary behavioural run (54/54 parse ok)
```

These changes occurred because the output interface was unusable, not
because behavioural scores were inspected and optimised: with zero
parseable outputs there was nothing to tune against, and the fixture
manifest's version notes record the wrapper change as a harness fix
(tasks, truth, graders, parser, budgets, schedule, readers unchanged).
The response-constraint upgrade is pinned in the run-003 manifest
environment (`response_constraint=json-schema-enum`).

## Reader contract

Primary reader: `mistral-small:latest`. Transfer reader: `llama3.1:8b`.
Both via the local Ollama OpenAI-compatible endpoint
(`/v1/chat/completions`) through the stdlib `openai-chat` adapter
(verified in `src/project_context/readers/openai_chat.py`; secrets
header-only, never in artifacts).

Per-case contract (verified in `behavior/runner.py` + run manifests):

```text
temperature = 0
seed = 20260923
max output = 512 tokens
no tools, no retrieval, no memory, no conversation history
one isolated request per case
case IDs encode fixture/budget/condition/reader/repeat
JSON-schema-enum constrained output (run-003; pilots pre-constraint)
transport errors retried with bounded backoff (≤2 retries, 2s/5s);
  valid model behaviour never retried, never repaired
```

Reasoning telemetry is unavailable from the endpoint and recorded as
`null` with provenance intact (0/54 non-null), not zero. `model_version`
is likewise null. The transfer reader is a transfer instrument, not a
competitor: readers are never averaged and never ranked.

A third candidate, `qwen3.5:latest`, was retired before any experimental
call after repeated empty message content (output consumed by a separate
reasoning channel despite `think:false` and JSON mode); its canary
output was never used. This is recorded in the fixture manifest's
`rejected_readers`, not in any result table.

## Behavioural fixture selection

Six eligible fixtures (frozen manifest reasons, verified against
run-001 traces where stated):

```text
qualification-trap — staged preserves the required group while greedy
  baselines split it at tight
stale-cheap — staged/oracle carry validated current state; baselines
  carry superseded state or nothing
wrong-scope — staged/gated/oracle exclude the other world;
  dump/topk/weighted admit it
dependency-trap — eligible at tight: staged/oracle carry the resolver
  dependency; others lack it
heterogeneous-basic — rich strategy differences incl. harmful-labelled
  admission at medium/roomy
calibration-echo — behaviour-only negative/calibration control borrowing
  frozen heterogeneous-basic/tight context per condition
```

Eight excluded fixtures (frozen manifest reasons):

```text
conflict-trap, dependency-cycle, shared-dependency —
  all six bundles identical at every budget
mandatory-overflow — tight/medium fail for all; roomy identical
no-legal-representation — all strategies fail: compiler evidence only
rendered-overflow — only dump deviates (drops task request),
  behaviourally inert by construction
required-unavailable — staged/oracle fail by design; baselines ignore
  the requirement: compiler evidence only
representation-alternatives — anchor vs compact carry identical
  semantic content; no gradable behavioural difference possible
```

Inclusion was not revised on results: the manifest predates all reader
output and the runner enforces it.

## Primary budget

Pre-reader rule (frozen manifest): largest count of behaviourally
eligible fixtures where B1–B5 and BO all produce usable inputs and at
least two non-oracle strategies produce different bundle identities
(content digests, not request-derived bundle ids); tie-break medium.

Recomputed from `compiler-v1/run-001` content digests:

```text
tight   5 compiler-derived + calibration-echo (borrows hetero-tight) = 6
medium  3 (stale-cheap, wrong-scope, heterogeneous-basic)
roomy   3 (stale-cheap, wrong-scope, heterogeneous-basic)
```

Primary budget: `tight`. (At medium/roomy, qualification-trap and
dependency-trap strategies converge to identical bundles — itself
informative: looser budgets erase the construction differences the
tight ladder discriminates.)

Transfer wave: `heterogeneous-basic @ medium`, chosen because the two
Stage 3 harmful-labelled admissions exist only at medium/roomy — a
bundle-property reason fixed before any reader output, not because
tight produced favourable outcomes.

## Call accounting (recomputed from artifacts)

```text
primary run-003:        54 calls
  = 46 ladder (5 fixtures × 7 B-conditions = 35
               + qualification-trap 11: B0–BO plus MA/MR/MT/MW)
  + 8 pre-registered diagnostic repeats
      (heterogeneous-basic B5 ×2, stale-cheap B5 ×2,
       qualification-trap MA ×2, calibration-echo B0 ×2)
transfer run:            7 calls (heterogeneous-basic @ medium, B0–BO, r0)
connectivity canaries:   2 calls (qwen3.5 failure + mistral ok;
                         marked NOT EXPERIMENT DATA, never aggregated)
```

54 invocations recorded for 54 primary cases (one record per case; no
retry artefacts in the invocation log). All 54 primary and all 7
transfer cases completed with parse status `ok`.

## Canonical matched B0–BO outcomes (run-003, r0, tight)

Scores are deterministic grader outputs; actions are parsed structured
outputs (target/value in parentheses). Harmful flags shown where set.

```text
dependency-trap (materialise: WITH_TOOL / WITHOUT_TOOL / ABSTAIN)
  B0  1.0 WITH_TOOL   B1–BO 1.0 WITH_TOOL throughout
  → context makes no scored difference here.

wrong-scope (choose_evidence: USE_A / USE_B / ABSTAIN)
  B0  1.0 USE_A       B1–BO 1.0 USE_A throughout
  → context makes no scored difference here. (B0 already succeeds, so
    this fixture is contaminated for scope-gate behavioural claims;
    scope remains a construction-policy requirement.)

stale-cheap (use_current: PROCEED / HOLD / ABSTAIN)
  B0  0.0 ABSTAIN
  B1–BO 1.0 PROCEED throughout
  → context necessary: no context fails, every supplied-context
    condition succeeds.

heterogeneous-basic (constraint: REFUSE / PROCEED / ABSTAIN)
  B0  0.0 ABSTAIN (not harmful; the harmful PROCEED was never observed
      at B0 — correction to any summary stating otherwise)
  B1–BO 1.0 REFUSE throughout
  → context moves ABSTAIN to correct REFUSE. The grader defines PROCEED
    as harmful by counterfactual risk, but no primary-ladder observation
    took it; do not claim context "prevented" an observed harm here.

qualification-trap (hold_release: HOLD / RELEASE / ABSTAIN)
  B0  1.0 HOLD
  B1–BO 0.0 RELEASE (harmful) throughout, including staged and oracle
  → supplied context systematically causes the failure. Direct evidence
    that adding context can degrade behaviour.

calibration-echo (echo: ECHO / ABSTAIN; correct ECHO mig-7Q2)
  all conditions 0.0 (B0/B1 ABSTAIN with empty value; B2 ECHO empty;
  B3/BO ECHO 'FAILURE'; B4/B5 ECHO 'migration failure')
  → the negative control failed (see Calibration section).
```

These six rows demonstrate all three possibilities — context helps,
context hurts, context makes no scored difference — and that is one of
the strongest final findings. They must not be smoothed into a "context
helps" narrative.

## Influence versus utility (paired, n=6, tight r0)

Two granularities are reported because they answer different questions.
"Changed" below counts full parsed-action records (action + target +
value + reason_code); action-name-only counts follow in parentheses.

```text
B0 → B5:  6/6 records changed (4/6 action names)
          improved 2 (stale-cheap, heterogeneous-basic)
          degraded 1 (qualification-trap)
          same score 3 (dependency-trap, wrong-scope, calibration-echo)

B4 → B5:  4/6 records changed (0/6 action names)
          score improved 0, score degraded 0

B5 → BO:  2/6 records changed (0/6 action names)
          score improved 0, score degraded 0
```

Findings:

> Context can influence behaviour without improving utility
> (B0→B5: 6 influenced, net +1 task).

> A more sophisticated bundle can alter response surface without
> changing the decided action or the scored outcome (B4→B5 and B5→BO:
> zero action-name changes, zero score changes on this matched set).

Do not convert action difference into task improvement. The B4→B5 and
B5→BO differences are target/value/reason-code surface strings
(e.g. `generated file` vs `generated_file`, reason-code prose
variants), not decisions. The staged machinery over hard-gated greedy
changed no decision and no score here — while remaining required for
construction legality (Stage 3), which is a separate objective.

## Harmful actions (12 harmful case-observations, decomposed)

Total 12, all `RELEASE` on `qualification-trap`, all parse-ok:

```text
headline r0 ladder harm (10):
  B1, B2, B3, B4, B5, BO (6 — every supplied-context ladder condition)
  MA, MR, MT, MW         (4 — every surgical derivative)

repeat observations (2):
  MA r1, MA r2 (both RELEASE/harmful; repeats stable, see below)
```

No other fixture, condition, or repeat produced a harmful observation.
The reader-facing book must use the r0 ladder denominator (10 cases:
6/6 supplied ladder conditions plus 4/4 derivatives harmful) rather
than the larger count; the repeats corroborate stability, they are not
independent harms.

The qualification-trap must remain visible: B0 succeeds (HOLD/1.0) and
every supplied-context strategy — including staged and oracle — fails
harmfully. Adding context systematically created this failure.

## Calibration / negative control (failed — reported precisely)

`calibration-echo` was intended as a negative/context-interference
calibration: the correct answer (`mig-7Q2`) is present in the task
prompt. It failed its stability expectation, scoring 0.0 under every
condition: with bundle content present (B2–BO) the reader echoed
bundle-derived wrong values (`''`, `'FAILURE'`, `'migration failure'`)
instead of the task-stated identifier; without bundle content (B0/B1)
it abstained.

> The negative control failed: the reader followed bundle content over
> the task-stated identifier, exposing context interference.

This result is evidence and also a limitation. It demonstrates the
reader is context-sensitive enough for interference to occur, while
warning that supplied context can overpower the explicit task — and
that a benchmark which cannot preserve its negative control does not
get to make sweeping claims from its positive conditions.

## Remove / restore controls (attribution not earned)

`M` below denotes the staged parent bundle condition (B5); the schedule
contains no standalone M case — MA/MR/MT/MW derive from the B5 parent
with recorded linkage. Full M/MA/MR/MT/MW traces for
`qualification-trap` @ tight r0:

```text
M (B5 parent)  0.0 RELEASE harmful   bundle dd652304…
MA             0.0 RELEASE harmful   bundle d18fe19f… (exception-tenant removed)
MR             0.0 RELEASE harmful   bundle dd652304… (byte-identical to M)
MT             0.0 RELEASE harmful   bundle 820fe340… (removed + mt-distract-2)
MW             0.0 RELEASE harmful   bundle b49d2950… (removed + wrong-tenant-cleared)
```

MR digest equality with the parent proves experimental integrity of the
restore path, not causal attribution. MT carries a test-pinned
token-volume difference from MA, but the floor never moved, so MT
provides no token-volume discrimination here. MW shows the reader is
responsive to misleading completion framing, but the pre-registered true
item cannot rescue the outcome at this floor.

> No restoration-based causal attribution was demonstrated on this
> fixture because the original staged bundle was already at the
> behavioural floor. The report does not claim the decisive item caused
> the failure and does not claim restoration worked.

Diagnostic repeats corroborate the floor: MA r1/r2 both RELEASE/harmful.
All 8 diagnostic repeats match their r0 counterparts exactly
(hetero-B5 REFUSE/1.0, stale-B5 PROCEED/1.0, calib-B0 ABSTAIN/0.0).

## Five staged distractors (disposition, not blanket harm)

Distractor-class identities in Stage 3 fixture truth and their Stage 4
primary-budget disposition (hidden `DISTRACTOR` labels are never treated
as behavioural truth):

```text
scope-out (wrong-scope) — admitted by dump/topk/weighted at tight, yet
  B1/B2/B3 score 1.0 USE_A: behaviourally inert in those conditions.
distract-big (dependency-trap) — staged omits it (resolver closure
  instead); B5 scores WITH_TOOL/1.0: not exercised as a harm vector.
distract-h / scope-bad / stale-bad (heterogeneous-basic) — staged omits
  all three at tight: not exercised in the primary budget.
distract-2 (qualification-trap) — staged omits at tight; the MT
  derivative carries a different synthetic-intervention record
  (mt-distract-2) with a floor outcome: not exercised as a harm vector.
```

No Stage 3 distractor-class item is associated with realised harm in the
primary ladder: all 12 harmful observations are the qualification
RELEASE, whose bundle mechanism is the required-group/exception-tenant
structure, not any labelled distractor. Do not claim every Stage 3
distractor caused harm.

## Two Stage 3 harmful-labelled admissions (heterogeneous-basic)

The two Stage 3 `HARMFUL` labels are the staged admissions of
`harmful-h` (eligible, 0.55 relevance — honest over-admission, visible
in the trace) at medium and roomy; at tight staged admits no
harmful-class item, and roomy additionally admits `distract-h`.

The transfer wave used heterogeneous-basic @ medium, but the transfer
reader abstained on every condition (7/7 ABSTAIN, 0/7). The reader never
produced the action needed to discriminate the label. Therefore the
report claims neither "harmful label realised harm" nor "harmful label
proved harmless" for that wave.

## Transfer wave (narrow reading)

```text
reader = llama3.1:8b (same adapter, endpoint, decoding contract)
cases  = 7 (heterogeneous-basic @ medium, B0–BO, r0)
parse  = 7/7 ok
score  = 0/7 (ABSTAIN throughout)
```

The transfer wave does not replicate the primary reader's REFUSE
behaviour. Interpretation, narrowly: behavioural effects are
reader-dependent in this transfer probe. No inference about which reader
is better, no cross-reader average, no treatment as external
validation. Context sufficiency and behavioural utility are
reader-relative on this evidence; the compiler must not automatically
optimise itself per model on this basis.

## Token, latency and economic telemetry (exact artifact values)

Provider totals per invocation (wrapper + task + schema + bundle as
received by the endpoint), primary run-003, n=54:

```text
provider input tokens:  mean 121.9, min 85, max 142
provider output tokens: mean 38.8
latency: mean 11176 ms (≈11.2 s), range 7732–14885 ms (≈7.7–14.9 s)
reasoning tokens: unavailable (0/54 non-null)
cost: None (0/54 non-null; no price schedule configured)
cache tokens: unavailable (0/54 non-null)
```

Frozen bundle tokens (compiler artifact, `compiler-v1/run-001`, tight
ladder) are a separate quantity from provider input totals and are not
interchangeable with them:

```text
fixture              B0(empty)  B1    B2    B3    B4    B5    BO
dependency-trap      —          395   439   439   439   789   789
wrong-scope          —          319   319   319   265   265   265
stale-cheap          —          215   215   215   111   715   715
heterogeneous-basic  —          475   497   497   493   493   289
qualification-trap   —          479   439   319   439   319   319
```

(B0 carries no bundle; its provider input, mean ≈93 tokens across
fixtures, is wrapper + task + schema alone.) No economic-superiority
inference is made; no claim that shorter bundles ran faster (latency was
not analysed against bundle size and the endpoint gives no cache
telemetry).

## Stage 4 mechanism status

Several statuses, not winners. Labels used: construction-core (required
machinery), behaviourally demonstrated, construction-only (built and
correct, no downstream behavioural advantage shown), conditional
(needed only under specific failures), not behaviourally earned,
falsified on this fixture, unresolved.

- Hard eligibility, explicit failure, budget validation, deterministic
  trace: strongly earned as **construction machinery** (Stage 3;
  unchallenged by Stage 4).
- Actual supplied context is behaviourally necessary on `stale-cheap`
  and `heterogeneous-basic` (B0 fails, supplied conditions succeed).
- Context interference is behaviourally demonstrated by
  `qualification-trap` (supplied context causes harm) and
  `calibration-echo` (bundle content overpowers the task identifier).
- Wrong-context sensitivity is behaviourally demonstrated (B1–B3 admit
  `scope-out` in wrong-scope; behaviour held at 1.0 — sensitivity of
  the construction layer with inert behavioural outcome here).
- The extra staged machinery over hard-gated greedy (B4→B5) changes
  response surface but shows **no utility advantage on this matched
  set**: construction-level, not behaviourally earned beyond B4.
- Dependency-aware costing, representation alternatives, group
  preservation: primarily **construction-level** — Stage 4 did not
  demonstrate their downstream behavioural advantage (behaviour held
  identical with and without them wherever both were exercised).
- Remove/restore attribution: **not earned** in Stage 4 (floor result).
- Oracle-minimum-as-behavioural-optimum: **falsified on this
  population** — the BO bundle (hidden-evidence minimum) scores 0.0 on
  qualification-trap and echoes wrong content on calibration-echo
  identically to B5. The bundle oracle is not wrong; it optimises hidden
  evidence sufficiency, not reader behaviour. Minimum semantic evidence
  is reader-relative in practice.

## Falsification outcomes

- Oracle minimum as behavioural optimum: falsified (above).
- "More selected context is better": falsified by qualification-trap
  (B0 > B1–BO) and unsupported by dependency-trap/wrong-scope (flat).
- "Staged construction implies behavioural gain over greedy": falsified
  on this matched set (B4→B5: no action-name or score change).
- "Distractor labels predict behavioural harm": unsupported — no
  labelled distractor is associated with realised harm in the primary
  ladder.
- "Harmful labels realise harm": unresolved — the labelled admissions
  sit outside the primary budget and the transfer probe abstained.

## Limitations and evidence boundary

> Real reader behaviour on controlled synthetic tasks under frozen
> context interventions — and nothing more.

Not real OpenCode prevalence (ecological corpus: 0 genuine sessions;
`corpus/campaigns/` holds metadata scaffolding only). Not production
performance. Not deployment evidence. Not real-repository improvement.
Not proof of generalisation across models (one primary reader, one
abstaining transfer probe). Not proof the staged compiler is optimal.
Single temperature/seed/decoding contract; single tight primary budget
(with one medium transfer slice); six behavioural fixtures; small-N
task-level evidence throughout — aggregates are reported with
denominators attached to the relevant subset, never as bare rates.

## Validation

- 148/148 tests pass; ruff check and format clean; `git diff --check`
  clean.
- `compiler validate-run .local/runs/compiler-v1/run-001` → valid.
- `behavior validate-run .local/runs/compiler-behavior-v1/run-003`
  → valid (54 cases).
- `behavior validate-run
  .local/runs/compiler-behavior-v1/run-003-transfer` → valid (7 cases).
- No model reruns, no grader/policy/budget/intervention changes, no
  artifact mutations were made for this report; all numbers above were
  recomputed read-only from the frozen artifacts.

## Chapter 24 handoff — what may and may not be claimed

May claim (with frozen identities attached):

```text
- compiler-v1/run-001 @ ec642dc: staged construction legality over greedy
- compiler-behavior-v1/run-003 @ ea95e78: the six-row matched ladder,
  both influence granularities, the 12-observation harm decomposition,
  the failed calibration, the floor-bound M-series, telemetry as stated
- run-003-transfer @ ea95e78: reader-dependence (7 ABSTAIN, 0/7)
- construction-core machinery as contract requirements
- interference/harm directionality at task level with denominators
```

May not claim:

```text
- any mechanism's behavioural superiority from B4→B5 or B5→BO
  (no action-name or score change on this set)
- scope-gate behavioural contribution (B0 already succeeds)
- causal item-level attribution for the qualification harm
  (remove/restore unresolved)
- harmful/distractor label realisation (unexercised or abstained)
- reader ranking or cross-reader averages
- economic or latency superiority
- ecological prevalence, production readiness, or optimality
- anything from run-001/run-002 beyond harness-pilot history
```
