"""F1 structural analysis: from one session's raw records to a content-free derivative.

Everything here is deterministic and exact: byte identity, exact identity after
whitespace normalisation, and tool-call identity. There are no embeddings and no model
judging similarity. The output (`analyse_session`) holds numbers, closed-vocabulary
labels and the string ``UNOBSERVED``; it never holds text, paths, arguments, identifiers,
hashes or timestamps. The raw text exists only inside this module's call frames.

The record shape is the one OpenCode 2.0.16 really produces, established by the
calibration run (`specs/f1-calibration.md`): messages are `{role, content: [parts]}` and a
part is `text`, `reasoning`, `tool-call` (name, id, input) or `tool-result` (name, id,
result). Tool-call arguments **are** observed, so a call's identity is its tool plus its
arguments. A record in any other shape is not analysed silently: the completeness check
refuses it.

Three ideas are kept apart on purpose:

* **carry-over**: a part re-sent unchanged from an earlier request. Expected; a session's
  history is re-sent every turn. Never called redundancy.
* **redundant payload**: the same tool-output body appearing more than once inside a
  single request. This is what H1 measures.
* **prefix**: computed under an assumed render order, and reported as a proxy because the
  provider's real order is not observed.

Window pressure is reported three ways and never merged into one number: what the provider
measured (when the harness's own record is joined), a bytes-based estimate, and a
word-based estimate.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from project_context.corpus.completeness import UNOBSERVED
from project_context.domain.items import estimate_tokens

ANALYSIS_VERSION = "1.1.0"
L1_SCHEMA = "project_context.f1_structure.v1"

CATEGORIES = (
    "tool_definition",
    "system",
    "user",
    "assistant",
    "reasoning",
    "tool_call",
    "tool_result",
    "other",
)

# The order the parts are assumed to be laid out for the prefix measurement. Anthropic's
# documented order is tools, system, messages; other providers differ, and none of this
# is observed. Reported as an assumption wherever the prefix appears.
ASSUMED_RENDER_ORDER = ("tool_definition", "system", "messages")

# Tool names seen in the calibration run: edit, execute, glob, grep, question, read, shell,
# skill, subagent, webfetch, websearch, write. The sets below are closed lists over those
# names (plus a few common aliases); anything else is "other tool".
FILE_READ_TOOLS = frozenset({"read", "view", "cat", "open"})
EDIT_TOOLS = frozenset({"edit", "write", "patch", "multiedit", "apply_patch"})
SHELL_TOOLS = frozenset({"shell", "execute", "bash"})
TEST_COMMAND = re.compile(
    r"\b(pytest|py\.test|npm (?:run )?test|yarn test|pnpm test|jest|vitest|mocha|"
    r"cargo test|go test|dotnet test|mvn test|gradle test|rspec|phpunit|"
    r"python[0-9.]* [\w./\\-]*test[\w./\\-]*\.py)\b",
    re.IGNORECASE,
)

# A tool output shorter than this is not counted as redundant payload. "ok" twice is not
# a finding. Fixed before any data.
MIN_PAYLOAD_BYTES = 32


def r6(x: float) -> float:
    return round(float(x), 6)


@dataclass(frozen=True)
class Part:
    """One rendered part. Local to this module; never serialised."""

    category: str
    text: str
    body: str | None = None  # tool-result output
    tool: str | None = None
    identity: str | None = None  # tool plus canonical arguments; local only
    target: str | None = None  # file path for an edit call; local only
    command: str | None = None  # shell command for a shell call; local only

    @property
    def nbytes(self) -> int:
        return len(self.text.encode("utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _result_text(result: Any) -> str:
    """The text a tool result carries: a string, or the text of a list of content items."""
    value = result.get("value") if isinstance(result, dict) else result
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            item["text"]
            if isinstance(item, dict) and isinstance(item.get("text"), str)
            else _canonical(item)
            for item in value
        )
    return _canonical(value)


def extract_request(record: dict[str, Any]) -> list[Part]:
    """Parts of one request, in the assumed render order.

    Tool definitions first, then system entries, then message parts in their recorded order.
    """
    definitions: list[Part] = []
    for name in sorted(record.get("tools", {})):
        definition = record["tools"][name]
        body = {"tool": name, **{k: definition[k] for k in sorted(definition)}}
        definitions.append(Part("tool_definition", json.dumps(body, sort_keys=True), tool=name))

    system = [
        Part("system", entry["text"] if isinstance(entry.get("text"), str) else _canonical(entry))
        for entry in record.get("system", [])
    ]

    calls: dict[str, str] = {}  # call id -> identity, so a result knows which call it answers
    for message in record.get("messages", []):
        for part in message.get("content", []):
            if part.get("type") == "tool-call" and isinstance(part.get("id"), str):
                calls[part["id"]] = f"{part.get('name')} {_canonical(part.get('input'))}"

    messages: list[Part] = []
    for message in record.get("messages", []):
        role = message.get("role")
        for part in message.get("content", []):
            kind = part.get("type")
            if kind == "text":
                category = {"user": "user", "assistant": "assistant"}.get(role, "other")
                messages.append(Part(category, str(part.get("text", ""))))
            elif kind == "reasoning":
                messages.append(Part("reasoning", str(part.get("text", ""))))
            elif kind == "tool-call":
                name, args = part.get("name"), part.get("input")
                target = command = None
                if isinstance(args, dict):
                    target = next(
                        (
                            args[k]
                            for k in ("path", "filePath", "file_path")
                            if isinstance(args.get(k), str)
                        ),
                        None,
                    )
                    command = args["command"] if isinstance(args.get("command"), str) else None
                messages.append(
                    Part(
                        "tool_call",
                        f"{name} {_canonical(args)}",
                        tool=name,
                        identity=f"{name} {_canonical(args)}",
                        target=target,
                        command=command,
                    )
                )
            elif kind == "tool-result":
                body = _result_text(part.get("result"))
                identity = calls.get(part.get("id")) if isinstance(part.get("id"), str) else None
                messages.append(
                    Part("tool_result", body, body=body, tool=part.get("name"), identity=identity)
                )
            else:
                messages.append(Part("other", _canonical(part)))
    return definitions + system + messages


def _carry_over(earlier: list[Part] | None, later: list[Part]) -> int:
    """Bytes of `later` that the previous request already held, matched part for part.

    A part is carried over when the previous request had an unmatched part with identical
    text. A second copy of something the previous request held once is new material, not
    carry-over: that is exactly what a repeated read looks like.
    """
    if earlier is None:
        return 0
    available = Counter(p.text for p in earlier)
    carried = 0
    for part in later:
        if available[part.text] > 0:
            available[part.text] -= 1
            carried += part.nbytes
    return carried


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _dedupe_stats(parts: list[Part]) -> dict[str, int]:
    """Repeats inside one request. Counts the second and later occurrences only."""
    seen_bodies: set[str] = set()
    seen_norm: set[str] = set()
    seen_texts: set[str] = set()
    out: Counter[str] = Counter()
    for part in parts:
        if part.text in seen_texts:
            out["duplicate_part_bytes"] += part.nbytes
        seen_texts.add(part.text)
        if part.category != "tool_result" or not part.body or part.nbytes < MIN_PAYLOAD_BYTES:
            continue
        if part.body in seen_bodies:
            out["redundant_payload_bytes"] += part.nbytes
            out["redundant_payload_parts"] += 1
            if part.tool in FILE_READ_TOOLS:
                out["redundant_file_bytes"] += part.nbytes
        elif _normalise(part.body) in seen_norm:
            out["normalised_only_redundant_bytes"] += part.nbytes
        seen_bodies.add(part.body)
        seen_norm.add(_normalise(part.body))
    return dict(out)


def _prefix(earlier: list[Part], later: list[Part]) -> dict[str, Any]:
    shared = 0
    for a, b in zip(earlier, later):
        if a.text != b.text:
            break
        shared += 1
    shared_bytes = sum(p.nbytes for p in later[:shared])
    total = sum(p.nbytes for p in later)
    if shared >= len(earlier) and shared <= len(later):
        divergence = "append_only" if shared < len(later) else "identical"
    else:
        divergence = later[shared].category if shared < len(later) else "shorter"
    return {
        "parts": shared,
        "bytes": shared_bytes,
        "fraction": r6(shared_bytes / total) if total else 0.0,
        "first_divergence": divergence,
        "divergence_position": r6(shared / len(later)) if later else 0.0,
    }


def _messages(parts: list[Part]) -> list[Part]:
    return [p for p in parts if p.category not in ("tool_definition", "system")]


def _rewrite(earlier: list[Part], later: list[Part]) -> bool:
    """History rewritten: an earlier message part changed or disappeared.

    Independent of render order. Growth by appending is not a rewrite.
    """
    a, b = _messages(earlier), _messages(later)
    return not (len(b) >= len(a) and all(x.text == y.text for x, y in zip(a, b)))


def _limit(record: dict[str, Any]) -> tuple[int | None, str]:
    """The window a request is measured against, and which limit it is.

    The harness records a context limit and sometimes a smaller input limit. Pressure is
    about what the prompt must fit inside, so the input limit is used when there is one.
    """
    limits = record.get("model_limits")
    if not isinstance(limits, dict):
        return None, UNOBSERVED
    for key in ("input", "context"):
        value = limits.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value, key
    return None, UNOBSERVED


def _fraction(tokens: float, limit: int | None) -> float | str:
    return UNOBSERVED if limit is None else r6(tokens / limit)


def _duration_minutes(records: list[dict[str, Any]]) -> float | str:
    try:
        stamps = [
            datetime.fromisoformat(str(r["captured_at"]).replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
            for r in records
        ]
    except (KeyError, ValueError):
        return UNOBSERVED
    if len(stamps) < 2:
        return UNOBSERVED
    return r6((max(stamps) - min(stamps)).total_seconds() / 60.0)


def growth_shape(sizes: list[int]) -> str:
    """Fixed rule from the preregistration.

    step: any request at least 1.5 times the previous one. Otherwise accelerating if the
    mean increase per request in the second half is at least 1.5 times the first half's
    (or the first half did not grow and the second did). Otherwise steady. Fewer than four
    requests cannot be split into halves, so the shape is undefined.
    """
    if len(sizes) < 4:
        return "undefined_too_few_requests"
    if any(later >= 1.5 * earlier for earlier, later in zip(sizes, sizes[1:]) if earlier > 0):
        return "step"
    deltas = [b - a for a, b in zip(sizes, sizes[1:])]
    mid = len(deltas) // 2
    first, second = statistics.fmean(deltas[:mid]), statistics.fmean(deltas[mid:])
    if first > 0:
        return "accelerating" if second >= 1.5 * first else "steady"
    return "accelerating" if second > 0 else "steady"


def _maximum(values: list[Any]) -> Any:
    observed = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return max(observed) if observed else UNOBSERVED


def analyse_session(
    records: list[dict[str, Any]],
    *,
    declared: dict[str, Any] | None = None,
    usage: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The L1 structural derivative of one session's *primary* requests.

    `declared` is the sidecar (closed vocabulary), never inferred from the capture. `usage`
    is the harness's own per-request usage record (see `corpus/usage.py`), one entry per
    primary request in order, or None. It is only used when its length matches the number of
    primary requests; a mismatch is recorded and nothing is guessed.
    """
    declared = declared or {}
    primary = sorted(
        (r for r in records if r.get("request_kind") == "context"),
        key=lambda r: int(r["invocation_sequence"]),
    )
    other_kinds = Counter(r.get("request_kind") for r in records if r not in primary)
    if usage is None:
        usage_join = UNOBSERVED
        aligned: list[dict[str, Any]] | None = None
    elif len(usage) == len(primary):
        usage_join, aligned = "aligned", usage
    else:
        usage_join, aligned = "count_mismatch", None

    requests: list[dict[str, Any]] = []
    prior_parts: list[Part] | None = None
    tools_ever_seen = any(bool(r.get("tools")) for r in primary)
    identity_bodies: dict[str, set[str]] = {}
    rewrite_events = 0
    limit_kinds: set[str] = set()

    for index, record in enumerate(primary, start=1):
        parts = extract_request(record)
        total = sum(p.nbytes for p in parts)
        by_cat: Counter[str] = Counter()
        count_cat: Counter[str] = Counter()
        for p in parts:
            by_cat[p.category] += p.nbytes
            count_cat[p.category] += 1
        est_words = sum(estimate_tokens(p.text)[0] for p in parts)
        est_bytes = -(-total // 4)  # ceiling of bytes / 4
        carry = _carry_over(prior_parts, parts)
        dedupe = _dedupe_stats(parts)
        results = [p for p in parts if p.category == "tool_result"]
        limit, limit_kind = _limit(record)
        limit_kinds.add(limit_kind)
        defs_share: float | str = (
            UNOBSERVED
            if not tools_ever_seen
            else (r6(by_cat["tool_definition"] / total) if total else 0.0)
        )
        used = aligned[index - 1] if aligned else None
        measured = used["prompt_tokens"] if used else UNOBSERVED
        entry: dict[str, Any] = {
            "index": index,
            "bytes": total,
            "est_tokens_words": est_words,
            "est_tokens_bytes": est_bytes,
            "measured_prompt_tokens": measured,
            "measured_output_tokens": used["output_tokens"] if used else UNOBSERVED,
            "measured_cache_read_tokens": used["cache_read_tokens"] if used else UNOBSERVED,
            "measured_cost": used["cost"] if used else UNOBSERVED,
            "measured_latency_ms": used["latency_ms"] if used else UNOBSERVED,
            "parts": len(parts),
            "bytes_by_category": {c: by_cat[c] for c in CATEGORIES if by_cat[c]},
            "parts_by_category": {c: count_cat[c] for c in CATEGORIES if count_cat[c]},
            "carry_over_bytes": carry,
            "new_bytes": total - carry,
            "duplicate_part_bytes": dedupe.get("duplicate_part_bytes", 0),
            "redundant_payload_bytes": dedupe.get("redundant_payload_bytes", 0),
            "redundant_payload_parts": dedupe.get("redundant_payload_parts", 0),
            "redundant_file_bytes": dedupe.get("redundant_file_bytes", 0),
            "normalised_only_redundant_bytes": dedupe.get("normalised_only_redundant_bytes", 0),
            "largest_tool_result_bytes": max((p.nbytes for p in results), default=0),
            "tool_definition_share": defs_share,
            "tool_result_share": r6(by_cat["tool_result"] / total) if total else 0.0,
            "window_fraction_measured": _fraction(measured, limit)
            if isinstance(measured, int)
            else UNOBSERVED,
            "window_fraction_bytes_estimate": _fraction(est_bytes, limit),
            "window_fraction_word_estimate": _fraction(est_words, limit),
        }
        # Call identity (tool plus arguments) is used locally to count repeated calls and
        # changed results. Only counts leave.
        calls: Counter[str] = Counter(
            p.identity for p in parts if p.category == "tool_call" and p.identity
        )
        bodies: dict[str, set[str]] = {}
        for p in results:
            if p.identity:
                bodies.setdefault(p.identity, set()).add(p.body or "")
        for key, seen in bodies.items():
            identity_bodies.setdefault(key, set()).update(seen)
        entry["max_calls_per_identity"] = max(calls.values(), default=0)
        entry["identities_with_differing_bytes"] = sum(1 for v in bodies.values() if len(v) > 1)
        if prior_parts is None:
            entry["prefix"] = None
            entry["history_rewrite"] = False
            entry["definitions_changed"] = False
            entry["system_changed"] = False
        else:
            entry["prefix"] = _prefix(prior_parts, parts)
            rewrote = _rewrite(prior_parts, parts)
            rewrite_events += int(rewrote)
            entry["history_rewrite"] = rewrote
            entry["definitions_changed"] = [
                p.text for p in prior_parts if p.category == "tool_definition"
            ] != [p.text for p in parts if p.category == "tool_definition"]
            entry["system_changed"] = [p.text for p in prior_parts if p.category == "system"] != [
                p.text for p in parts if p.category == "system"
            ]
        requests.append(entry)
        prior_parts = parts

    sizes = [r["bytes"] for r in requests]
    last = requests[-1] if requests else None
    first = requests[0] if requests else None
    prefix_fractions = [r["prefix"]["fraction"] for r in requests if r["prefix"]]
    divergences = Counter(r["prefix"]["first_divergence"] for r in requests if r["prefix"])
    cache_fractions = [
        r["measured_cache_read_tokens"] / r["measured_prompt_tokens"]
        for r in requests[1:]
        if isinstance(r["measured_prompt_tokens"], int)
        and r["measured_prompt_tokens"] > 0
        and isinstance(r["measured_cache_read_tokens"], int)
    ]
    last_parts = extract_request(primary[-1]) if primary else []
    session: dict[str, Any] = {
        "primary_requests": len(requests),
        "other_requests": dict(sorted(other_kinds.items())),
        "compaction_records": other_kinds.get("compaction", 0),
        "duration_minutes": _duration_minutes(records),
        "usage_join": usage_join,
        "tools_available_first_request": (
            first["parts_by_category"].get("tool_definition", 0)
            if first and tools_ever_seen
            else UNOBSERVED
        ),
        "growth_shape": growth_shape(sizes),
        "growth_ratio_last_over_first": r6(sizes[-1] / sizes[0])
        if sizes and sizes[0]
        else UNOBSERVED,
        "first_request_tool_definition_share": first["tool_definition_share"]
        if first
        else UNOBSERVED,
        "first_request_system_share": (
            r6(first["bytes_by_category"].get("system", 0) / first["bytes"])
            if first and first["bytes"]
            else UNOBSERVED
        ),
        "last_request_redundant_payload_share": (
            r6(last["redundant_payload_bytes"] / last["bytes"])
            if last and last["bytes"]
            else UNOBSERVED
        ),
        "last_request_carry_over_share": (
            r6(last["carry_over_bytes"] / last["bytes"]) if last and last["bytes"] else UNOBSERVED
        ),
        "last_request_tool_result_share": last["tool_result_share"] if last else UNOBSERVED,
        "last_request_user_share": (
            r6(last["bytes_by_category"].get("user", 0) / last["bytes"])
            if last and last["bytes"]
            else UNOBSERVED
        ),
        "largest_tool_result_share_max": (
            r6(max(r["largest_tool_result_bytes"] / r["bytes"] for r in requests if r["bytes"]))
            if requests
            else UNOBSERVED
        ),
        "largest_growing_category": _largest_growing(first, last),
        "prefix_fraction_median": r6(statistics.median(prefix_fractions))
        if prefix_fractions
        else UNOBSERVED,
        "prefix_first_divergence_counts": dict(sorted(divergences.items())),
        "provider_cache_read_fraction_median": r6(statistics.median(cache_fractions))
        if cache_fractions
        else UNOBSERVED,
        "history_rewrite_events": rewrite_events,
        "definition_change_events": sum(1 for r in requests if r["definitions_changed"]),
        "system_change_events": sum(1 for r in requests if r["system_changed"]),
        "window_limit_kind": (sorted(limit_kinds)[0] if len(limit_kinds) == 1 else "mixed"),
        "window_fraction_max_measured": _maximum([r["window_fraction_measured"] for r in requests]),
        "window_fraction_max_bytes_estimate": _maximum(
            [r["window_fraction_bytes_estimate"] for r in requests]
        ),
        "window_fraction_max_word_estimate": _maximum(
            [r["window_fraction_word_estimate"] for r in requests]
        ),
        "measured_prompt_tokens_max": _maximum([r["measured_prompt_tokens"] for r in requests]),
        "measured_cost_total": (
            round(sum(r["measured_cost"] for r in requests), 6)
            if requests and all(isinstance(r["measured_cost"], (int, float)) for r in requests)
            else UNOBSERVED
        ),
        "identities_with_differing_bytes": sum(1 for v in identity_bodies.values() if len(v) > 1),
        "max_calls_per_identity_last_request": last["max_calls_per_identity"]
        if last
        else UNOBSERVED,
        "edit_call_count": sum(
            1 for p in last_parts if p.category == "tool_call" and p.tool in EDIT_TOOLS
        ),
        "test_command_call_count": sum(
            1
            for p in last_parts
            if p.category == "tool_call"
            and p.tool in SHELL_TOOLS
            and p.command is not None
            and TEST_COMMAND.search(p.command)
        ),
        "distinct_edit_targets": len(
            {
                p.target
                for p in last_parts
                if p.category == "tool_call" and p.tool in EDIT_TOOLS and p.target
            }
        ),
    }
    return {
        "schema": L1_SCHEMA,
        "analysis_version": ANALYSIS_VERSION,
        "assumed_render_order": list(ASSUMED_RENDER_ORDER),
        "declared": {k: declared[k] for k in sorted(declared)},
        "session": session,
        "requests": requests,
    }


def _largest_growing(first: dict[str, Any] | None, last: dict[str, Any] | None) -> str:
    if not first or not last:
        return UNOBSERVED
    growth = {
        c: last["bytes_by_category"].get(c, 0) - first["bytes_by_category"].get(c, 0)
        for c in CATEGORIES
    }
    top = max(growth, key=lambda c: (growth[c], c))
    return top if growth[top] > 0 else "none"


def reconcile(records: list[dict[str, Any]], l1: dict[str, Any]) -> list[str]:
    """Instrument control 2: recount each request directly from the raw record.

    A second, simpler walk over the raw structure, compared exactly (bytes, not tolerance).
    Returns disagreements; empty means the derivative reconciles with its source.
    """
    problems: list[str] = []
    primary = sorted(
        (r for r in records if r.get("request_kind") == "context"),
        key=lambda r: int(r["invocation_sequence"]),
    )
    if len(primary) != len(l1["requests"]):
        return [f"request count {len(l1['requests'])} != {len(primary)}"]
    for record, entry in zip(primary, l1["requests"]):
        n_parts = len(record["system"]) + len(record["tools"])
        n_parts += sum(len(m.get("content", [])) for m in record["messages"])
        if n_parts != entry["parts"]:
            problems.append(f"request {entry['index']}: parts {entry['parts']} != {n_parts}")
        system_bytes = sum(len(str(e.get("text", "")).encode("utf-8")) for e in record["system"])
        if system_bytes != entry["bytes_by_category"].get("system", 0):
            problems.append(f"request {entry['index']}: system bytes differ")
        text_bytes = sum(
            len(str(p.get("text", "")).encode("utf-8"))
            for m in record["messages"]
            for p in m.get("content", [])
            if p.get("type") in ("text", "reasoning")
        )
        counted = sum(
            entry["bytes_by_category"].get(c, 0)
            for c in ("user", "assistant", "reasoning", "other")
        )
        if text_bytes > counted:
            problems.append(f"request {entry['index']}: message text bytes fell short")
        if sum(entry["bytes_by_category"].values()) != entry["bytes"]:
            problems.append(f"request {entry['index']}: categories do not sum to total")
    return problems


def dumps(l1: dict[str, Any]) -> str:
    """Canonical serialisation: sorted keys, fixed separators, so two runs are byte-identical."""
    return json.dumps(l1, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
