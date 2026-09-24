# Privacy boundary

This repository is public. Real agent sessions contain credentials, private
code, personal data, and customer information. The boundary is structural,
not advisory.

## Never commit by default

```text
credentials, API keys, tokens, private source code,
private repository content, personal data, private prompts,
private messages, local filesystem secrets, raw connected-account data
```

## Local-only locations (git-ignored)

```text
.local/          scratch, downloads, transient analysis
raw-corpus/      unprocessed real traces (never committed)
private-runs/    runs against private material (never committed)
runs/*/          frozen run directories, except runs/README.md
```

Only `runs/README.md` (the convention document) is committed. Run
artifacts live in CI-local or explicitly published locations per future
policy; Stage 0 commits no run artifacts at all.

## Publication path

Raw material may enter git only through explicit sanitisation plus human
approval, recorded as `CorpusManifest.sanitisation_status =
"approved-public"`. `assert_publishable()` refuses everything else, and
tests pin that refusal. Sanitised-but-unapproved material is still
unpublishable: approval is a human decision, not a script output.

## Identifier hygiene

Never derive stable IDs from secret or private content. Fixture IDs are
authored constants; live capture IDs are random UUIDs.

## OpenCode capture (Stage 1)

Local raw captures may contain source code, conversation text, tool
output, system and project instructions, and any secret the model was
genuinely shown. Therefore raw captures are private, git-ignored, never
uploaded, never automatically sanitised, and never printed casually
(`inspect` defaults to structural output; raw printing requires an
explicit local flag). Bundle ids (`opencode-<capture-uuid>`) and
filenames (UUIDs, never prompt/project/secret-derived) carry no content.
Content fingerprints are local-only and never exported; export relabels
session keys to ordinals and the gate refuses content, identifier, hash,
and secret markers.
## Context Debugger (Stage 5)

The debugger is a local-only product layer over the same raw captures:
it makes zero model calls and modifies no context. Default reports are
structural only — no raw content, no raw session identifiers (local
ordinals such as `local:1` instead), no hashes. Raw content prints only
under an explicit local flag (`--show-content`, `--allow-content-search`
for substring search), with a local-only warning on stdout. Debugger
JSON is deterministic and versioned for a future local TUI; it carries
the same structural-only default. Nothing captured or derived is ever
sent to a model or the network by debugger code.

## Approved publications

Run artifacts are private by default. A run may be published only after the
sanitisation gate in `scripts/publish_evidence_runs.py` passes and a human
approval is recorded here.

| Run | Approved | Approver | Basis |
|---|---|---|---|
| `compiler-v1/run-001` | 2026-09-24 | project author | synthetic fixtures; gate passed |
| `compiler-behavior-v1/run-003` | 2026-09-24 | project author | synthetic tasks, synthetic responses to them; gate passed |
| `compiler-behavior-v1/run-003-transfer` | 2026-09-24 | project author | as above; gate passed |

Published runs are copied byte for byte to `evidence/runs/`. The gate refuses
any run that is not `evidence_class: synthetic`, and any file containing a
machine path, hostname, address, key-like string, credential assignment or
e-mail address. It never edits a file and never overwrites a differing one.

The approval covers these three runs only. Real captured sessions
(`raw-corpus/`, OpenCode captures) are unaffected: they stay private, and a
sanitised derivative of a real corpus needs its own approval under
`CorpusManifest.sanitisation_status`.