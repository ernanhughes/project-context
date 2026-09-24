"""F1 privacy pipeline: scan the raw capture, then gate the derivative.

Raw material never leaves the machine. What may leave is the L1 derivative, and only
after two independent lines of defence, either of which is enough to stop it:

1. **Construction.** The derivative is a whitelisted structure of numbers and closed
   vocabulary. It has nowhere to put text, so a scanner that misses something in the raw
   capture cannot cause a leak.
2. **Verification.** The gate then checks the built derivative against the raw capture:
   no identifier, secret-shaped string, planted term, or distinctive raw token may appear
   in it.

The scan decides *inclusion* (a credential in the raw capture excludes the session). The
gate decides *publication*. They use different code, so a blind spot in one does not
become a blind spot in the other.

Scan reports and gate results carry categories and counts. They never carry the matched
text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from project_context.corpus.completeness import UNOBSERVED
from project_context.corpus.f1_analysis import ANALYSIS_VERSION, CATEGORIES, L1_SCHEMA
from project_context.corpus.ledger import SIDECAR_KEYS
from project_context.corpus.manifest import SECRET_PATTERNS
from project_context.corpus.shapecards import SHAPES
from project_context.corpus.strata import STRATA, UNCLASSIFIED
from project_context.opencode.prevalence import assert_exportable

# ---- scan: credential classes exclude a session; identifier classes are recorded ----------

CREDENTIAL_PATTERNS: dict[str, re.Pattern[str]] = {
    **{f"secret-pattern-{i}": p for i, p in enumerate(SECRET_PATTERNS)},
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "bearer-token": re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    "url-credentials": re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s:@/]+:[^\s@/]+@"),
    # A name that contains a secret-like word, assigned a literal value that has a digit in
    # it. Requiring the digit keeps ordinary code (`token = next_token()`) from excluding a
    # session while still catching `SOME_SECRET=abc123...`.
    "assigned-secret": re.compile(
        r"(?i)[A-Za-z0-9_]*(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)"
        r"[A-Za-z0-9_]*\s*[:=]\s*[\"']?(?=[A-Za-z0-9/+_.\-]*\d)[A-Za-z0-9/+_.\-]{8,}"
    ),
}

IDENTIFIER_PATTERNS: dict[str, re.Pattern[str]] = {
    "windows-path": re.compile(r"[A-Za-z]:[\\/](?:[^\s\\/\"'<>|]+[\\/])*[^\s\\/\"'<>|]*"),
    "posix-home-path": re.compile(r"/(?:home|Users|var|etc|opt|srv|mnt|tmp)/[^\s\"'<>]+"),
    "email": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "hostname": re.compile(
        r"\b(?:[a-z0-9\-]+\.)+(?:internal|local|corp|lan|test|example|com|net|org|io|dev)\b"
    ),
}

_TOKEN = re.compile(r"[A-Za-z0-9_./\\:@+\-]{8,}")


def _strings(node: Any):
    """Every string value in a raw record, at any depth."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _structural_identifiers(record: dict[str, Any]):
    """Identifiers and arguments the capture itself carries, kept locally so the gate can look
    for them: session, capture, message and call ids, and every string inside a tool call's
    arguments (paths, commands, patterns)."""
    for key in ("session_id", "capture_id", "captured_at"):
        if isinstance(record.get(key), str):
            yield record[key]
    for message in record.get("messages", []):
        if not isinstance(message, dict):
            continue
        if isinstance(message.get("id"), str):
            yield message["id"]
        for part in message.get("content", []) if isinstance(message.get("content"), list) else []:
            if isinstance(part.get("id"), str):
                yield part["id"]
            if part.get("type") == "tool-call":
                yield from _strings(part.get("input"))


@dataclass(frozen=True)
class ScanReport:
    """What the raw scan found. `to_dict` is safe to log; `retained` never is."""

    credentials: dict[str, int]
    identifiers: dict[str, int]
    sensitive_terms_found: int
    retained: tuple[str, ...] = field(default=(), repr=False, compare=False)

    @property
    def excludes_session(self) -> bool:
        return bool(self.credentials)

    def to_dict(self) -> dict[str, Any]:
        return {
            "credentials": dict(sorted(self.credentials.items())),
            "identifiers": dict(sorted(self.identifiers.items())),
            "sensitive_terms_found": self.sensitive_terms_found,
        }


