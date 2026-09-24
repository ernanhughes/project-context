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
