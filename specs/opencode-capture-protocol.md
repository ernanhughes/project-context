# OpenCode capture protocol (future collection)

Status: protocol defined; no collection runs yet. A session enters the
ecological corpus only through the steps below, in order.

## Activation (user-driven)

1. Install the adapter for one project: copy
   `integrations/opencode/src/*.ts` to
   `<project>/.opencode/plugins/contextlab/` (pure TypeScript, no
   runtime dependencies). Load it **last** among context-touching
   plugins; record the plugin order in the session notes.
2. Set `PROJECT_CONTEXT_CAPTURE=1` and optionally
   `PROJECT_CONTEXT_SPOOL_DIR` (default
   `~/.local/share/project-context/captures`, never inside a repo).
3. Run OpenCode normally. No model calls are made by the adapter; no
   data leaves the machine. Never start or stop the user's unrelated
   OpenCode processes to test capture; activation is user-driven only.

## Per session record (public manifest only, no task text)

```text
capture version (adapter + bridge schema)
OpenCode version + plugin API version
project category (not name/path)
approximate task type (not prompt text)
model/provider where observed
start/end timestamps
number of invocations observed
whether compaction occurred (separately hooked; Stage 1: deferred)
whether capture was complete (gaps noted)
sanitisation/publication status
```

## Session diversity (sampling plan, not a result)

Eventually aim for variation such as: short bug fix, long debugging
session, test-driven change, repository exploration, multi-file
refactor, tool-heavy investigation, documentation/research work, a long
session approaching compaction. Do not manufacture sessions to tick
categories. Do not generalise from one session; the ~10-session target
from the book remains the ecological bar.

## What never enters the public manifest

Task text, prompts, file contents, paths, repository names, session or
message IDs, user information, secrets. Manifests carry counts, ranges,
hashes of sanitised artifacts, and statuses only.