def scan_raw(records: list[dict[str, Any]], sensitive_terms: tuple[str, ...] = ()) -> ScanReport:
    """Scan a raw capture. Credentials exclude the session; identifiers are recorded.

    Identifiers (paths, addresses, hostnames) are expected in real work and cannot reach the
    derivative, so they do not exclude a session; the gate makes sure they do not travel.
    `sensitive_terms` are literal strings the author lists locally (repository names, a user
    name, an internal host) and are matched case-insensitively.
    """
    credentials: dict[str, int] = {}
    identifiers: dict[str, int] = {}
    terms_found = 0
    retained: list[str] = []
    for record in records:
        for text in _strings(record):
            for name, pattern in CREDENTIAL_PATTERNS.items():
                for match in pattern.finditer(text):
                    credentials[name] = credentials.get(name, 0) + 1
                    retained.append(match.group(0))
            for name, pattern in IDENTIFIER_PATTERNS.items():
                for match in pattern.finditer(text):
                    identifiers[name] = identifiers.get(name, 0) + 1
                    retained.append(match.group(0))
            lowered = text.lower()
            for term in sensitive_terms:
                if term and term.lower() in lowered:
                    terms_found += 1
        retained.extend(_structural_identifiers(record))
    retained.extend(t for t in sensitive_terms if t)
    return ScanReport(credentials, identifiers, terms_found, tuple(dict.fromkeys(retained)))


def raw_tokens(records: list[dict[str, Any]]) -> set[str]:
    """Distinctive tokens (eight or more identifier-like characters) from all raw text."""
    tokens: set[str] = set()
    for record in records:
        for text in _strings(record):
            tokens.update(m.group(0) for m in _TOKEN.finditer(text))
    return tokens


# ---- schema: what a derivative may contain --------------------------------------------

SESSION_KEYS = frozenset(
    {
        "primary_requests",
        "other_requests",
        "compaction_records",
        "duration_minutes",
        "tools_available_first_request",
        "growth_shape",
        "growth_ratio_last_over_first",
        "first_request_tool_definition_share",
        "first_request_system_share",
        "last_request_redundant_payload_share",
        "last_request_carry_over_share",
        "last_request_tool_result_share",
        "last_request_user_share",
        "largest_tool_result_share_max",
        "largest_growing_category",
        "prefix_fraction_median",
        "prefix_first_divergence_counts",
        "history_rewrite_events",
        "definition_change_events",
        "system_change_events",
        "usage_join",
        "provider_cache_read_fraction_median",
        "window_limit_kind",
        "window_fraction_max_measured",
        "window_fraction_max_bytes_estimate",
        "window_fraction_max_word_estimate",
        "measured_prompt_tokens_max",
        "measured_cost_total",
        "identities_with_differing_bytes",
        "max_calls_per_identity_last_request",
        "edit_call_count",
        "test_command_call_count",
        "distinct_edit_targets",
    }
)
REQUEST_KEYS = frozenset(
    {
        "index",
        "bytes",
        "est_tokens_words",
        "est_tokens_bytes",
        "measured_prompt_tokens",
        "measured_output_tokens",
        "measured_cache_read_tokens",
        "measured_cost",
        "measured_latency_ms",
        "parts",
        "bytes_by_category",
        "parts_by_category",
        "carry_over_bytes",
        "new_bytes",
        "duplicate_part_bytes",
        "redundant_payload_bytes",
        "redundant_payload_parts",
        "redundant_file_bytes",
        "normalised_only_redundant_bytes",
        "largest_tool_result_bytes",
        "tool_definition_share",
        "tool_result_share",
        "window_fraction_measured",
        "window_fraction_bytes_estimate",
        "window_fraction_word_estimate",
        "max_calls_per_identity",
        "identities_with_differing_bytes",
        "prefix",
        "history_rewrite",
        "definitions_changed",
        "system_changed",
    }
)
PREFIX_KEYS = frozenset({"parts", "bytes", "fraction", "first_divergence", "divergence_position"})
TOP_KEYS = frozenset(
    {"schema", "analysis_version", "assumed_render_order", "declared", "session", "requests"}
)

# Closed sets of strings that may appear as values or as keys of category-keyed maps.
DIVERGENCE_VALUES = ("append_only", "identical", "shorter", *CATEGORIES)
GROWTH_VALUES = ("step", "accelerating", "steady", "undefined_too_few_requests")
REQUEST_KIND_KEYS = ("context", "compaction", "generate", "title")
VOCAB: frozenset[str] = frozenset(
    {
        UNOBSERVED,
        "none",
        "aligned",
        "count_mismatch",
        "input",
        "context",
        "mixed",
        L1_SCHEMA,
        ANALYSIS_VERSION,
        "tool_definition",
        "system",
        "messages",
        *CATEGORIES,
        *DIVERGENCE_VALUES,
        *GROWTH_VALUES,
        *REQUEST_KIND_KEYS,
        *(v for values in SIDECAR_KEYS.values() for v in values if isinstance(v, str)),
    }
)
CATEGORY_KEYED = {
    "bytes_by_category": frozenset(CATEGORIES),
    "parts_by_category": frozenset(CATEGORIES),
    "prefix_first_divergence_counts": frozenset(DIVERGENCE_VALUES),
    "other_requests": frozenset(REQUEST_KIND_KEYS),
}


