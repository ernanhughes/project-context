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
