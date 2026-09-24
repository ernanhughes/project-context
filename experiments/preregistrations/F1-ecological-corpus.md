---
family: F1
title: Ecological observation corpus
version: 3
status: draft
depends_on: []
model_calls: none
---

# F1 — Ecological observation corpus

Status: **draft, not frozen, nothing captured.** No genuine session has been
captured, and none should be until this is reviewed and frozen. The capture
machinery, the session index and the dry runs exist and pass on synthetic data only.

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
- **Q3 Repetition.** How much of a request is the same tool output more than once?
  (Carry-over of history is a separate, expected quantity; see *Measurements*.)
- **Q4 Tool definitions.** What do they cost, and how stable are they?
- **Q5 Standing instructions.** What does the system block cost, and how stable is it?
- **Q6 Prefix stability.** How much of each request matches the previous one under a
  stated render order, and what breaks it first?
- **Q7 Freshness evidence.** Does the capture expose enough to study staleness at
  all (the same call returning different bytes; version information)?
- **Q8 Pressure.** How close do sessions come to the model's window, and do
  compaction or rewrites occur?

## Hypotheses

These are expectations the book is prepared to be wrong about. They are not tested
with significance tests. They feed **routing triggers** (see the analysis plan), which
decide what is built next and which say nothing about whether a mechanism works.

- **H1** In long sessions, at least 10% of the bytes in the last request are
  **redundant payload**: a tool output that appears more than once in that request.
  History that is simply re-sent is *carry-over* and is not counted. (Earlier draft
  wording counted "byte-identical repeats of earlier material", which history re-sending
  would satisfy in almost every session; it was narrowed before any data existed.)
- **H2** Tool definitions are at least 10% of the first request in the harness's
  default configuration.
- **H3** For most requests, at least half of the request matches the previous one as
  a stable prefix, and the first break is usually late (tool results), not early. The
  prefix is computed under an **assumed** render order (tool definitions, system,
  messages) and is a proxy, because the provider's actual order is not observed.
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

**Strata are for coverage, not ontology.** They show which kinds of natural work the
corpus has and has not met. Each usable session gets one **primary** stratum and any
number of **secondary tags**, from what was observed, not from what was intended:

- The primary stratum is the first of S6, S5, S4, S3, S2, S1 whose definition the
  session meets, in that fixed order. The rule reads the session only. It never looks
  at how many sessions each stratum already has, and a session is never relabelled to
  fill a gap.
- Every other definition the session also meets is recorded as a tag. S7 and S8 are
  tags only.
- A session that meets none is kept and labelled `S0_unclassified`.
- A stratum that no session met is recorded as **naturally absent**, together with the
  number of sessions observed while it was absent. Nothing is sampled to fill it.

| Stratum | Operational definition | Basis |
|---|---|---|
| S1 short question | 1–3 model requests, no file edit | observed |
| S2 single-file repair | edits exactly one file, up to 15 requests | derived: distinct paths in the arguments of edit-tool calls |
| S3 multi-file repair | edits three or more files | derived: distinct paths in the arguments of edit-tool calls |
| S4 test/debug loop | three or more test-runner tool calls | derived: shell-tool calls whose command is a recognised test runner |
| S5 tool-heavy investigation | tool results are over half of the rendered bytes at the last request | observed |
| S6 long-running | 40 or more requests, or a compaction record observed | observed |
| S7 project instructions | the author declares project instructions were present | declared (sidecar; origin is never inferred from text) |
| S8 stale or re-read material | the same call (tool and arguments) returns different bytes later in the session, and both results remain | derived; a re-run whose state changed also qualifies, so this shows an older result surviving, not that it is wrong |

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

0. The synthetic dry runs pass: the privacy dry run (no planted material reaches a
   derivative, whether or not the scan noticed it) and the measurement dry run (every
   reported quantity matches a value worked out by hand). Synthetic sessions never
   enter the corpus; the session index for dry runs cannot be opened as the corpus.
1. The golden-fixture reconciliation test passes.
2. Per session, the derivative reconciles with its source by an independent recount
   (exact bytes and part counts). Token counts are approximations and labelled so.
3. The analysis is deterministic: running it twice gives byte-identical output.
4. The harness and adapter versions are pinned and recorded per session. A version
   change starts a new block, which must pass control 1 again.
5. Sessions in which the author is testing the tool itself are excluded.

## Observability and completeness

What the capture can and cannot see is fixed before any data. Every reported quantity
has one status, held in code and tested:

