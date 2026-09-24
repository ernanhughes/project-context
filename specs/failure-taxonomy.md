# Failure taxonomy

A failed or degraded case is never reported as just "wrong answer". Every one is
attributed to a **primary state** by walking a fixed ladder over facts the run
established deterministically. The ladder asks, in order: at which stage did the
information stop doing its job?

It is implemented in `src/project_context/domain/failure.py`
(`FailureState`, `FailureEvidence`, `attribute`) so the same rule is applied by
every family.

## The nine states

| State | Plain meaning | What must be true |
|---|---|---|
| `CONTROL_FAILURE` | The experiment itself is invalid. | Conditions were not matched, a bundle digest did not verify, or the grader did not run. The case is excluded from every result and counted. |
| `ABSENT` | The information was never admitted. | The required item is not in the admitted set (from the decision trace). |
| `LOST` | It was admitted, then destroyed. | A transformation removed or changed what had to survive exactly, or a required fact fails its survival check. |
| `STALE` | It was true once and is not now. | The action equals the action a stale item in the bundle implies, and the fixture says that item is out of date. |
| `SCOPE_LEAK` | The wrong world influenced behaviour. | The action equals the action an out-of-scope item implies. |
| `OVERRIDDEN` | A conflicting or higher-authority item drove the action. | The action equals the action implied by an item the policy says must not govern here. |
| `UNRECOVERED` | It survived, but the reader did not find or use it. | The item was admitted and survived, and the action does not contain the decisive value. |
| `MISAPPLIED` | It was found and used wrongly. | The action contains the decisive value, and the action is still wrong. |
| `INTERFERENCE` | Extra context made viable behaviour worse. | The same reader succeeds with the minimal bundle and fails with this one, and no earlier state explains it. |

## How attribution works

Attribution walks the ladder in the order above and stops at the first state whose
fact is **explicitly** false. A fact the run did not establish never triggers a
state: unavailable is not false. So a case that was never admitted is `ABSENT`
even if it was also misapplied, because nothing downstream could have rescued it.

The facts are booleans produced by the run's own checks, never by asking the reader:

| Fact | Comes from |
|---|---|
| control valid | matched conditions; verified bundle digests; the grader ran |
| required admitted | the decision trace or bundle membership |
| required survived | the survival checks (`specs/measurement-contract.md`) |
| source current | the fixture's validity state for each item |
| in scope | the fixture's scope binding for each item |
| no conflicting influence | the action compared with the actions the trap items imply |
| evidence used | the action contains the decisive value |
| applied correctly | the grader |
| degraded versus baseline | the same reader's outcome with the minimal bundle |

## Fixture obligations

Deterministic attribution needs the fixture to say more than what is correct:

1. **Trap items carry the action they would induce.** A stale record, an
   out-of-scope note or a conflicting instruction each declares, in the hidden
   truth, the action a reader following it would take. `STALE`, `SCOPE_LEAK` and
   `OVERRIDDEN` are then decided by comparison, not by judgement.
2. **The decisive value is named.** `UNRECOVERED` and `MISAPPLIED` are decided by
   whether the action contains it.
3. **A minimal-bundle control exists** for every task, so `INTERFERENCE` has
   something to be measured against.
4. Hidden truth never renders into model-visible text (existing invariant).

## Secondary states

The primary state is the first the ladder finds. Other states that also apply are
recorded as secondary, so a case that was stale *and* misapplied is not flattened.
Aggregates report the primary state; the secondary states are for diagnosis.

## What the taxonomy is not

It is not a scoring rule and not a ranking of mechanisms. It says where a failure
came from, so that a null result can be explained (the mechanism was never asked to
help: `ABSENT`) and a real failure can be located (the mechanism destroyed the
information: `LOST`).

## Applying it to the first three runs

The first behavioural runs were frozen before this taxonomy. Their cases can be
re-labelled by analysis, appending new observations that point back at the frozen
records, since their hidden truth exists; nothing in them is edited. That
re-labelling is not needed to start the programme.
