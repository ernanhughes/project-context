---
family: F1
title: Ecological observation corpus
version: 1
status: draft
depends_on: []
model_calls: none
---

# F1 — Ecological observation corpus

Status: **draft, not frozen, nothing captured.** No genuine session has been
captured yet, and none should be until this is agreed and frozen.

## Question

What do real coding-agent context bundles contain, and how do they change over a
session?

This is a descriptive question. It asks what is there, not what works. Its
purpose is to tell the book which failures actually occur, so that later
controlled experiments recreate real shapes instead of invented ones.

Sub-questions, each answered per session:

- **Q0 Instrument.** Does the capture reconcile with itself, and can it be
  re-analysed to identical output?
- **Q1 Composition.** What share of the rendered context is each kind of material?
- **Q2 Growth.** How does the rendered size change request by request, and what
  drives it?
- **Q3 Repetition.** How much is byte-identical to earlier material?
- **Q4 Tool definitions.** What do they cost, and how stable are they?
- **Q5 Standing instructions.** What do project and system instructions cost, and how
  stable are they?
- **Q6 Prefix stability.** How much of each request matches the previous one, and
  what breaks it first?
- **Q7 Freshness evidence.** Does the capture expose enough to study staleness at
  all (the same call returning different bytes; version information)?
- **Q8 Pressure.** How close do sessions come to the model's window, and do
  compaction or rewrites occur?

## Hypotheses

These are expectations the book is prepared to be wrong about. They are not tested
with significance tests; they become decision triggers for later work (see the
analysis plan).

- **H1** In long sessions, at least 10% of the tokens in the last request are
  byte-identical repeats of earlier material.
- **H2** Tool definitions are at least 10% of the first request in the harness's
  default configuration.
- **H3** For most requests, at least half of the request matches the previous one as
  a stable prefix, and the first break is usually late (tool results), not early.
- **H4** In tool-using sessions, text the user typed is under 5% of the last request.
- **H5** In tool-heavy sessions, tool results are the largest growing category.

## Population

**Natural sessions**: real work by the project author, in their own repositories,
with one harness. The session is the unit.

The corpus must capture natural work. A task that would not otherwise be done is
never started just to fill a category.

**Eligible repositories** are chosen in advance as an allow-list. Each must contain
no third-party confidential material and no secrets. Only the *class* of each
repository is recorded (language family, size band, whether tests exist), never its
name or path.

**Strata.** A session is labelled from what was observed, not from what was
intended, and may carry several labels:

| Stratum | Operational definition |
|---|---|
| S1 short question | 1–3 model requests, no file edit |
| S2 single-file repair | edits exactly one file, up to 15 requests |
| S3 multi-file repair | edits three or more files |
| S4 test/debug loop | three or more test-runner tool calls |
| S5 tool-heavy investigation | tool results are over half of the rendered bytes at the last request |
| S6 long-running | 40 or more requests, or a compaction event observed |
| S7 project instructions | the author declares project instructions were present (sidecar field; origin is never inferred from text) |
| S8 stale or re-read material | the same call returns different bytes later in the session, if the capture exposes call identity; otherwise this stratum is dropped and reported |

**Target:** 24 usable sessions, at least 3 in each achievable stratum, at most 30 in
total and at most 6 whose primary label is the same stratum. At least 3 different
repositories, sessions spread over at least 3 calendar weeks, and every model
identity the author normally uses.

## Intervention and conditions

There is no intervention. Capture is read-only, opt-in and user-driven. The adapter
changes nothing about the context it observes; its no-mutation test stays green.

The single condition is "capture on, author works normally".

## Controls

Instrument controls, checked before each capture block:

1. The golden-fixture reconciliation test passes.
2. Per session, category totals reconcile with request totals (tolerance 2% of
   tokens; token counts are approximations and labelled so).
3. The analysis is deterministic: running it twice gives byte-identical output.
4. The harness and adapter versions are pinned and recorded per session. A version
   change starts a new block, which must pass control 1 again.
5. Sessions in which the author is testing the tool itself are excluded.

## Privacy and sanitisation

Decided before any capture, because raw material is never collected first and
sanitised later.

Four tiers, each derived from the one before:

| Tier | What | Where | Published |
|---|---|---|---|
| L0 | raw capture (full context text) | local spool, git-ignored, never uploaded | never |
| L1 | structural per-request metrics: counts, bytes, token estimates, shares, recurrence indicators, no text | derived locally | after export gate and recorded approval |
| L2 | aggregate tables across sessions | derived from L1 | after recorded approval |
| L3 | **shape cards** and synthetic fixtures recreating a shape | authored | yes; contain no ecological text |

Rules:

- The public derivative contains no content, paths, repository names, session or
  message identifiers, hashes, or timestamps (relative time only). This is the
  existing export gate, applied unchanged.
- The relation between L0 and L1 is kept in a **local-only index** holding both
  digests. A public claim that a derivative came from a raw capture is
  demonstrable by the author on request, and is never a public hash.
- **Before each session:** the author confirms the repository is on the allow-list,
  that no secrets are in the environment or working tree, and fills a **sidecar**
  with a closed vocabulary only: repository class, task type, whether project
  instructions are present, and (at the end) an objective outcome such as tests
  passing, build passing, change accepted, abandoned, or not applicable. The
  outcome is a fact about the work, not a measure of context quality.
- **After each session:** the raw spool is scanned with the same patterns as the
  publication gate. Any hit excludes the session from analysis and publication
  and is recorded in the exclusion ledger with its reason.
