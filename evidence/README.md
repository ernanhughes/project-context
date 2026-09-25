# Evidence register

This directory is where a claim in the book is traced to its evidence. The
book's prose describes findings in plain language and does not print
identifiers; each finding has a short name here, and this register holds the
identifiers.

```text
finding in the book
      ↓  (its name in the table below)
evidence manifest         evidence/manifests/
      ↓
frozen run                evidence/runs/
      ↓
fixtures and configuration    fixtures/, experiments/
      ↓
code revision that produced it
```

## Findings

| Name in the book | Experiment | Run | Code revision | Manifest |
|---|---|---|---|---|
| Compiler construction | `compiler-v1` | `run-001` | `ec642dc` | `compiler-v1__run-001.json` |
| Matched behaviour | `compiler-behavior-v1` | `run-003` | `ea95e78` | `compiler-behavior-v1__run-003.json` |
| Reader-transfer probe | `compiler-behavior-v1` | `run-003-transfer` | `ea95e78` | `compiler-behavior-v1__run-003-transfer.json` |

These three predate the programme's preregistration scheme. They were frozen
before their outcomes were seen, but are labelled *pre-programme*, not
preregistered.

## Other frozen findings

Not every finding is a run. These four are pinned by digest in the same way, by
`scripts/evidence_findings.py`, and each has a manifest in `evidence/manifests/`.

| Name in the book | Kind | Artifacts | Manifest |
|---|---|---|---|
| Live compile-to-observe qualification | transport qualification | `evidence/qualifications/compile-inject-observe-live/` | `compile-inject-observe-live.json` |
| Instrumentation failure | inconclusive behavioural wave (24 planned, 24 executed, none valid) | `evidence/oracle-leverage-v1/result.json` | `instrumentation-failure.json` |
| Earlier runtime qualifications | transport qualifications (one failed attempt, one pass) | `evidence/qualifications/runtime-live-*.json` | `earlier-runtime-qualifications.json` |
| Implementation parity | structural: TypeScript reproduces the frozen Python outputs on 42 compilations | external, in the compiler repository | `implementation-parity.json` |

The first finding is frozen from one live run of the compile, inject and observe
chain. Its observer capture contains full model context and stays private; only its
digest is recorded (`private-artifacts.json`). The third holds two marker probes of
an earlier plugin layout and does not involve the compiler. The fourth is external:
its manifest pins the compiler repository's goldens and fixtures by digest and
records the conformance run at the frozen revision.

```bash
python scripts/evidence_findings.py            # (re)write these manifests
python scripts/evidence_findings.py --verify   # 0 ok, 1 drift, 2 artifact absent
```

The parity finding is verified only where a sibling checkout of the compiler
repository is present. Historical artifacts are never rewritten: the two trace
defects in the frozen Python outputs are recorded in the manifest's limitations, and
a later corrected trace is a new schema, not an edit of these goldens.

## What a manifest holds

- the run identity and the code revision that produced it;
- the SHA-256 and size of every artifact file;
- the environment as recorded (reader model, decoding settings, ...);
- the headline numbers **recomputed from the artifacts**, not typed in;
- the known limitations of the recorded run.

```bash
python scripts/evidence_manifest.py            # (re)write manifests
python scripts/evidence_manifest.py --verify   # 0 ok, 1 drift, 2 artifact absent
```

`--verify` works on a fresh clone. Where the machine-local original also
exists, the published copy is compared with it byte for byte.

## Publication

Published runs are byte-for-byte copies of the local originals, synthetic
runs only, released through the sanitisation gate in
`scripts/publish_evidence_runs.py` after recorded approval
(`specs/privacy.md`, "Approved publications"). Historical artifacts are never
rewritten to improve them; where a frozen file is inaccurate, the correction
is recorded in the manifest's limitations.

Adding a run: add it to `RUNS` in `scripts/evidence_manifest.py` and to
`APPROVED` in `scripts/publish_evidence_runs.py`, record the approval, publish,
and commit the new manifest. Existing manifests are not edited by hand.

## Sibling-project results used as background

The book's Memory-project findings are background, not evidence for the Context
book. The Memory manuscript is unpublished and its manuscript repository is
private; the runs behind the quoted findings are public in
`ernanhughes/project-memory`, under `experiments/benchmark/runs/`, first added in
commit `8044214`.

| Finding as described in the book | Sibling run | Checked against stored results |
|---|---|---|
| Memory-dependent tasks: assembled memory, removal and restoration, wrong memory, small reader | `ch12-20260920T204414Z-behavior` | yes |
| Stronger reader: full history against its own floor; frame-selected against assembled | `sr1c-ch12-confirm-20260920T234546Z-muse` | yes |
| Project scoping and cross-project leakage | `ch10-20260920T163314Z-context-frames` | yes |
| Stronger reader gaining on arbitrary-history tasks | none located | **no**: not used in the book |