# Every key the schema permits. A raw token equal to one of these cannot carry raw
# information out, because the key is a schema constant.
SCHEMA_KEYS: frozenset[str] = frozenset(
    {
        *TOP_KEYS,
        *SESSION_KEYS,
        *REQUEST_KEYS,
        *PREFIX_KEYS,
        *SIDECAR_KEYS,
        *(k for keys in CATEGORY_KEYED.values() for k in keys),
    }
)
_NUMERIC = re.compile(r"^[0-9.\-+eE]+$")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_l1(l1: dict[str, Any]) -> list[str]:
    """Strict whitelist. Any key or string outside the closed sets is an error."""
    errors: list[str] = []

    def leaf(value: Any, path: str) -> None:
        if value is None or isinstance(value, bool) or _is_number(value):
            return
        if isinstance(value, str):
            if value not in VOCAB:
                errors.append(f"{path}: string outside the closed vocabulary")
            return
        errors.append(f"{path}: unexpected {type(value).__name__}")

    def mapping(node: Any, allowed: frozenset[str], path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path}: not an object")
            return
        for key, value in node.items():
            here = f"{path}.{key}"
            if key not in allowed:
                errors.append(f"{here}: key not in the whitelist")
                continue
            if key in CATEGORY_KEYED:
                if not isinstance(value, dict):
                    errors.append(f"{here}: not an object")
                    continue
                for sub, number in value.items():
                    if sub not in CATEGORY_KEYED[key]:
                        errors.append(f"{here}.{sub}: key not in the whitelist")
                    elif not _is_number(number):
                        errors.append(f"{here}.{sub}: not a number")
            elif key == "prefix":
                if value is not None:
                    mapping(value, PREFIX_KEYS, here)
            elif key == "declared":
                for k, v in value.items():
                    if k not in SIDECAR_KEYS or v not in SIDECAR_KEYS[k]:
                        errors.append(f"{here}.{k}: not in the sidecar vocabulary")
            elif key == "assumed_render_order":
                if list(value) != ["tool_definition", "system", "messages"]:
                    errors.append(f"{here}: unexpected order")
            elif key == "session":
                mapping(value, SESSION_KEYS, here)
            elif key == "requests":
                if not isinstance(value, list):
                    errors.append(f"{here}: not a list")
                for i, item in enumerate(value):
                    mapping(item, REQUEST_KEYS, f"{here}[{i}]")
            else:
                leaf(value, here)

    mapping(l1, TOP_KEYS, "l1")
    if l1.get("schema") != L1_SCHEMA:
        errors.append("l1.schema: unexpected")
    return errors


# ---- gate: is this derivative fit to leave ----------------------------------------------

VALUE_PATTERNS = {
    "iso-date": re.compile(r"\d{4}-\d{2}-\d{2}"),
    "long-hex": re.compile(r"\b[0-9a-fA-F]{32,}\b"),
    "email": IDENTIFIER_PATTERNS["email"],
    "url": re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://"),
    "path": re.compile(r"[A-Za-z]:[\\/]|/(?:home|Users)/"),
}


@dataclass(frozen=True)
class GateResult:
    content_clean: bool
    violations: tuple[str, ...]
    approved: bool

    @property
    def publishable(self) -> bool:
        """Clean content is necessary, never sufficient: publication also needs the recorded
        approval that the privacy specification requires."""
        return self.content_clean and self.approved


def gate(
    l1: dict[str, Any],
    raw_records: list[dict[str, Any]],
    scan: ScanReport,
    *,
    approved: bool = False,
) -> GateResult:
    """Check a built derivative against the raw capture it came from."""
    violations: list[str] = [f"schema: {e}" for e in validate_l1(l1)]
    violations += [f"export gate: {e}" for e in assert_exportable(l1)]
    blob = _canonical_blob(l1)
    for name, pattern in VALUE_PATTERNS.items():
        if pattern.search(blob):
            violations.append(f"value pattern: {name}")
    for text in scan.retained:
        # Words the schema itself uses (a role name, a key) cannot carry raw information out.
        if len(text) >= 4 and text not in VOCAB and text not in SCHEMA_KEYS and text in blob:
            violations.append("retained raw string present in derivative")
    derivative_tokens = {m.group(0) for m in _TOKEN.finditer(blob)}
    shared = {
        t
        for t in derivative_tokens & raw_tokens(raw_records)
        if t not in VOCAB and t not in SCHEMA_KEYS and not _NUMERIC.match(t)
    }
    if shared:
        violations.append(f"{len(shared)} distinctive raw token(s) present in derivative")
    return GateResult(not violations, tuple(violations), approved)


def _canonical_blob(l1: dict[str, Any]) -> str:
    import json

    return json.dumps(l1, sort_keys=True, ensure_ascii=True)


def stratum_names() -> tuple[str, ...]:
    return (*STRATA, UNCLASSIFIED, *SHAPES)
