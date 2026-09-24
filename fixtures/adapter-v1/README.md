# adapter-v1 fixtures (SYNTHETIC)

Deterministic compatibility cases: each case pairs a ledger stream and
a typed activation request with an ordinary candidate pool and a
compiler request. Expected compile outcomes live in `truth.json`,
which tests and inspection may read but adapter and compiler runtime
code must never touch.

## Layout

```text
cases/<case>/events.jsonl              ledger stream (some shared with activation-v1)
cases/<case>/request.json              ActivationRequest (typed policy)
cases/<case>/ordinary.candidates.json  ordinary non-ledger pool (strict keys)
cases/<case>/compile.json              ContextRequest (required_ids always empty)
cases/<case>/truth.json                oracle: ledger/ordinary admission + trace reasons
```

`required_ids` is empty in every case on purpose: adapted state must
earn admission; nothing is forced in.

## Cases

| Case | What it proves |
|---|---|
| a-admitted | active ledger items admit normally alongside ordinary candidates |
| b-ordinary-wins | a stronger ordinary candidate wins the contested budget |
| c-budget-excludes | valid active items may be omitted by budget; compile still succeeds |
| d-authority-not-source | user ledger state outranks agent ledger state by authority metadata, never by source |
| e-epistemic-survives | pending verification reaches the bundle marked as such |
| f-multiple | several ledger items convert without adapter ranking |
| g-mixed-pool | mixed-source pool compiles normally with full trace coverage |
