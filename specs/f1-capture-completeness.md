# F1 capture completeness and observability

Status: draft, tracks the F1 preregistration. Nothing has been captured.

This specification says what the F1 capture can and cannot see, when a session counts as a
whole observation, and how the difference between *unobserved* and *zero* is carried into
every aggregate. The code is `corpus/completeness.py`; the table below is checked against it
by a test, so the two cannot drift.

## Statuses

| Status | Meaning |
|---|---|
| OBSERVED | read directly from the captured record |
| DERIVED | computed deterministically from observed material |
| PROXY | a stand-in for the thing wanted; named as a stand-in wherever it is used |
| DECLARED | supplied by the author in the sidecar; never inferred from text |
| UNOBSERVED | the capture cannot see it; never zero, never absent |

## Observability matrix

| Quantity | Status | Basis |
|---|---|---|
| `rendered_input_bytes` | OBSERVED | bytes of system, message and tool-definition text at the harness's model-context boundary; not the provider's final rendered prompt |
| `rendered_input_tokens` | DERIVED | an estimate (word count times 1.3), labelled approximate everywhere; the provider's tokeniser is not applied |
| `category_composition` | DERIVED | grouping of observed parts by their recorded kind |
| `tool_definitions` | OBSERVED | one item per exposed tool: description plus input schema |
| `tool_definition_stability` | DERIVED | byte identity of each definition across requests |
| `tool_result_bytes_and_growth` | OBSERVED | completed tool-result parts as re-sent |
| `tool_name_per_result` | OBSERVED | recorded on the tool part |
| `tool_call_arguments` | UNOBSERVED | only the result and its title are captured |
| `tool_call_identity` | PROXY | tool name plus result title; a title may be path-like, so it is used locally and never leaves the machine |
| `carry_over` | DERIVED | a part re-sent unchanged from an earlier request in the session |
| `redundant_payload` | DERIVED | the same tool-output body more than once inside one request, header removed |
| `stable_prefix` | PROXY | longest run of identical leading parts between consecutive requests, under an ASSUMED render order (tool definitions, system, messages); the provider's actual order is not observed |
| `render_order` | UNOBSERVED | how the provider lays the parts out before the model sees them |
| `standing_instruction_split` | UNOBSERVED | system entries are not attributed to harness, project or user; only their total is seen |
| `history_window_distance` | OBSERVED | rendered size against model_limits.context when the record carries it |
| `compaction_record` | OBSERVED | a record whose request_kind is compaction |
| `history_rewrite` | DERIVED | an earlier part changed or disappeared between consecutive requests |
| `project_instruction_origin` | DECLARED | operator sidecar; origin is never inferred |
| `same_call_different_bytes` | PROXY | same tool and title returning different bytes; without arguments this can also be two different calls that share a title |
| `repository_state_or_version` | UNOBSERVED | the working tree is not part of the capture |
| `session_outcome` | DECLARED | sidecar, closed vocabulary; a fact about the work |
| `provider_cache_behaviour` | UNOBSERVED | not exposed at the harness boundary |
| `provider_added_material` | UNOBSERVED | added after the observation point |
| `provider_usage_and_cost` | UNOBSERVED | not part of the record |
| `latency` | UNOBSERVED | not part of the record |
| `hidden_reasoning` | UNOBSERVED | only reasoning parts the harness re-sends are visible |

## What counts as a complete session

A session is complete when its records, taken alone, are a whole observation of it:

- every record validates against the V2 schema, and its integrity value recomputes;
- all records share one non-empty session identity;
- sequence numbers are 1..N, each once, across every request kind. The adapter keeps one
  counter per session, incremented for every kind, so a repeated 1 means the harness
  process restarted mid-session and a gap means a record was lost;
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

Complete means *the observer records all arrived*. It does not mean the provider's final
prompt was seen, and it does not mean the work was representative.

## UNOBSERVED in aggregates

A quantity that is unobserved for a session is recorded as the string `UNOBSERVED` in that
session's derivative and is **not** entered into any median, share or count as zero.
Aggregates state two numbers: sessions used and sessions unobserved. A routing trigger with
fewer than three usable sessions is `NOT_EVALUABLE`, which is a different result from not
triggered.

Two rules where a value could be mistaken for zero:

- **Tool definitions.** If no record in a session carries any tool definition, the
  tool-definition share and tool count are `UNOBSERVED`. A harness that has no tools and a
  hook that fails to expose them cannot be told apart from the record.
- **Window distance.** If a record carries no model limit, the window fraction is
  `UNOBSERVED`. The fraction itself uses the labelled token estimate, which is an
  approximation and can be wrong by more than the borderline band; a value near 60% is
  reviewed, not settled.

A real zero is kept: a session with no redundant payload has `0`, because the capture did
observe that there was none.

## Assumed render order

The stable prefix depends on the order the provider lays parts out, which is not observed.
The measurement assumes tool definitions, then system, then messages, and reports the
prefix as a PROXY under that assumption. The harness ingester orders system, messages,
tools; the prefix analysis does not use that order. Changing the assumed order is a
versioned change to the measurement.
