# F1 capture completeness and observability

Status: draft, tracks the F1 preregistration. Nothing has been captured. Revised after the
calibration run (`specs/f1-calibration.md`), which corrected several assumptions.

This specification says what the F1 capture can and cannot see, when a session counts as a
whole observation, and how the difference between *unobserved* and *zero* is carried into
every aggregate. The code is `corpus/completeness.py`; the table below is checked against it
by a test, so the two cannot drift.

## Statuses

| Status | Meaning |
|---|---|
| OBSERVED | read directly from the captured record |
| DERIVED | computed deterministically from observed material |
| JOINED | read from the harness's own local record and joined to the session afterwards; read-only; not seen at the capture boundary |
| PROXY | a stand-in for the thing wanted; named as a stand-in wherever it is used |
| DECLARED | supplied by the author in the sidecar; never inferred from text |
| UNOBSERVED | the capture cannot see it; never zero, never absent |

## Observability matrix

| Quantity | Status | Basis |
|---|---|---|
| `rendered_input_bytes` | OBSERVED | bytes of system, message and tool-definition text at the model-context boundary; not the provider's final rendered prompt |
| `rendered_input_token_estimates` | DERIVED | two independent estimates, bytes divided by four and words times 1.3; neither is a tokeniser count and they are never merged |
| `category_composition` | DERIVED | grouping of observed parts by their recorded type and role |
| `tool_definitions` | OBSERVED | one item per exposed tool: description plus input schema |
| `tool_definition_stability` | DERIVED | byte identity of each definition across requests |
| `tool_result_bytes_and_growth` | OBSERVED | tool-result parts as re-sent |
| `tool_name_per_result` | OBSERVED | recorded on the tool-result part |
| `tool_call_arguments` | OBSERVED | the input of each tool-call part; used locally, never exported |
| `tool_call_identity` | DERIVED | tool name plus canonical arguments; two calls with equal identity ask the same thing |
| `carry_over` | DERIVED | a part re-sent unchanged from an earlier request in the session |
| `redundant_payload` | DERIVED | the same tool-output body (at least 32 bytes) more than once inside one request |
| `stable_prefix` | PROXY | longest run of identical leading parts between consecutive requests, under an ASSUMED render order (tool definitions, system, messages); the provider's actual order is not observed |
| `render_order` | UNOBSERVED | how the provider lays the parts out before the model sees them |
| `standing_instruction_split` | UNOBSERVED | system entries are not attributed to harness, project or user; only their total is seen |
| `model_limit` | OBSERVED | context, input and output limits from the harness's model registry when it knows the model; absent for a model configured without one |
| `window_pressure_measured` | JOINED | provider-reported prompt tokens (fresh input plus cache reads and writes) divided by the input limit if there is one, else the context limit |
| `window_pressure_estimates` | DERIVED | the same fraction from each of the two token estimates, kept beside the measured one |
| `provider_reported_tokens` | JOINED | per request, from the harness database; joined by order and only when counts agree |
| `provider_reported_cache_tokens` | JOINED | cache read and write tokens as the provider reported them; says what was reused, not why |
| `provider_cost` | JOINED | per request, as recorded by the harness |
| `latency` | JOINED | harness-recorded start to completion of the request |
| `compaction_record` | OBSERVED | a record whose request_kind is compaction |
| `history_rewrite` | DERIVED | an earlier message part changed or disappeared between consecutive requests |
| `project_instruction_origin` | DECLARED | operator sidecar; origin is never inferred |
| `same_call_different_bytes` | DERIVED | one call identity whose results differ in bytes. A re-run whose state changed is included, so this shows that an older result survives beside a newer one, not that the older one is wrong |
| `repository_state_or_version` | UNOBSERVED | the working tree is not part of the capture |
| `session_outcome` | DECLARED | sidecar, closed vocabulary; a fact about the work |
| `provider_cache_decisions` | UNOBSERVED | why the provider did or did not reuse a prefix |
| `provider_added_material` | UNOBSERVED | added after the observation point |
| `reasoning_sent_to_provider` | UNOBSERVED | reasoning parts are in the message list; whether the provider receives them is not seen |
| `subagent_relations` | UNOBSERVED | a subagent tool exists and the harness database links child sessions to parents, but that link is not read here |

## What counts as a complete session

A session is complete when its records, taken alone, are a whole observation of it:

- every record validates against the V2 schema, and its integrity value recomputes;
- every message has the shape the analysis understands (a role and a list of typed parts). A
  message in any other shape is refused, not misread;
- all records share one non-empty session identity;
- sequence numbers are 1..N, each once, across every request kind. The adapter keeps one
  counter per session, incremented for every kind and **persisted across harness restarts**, so
  a restart no longer resets it. A gap means a record was lost (a crash between reserving a
  number and writing the record leaves one); a repeated number would mean the state was lost;
- the adapter wrote no ordering-failure marker for the session. If its persisted state was
  damaged and the spool could not confirm the ordering, it says so in a control record and the
  session is incomplete even when the numbers look whole;
- no line of the spool was skipped as malformed;
- at least one primary (`context`) request exists. Compaction, generate and title records
  are counted separately and never merged into the primary series.

Reasons a session is incomplete (closed list):

- `no_records`
- `skipped_lines`
- `invalid_record`
- `integrity_mismatch`
- `mixed_or_missing_session`
- `sequence_gap`
- `sequence_duplicate_or_restart`
- `first_record_not_sequence_one`
- `no_primary_request`
- `ordering_state_lost`
- `unrecognised_message_shape`

Complete means *the observer records all arrived*. It does not mean the provider's final
prompt was seen, and it does not mean the work was representative.

## UNOBSERVED in aggregates

A quantity that is unobserved for a session is recorded as the string `UNOBSERVED` in that
session's derivative and is **not** entered into any median, share or count as zero.
Aggregates state two numbers: sessions used and sessions unobserved. A routing trigger with
fewer than three usable sessions is `NOT_EVALUABLE`, which is a different result from not
triggered.

Rules where a value could be mistaken for zero:

- **Tool definitions.** If no record in a session carries any tool definition, the
  tool-definition share and tool count are `UNOBSERVED`. A harness that has no tools and a
  hook that fails to expose them cannot be told apart from the record.
- **Window pressure.** If a record carries no model limit, every window fraction is
  `UNOBSERVED`. The harness registry knows the limits of registered models; a model configured
  without a limit has none.
- **Usage.** If the harness's own usage record is not joined, or its count of assistant
  messages differs from the count of primary requests, measured tokens, cost, latency and cache
  reads are `UNOBSERVED`. Nothing is guessed.

A real zero is kept: a session with no redundant payload has `0`, because the capture did
observe that there was none.

## Window pressure is reported three ways

For each request the window fraction is reported from **provider-reported prompt tokens** (when
usage is joined), from a **bytes-based estimate** (bytes divided by four, rounded up), and from
a **word-based estimate** (words times 1.3). They are three descriptive measurements and are
never merged into one token count. The window is the model's input limit when the registry
records one, else its context limit. The measured figure is preferred wherever it exists; the
estimates are kept beside it for comparison and for sessions where usage cannot be joined.

## Assumed render order

The stable prefix depends on the order the provider lays parts out, which is not observed.
The measurement assumes tool definitions, then system, then messages, and reports the
prefix as a PROXY under that assumption. The older ingester orders system, messages, tools; the
prefix analysis does not use that order. Changing the assumed order is a versioned change to
the measurement. Provider-reported cache reads are recorded beside the proxy: they say how much
of the prompt the provider reused, not why, and the proxy is never used to conclude anything
about provider caching by itself.
