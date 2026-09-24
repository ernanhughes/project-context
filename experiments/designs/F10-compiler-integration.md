# F10 — Compiler integration (design, new)

Status: design only. The last family. It answers whether the pieces work together.

**Tests:** an integration, not a mechanism.

## Question

Does a compiler built from the mechanisms that survived the earlier families beat
simple baselines on realistic tasks, and does each surviving mechanism still pay for
itself inside the whole?

## Why it exists

The first behavioural experiment could compare only a compiler with hard gates and
one with additional staging, on six tasks. It could not say anything about
pruning, compression, externalisation, recall or governance, because none of them
were in it. Whether they compose is a different question from whether each works.

## Design

Trajectories recreated from the shape cards, with hidden later probes. Conditions:

| Condition | What it is |
|---|---|
| Raw dump | everything that fits |
| Simple top-k | relevance only |
| Hard gates | eligibility only |
| Core compiler | derived eligibility, budget, deterministic assembly, explicit failure and trace |
| Core plus surviving passes | plus every conditional pass that earned its place earlier |
| Ablations | the previous condition with one pass removed at a time |
| Oracle | a ceiling |

Only passes that survived their own family are included. A pass that did not is not
added here to rescue it.

## Measurements

Task success, harmful action and evidence use; survival of exact requirements; net
tokens and cost; decision-trace completeness; the distribution of failure states.
Two pinned readers, one of them repeated across the ablations.

## Size

About 20 trajectories × 6 conditions × 6 probes × 2 readers, plus ablations: about
2,500 local calls. A subset may be read by a stronger hosted reader, about 300 calls
of roughly 20,000 tokens each, only where a local reader cannot discriminate.

## Null and negative outcomes

- **The core matches the full compiler:** the architecture is the core alone, and the
  conditional passes are documented as unearned.
- **A pass helps alone but not in the whole:** reported, and the pass stays optional.
- **Nothing beats simple baselines:** the book's final architecture claim is
  withdrawn, and the compiler chapter becomes a discussion of why.

## Depends on

Everything before it: the governance family, the transformation family, the
externalisation family, the reader-transfer replication.
