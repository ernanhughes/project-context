Yeah I don't I like to **** Gary Schedule an account what the **** **** # OpenCode V2 capture adapter (read-only)

Observes OpenCode **2.0.16** (V2 API) assembled model-request context
without mutating it. Pinned to `@opencode/plugin@2.0.16` exact.

## What it observes

One record per observed model request at the session context hook:

| Hook                         | Records                                               | Identity                          |
| ---------------------------- | ----------------------------------------------------- | --------------------------------- |
| `session.hook("context")`    | assembled system/messages/tools/options + model/agent | sessionID, agent, model, sequence |
| `session.hook("compaction")` | checkpoint-summary request (same shape)               | as above, kind=compaction         |
| `session.hook("generate")`   | transient generate request (same shape)               | as above, kind=generate           |

Tool definitions are captured as model-visible description plus input
schema only. Executable functions are never recorded. Request
`options` are observed overrides only, never the complete effective
provider configuration. Model limits are read from `ctx.model` where
available, otherwise `null` (UNAVAILABLE — never hard-coded, never
inferred from names). `event.result` is never set on compaction.

Capture stage: `opencode.v2.model_context`. This is the OpenCode V2
semantic model-request context, **not** the byte-for-byte provider HTTP
request: protocol/provider lowering happens after this hook, and
provider-added material, the wire representation, and cache decisions
remain unobserved. The debugger reports state this explicitly.

Version policy: setup asserts the exact pinned OpenCode version and
fails clearly otherwise. There is no V1 fallback and no dual-version
runtime; a version mismatch is deliberate migration work, not a
compatibility layer.

## Install (user-activated use only)

Requirements: OpenCode 2.0.x (exactly 2.0.16 supported),
`PROJECT_CONTEXT_CAPTURE=1` in the environment. The adapter registers
nothing when the flag is absent.

1. Copy `src/*.ts` into `<project>/.opencode/plugins/contextlab/`
   (pure TypeScript, node builtins only, no runtime dependencies), or
   reference this directory through `plugins` in `opencode.json(c)`.
2. Set `PROJECT_CONTEXT_SPOOL_DIR` (default
   `~/.local/share/project-context/captures`, never inside a repo).
3. Run OpenCode normally. Each observed model request appends one JSONL
   record. No model calls are made by the adapter; no data leaves the
   machine.

Verify: the plugin id `context-debugger-capture` appears in OpenCode's
active plugin list after startup; after normal work,
`contextlab debug latest $PROJECT_CONTEXT_SPOOL_DIR` renders the
latest observed request.

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
`../../fixtures/opencode-capture-v2/session-three-requests.json` with
the Python debugger.
