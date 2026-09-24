# oracle-leverage-v1 execution schedule (PRE-RUN FROZEN)

Machine record: `schedule.json` (schedule digest inside). This file
is the human companion; the JSON governs execution.

## Wave

24 runs: 8 frozen fixtures × conditions N (none), D (distractor),
O (oracle). One repeat per cell. Small-N leverage qualification,
not an effect-size study.

## Order (deterministic, no RNG)

Fixture sequence is a fixed stride-3 permutation over sorted ids:
t01, t04, t07, t02, t05, t08, t03, t06. Condition cycle [N,D,O]
rotates by fixture position; three round-robin rounds produce
olv1-r001…olv1-r024. First block of eight holds N×3 D×3 O×2; no
condition runs consecutively for one fixture. One same-condition
adjacency exists at a round boundary across different fixtures and
is documented, not hidden.

## Subject model

Local Ollama `ollama/mistral-small:latest`, expected digest
recorded in the JSON, verified by the runner before the first
call; mismatch stops the wave pending amendment. Chosen for prior
primary-reader continuity, tools capability, and zero spend — no
outcome-based selection exists to make. Decoding and limits are
provider defaults, recorded not invented. Fresh
`opencode run --standalone --auto` per run; no session reuse.

## Run discipline

Per-run private workdir from the digest-verified fixture repo;
fail closed on mismatch. Payloads consumed as frozen bytes
rendered through frozen code, never paraphrased; N renders empty
and is observer-verified absent. Payloads carry no condition
labels; truth never enters sessions. Per-run transport reconcile
required — mismatch is transport failure, never task failure.
Behavioural responses are never retried; pre-response provider
failure allows one identical retry under the same run ID with an
attempt number. Exclusions cover validity only (digest mismatch,
wrong state, wrong model, truth exposure, corruption) — never
strange or inconvenient behaviour. The wave runs all 24 slots;
no interim adaptation. Grading is condition-independent per
fixture (grade by run ID, join condition after). Economics:
latency, call count, tokens where exposed else unavailable.
