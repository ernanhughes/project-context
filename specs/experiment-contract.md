# Experiment contract

No serious experiment runs before its contract exists. Each experiment
directory must define, in writing, before execution:

```text
question
hypothesis
population (fixtures and/or corpus references)
independent variable
controlled variables
conditions
measurements (per measurement-contract.md)
success / failure criteria
falsification criteria
seed and repetition strategy
provider / model / version (or synthetic)
cost ceiling
```

Then, and only then: results.

## Method (mirrors the book)

```text
observe → baseline → failure → smallest intervention
→ controlled comparison → ablation / counterfactual
→ keep, revise, or remove
```

## Stage 0 scope

Stage 0 experiments are fixture-inspection and schema-validation runs
only. No model is called, no money is spent, no intervention is tested.
Intervention experiments (pruning onward) each get their own directory
under `experiments/` with a frozen `spec.yaml` before any run.

## Evidence runs (programme contract)

The rules above apply to any experiment. A run that is meant to support a
published claim, an **evidence run**, must also satisfy the contract below. It
exists for one purpose: **another person must be able to say exactly what
changed between two experimental conditions, and nothing else.**

The contract extends the records that already exist. It adds no parallel
framework and no new record type; where a field is not already stored, it is a
reserved key in `RunManifest.environment`.

### Where each required fact lives

| Fact | Where it is recorded | Notes |
|---|---|---|
| experiment id, version | `RunManifest.experiment_id`, `experiment_version` | exists |
| experiment family | environment key `experiment_family` | new key |
| run id, time | `RunManifest.run_id`, `timestamp` | evidence runs record real UTC time; the fixed placeholder time used by the first three runs is not allowed |
| code revision | `RunManifest.git_commit`; environment `vcs_dirty` | evidence runs require a clean tree |
| fixture revision | environment `fixture_revision` (digest of the fixture set); `RunManifest.fixture_id`, `fixture_version` | new key |
| configuration revision | environment `configuration_revision` (digest of `spec.yaml`, policy and weight files) | new key |
| preregistration | environment `preregistration` = `<path>@<commit>` | new key; required for evidence runs |
| model provider and name | `RunManifest.provider`, `RunManifest.model` | for a behavioural run these name the **reader**; the synthetic nature of the fixtures is `evidence_class`, not the provider. (The first runs recorded `synthetic` here; that was ambiguous.) |
| model version or digest | environment `reader_model_digest` (+ `reader_model_identity_source`); `ModelInvocation.model_version` | required for a live evidence run; `unavailable` is a failure, not a value |
| reader identity and role | environment `reader_model`, `reader` (`primary`, `transfer`, ...) | exists for reader runs |
| task id, task population | case id encodes fixture; environment `task_population` (generator name and version, or fixture set) | new key |
| context condition | `BehaviorRecord.condition_id` | exists |
| bundle id, bundle digest | `ModelInvocation.bundle_id`; `BehaviorRecord.source_bundle_digest` | exists |
| trial id, seed | case id encodes repeat; `RunManifest.seed`; environment `decoding_seed` | exists |
| measurements, outcome | `EvaluationObservation` (metric, value, verdict, evidence) | metric names follow `measurement-contract.md` |
| artifact digests | the evidence manifest (`evidence/manifests/`) | derived, committed |
| environment | `RunManifest.environment` | exists |
| known limitations | the evidence manifest | derived, committed |
| run purpose | environment `run_purpose` = `evidence` or `exploratory` | exploratory runs stay local |

`src/project_context/runs/contract.py` checks a manifest for these keys.
Exploratory runs need only the `run_purpose` label.

### What changed between conditions

Every comparison declares its **factor** and the **control** it is measured
against. For each condition the case schedule records the control it differs from
and the items it added, removed or transformed (the fields `added_ids`,
`removed_ids` and the bundle digest already exist for this). A comparison that
changes more than its declared factor, for example a different budget or a
different reader alongside a different bundle, is not valid evidence for that
factor. This is exactly the fault in the first reader-transfer probe, and the
rule exists to make it impossible to repeat quietly.

### Frozen means frozen

Fixtures, graders, prompts and schedules are versioned and fixed before the first
model call. Nothing is tuned after outputs are seen. A pilot that shows the
interface is unusable (as happened before the first behavioural run) may amend the
interface, as a new version, if there is nothing yet to tune against; the amendment
is recorded, and the earlier version's runs are not merged into later ones.
