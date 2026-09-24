"""F1 structural analysis: from one session's raw records to a content-free derivative.

Everything here is deterministic and exact: byte identity, exact identity after
whitespace normalisation, and source or tool identity. There are no embeddings and no
model judging similarity. The output (`analyse_session`) holds numbers, closed-vocabulary
labels and the string ``UNOBSERVED``; it never holds text, paths, titles, identifiers,
hashes or timestamps. The raw text exists only inside this module's call frames.

Three ideas are kept apart on purpose:

* **carry-over**: a part re-sent unchanged from an earlier request. Expected; a session's
  history is re-sent every turn. Never called redundancy.
* **redundant payload**: the same tool-output body appearing more than once inside a
  single request. This is what H1 measures.
* **prefix**: computed under an assumed render order, and reported as a proxy because the
  provider's real order is not observed.
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
from project_context.opencode.ingest import record_to_items

ANALYSIS_VERSION = "1.0.0"
L1_SCHEMA = "project_context.f1_structure.v1"

CATEGORIES = (
    "tool_definition",
    "system",
    "user",
    "assistant",
    "tool_call",
    "tool_result",
    "other",
)

# The order the parts are assumed to be laid out for the prefix measurement. Anthropic's
# documented order is tools, system, messages; other providers differ, and none of this
# is observed. Reported as an assumption wherever the prefix appears.
ASSUMED_RENDER_ORDER = ("tool_definition", "system", "messages")

_KIND_TO_CATEGORY = {
    "system_instruction": "system",
    "conversation_user": "user",
    "conversation_assistant": "assistant",
    "reasoning_part": "assistant",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "tool_definition": "tool_definition",
}

_HEADER = re.compile(
    r"^\[tool:(?P<tool>[^\s\]]*) call:(?P<call>[^\s\]]*)(?: title:(?P<title>.*))?\]$"
)

# Tools whose results are file material. A closed list; anything else is "other tool output".
FILE_READ_TOOLS = frozenset({"read", "view", "cat", "open"})
EDIT_TOOLS = frozenset({"edit", "write", "patch", "multiedit", "apply_patch"})
TEST_COMMAND = re.compile(
    r"\b(pytest|py\.test|npm (?:run )?test|yarn test|pnpm test|jest|vitest|mocha|"
    r"cargo test|go test|dotnet test|mvn test|gradle test|rspec|phpunit)\b",
    re.IGNORECASE,
)


def r6(x: float) -> float:
    return round(float(x), 6)


@dataclass(frozen=True)
class Part:
    """One rendered part. Local to this module; never serialised."""

    category: str
    text: str
    body: str | None = None  # tool-result output with its header removed
    tool: str | None = None
    title: str | None = None

    @property
    def nbytes(self) -> int:
        return len(self.text.encode("utf-8"))


def _split_tool_result(text: str) -> tuple[str | None, str | None, str]:
    head, _, rest = text.partition("\n")
    match = _HEADER.match(head)
    if not match:
        return None, None, text
    return match.group("tool"), match.group("title") or "", rest


def extract_request(record: dict[str, Any]) -> list[Part]:
    """Parts of one request, in the assumed render order.

    Tool definitions first, then system entries, then message parts in their recorded order.
    """
    ordered = record_to_items(record, observed_at="-")
    definitions, system, messages = [], [], []
    for item in ordered:
        category = _KIND_TO_CATEGORY.get(item.kind, "other")
        part = Part(category, item.content)
        if category == "tool_result":
            tool, title, body = _split_tool_result(item.content)
            part = Part(category, item.content, body=body, tool=tool, title=title)
        elif category == "tool_definition":
            part = Part(category, item.content, tool=item.ref)
        {"tool_definition": definitions, "system": system}.get(category, messages).append(part)
    return definitions + system + messages


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _dedupe_stats(parts: list[Part]) -> dict[str, int]:
    """Repeats inside one request. Counts the second and later occurrences only."""
    seen_bodies: set[str] = set()
    seen_norm: set[str] = set()
    seen_texts: set[str] = set()
    out = Counter()
    for part in parts:
        if part.text in seen_texts:
            out["duplicate_part_bytes"] += part.nbytes
        seen_texts.add(part.text)
        if part.category != "tool_result" or not part.body:
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


def _window_fraction(record: dict[str, Any], est_tokens: int) -> float | str:
    limits = record.get("model_limits")
    context = limits.get("context") if isinstance(limits, dict) else None
    if not isinstance(context, int) or isinstance(context, bool) or context <= 0:
        return UNOBSERVED
    return r6(est_tokens / context)


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


def analyse_session(
    records: list[dict[str, Any]], *, declared: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The L1 structural derivative of one session's *primary* requests.

    `declared` is the sidecar (closed vocabulary), never inferred from the capture.
    """
    declared = declared or {}
    primary = sorted(
        (r for r in records if r.get("request_kind") == "context"),
        key=lambda r: int(r["invocation_sequence"]),
    )
    other_kinds = Counter(r.get("request_kind") for r in records if r not in primary)
    requests: list[dict[str, Any]] = []
    prior_parts: list[Part] | None = None
    seen_texts: set[str] = set()
    tools_ever_seen = any(bool(r.get("tools")) for r in primary)
    identity_bodies: dict[tuple[str, str], set[str]] = {}
    rewrite_events = 0

    for index, record in enumerate(primary, start=1):
        parts = extract_request(record)
        total = sum(p.nbytes for p in parts)
        by_cat = Counter()
        count_cat = Counter()
        for p in parts:
            by_cat[p.category] += p.nbytes
            count_cat[p.category] += 1
        est = sum(estimate_tokens(p.text)[0] for p in parts)
        carry = sum(p.nbytes for p in parts if p.text in seen_texts)
        dedupe = _dedupe_stats(parts)
        results = [p for p in parts if p.category == "tool_result"]
        defs_bytes = by_cat["tool_definition"]
        if not tools_ever_seen:
            defs_share: float | str = UNOBSERVED
        else:
            defs_share = r6(defs_bytes / total) if total else 0.0
        entry: dict[str, Any] = {
            "index": index,
            "bytes": total,
            "est_tokens": est,
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
            "window_fraction_estimate": _window_fraction(record, est),
        }
        # Tool identity (proxy) is used locally to count re-reads and changed bytes.
        calls: Counter[tuple[str, str]] = Counter()
        bodies: dict[tuple[str, str], set[str]] = {}
        for p in results:
            if p.tool is not None:
                key = (p.tool, p.title or "")
                calls[key] += 1
                bodies.setdefault(key, set()).add(p.body or "")
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
        seen_texts.update(p.text for p in parts)
        prior_parts = parts

    sizes = [r["bytes"] for r in requests]
    last = requests[-1] if requests else None
    first = requests[0] if requests else None
    prefix_fractions = [r["prefix"]["fraction"] for r in requests if r["prefix"]]
    divergences = Counter(r["prefix"]["first_divergence"] for r in requests if r["prefix"])
    window = [
        r["window_fraction_estimate"]
        for r in requests
        if r["window_fraction_estimate"] != UNOBSERVED
    ]
    session: dict[str, Any] = {
        "primary_requests": len(requests),
        "other_requests": dict(sorted(other_kinds.items())),
        "compaction_records": other_kinds.get("compaction", 0),
        "duration_minutes": _duration_minutes(records),
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
        "history_rewrite_events": rewrite_events,
        "definition_change_events": sum(1 for r in requests if r["definitions_changed"]),
        "system_change_events": sum(1 for r in requests if r["system_changed"]),
        "window_fraction_max": max(window) if window else UNOBSERVED,
        "identities_with_differing_bytes": sum(1 for v in identity_bodies.values() if len(v) > 1),
        "max_calls_per_identity_last_request": last["max_calls_per_identity"]
        if last
        else UNOBSERVED,
        "edit_result_count": _count_local(primary, lambda p: p.tool in EDIT_TOOLS),
        "test_command_result_count": _count_local(
            primary, lambda p: bool(TEST_COMMAND.search(p.title or ""))
        ),
        "distinct_edit_targets": _distinct_edit_targets(primary),
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


def _last_request_results(primary: list[dict[str, Any]]) -> list[Part]:
    return (
        [p for p in extract_request(primary[-1]) if p.category == "tool_result"] if primary else []
    )


def _count_local(primary: list[dict[str, Any]], predicate: Any) -> int:
    """Tool results in the last request satisfying `predicate`. Counts leave; titles never do."""
    return sum(1 for p in _last_request_results(primary) if predicate(p))


def _distinct_edit_targets(primary: list[dict[str, Any]]) -> int:
    """Proxy for files edited: distinct titles among edit-tool results in the last request."""
    return len({p.title for p in _last_request_results(primary) if p.tool in EDIT_TOOLS})


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
        n_parts += sum(len(m.get("parts", [])) for m in record["messages"])
        if n_parts != entry["parts"]:
            problems.append(f"request {entry['index']}: parts {entry['parts']} != {n_parts}")
        system_bytes = sum(len(str(e.get("text", "")).encode("utf-8")) for e in record["system"])
        if system_bytes != entry["bytes_by_category"].get("system", 0):
            problems.append(f"request {entry['index']}: system bytes differ")
        if sum(entry["bytes_by_category"].values()) != entry["bytes"]:
            problems.append(f"request {entry['index']}: categories do not sum to total")
    return problems


def dumps(l1: dict[str, Any]) -> str:
    """Canonical serialisation: sorted keys, fixed separators, so two runs are byte-identical."""
    return json.dumps(l1, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
