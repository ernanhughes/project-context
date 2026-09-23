# Stage 2 report — ecological corpus and prevalence baseline

## Baseline

- Stage 0 SHA: `dccc796`. Stage 1 state: committed locally (dirty at
  Stage 2 start: none — tree was clean).
- Adapter: `integrations/opencode` 0.1.0; OpenCode 1.18.27 (V1);
  `@opencode-ai/plugin` 1.18.27 exact.
- Boundary throughout: `opencode.v1.pre_dispatch_partial` (partial V1
  observation, never the assembled provider request).

## Campaign tooling

- `corpus/campaigns/` committed manifests (identity, versions, counts,
  exclusion ledger; no paths, no content, no session ids).
- Local-only index `.local/corpus/index.json` maps opaque local ids to
  original session refs; never committed.
- CLI: `corpus campaign create/status/add`, `corpus quality`,
  `corpus prevalence [--campaign] [--export] [--run-id --runs-dir]`.
- Session identity: shared provenance `session_ref`; unlinked records
  never merged. Completeness: no skipped lines in contributing files,
  no attributed invalid records, ≥1 validated record (observer-complete
  ≠ provider-complete, documented in protocol).
- Exclusion reasons closed set; ledger deterministic; synthetic evidence
  refused with reason, never counted.

## Corpus status

- Target sessions: 8–12. Genuine captured sessions: **0**.
- No local spool, raw-corpus, or private-runs content exists in this
  environment. No real OpenCode work was performed or manufactured.
- Outcome per protocol: **campaign readiness** (tooling complete and
  exercised on synthetic spools), analysis status **not run on genuine
  data**. The E2E smoke used hand-built synthetic spools only.

## Capture quality

No genuine captures, so quality reporting is exercised, not populated:
hook-family union, version pairs, completeness counts, parse warnings,
exclusion ledger, and privacy/publication statuses all render from the
campaign file. Compaction observation reads False by construction on
the Stage 1 boundary.

## Prevalence questions (pre-registered)

1. How quickly does observed context grow within realistic sessions?
2. Which observed categories dominate context volume?
3. How much byte-identical repetition exists?
4. How stable are consecutive context prefixes?
5. Where does structural divergence usually occur?
6. What share of observed context comes from tool results?
7. How much variation exists between sessions?
8. How much theoretically interesting context stays unobservable (V1)?

Predictions (qualitative, no thresholds): H1 tool results dominate
growth in tool-heavy sessions; H2 consecutive invocations share
substantial structural prefixes; H3 repetition is highly skewed across
sessions.

## Results

None on genuine data. The machinery was verified on synthetic spools:
session/invocation weighting diverges as designed, exclusions fire with
reasons, exports relabel and gate correctly.

## Unobservable categories (V1, recorded)

Tool definitions, generation settings, provider usage and cost,
transport detail, assembled provider request, compaction input/output.
Tool definitions are reported UNOBSERVED, never zero.

## Sampling limitations

~10 sessions characterise workload shape for fixture design; they do
not estimate population parameters. Distributions report min/median/max
below n=20. Session-weighted and invocation-weighted views are both
reported with denominators stated.

## Book implications (no chapters rewritten)

- Supported so far: none empirically; the instrument exists and the
  collection contract is fixed.
- Challenged: none yet; nothing measured.
- Unanswerable at V1: tool-definition standing cost (Ch17 input),
  provider token/cache behaviour (Ch9 economics on real traffic),
  assembled-request ordering effects (Ch6 on real bundles).
- New experiment priorities: once sessions exist, repetition prevalence
  feeds Ch10 fixture realism; prefix-stability feeds Ch9 timing design;
  growth shapes feed Ch4 budget calibration.

## Opportunity map (research prioritisation, no mechanisms)

Observed repetition → Ch10 candidate prevalence. Prefix stability →
Ch9 experiments. Old-history accumulation → Ch11/12 relevance. Large
tool results → Ch17 design. Rapid growth → Ch4 pressure. None of these
activates its mechanism; prevalence is opportunity, fixtures prove
safety.

## Instrumentation gaps (ranked by experimental blocking power)

1. Unified assembled request (blocks Ch6/Ch9 real-traffic measurement).
2. Tool-definition bytes (blocks Ch17 standing-cost measurement).
3. Provider usage/cache telemetry (blocks Ch9 economic closure).
4. Response-side observation (blocks latency/outcome linkage).
5. Compaction hook coverage (blocks Ch11 real-trace analysis).
None may be bypassed outside the public API; a V2 adapter is the
honest path to 1–3 if the environment upgrades.

## Privacy status

No raw real corpus exists or was committed. Spool, index, and run
directories are git-ignored and absent. Export gate adversarially
tested. Publication gate unchanged and passing.

## Validation

- 47 Python tests pass; 10 TS tests pass; tsc, ruff check/format,
  prettier clean; `git diff --check` clean in both repos.
- New coverage: synthetic exclusion, unique-session counting, corrupt
  exclusion with reason, observed-zero vs UNOBSERVED, both weighting
  views, cross-session prefix refusal, exact-identity repetition,
  export cleanliness and re-keying, path/hash absence, under-target
  readiness, deterministic ledger, run version stamping, publication
  gate, process-safety source scan, no-intervention scan.
- E2E exercised: campaign create/add/status/quality, prevalence with
  campaign labelling, gated export, frozen local run — on synthetic
  spools in scratch directories only.
- Book repository untouched. No model called. No OpenCode process
  managed. No push from either repository.

## Recommended Stage 3

Do not build a mechanism yet. The next implementation step is
contingent on the first genuine sessions: run the collection campaign
during ordinary work, then execute the first ecological baseline and
let its distributions arbitrate between outcome A (repetition-led →
Ch10 controlled experiment), B (history-led → Ch11/12), C
(artifact-led → Ch13), or D (gaps dominate → V2 adapter). If genuine
sessions remain at zero, the correct action is continued collection
readiness, not invention. On the book side, Chapter 13 may proceed
independently: externalisation needs no prevalence result that Stage 2
was supposed to supply, and the anchor/pointer firewall is already
frozen.