- **OBSERVED**: read directly from the record.
- **DERIVED**: computed deterministically from observed material.
- **JOINED**: read from the harness's own local record and joined to the session
  afterwards, read-only and from one table, so it was not seen at the capture boundary.
- **PROXY**: a stand-in for the thing wanted, named as a stand-in wherever it is used.
- **DECLARED**: supplied by the author in the sidecar, never inferred.
- **UNOBSERVED**: the capture cannot see it. It is never zero and never absent. A
  summary over sessions where a quantity was unobserved has a smaller denominator, and
  the report states both counts.

UNOBSERVED includes: repository state or version, why the provider did or did not reuse
a prefix, provider-added material, whether reasoning parts reach the provider, the
provider's render order, sub-agent relations, and the split of the system block into
harness, project and user instructions. (An earlier draft also listed tool-call
arguments, provider usage, cost, latency and cache reads. The calibration run showed the
arguments are in the record and the rest are in the harness's own database; see
`specs/f1-calibration.md`.) A
session with no tool definitions in any record has its tool-definition share recorded
as UNOBSERVED, not as zero, because a harness that fails to expose tools and a harness
that has none cannot be told apart.

**A complete session** is one whose records, taken alone, are a whole observation: every
record is valid and its integrity value recomputes; all records share one session
identity; every message has the shape the analysis understands; sequence numbers run 1..N, each
once, across all request kinds (the adapter keeps one counter per session and persists it,
so a harness restart does not reset it; a gap means a lost record, and if the adapter could
not vouch for its ordering it writes a marker that makes the session incomplete); no lines
were skipped; and at least one primary (`context`) request
exists. A session that is not complete is excluded, its reason recorded, and never repaired.
"Complete" means all expected observer records arrived. It does not mean the provider's
final prompt was seen.

## Privacy and sanitisation

Decided before any capture, because raw material is never collected first and
sanitised later.

Four tiers, each derived from the one before:

| Tier | What | Where | Published |
|---|---|---|---|
| L0 | raw capture (full context text) | local spool, git-ignored, never uploaded | never |
| L1 | structural per-request metrics: counts, bytes, token estimates, shares, indicators, no text | derived locally | after the publication gate and recorded approval |
| L2 | aggregate tables across sessions | derived from L1 | after recorded approval |
| L3 | **shape cards** and synthetic fixtures recreating a shape | authored | yes; contain no ecological text |

Rules:

- The public derivative is a whitelisted structure of numbers, closed-vocabulary
  labels and the string `UNOBSERVED`. It has no field that can hold text, so a scan that
  misses something in the raw capture cannot cause a leak. It contains no content,
  paths, repository names, session or message identifiers, content hashes, or
  timestamps (relative time only).
- The **publication gate** then checks the built derivative against the raw capture it
  came from: schema whitelist, the existing export gate, value patterns (dates, long
  hexadecimal strings, addresses, URLs, paths), every string the scan retained locally,
  and every distinctive raw token. Any hit blocks publication. A blocked derivative is
  regenerated by fixing the tool, never edited by hand.
- Clean content is necessary and not sufficient: publication also needs the recorded
  approval that the privacy specification requires.
- The relation between L0 and L1 is kept in a **local-only index** holding both
  digests. This is a digest of raw content and never appears in a public file. The
  evidence manifests may carry the digest of a *published file* so that its bytes can be
  verified; that is a different thing from a digest of raw content.
- **Before each session:** the author confirms the repository is on the allow-list,
  that no secrets are in the environment or working tree, and fills a **sidecar**
  with a closed vocabulary only: language family, size band, whether tests exist, task
  type, whether project instructions are present, whether other plugins that can change
  the context were active, whether the author saw scope or authority problems, and (at the end) an objective outcome such as tests passing, build
  passing, change accepted, abandoned, or not applicable. The outcome is a fact about the
  work, not a measure of context quality. Free text is not accepted.
- **After each session:** the raw spool is scanned. Two classes of hit are kept apart.
  A **credential** (an API-key-shaped string, a token, a private key block, a URL with
  embedded credentials, a named secret assigned a literal) excludes the session from
  analysis and publication and is recorded in the exclusion record. An **identifier**
  (a path, an address, a hostname, an email) is expected in real work, is recorded as a
  count by class, and does not exclude the session, because the derivative has nowhere
  to carry it and the gate confirms that it does not. Literal sensitive terms the author
  lists locally (a repository name, a user name) are matched as well. Scan reports hold
  categories and counts, never the matched text.
- The author may withdraw any session at any time, unread, with the reason
  recorded as "author withdrawal". A withdrawn session stays in the session index as a row.
