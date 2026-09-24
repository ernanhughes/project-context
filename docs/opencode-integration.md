# OpenCode integration (canonical package)

Historical local/global plugin deployments have been replaced by the
canonical `project-context-opencode` package:

```powershell
opencode plugin add github:ernanhughes/project-context-opencode
opencode plugin update
```

Historical artifacts (`runtime-live-6dl`, `runtime-live-6dr1`,
`oracle-leverage-v1`) remain immutable evidence and are not normative
installation instructions. The frozen sources under
`integrations/opencode/` and `integrations/opencode-runtime/` are
kept byte-identical as reference for those qualifications; see the
`DEPRECATED.md` files there.

## Boundary

```text
project-context
    research harness / experiments / evidence
              │
              ↓ consumes as transport dependency
project-context-opencode
    OpenCode integration (observer + runtime)
              │
              ↓
OpenCode
```

No independent source copies of the TypeScript plugin are maintained
in both repositories. For experiments, record the plugin package
version, the plugin Git commit, the OpenCode version, the requested
and observed provider/model, and the liveness result.

## Transport preflight (oracle-leverage-v1, amendment 03)

Static identity checks (digests, versions, file presence) do not
prove a live observation/injection path. Before any behavioural wave,
the harness additionally requires a liveness canary:

```text
plugin installed/configured (opencode plugin list)
+ current package identity known (version + Git commit)
+ live observer canary PASS
+ live runtime canary PASS
+ runtime→observer reconciliation PASS (marker exactly once,
  post-mutation, same session)
+ requested model/provider attribution PASS
```

Procedure: run the package smoke test with the scheduled subject
model, copy the resulting `canary.json` to
`.local/transport-canary.json` (local-only, never committed), and
pass it to `preflight(..., transport_canary=...)`. The wave stops
before subject inference when the gate fails. See
`experiments/oracle-leverage-v1/harness-amendment-03.json`.

The behavioural experiment itself (`oracle-leverage-v1`) is not
rerun here.
