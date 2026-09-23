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
