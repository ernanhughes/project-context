# Synthetic fixtures

Stage 0 fixtures are defined in code under
`src/project_context/fixtures/` so generation stays deterministic and
reviewable. The committed reference is:

- `reference` v1 — project rule, exact identifier, synthetic file
  observation, synthetic tool result, explicitly unverified hypothesis,
  current request; three hidden probes. SYNTHETIC — NOT BOOK RESULT.

`reference-v1.manifest.json` beside this file describes it without
duplicating hidden answers. Probe questions live in code, never in the
model-visible bundle; tests enforce the boundary.
