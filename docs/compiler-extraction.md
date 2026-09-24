# Compiler extraction

The deterministic Context Compiler is owned by the standalone
package
[`project-context-compiler`](https://github.com/ernanhughes/project-context-compiler)
(`context_compiler`, version 0.1.0, compiler-policy-v1 semantics).

```text
project-context
    depends on project-context-compiler @ <pinned git commit>
    (see pyproject.toml; upgrades are deliberate, never floating)
```

`src/project_context/compiler/` is a compatibility shim: it
re-exports the canonical records, engine, loaders, and policy, and
contains no implementation. New code should import
`context_compiler` directly.

Compatibility is proven two ways:

1. Differential gate: the historical in-repo engine versus the
   installed package over all 42 compiler-v1 fixture/budget cases —
   zero semantic mismatches, including full result/trace/bundle
   serialization equality.
2. `tests/test_compiler_external.py` plus the regression tripwire
   `tests/compiler_v1_external_expectations.json`: admitted ids,
   tokens, hashes, and failure reasons per case, checked against the
   installed package on every run.

Historical compiler experiments and frozen evidence
(`evidence/runs/compiler-v1/`, `compiler-behavior-v1` and their
manifests) remain immutable and describe the implementation that
existed at the time. The behavioural experiment
(`experiments/compiler-behavior-v1`) stays here; it consumes bundle
objects through the shim.

## TypeScript canonical compiler (0.2.0)

The standalone repository is now TypeScript-canonical
(`project-context-compiler` 0.2.0, same GitHub repository). The
Python 0.1.0 implementation is frozen under tag `python-v0.1.0` in
that repository and remains the pinned dependency here, so
historical runs reproduce exactly.

For new compiler use, the language boundary is JSON through the
TypeScript CLI (`context-compiler compile --request ... --output
...`); the Python harness reads the emitted bundle/result/trace
under the unchanged `project_context.*.v1` schemas. No second
Python compiler is maintained to avoid this boundary.
