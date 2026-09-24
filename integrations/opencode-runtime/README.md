# opencode-runtime — explicit intervention integration (UNVERIFIED)

Separate from `../opencode` (the read-only observer). This package owns
mutation; the observer must never import it and it must never import
the observer.

**Status: hook mutation contract unverified.** The tested Stage 6D
surface is the Python synthetic harness (`src/project_context/
runtime/`, `fixtures/runtime-v1/`). This skeleton prepares the live
shape only: whether assigning `event.system` inside
`session.hook("context")` alters a real model request has not been
confirmed against live OpenCode 2.0.16. Do not install for ordinary
work. A single throwaway live probe is the explicit next step if hook
validation is required; it counts as no evidence.

Opt-in: registers hooks only with `PROJECT_CONTEXT_RUNTIME=inject`
and reads the rendered block from `PROJECT_CONTEXT_RUNTIME_BLOCK`.
Anything else is a no-op. Conflicting pre-existing blocks refuse
loudly; identical blocks are idempotent; errors never partially write.