- **The session index** exists before the first session (see *Measurements*). Synthetic
  and dry-run material is refused by the ecological session index by rule.

## Measurements

Per session, from the capture and the sidecar. Names follow the shared vocabulary.

- session identity (local ordinal), repository class, task type, duration and
  request count, model identity, number of tools available;
- rendered size per request (bytes; tokens as two labelled estimates, bytes divided by four
  and words times 1.3), by category, and, where the harness's usage record is joined,
  provider-reported prompt tokens, output tokens, cache reads, cost and latency;
- tool-definition share of the first request, and definition stability across
  requests;
- system-block share, and its stability (the split by origin is unobserved);
- history growth and tool-result growth per request;
- **carry-over** per request: bytes of parts re-sent unchanged from an earlier request in
  the session. Expected, not a finding on its own;
- **redundant payload** per request: bytes of tool-output parts whose output body,
  is byte-identical to one earlier in the same request and is at least 32 bytes; the
  second and later occurrences are counted. Whitespace-normalised identity is reported
  separately and never mixed in;
- stable-prefix length per request under the assumed render order, and the category of
  the first divergence;
- same-call-different-bytes events (derived from observed arguments; a signal that an
  older result survives beside a newer one, not that it is wrong);
- compaction records, and **history rewrite** events (an earlier message part changed or
  disappeared between consecutive requests; appending is not a rewrite);
- distance to the model window, three ways and never merged: provider-reported prompt
  tokens, a bytes-based estimate and a word-based estimate, each over the model's input
  limit if the harness records one, else its context limit; unobserved where the model has
  no recorded limit;
- the sidecar outcome.

No embedding, no model and no similarity judge is used anywhere. Every measure is byte
identity, exact identity after whitespace normalisation, or tool and source identity.

**The session index** has one row per session: ordinal, capture date (local only) and campaign
week, primary stratum and tags with their basis, repository class, reader identity,
turn count, tools available, completeness and reasons, privacy state, sanitisation state,
whether a derivative exists, shape cards derived, and a withdrawn or excluded flag with
its reason. Its public projection carries ordinals and structure only.

Not observable at this boundary and recorded as unobserved, never zero: provider
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
exclusion record, and never because its result looks unusual:

capture incomplete (with its attributed reason); credential hit in the raw scan;
repository not on the allow-list; tool-testing session; author withdrawal; capture made
under a version block that has not passed control 1; fewer than one primary request;
instrument reconciliation failure; privacy gate failure.

## Failure criteria

- **Instrument failure.** More than 25% of sessions in a block are incomplete, or
  any reconciliation error occurs twice, or the analysis is not deterministic. The
  campaign pauses, the adapter is fixed, and a new block starts.
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

A stratum is achievable if the author met natural work of that kind, which the session index
records. The corpus is never extended because its result is uninteresting. If it
stops on time, it is published as it stands, with its coverage described.

## Analysis plan

1. Produce the L1 structural file for each session, deterministically.
2. **Per session** summaries first. Then across sessions: median, interquartile
   range and range of every share, over the sessions where it was observed, with the
   number unobserved stated. A bootstrap interval (2,000 resamples of sessions) only
   for groups of at least 12 sessions.
3. **Growth shape** per session by a fixed rule: a *step* if any request is at least
   1.5 times the previous one; otherwise *accelerating* if the average increase per
   request in the second half is at least 1.5 times that of the first half (or the first
   half did not grow and the second did); otherwise *steady*. Fewer than four requests
   cannot be split into halves, so the shape is undefined and reported as such.
