# Frozen experiment spec: oracle-leverage-v1 (behavioural qualification)

Status: **spec frozen, no fixtures built, no model call made under it.**

## Background (preserved verbatim from the transport stage)

> Transport viability is now earned: compiler-selected context
> rendered by the frozen pipeline can reach a live model request and
> be independently verified there. It says nothing about whether such
> context helps behaviour.

This experiment asks the next question and nothing else.

## Question

Can correct context, delivered through the qualified live runtime
path, change model behaviour on tasks constructed to require it?

## What this is not

- Not a test of retrieval quality, compiler quality, or extraction.
  Ledger state here is oracle-authored from fixture truth, which
  removes activation and selection as confounds by design.
- Not an effect-size estimate. This is a leverage check with a small
  task set: it can show that context composition has behavioural
  leverage through the runtime path; it cannot measure how much.
  The programme's inference machinery (many tasks, disagreeing
  pairs) belongs to later stages.
- Not F4B. It gates F4B: if oracle context cannot move behaviour,
  there is little value debugging the compiler. The compiler-selected
  condition is explicitly excluded until oracle leverage is shown.

## Causal chain under test

```text
oracle information (authored from hidden truth, never inferred)
      ↓
frozen Stage 6D renderer (unchanged)
      ↓
qualified live transport (6D-R1 path, observer-verified per run)
      ↓
model receives information
      ↓
behaviour changes
```

## Conditions (wave 1; exactly one factor varies)

| ID | Name | Supplied context |
|---|---|---|
| N | No context | none (runtime active with empty selection; observer-verified absent) |
| D | Matched distractor | same approximate size and structure as O, information that should not help |
| O | Oracle relevant context | exact minimal information known in advance to be relevant |

The runtime, hooks, reader, decoding, budget, repo snapshot, and
task text are identical across conditions. The declared factor is
supplied context content only. A comparison changing anything else
is not valid evidence for that factor.

Deferred: X (wrong/stale but plausible context — second wave, the
basis for provenance/recency/authority questions) and any
compiler-selected condition (the later selection stage).

## Population

A small frozen set of synthetic tasks (target four to six), each
built around latent project state that cannot reasonably be
inferred from the visible task alone. Task acceptance rules:

- the repository contains enough plausible evidence for an
  apparently reasonable but wrong choice (the N default);
- hidden oracle state, supplied only as injected context, names the
  invariant that flips the choice (counterfactual dependence: the
  agent should behave differently if and only if that piece is
  supplied);
- the action is machine-checkable: a deterministic parser over a
  frozen schema plus a deterministic grader over hidden truth. No
  model judges the primary score. Malformed output is observed,
  never repaired.
- hidden truth lives evaluator-side only. Task files, prompts, repo
  contents, and payloads carry no hidden labels or expected values;
  a scan pins this for every task.

Illustrative sketch (not a fixture — fixtures are authored later
under these rules): a parser task where the repo favours
normalising legacy IDs, while hidden oracle state records that
legacy prefixes must be preserved byte-for-byte for a downstream
migration. N and D should produce the plausible wrong
implementation; O should preserve the invariant.

## Measurements (four layers, no composites)

| Layer | Terms (per `specs/measurement-contract.md`) |
|---|---|
| Transport | observer-verified block presence, byte identity, singularity, placement per invocation (6D-R1 reconcile); bundle digest |
| Utilisation | evidence use (decisive value in action with decisive item admitted); constraint adherence with per-constraint booleans kept |
| Behaviour | task success (all graded fields equal fixture truth); harmful action (fixture forbidden set); parse success |
| Economics | input/output tokens as reported, latency wall-clock, call count; provider cost unavailable for local models, never zero |

This keeps apart, by construction: available versus noticed,
noticed versus used, used versus helpful, helpful versus
economical. Influence (remove-and-restore) is deferred.

## Reader and path

Live OpenCode sessions through the qualified runtime/observer
pair, local model via the OpenCode provider path at zero monetary
spend. Exact model pinned at fixture-freeze with digest recorded;
moving aliases refused for evidence runs. Decoding fixed and
recorded. Every model call isolated: one session per
task × condition × repeat, no cross-condition state.

## Repetition and cost

One repeat per cell in wave 1 unless the frozen schedule says
otherwise; case IDs encode fixture/condition/reader/repeat.
Transport errors retry with bounded backoff and recorded attempts;
provider errors are never task failures. Cost ceiling: a fixed
model-call guard recorded in the schedule; zero monetary spend.

## Success, failure, falsification

- Success: on tasks meeting the acceptance rules, O succeeds where
  N fails with transport PASS in every run, and D behaves like N
  (distractor does not help). Per-task outcomes kept beside any
  aggregate; no claim beyond the task set.
- Failure: O does not outperform N on counterfactual-designed
  tasks despite verified transport — context arrived and behaviour
  did not move.
- Falsification: transport FAIL in any run removes that run from
  behavioural comparison (it tests nothing about leverage);
  oracle text leaking into N/D payloads voids the comparison;
  any tuning of tasks, graders, budgets, or prompts after outputs
  voids the run.

## Relation to the programme

This is the ORACLE LEVERAGE step in
transport → leverage → selection → system → economics. It precedes
the F4B selection conditions (all-unresolved versus activated
versus compiler, the C2/C3/C4 questions) and the F8 reader-transfer
machinery, which it neither replaces nor duplicates: those test
other links. The stale-context wave (X) feeds later governance
questions, not this one.
