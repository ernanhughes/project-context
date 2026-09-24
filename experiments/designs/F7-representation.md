# F7 — Representation (design)

Status: design only. Supports the chapter on representation, and the narrow question
of marking epistemic status.

**Tests:** a mechanism (does the form of the same information change use and cost).

## Question

Holding the facts constant, does presenting them as prose, a table, a typed record or a
compact structure change what a reader does with them, and what it costs?

## The rule that makes it valid

**The facts must be identical in every condition.** Each fixture starts from one
canonical record. Deterministic renderers produce each form with no model in the
loop, and a fact manifest checks that every required fact and relation survives every
renderer. A form that cannot carry a fixture's facts leaves that fixture rather than
faking equivalence.

## Factors

| Factor | Levels |
|---|---|
| Form | prose, table, typed record (labelled fields), compact key-value |
| Operation | lookup, compare, filter or aggregate, follow a relation, explain a rationale, apply an update |
| Size | small, medium, large |
| Encoding (a second, separate experiment) | the same record as JSON, XML, key-value, CSV |

Form and encoding are never varied together: changing organisation and changing
syntax answer different questions.

## Epistemic-status arm

One small factor, kept apart: the same claim rendered as a plain fact, or with its
status and evidence attached ("unverified, based on observation X"). It tests whether
a persisted hypothesis without its status is treated as fact.

## Traps that keep it honest

Near-identical identifiers with leading zeros; unknown against zero against not-run;
relation direction both ways; the same fact from two sources; decisions with the same
outcome but different reasons, so a gist-only form fails the "why" question it
deserves to fail.

## Measurements

Task success per operation (never averaged across operations); rendered tokens per
form, separately; parseability on its own ledger; edit locality for updates (fields
changed, not characters). Failure state per failure.

## Size

At least 12 fact sets × 6 operations × 4 forms × 2 sizes × 2 readers: about 1,200
local calls, plus the status arm.

## Null and negative outcomes

- **Forms do not differ for capable readers:** the chapter says so, and the cost
  difference is the finding.
- **Each form wins its own operation, none overall:** this is the predicted result;
  the chapter states the operation-relative rule.
- **A compact form loses exactness:** noted as the price of its tokens.

## What would remove or merge the chapter

If no form differs on any operation for either reader, the chapter reduces to the
external evidence plus a token-cost table.

## Depends on

The shape cards for realistic sizes and mixes (soft).
