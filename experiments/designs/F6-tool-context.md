# F6 — Tool context (design)

Status: design only, and **conditional**. It runs only if the ecological corpus
shows tool definitions are a meaningful share of real context (routing trigger in
the corpus preregistration). If not, the tool chapter's standing-cost claim is
reduced to a description of the harness observed, and this family is not run.

**Tests:** a mechanism (what the capability surface costs and what it does to tool
choice).

## Scope, deliberately narrow

Tool-result growth and tool-result shaping are **not** here: they are item types in
the transformation and externalisation families. This family is only about the
**definitions**.

Distinguished factors:

| Factor | Question |
|---|---|
| standing cost | what do the definitions cost per request, as the number and size of tools grows |
| number of tools | does choice degrade as the set grows |
| schema verbosity | minimal, typical and verbose schemas for the same tool |
| name overlap | do near-duplicate names cause wrong or redundant calls |
| deferred loading | does loading definitions on demand save tokens without causing misses |

The tools themselves are not redesigned. Only the surface presented to the reader
varies, over identical deterministic backends.

## Population

Tool sets sized from the real definitions in the ecological corpus (real counts,
real description lengths, real schema sizes), instantiated with synthetic names and
behaviour. At least 25 tasks, each needing one specific tool.

## Measurements

- Standing cost: definition tokens, deterministic, no model needed.
- Selection accuracy, invalid and redundant calls, task success.
- Deferred loading: search steps, misses (tool needed but not loaded), net tokens.
- Cache effect of mutating the definition block, as first divergence (computed).

## Confounds

Definition order is fixed and reported. Names are randomised across conditions so no
name is systematically favoured. Schema verbosity changes tokens but not
information.

## Size

Standing cost is free. Selection accuracy: 25 tasks × 4 set sizes × 3 overlap levels
× 2 readers, about 600 local calls.

## Null and negative outcomes

- **Definitions are a small share in real sessions:** the family is not run; the
  chapter is reduced.
- **Selection does not degrade with set size or overlap:** the choice-interference
  claim is dropped; only the cost claim remains.
- **Deferred loading misses often:** stated as the trade it is.

## Depends on

The ecological corpus (hard: it decides whether this runs at all).