- The author may withdraw any session at any time, unread, with the reason
  recorded as "author withdrawal".
- No derivative is published without the recorded approval that the privacy spec
  already requires.

## Measurements

Per session, from the capture and the sidecar. Names follow the shared vocabulary.

- session identity (local ordinal), repository class, task type, duration and
  request count, model identity, number of tools available;
- rendered tokens per request, by category (the evolution of the rendered context);
- tool-definition share of the first request, and definition stability across
  requests;
- standing-instruction share, and its stability;
- history growth and tool-result growth per request;
- duplicate tokens per request (byte-identical to earlier material);
- stable-prefix length per request, and the category of the first divergence;
- availability of freshness or version evidence (counts of same-call-different-result
  events; whether repository state is visible), recorded as availability, not truth;
- compaction or rewrite events;
- distance to the declared model window, where the capture yields it, else unavailable;
- the sidecar outcome.

Not observable at this boundary and recorded as unavailable, never zero: provider
cache behaviour, provider-added material, provider usage and cost, latency.

## Trial design and rationale

- **Unit:** the session. Requests inside a session are repeated measures and are
  never pooled as if independent.
- **Size:** 24 sessions is chosen for descriptive precision. With a between-session
  standard deviation of 0.10, a mean share is known to about ±0.04; at 0.15,
  about ±0.06. It is not chosen to detect an effect, because none is tested.
- **At least 3 per stratum** is enough to see whether a shape recurs (two of three)
  without claiming a rate. Strata with fewer than 12 sessions are reported as
  individual sessions, never as estimated distributions.
- **No repeats.** Natural sessions cannot be repeated, and are not.

## Exclusions

A session is excluded only for a reason on this closed list, recorded in the
exclusion ledger, and never because its result looks unusual:

capture incomplete (attributed parse warnings or gaps); secret or identifier hit in
the raw scan; repository not on the allow-list; tool-testing session; author
withdrawal; capture made under a version block that has not passed control 1;
fewer than one primary request.

## Failure criteria

- **Instrument failure.** More than 25% of sessions in a block are incomplete, or
  any reconciliation error above tolerance occurs twice, or the analysis is not
  deterministic. The campaign pauses, the adapter is fixed, and a new block starts.
- **Design failure.** At the stopping point, fewer than three strata have three
  usable sessions each. The corpus is then reported as insufficient for claims about
  the missing strata, and nothing is extrapolated to them.
- **Privacy failure.** Any content or identifier appears in a candidate public
  derivative. Publication is blocked and the derivative regenerated.
- **Result that this design must survive.** Every hypothesis may be false. That is
  a valid outcome (see the analysis plan).

## Stopping rule

Stop at the first of:

1. every achievable stratum has at least 3 usable sessions and there are at least 24
   in total;
2. 30 usable sessions;
3. ten calendar weeks from the first capture.

A stratum is achievable if the author met natural work of that kind, which is
recorded. The corpus is never extended because its result is uninteresting. If it
stops on time, it is published as it stands, with its coverage described.

## Analysis plan

1. Produce the L1 structural file for each session, deterministically.
2. **Per session** summaries first. Then across sessions: median, interquartile
   range and range of every share. A bootstrap interval (2,000 resamples of
   sessions) only for groups of at least 12 sessions.
3. **Growth shape** per session by a fixed rule: a *step* if any request is at least
   1.5 times the previous one; otherwise *accelerating* if the average increase per
   request in the second half is at least 1.5 times that of the first half;
   otherwise *steady*.
4. **Decision triggers.** The following are decision rules for what is built next.
   They are not claims. They were chosen in advance as the size at which a design
   intervention could plausibly matter, and the author confirms them before this is
   frozen.
   - Run the tool-context family only if the median first-request tool-definition
     share is at least 10%. Otherwise the tool chapter's standing-cost claim is
     reduced to a description of this harness.
   - Prioritise safe removal in the transformation family if, in long sessions, the
     median share of duplicate tokens at the last request is at least 10%.
     Otherwise the pruning chapter becomes a conditional pass with the measured
     prevalence stated.
   - Prioritise externalise-and-recall if at least two sessions reach 60% of the
     declared window, or any compaction occurs. If neither, those chapters are
     framed as pressure-conditional.
   - Run the paid cache probe only if the median stable-prefix fraction is at least
     50% in at least half of long sessions.
5. **Shape catalogue.** For each pathology seen in at least two sessions (duplicate
   reads, superseded observations, growing history, rule blocks, overlapping
   excerpts, definition overhead, scope boundaries), write a shape card: its
   structure, sizes and positions, how often it occurs in the sample, and how to
   recreate it synthetically. Cards contain no ecological text. These cards, not the
   raw sessions, are the input to the interference, transformation, externalisation,
   tool and representation families.
6. A reconciliation report (Q0).
7. Report descriptive facts only.

## Claims this result may support

- What real bundles in this sample contain, how they grow, where they repeat, what
  tool definitions and standing instructions cost, how stable the prefix is, whether
  freshness evidence is observable, and how close sessions come to the window.
- That the capture instrument reconciles.
- That particular failure shapes occur, and how often in this sample.
- Which later experiments the decision triggers select.

## Claims this result may not support

- That pruning improves performance.
- That summaries preserve information.
- That any ordering is better.
- That retrieval should occur.
- That context caused any behavioural difference.
- That the shapes found are harmful; only that they exist.
- Anything about prevalence beyond this developer, these repositories and this
  harness.
- Anything about cost or latency, which the capture does not observe.

## Deviations

None yet.
