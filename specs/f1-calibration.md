# F1 instrument calibration

Status: done once, before any ecological capture. **Nothing here is evidence and nothing here
feeds a result.** The calibration session is excluded from the corpus by construction: it was
captured into its own spool, its session id is on a registry the ecological index consults, and
the calibration index cannot be opened as the corpus.

## What was done

One deliberate tool-testing session in a throwaway repository (a two-function Python module with
one wrong operator and a five-line test), run through the real OpenCode 2.0.16 with the capture
adapter loaded, against an isolated harness configuration and data directory, and a local model.
The session was continued several times, each time in a new harness process, so that it crossed
real restarts. A few of those turns were used to probe what the plugin context exposes.

Several earlier attempts failed before a valid capture: the local model's default context was
smaller than the harness's own prompt, and the plugin did not load until it was placed where the
harness discovers plugins. Both are set-up facts, not findings about the capture.

## What the design assumed, and what was found

| Assumption | Result |
|---|---|
| The capture hook fires and writes well-formed V2 records | **Confirmed.** Sixteen records, integrity values recompute |
| Messages are `{info, parts}` | **Refuted.** Messages are `{role, content: [parts]}`. A part is `text`, `reasoning`, `tool-call` (id, name, input) or `tool-result` (id, name, result). Tool results are their own `tool`-role messages. The synthetic fixtures had the wrong shape and now match the real one |
| Tool-call arguments are not captured | **Refuted.** Each `tool-call` part carries its `input`. A call's identity is its tool and arguments |
| Tool results carry a header and a title | **Refuted.** They carry the tool name and the id of the call they answer, and no title |
| The shell tool is called `bash` | **Refuted.** The tool names are `edit`, `execute`, `glob`, `grep`, `question`, `read`, `shell`, `skill`, `subagent`, `webfetch`, `websearch`, `write` |
| The model limit is read with `ctx.model.get` | **Refuted.** There is no `get`. The adapter's read always failed silently, so every limit was null. `ctx.model.list()` returns `{location, data}` with one entry per model, each with `providerID`, `modelID` and a `limit` (`context`, sometimes `input`, `output`). Fixed |
| The model limit is always available | **Refuted.** A model configured without a limit has none. A limit set in the configuration was observed. Registered hosted models carry their own |
| Provider usage, cost and latency are unobservable | **Refuted for the harness's own record.** The harness stores, per assistant message, provider-reported input, output, reasoning and cache read and write tokens, cost, and start and completion times. They are read after the fact, read-only, from one table. This is JOINED, not OBSERVED at the capture boundary |
| Sequence numbers restart when the harness restarts | **Confirmed for the old counter, fixed.** The counter is now persisted per session. Across many separate harness processes the numbers ran 1..16 with no repeat and no gap |
| Reasoning parts are dropped from history between requests | **Not the case here.** They were re-sent unchanged, so no history rewrite appeared |
| `words × 1.3` is a usable token estimate | **Poor on this content.** Against provider-reported prompt tokens it was 33% to 39% low over 16 requests. Bytes divided by four was 2% to 9% low. One session, one model, mostly English and JSON: this says the word estimate should not be the primary figure, not how either behaves in general |
| Sub-agents are visible | **Not exercised.** A `subagent` tool is exposed and the harness database links child sessions to parents, but nothing was run that used it |

## The environment is not the harness default

The author's normal harness configuration loads other plugins alongside the capture adapter, at
least one of which can add retrieved material to the context. The capture position relative to
such a plugin's changes is not established: the observer may see the context before or after they
are applied. Two consequences:

- F1 sessions are not "the harness as shipped". Each session's index row records, from the
  sidecar, whether other context-modifying plugins were active, so a session is never presented
  as a plain baseline when it was not.
- Whether the capture sees what such a plugin adds has to be settled before capture one. It was
  not tested here, because running that plugin would have written to its own persistent store.

An older copy of the capture adapter is installed in the author's global plugin directory. It has
the wrong limit call and the in-memory counter. It has to be replaced by the current adapter before
any ecological capture; that changes global configuration and needs the author's approval.

## Consequences applied

- The analysis reads the real message shape; a record in any other shape is refused as incomplete
  (`unrecognised_message_shape`) rather than analysed as if it were understood.
- Call identity, edited files and test runs come from observed arguments (derived), not from
  titles. Strata S2, S3, S4 and S8 are now derived rather than proxy.
- Window pressure is reported three ways and never merged: provider-reported prompt tokens over
  the input limit (else context limit), a bytes-based estimate, and the word-based estimate.
- The adapter persists its sequence counter and writes a control record if it cannot vouch for its
  ordering.
- The observability matrix gained a JOINED status and lost three UNOBSERVED entries.

## What was not checked

- A compaction, a title or a generate request, and a session crossing a UTC midnight, none of which
  occurred.
- Behaviour with a hosted model. Its limits are in the registry; the read path was verified with a
  configured limit, and the registry shape with hosted entries, but no hosted model was called.
- Whether the harness usage record stays one row per primary request when a request fails or is
  retried. Usage is joined only when the counts agree, and otherwise stays unobserved.
