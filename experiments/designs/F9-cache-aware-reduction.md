# F9 — Cache-aware reduction economics (design, new)

Status: design only, and **optional**. It adds a family the first list did not have.
It runs only if the ecological corpus shows reuse is available to lose (decision
trigger) and after the transformation family has produced real reductions.

**Tests:** an integration between two mechanisms (reduction and prompt caching).

## Question

When a reduction that saves tokens rewrites the front of the context, does it save
money after the cache reuse it destroys is counted?

## Why it is separate

The transformation family measures what survives and what it saves in tokens. Whether
those savings are real cost savings depends on provider caching, which needs a live
provider with cache telemetry. It is small, costs money, and is deliberately kept apart
so no other family depends on spend.

## Design

One provider whose responses separate ordinary, cache-write and cache-read tokens. A
fixed synthetic prefix (instructions, definitions, frozen history) and a small dynamic
suffix, with deterministic lookup tasks so model quality cannot dominate.

| Condition | What it is |
|---|---|
| A | stable, append-only growth |
| B | a small inert change near the start |
| C | the same-sized change after the cacheable prefix |
| D | a reduction from the transformation family applied mid-prefix |
| E | the same reduction deferred to a cache-safe boundary |
| F | no reuse possible (cold control) |

Intervals between requests are varied around the lifetime boundary so identical
prefixes are seen both hitting and expiring.

## Measurements

Write, read and uncached tokens; time to first token; provider cost from a recorded
price schedule; first-divergence position; reusable-prefix ratio, reported per
provider and never combined across providers.

## Size

About 5 conditions × 40 requests × 50,000-token prefix, one provider: about 10 million
input-token equivalents without caching. At an assumed 1–3 currency units per million
input tokens that is 10–30 units before cache discounts. The price schedule is recorded
with the result, and the assumed rate is replaced by the current one before running.

## Null and negative outcomes

- **The reduction pays despite invalidation:** the deferral machinery is unnecessary.
- **Invalidation cost exceeds savings for typical shapes:** the chapters state when
  not to reduce.
- **Provider behaviour differs from its documentation:** recorded, and the chapter says
  which claims rest on documentation only.

## Depends on

The transformation family (hard); the ecological corpus trigger (soft).