4. **Routing triggers.** The four values below decide what is built next. They are
   *operational routing thresholds*. They are not empirical thresholds and they are not
   evidence that a mechanism matters. Three things are kept apart:
   - the **activation threshold** is the size at which a later experiment is worth
     running, and is what these are;
   - the **effect threshold** is the size of change that would matter to behaviour,
     which this study does not observe or estimate;
   - the **success criterion** belongs to the later experiment and is set in its own
     preregistration.

   They were chosen before any data as the size at which a design intervention could
   plausibly be worth testing. The values are:
   - **T1** run the tool-context family only if the median first-request tool-definition
     share, across sessions where definitions were observed, is at least **10%**.
     Otherwise the tool chapter's standing-cost claim is reduced to a description of this
     harness.
   - **T2** prioritise safe removal in the transformation family if the median share of
     redundant payload at the last request, across long sessions, is at least **10%**.
     Otherwise the pruning chapter becomes a conditional pass with the measured
     prevalence stated. (A long session is one meeting the S6 definition.)
   - **T3** prioritise externalise-and-recall if at least two sessions reach **60%** of the
     window, or any compaction record occurs. The primary basis is the provider-reported
     prompt tokens when at least three sessions have them, otherwise the bytes-based
     estimate; the word-based estimate is reported beside them and is not primary. The decisive value is
     the second-highest session, since two must reach the line. If neither, those chapters
     are framed as pressure-conditional.
   - **T4** run the paid cache probe only if the median stable-prefix fraction is at least
     **50%** in at least half of long sessions.

   For each trigger the report records: the metric, the observed value, the routing
   threshold, the status (`TRIGGERED`, `NOT_TRIGGERED`, or `NOT_EVALUABLE`), the distance
   from the threshold, the number of sessions used and unobserved, and the effect on the
   status of leaving out each session in turn. A value within a quarter of its threshold
   (relative) is labelled **borderline**, meaning worth review: 9.8% against 10% is a near
   miss, not an absence. For T3 the record states the basis it rests on, shows the other bases
   beside it, and is labelled borderline if any basis sits near the line, naming which one. `NOT_EVALUABLE` means fewer than three sessions could be used, and
   is not the same as not triggered. Reaching a trigger means "test this next"; missing it
   means "do not spend the effort yet". It never means the mechanism helps or does not
   matter. The measurement code is versioned before capture and is not tuned to cross a
   line.
5. **Shape catalogue.** For each shape seen in at least two sessions, write a shape card:
   its structure, sizes and positions, how often it occurs in the sample, and how to
   recreate it synthetically. The vocabulary is closed (repeated file material, repeated
   tool output, large standing tool schema, history-dominated growth, volatile early
   prefix, stale observation surviving, repeated re-read, large recoverable artifact,
   compaction or rewrite event, plus scope crossover and authority conflict, which the
   capture cannot see and which appear only when the author declares them). A card has no
   free-text field and states no conclusion: it does not say a shape is harmful or what
   should be done about it. These cards, not the raw sessions, are the input to the
   interference, transformation, externalisation, tool and representation families.
6. A reconciliation report (Q0).
7. Report descriptive facts only.

## Claims this result may support

- What real bundles in this sample contain, how they grow, where the same output repeats,
  what tool definitions and the system block cost, how stable the prefix is under a stated
  order, whether freshness evidence is observable, and how close sessions come to the
  window.
- That the capture instrument reconciles.
- That particular failure shapes occur, and how often in this sample.
- Which later experiments the routing triggers select.

## Claims this result may not support

- That pruning improves performance.
- That summaries preserve information.
- That any ordering is better.
- That retrieval should occur.
- That context caused any behavioural difference.
- That the shapes found are harmful; only that they exist.
- That a routing trigger being reached shows a mechanism matters, or that missing one
  shows it does not.
- Anything about prevalence beyond this developer, these repositories and this
  harness.
- Anything about cost, latency or cache behaviour, which the capture does not observe.

## Deviations

Changes made before any data existed, recorded so the difference from version 1 is
visible:

- H1 was narrowed from "byte-identical repeats of earlier material" to redundant
  payload within one request, because re-sent history would satisfy the earlier wording
  in nearly every session.
- The prefix is computed under a stated assumed order and labelled a proxy.
- Strata gained a fixed-precedence primary label with secondary tags, an
  `S0_unclassified` label, a recorded basis (observed, proxy or declared), and natural
  absence.
- The raw scan now separates credentials (exclude) from identifiers (recorded).
- A tool-definition share over a session that never exposed a definition is unobserved,
  not zero.
- The four values are unchanged and are now called routing triggers.
- A long session is defined as one meeting S6. Fewer than three usable sessions makes a
  trigger not evaluable.
- Growth shape is undefined below four requests.

Changes made after the calibration run (`specs/f1-calibration.md`), still before any data:

- The message shape, call identity, model-limit read and the token estimate were corrected from
  what the real harness produced. Strata S2, S3, S4 and S8 are derived from observed call
  arguments, no longer proxies.
- Provider usage, cost, latency and cache reads are joined from the harness's own record and are
  JOINED, not unobserved. T3 prefers the provider-reported prompt tokens.
- Window pressure is reported three ways and never merged; the input limit is used when there is
  one.
- Redundant payload has a 32-byte floor. Carry-over is matched part for part against the previous
  request, so a repeated read is new material rather than carry-over.
- Reasoning is its own category.
- The adapter's sequence counter is persisted. A session with an ordering-failure marker or a
  message in an unrecognised shape is incomplete.
- The sidecar records whether other context-modifying plugins were active.
- The session index is the name for what earlier drafts called the ledger.
