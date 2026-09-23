# OpenCode V1 capture adapter (read-only)

Observes OpenCode **1.18.27** (V1 API) pre-dispatch context signals
without mutating them. Pinned to `@opencode-ai/plugin@1.18.27` exact.

## What it observes

| Hook                                   | Records                                   | Identity                                                             |
| -------------------------------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| `experimental.chat.system.transform`   | system string array                       | sessionID when present + model                                       |
| `experimental.chat.messages.transform` | message list with parts                   | **none** (hook input is `{}`); parts may carry their own session IDs |
| `chat.message`                         | admission message + parts                 | sessionID, agent, model                                              |
| `tool.execute.after`                   | tool title/output/metadata + call linkage | sessionID, callID, tool name (input args excluded)                   |

Capture stage: `opencode.v1.pre_dispatch_partial`. This is **not** the
assembled provider request: V1 exposes no unified pre-dispatch hook, so
system, messages, admissions, and tool results arrive as separate
records. Deferred on V1: per-tool definitions (no invocation linkage),
generation settings (not context membership), compaction observation.

## Install (user-activated smoke use only)

Requirements: OpenCode 1.18.x, `PROJECT_CONTEXT_CAPTURE=1` in the
environment. The adapter registers nothing when the flag is absent.

1. Copy `src/*.ts` into `<project>/.opencode/plugins/contextlab/` (pure
   TypeScript, node builtins only, no runtime dependencies).
2. Set `PROJECT_CONTEXT_SPOOL_DIR` (default
   `~/.local/share/project-context/captures`, never inside a repo).
3. Load the capture plugin **last** among context-touching plugins so
   earlier hooks' mutations are visible. OpenCode runs hooks in plugin
   order; nothing here can prove later hooks made no further change.
4. Run OpenCode normally. Each observed hook appends one JSONL record.
   No model calls are made by the adapter; no data leaves the machine.

## Develop

```bash
npm install          # pinned devDeps only
npm run typecheck    # tsc --noEmit
npm test             # node --test (built-in runner, no framework)
npm run lint         # prettier --check
```

Runtime code (`src/`) must stay dependency-free and use only erasable
TypeScript so it runs identically under OpenCode's runtime and plain
node. Tests live in `tests/` and share the golden fixture at
`../../fixtures/opencode-capture-v1/primary-one-request.json` with the
Python ingester.
