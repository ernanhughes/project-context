# Deprecated: use the canonical package

This directory (`integrations/opencode-runtime`) is a **frozen
reference** for historical qualifications (notably
`runtime-live-6dr1`, whose artifact records these files' hashes). It
is not the canonical integration.

Canonical source and development home:

```powershell
opencode plugin add github:ernanhughes/project-context-opencode
```

The live-tested behaviour (hook-boundary mutation, opt-in only,
fail-safe injection, trace outcomes) now lives there. See
`docs/opencode-integration.md`. Do not extend these files; do not
add new per-file hash workflows around them.
