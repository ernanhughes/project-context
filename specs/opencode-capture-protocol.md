# OpenCode capture protocol (V2 collection)

Status: protocol defined; V1 collection retired. A session enters the
ecological corpus only through the steps below, in order.

## Versions (pinned, exact)

```text
OpenCode:             2.0.16
plugin API:           V2
plugin package:       @opencode/plugin 2.0.16
adapter:              0.2.0
bridge schema:        project_context.opencode_capture.v2
capture stage:        opencode.v2.model_context
```

The adapter asserts the exact OpenCode version at setup and fails
clearly otherwise. There is no V1 fallback. A version mismatch is
deliberate migration work.

## Activation (user-driven)

1. Install the adapter for one project: copy
   `integrations/opencode/src/*.ts` to
   `<project>/.opencode/plugins/contextlab/` (pure TypeScript, no
   runtime dependencies), or reference it through `plugins` in
   `opencode.json(c)`.
2. Confirm the plugin id `context-debugger-capture` appears in
   OpenCode's active plugin list after startup.
3. Set `PROJECT_CONTEXT_CAPTURE=1` and optionally
   `PROJECT_CONTEXT_SPOOL_DIR` (default
   `~/.local/share/project-context/captures`, never inside a repo).
4. Run OpenCode normally. No model calls are made by the adapter; no
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
number of primary invocations observed (plus auxiliary counts, if any)
whether compaction was observed (kind=compaction records)
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

## Session identity (operational definition)

A campaign session is the set of validated V2 bridge records sharing
one `session_id`, ordered by `invocation_sequence`. The debugger's
primary timelines use `request_kind == "context"` only; compaction and
generate records carry an explicit kind and are counted separately,
never merged into the primary series. Records without any session
scope are `unlinked`: counted separately, never merged into a
fictitious session, and excluded from session-scoped analyses (growth,
shared prefix) with an explicit reason.

## Capture completeness (operational definition)

`complete_capture` is true for a session when all its contributing
files parsed without skipped lines, no invalid records were attributed
to it, and at least one validated record exists. It means: all expected
V2 observer records for the session arrived without known adapter
interruption. It does NOT mean complete provider context: the wire
payload, provider-added material, cache behaviour, usage telemetry,
and transport detail remain outside the `opencode.v2.model_context`
boundary. A session can be observer-complete and provider-incomplete
at once.
