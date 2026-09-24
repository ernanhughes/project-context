"""Shape cards: the structure of a context pathology, with no conclusion and no content.

A card says *what shape was present*: which structural pattern, how large, where in the
request, how often within the session, and how to recreate it synthetically. It never says
what the shape does, whether it hurts, or what should be done about it. Those are the
questions the later experiments ask.

The vocabulary is closed and the schema has no free-text field. A card therefore cannot
carry ecological text, and the validator rejects evaluative phrasing in any string that
reaches it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from project_context.corpus.completeness import DECLARED, DERIVED, OBSERVED, PROXY

# shape -> (basis, how it is recognised). Recognition rules use fixed constants below.
SHAPES: dict[str, tuple[str, str]] = {
    "repeated_file_material": (
        DERIVED,
        "identical output body from a file-reading tool more than once in one request",
    ),
    "repeated_tool_output": (
        DERIVED,
        "identical output body from any other tool more than once in one request",
    ),
    "large_standing_tool_schema": (
        OBSERVED,
        "tool definitions are a large share of a request and unchanged across requests",
    ),
    "history_dominated_growth": (
        DERIVED,
        "most of the growth from first to last request is user and assistant text",
    ),
    "volatile_early_prefix": (
        PROXY,
        "the stable prefix breaks early in the request in many consecutive pairs",
    ),
    "stale_observation_surviving": (
        DERIVED,
        "one call (tool and arguments) returned different bytes and both results remain in "
        "one request; a re-run whose state changed also qualifies",
    ),
    "repeated_re_read": (
        DERIVED,
        "the same call (tool and arguments) made several times, whether or not the bytes matched",
    ),
    "large_recoverable_artifact": (
        DERIVED,
        "a single tool result is a large share of a request, and its call could be made again",
    ),
    "compaction_or_rewrite_event": (
        OBSERVED,
        "a compaction record, or an earlier message part changed between requests",
    ),
    # These two cannot be seen in the capture. They are emitted only when the author
    # declares them in the sidecar, and are recorded as declared.
    "scope_crossover_opportunity": (
        DECLARED,
        "the author declares material from another task or project was reachable",
    ),
    "authority_conflict": (
        DECLARED,
        "the author declares instructions of differing authority disagreed",
    ),
}

# Recognition thresholds. They decide only whether a card is written. They are not
# evidence that a shape matters.
LARGE_SCHEMA_SHARE = 0.10
HISTORY_GROWTH_SHARE = 0.50
EARLY_BREAK_POSITION = 0.25
EARLY_BREAK_PAIR_FRACTION = 1 / 3
LARGE_ARTIFACT_SHARE = 0.20
RE_READ_MIN_CALLS = 2

CARD_KEYS = frozenset({"shape", "basis", "requests_showing", "magnitude", "recreate"})
MAGNITUDE_KEYS = frozenset(
    {
        "bytes",
        "share",
        "occurrences",
        "position",
        "requests_in_session",
        "first_request_index",
        "calls",
    }
)
RECREATE_KEYS = frozenset({"parts", "part_bytes", "repeats", "position_fraction", "requests"})

# Words that state a conclusion. None may appear in any string on a card.
CONCLUSION_PHRASES = re.compile(
    r"\b(would improve|should be|could be removed|safe to|wasteful|waste|harmful|hurts|"
    r"degrad\w*|better|worse|unnecessary|redundant and|prune|pruning|recommend\w*|"
    r"causes?|caused|because)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Card:
    shape: str
    basis: str
    requests_showing: int
    magnitude: dict[str, float | int]
    recreate: dict[str, float | int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "shape": self.shape,
            "basis": self.basis,
            "requests_showing": self.requests_showing,
            "magnitude": dict(sorted(self.magnitude.items())),
            "recreate": dict(sorted(self.recreate.items())),
        }


def validate_card(card: dict[str, Any]) -> list[str]:
    """Structure only. Rejects free text, unknown keys and any conclusion wording."""
    errors: list[str] = []
    if set(card) != CARD_KEYS:
        errors.append(f"card keys {sorted(card)} != {sorted(CARD_KEYS)}")
        return errors
    if card["shape"] not in SHAPES:
        errors.append(f"unknown shape {card['shape']!r}")
    elif card["basis"] != SHAPES[card["shape"]][0]:
        errors.append("basis does not match the shape's recognised basis")
    for section, allowed in (("magnitude", MAGNITUDE_KEYS), ("recreate", RECREATE_KEYS)):
        for key, value in card[section].items():
            if key not in allowed:
                errors.append(f"{section}.{key} is not an allowed field")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{section}.{key} is not a number")
    if not isinstance(card["requests_showing"], int):
        errors.append("requests_showing is not an integer")
    strings = [card["shape"], card["basis"]]
    for text in strings:
        if CONCLUSION_PHRASES.search(str(text)):
            errors.append(f"conclusion wording in {text!r}")
    return errors


def derive_cards(l1: dict[str, Any]) -> list[Card]:
    """Cards for one session, from its L1 derivative and its sidecar. Deterministic."""
    requests, session, declared = l1["requests"], l1["session"], l1["declared"]
    n = len(requests)
    cards: list[Card] = []
    if not n:
        return cards

    def card(shape: str, showing: int, magnitude: dict, recreate: dict) -> None:
        cards.append(Card(shape, SHAPES[shape][0], showing, magnitude, recreate))

    # Repeated output inside one request, split by whether the tool reads files.
    for shape, key in (
        ("repeated_file_material", "redundant_file_bytes"),
        ("repeated_tool_output", None),
    ):
        showing = [
            r
            for r in requests
            if (r[key] if key else r["redundant_payload_bytes"] - r["redundant_file_bytes"]) > 0
        ]
        if showing:
            worst = max(
                showing,
                key=lambda r: (
                    r[key] if key else r["redundant_payload_bytes"] - r["redundant_file_bytes"]
                ),
            )
            size = (
                worst[key]
                if key
                else worst["redundant_payload_bytes"] - worst["redundant_file_bytes"]
            )
            card(
                shape,
                len(showing),
                {
                    "bytes": size,
                    "share": round(size / worst["bytes"], 6),
                    "occurrences": worst["redundant_payload_parts"],
                    "first_request_index": showing[0]["index"],
                    "requests_in_session": n,
                },
                {
                    "parts": worst["redundant_payload_parts"] + 1,
                    "part_bytes": size // max(1, worst["redundant_payload_parts"]),
                    "repeats": worst["redundant_payload_parts"],
                },
            )

    shares = [
        r["tool_definition_share"]
        for r in requests
        if isinstance(r["tool_definition_share"], float)
    ]
    if shares and max(shares) >= LARGE_SCHEMA_SHARE and session["definition_change_events"] == 0:
        first = requests[0]
        card(
            "large_standing_tool_schema",
            sum(1 for s in shares if s >= LARGE_SCHEMA_SHARE),
            {
                "bytes": first["bytes_by_category"].get("tool_definition", 0),
                "share": max(shares),
                "occurrences": first["parts_by_category"].get("tool_definition", 0),
                "requests_in_session": n,
            },
            {
                "parts": first["parts_by_category"].get("tool_definition", 0),
                "part_bytes": first["bytes_by_category"].get("tool_definition", 0)
                // max(1, first["parts_by_category"].get("tool_definition", 0)),
                "requests": n,
            },
        )

    first, last = requests[0], requests[-1]
    growth = last["bytes"] - first["bytes"]
    history = sum(
        last["bytes_by_category"].get(c, 0) - first["bytes_by_category"].get(c, 0)
        for c in ("user", "assistant", "reasoning")
    )
    if growth > 0 and history / growth >= HISTORY_GROWTH_SHARE:
        card(
            "history_dominated_growth",
            n,
            {"bytes": growth, "share": round(history / growth, 6), "requests_in_session": n},
            {"parts": last["parts"], "requests": n},
        )

    pairs = [r["prefix"] for r in requests if r["prefix"]]
    early = [
        p
        for p in pairs
        if p["divergence_position"] <= EARLY_BREAK_POSITION
        and p["first_divergence"] not in ("identical",)
    ]
    if pairs and len(early) / len(pairs) >= EARLY_BREAK_PAIR_FRACTION:
        card(
            "volatile_early_prefix",
            len(early),
            {
                "share": round(len(early) / len(pairs), 6),
                "position": min(p["divergence_position"] for p in early),
                "requests_in_session": n,
            },
            {"position_fraction": min(p["divergence_position"] for p in early), "requests": n},
        )

    stale = [r for r in requests if r["identities_with_differing_bytes"] > 0]
    if stale:
        card(
            "stale_observation_surviving",
            len(stale),
            {
                "occurrences": max(r["identities_with_differing_bytes"] for r in stale),
                "first_request_index": stale[0]["index"],
                "requests_in_session": n,
            },
            {"parts": 2, "repeats": 1},
        )

    rereads = [r for r in requests if r["max_calls_per_identity"] >= RE_READ_MIN_CALLS]
    if rereads:
        card(
            "repeated_re_read",
            len(rereads),
            {
                "calls": max(r["max_calls_per_identity"] for r in rereads),
                "first_request_index": rereads[0]["index"],
                "requests_in_session": n,
            },
            {"parts": max(r["max_calls_per_identity"] for r in rereads), "repeats": 1},
        )

    large = [
        r
        for r in requests
        if r["bytes"] and r["largest_tool_result_bytes"] / r["bytes"] >= LARGE_ARTIFACT_SHARE
    ]
    if large:
        worst = max(large, key=lambda r: r["largest_tool_result_bytes"] / r["bytes"])
        card(
            "large_recoverable_artifact",
            len(large),
            {
                "bytes": worst["largest_tool_result_bytes"],
                "share": round(worst["largest_tool_result_bytes"] / worst["bytes"], 6),
                "first_request_index": large[0]["index"],
                "requests_in_session": n,
            },
            {"parts": 1, "part_bytes": worst["largest_tool_result_bytes"], "requests": n},
        )

    rewrites = [r for r in requests if r["history_rewrite"]]
    if rewrites or session["compaction_records"]:
        card(
            "compaction_or_rewrite_event",
            len(rewrites),
            {
                "occurrences": len(rewrites) + session["compaction_records"],
                "first_request_index": rewrites[0]["index"] if rewrites else 0,
                "requests_in_session": n,
            },
            {"requests": n},
        )

    for shape, flag in (
        ("scope_crossover_opportunity", "scope_crossover"),
        ("authority_conflict", "authority_conflict"),
    ):
        if declared.get(flag) is True:
            card(shape, 0, {"requests_in_session": n}, {"requests": n})
    return cards


def catalogue(per_session: list[list[Card]], minimum_sessions: int = 2) -> dict[str, Any]:
    """How often each shape occurs across sessions. A shape needs `minimum_sessions` to be
    listed as a recurring shape; fewer is reported as a single occurrence, not a pattern."""
    counts = {shape: 0 for shape in SHAPES}
    for cards in per_session:
        for shape in {c.shape for c in cards}:
            counts[shape] += 1
    return {
        "sessions": len(per_session),
        "sessions_showing": counts,
        "recurring": sorted(s for s, c in counts.items() if c >= minimum_sessions),
        "single_occurrence": sorted(s for s, c in counts.items() if c == 1),
        "not_seen": sorted(s for s, c in counts.items() if c == 0),
    }
