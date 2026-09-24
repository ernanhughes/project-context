# runtime-v1 fixtures (SYNTHETIC)

Completely synthetic injection harness: hand-built selected bundles
plus minimal V2-shaped requests. No model calls; the existing V2
ingester serves as the observer in tests and the demo CLI.

## Layout

```text
requests/ordinary.json   base synthetic request (valid V2 record)
requests/conflict.json   same request with a differing runtime block
bundles/<case>.bundle.json  selected ContextBundles (hand-built)
truth.json               per-case oracle (tests and demo only)
```

## Cases

| Case | What it proves |
|---|---|
| a-empty | empty selection mutates nothing; observer sees the original |
| b-one-ordinary | one selected item renders once at the appended location |
| c-ledger-pending | pending-verification payload renders marked |
| d-mixed | mixed bundle renders in compiler order |
| e-rejected-absent | unselected content never appears |
| f-idempotent | second injection is a byte-identical no-op |
| g-conflict | differing pre-existing block fails loudly, unmutated |
| h-tampered | drop/duplicate/reorder/extra variants all fail reconciliation |
| j-privacy-trap | private-looking unselected strings never appear |

Case I (dormant/unknown never reaches runtime) is structural: the
adapter yields no candidate, so no bundle exists to render. It is
covered by adapter unit tests, not by a harness file.
