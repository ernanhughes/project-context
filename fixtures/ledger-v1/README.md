# ledger-v1 fixtures (SYNTHETIC)

Deterministic event stream for the Stage 6A Context Ledger. All people,
sessions, paths, and test names are invented. Nothing here is book
evidence; expected final states live in `ledger-v1.truth.json`, which
tests may read but ledger runtime code must never import.

## Scenarios in `events.jsonl`

| Events | Scenario |
|---|---|
| evt-001 | User constraint (`constraint-001`): migration 017 must not be modified. Stays active with user authority. |
| evt-002, evt-008, evt-009 | Decision supersession: `decision-002` (schema v2) supersedes `decision-001` (schema v1). |
| evt-003–evt-005, evt-013 | Conditional obligation: `obligation-001` (update docs) depends on `verification-001`; blocked until the tests pass, then actionable. |
| evt-006, evt-015 | Failed verification: `claim-001` (race fixed) contradicted by a failing test run. |
| evt-007 | Unresolved failure: `failure-001` (Windows paths) stays active. |
| evt-010–evt-012, evt-014 | Dependency satisfaction: `obligation-002` (remove old adapter) unblocks when `verification-004` verifies. |
| evt-016 | Irrelevant-but-valid state: `assumption-001` (telemetry) stays active and unrelated. |
| evt-017, evt-018 | Expiry: `obligation-003` expires via an explicit event (no wall clock). |
| evt-019–evt-022 | Contradiction: `result-001` (benchmark) contradicts `claim-002` (cache speeds up suite). |
| evt-023, evt-024 | Informational lineage: `verifies` and `blocks` edges change no lifecycle state. |
