# Evidence manifests

Frozen runs live under `.local/runs/` and are **local-only and git-ignored**
(`specs/privacy.md`: publication needs sanitisation plus recorded human
approval). The companion book (`ernanhughes/context`) cites some of them as
*Book results*. This directory makes those citations auditable without
publishing the artifacts.

`manifests/<experiment>__<run>.json` holds, for one frozen run:

- the run identity and the code commit that produced it;
- the SHA-256 and size of every artifact file in the run directory;
- the environment as recorded (reader model alias, decoding settings, ...);
- the headline numbers **recomputed from the artifacts**, not typed in;
- the known limitations of the recorded run.

```bash
python scripts/evidence_manifest.py            # (re)write manifests
python scripts/evidence_manifest.py --verify   # exit 0 ok, 1 drift, 2 artifact absent
```

Anyone holding a copy of a run can check it against its manifest; a book
number that no longer agrees with the run, or a run that has been altered,
fails `--verify`. The tool only reads `.local/runs/`.

## Publication policy (current)

**Policy B — derived evidence manifests — is in force.** Raw run artifacts
stay local. An audit of the three cited runs found them free of machine
paths, hostnames, credentials and personal data (all fixtures are synthetic,
and the reader saw only synthetic tasks), so **Policy A — publishing a
sanitised export of the artifacts — is technically possible**. It is not done
here because `specs/privacy.md` requires recorded human approval before any
publication. That decision is the author's; if approved, the export is the
run directory files named in each manifest, and the digests already recorded
here would apply to it unchanged.

## Cited runs

| Run | Book chapters | Code commit |
|---|---|---|
| `compiler-v1/run-001` | 23, 24 | `ec642dc` |
| `compiler-behavior-v1/run-003` | 24 | `ea95e78` |
| `compiler-behavior-v1/run-003-transfer` | 24 | `ea95e78` |

Adding a run means adding it to `RUNS` in `scripts/evidence_manifest.py` and
committing its new manifest. Existing manifests are never edited by hand.
