# compiler-behavior-v1 — matched behavioural evaluation of frozen bundles

SYNTHETIC FIXTURES. LIVE LOCAL READER. NOT A BOOK RESULT UNTIL PROMOTED.

Consumes `compiler-v1/run-001` bundles immutably and measures what a
fixed reader does with them. See `spec.yaml` for the frozen contract and
`fixtures/compiler-behavior-v1/manifest.json` for fixture selection,
budgets, readers, repeats, and spend guard.

## Reproduce (offline parts)

```text
contextlab behavior fixtures compiler-behavior-v1
contextlab behavior plan compiler-behavior-v1
contextlab behavior inspect <fixture> --condition B5
contextlab behavior dry-run compiler-behavior-v1 --reader fake
```

## Live run (after preregistration commit, canary first)

```text
contextlab behavior run compiler-behavior-v1 --reader primary --run-id run-001
contextlab behavior validate-run <run-dir>
```

Never edit fixtures, graders, tasks, budgets, or reader config after the
first genuine model call. The fake reader (`--reader fake`) is for
development and tests only.
