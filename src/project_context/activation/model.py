"""Activation records: request features, versioned policy, decisions, results.

The activator works from explicit structured request features, never by
parsing free-form prose. Matching is exact structural overlap (equality
or path-prefix), never similarity. Fields absent on either side simply
do not match; nothing is inferred.

The compiler's `ContextRequest` is not reused: it carries budget,
required IDs, and admission-oriented fields for a decision the
activator must not make. `ActivationRequest` carries only the features
activation is allowed to consult. Stage 6C will bridge the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

ACTIVATION_REQUEST_SCHEMA = "project_context.activation_request.v1"
ACTIVATION_POLICY_SCHEMA = "project_context.activation_policy.v1"
ACTIVATION_DECISION_SCHEMA = "project_context.activation_decision.v1"
ACTIVATION_RESULT_SCHEMA = "project_context.activation_result.v1"


class ActivationState(str, Enum):
    ACTIVE = "active"  # an explicit reason links this valid item to this request
    DORMANT = "dormant"  # valid, but no current activation reason
    INELIGIBLE = "ineligible"  # lifecycle, verification, or scope bars activation
    UNKNOWN = "unknown"  # available structure cannot decide safely


class ActivationMode(str, Enum):
    TYPED = "typed"  # the production two-stage rule set
    ALL_UNRESOLVED = "all_unresolved"  # naive: every active/blocked item wakes
    SCOPE_ONLY = "scope_only"  # naive: scope overlap alone, no validity gate
    NEWEST = "newest"  # naive: most recently created non-terminal items


# Stable reason codes. Sorted in every decision for deterministic output.
REPO_MISMATCH = "scope_repo_mismatch"
TERMINAL_CODES = {
    "satisfied": "terminal_satisfied",
    "failed": "terminal_failed",
    "cancelled": "terminal_cancelled",
    "expired": "terminal_expired",
    "superseded": "superseded",
    "contradicted": "contradicted",
}


@dataclass(frozen=True)
class ActivationRequest:
    """Structured features of the current computation. Every field but
    the identities is optional; absent fields never match."""

    request_id: str
    task_id: str
    created_at: str
    repo: str | None = None
    workspace: str | None = None
    branch: str | None = None
    paths: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    task: str | None = None
    operation: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def usable_features(self) -> tuple[str, ...]:
        """Request fields carrying information, in fixed order."""
        present = []
        if self.repo is not None:
            present.append("repo")
        if self.paths:
            present.append("paths")
        if self.components:
            present.append("components")
        if self.task is not None:
            present.append("task")
        if self.operation is not None:
            present.append("operation")
        if self.evidence_refs:
            present.append("evidence_refs")
        return tuple(present)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVATION_REQUEST_SCHEMA,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "created_at": self.created_at,
            "repo": self.repo,
            "workspace": self.workspace,
            "branch": self.branch,
            "paths": list(self.paths),
            "components": list(self.components),
            "task": self.task,
            "operation": self.operation,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivationRequest":
        version = data.get("schema_version", ACTIVATION_REQUEST_SCHEMA)
        if version != ACTIVATION_REQUEST_SCHEMA:
            raise ValueError(f"unsupported ActivationRequest schema: {version!r}")
        unknown = set(data) - {
            "schema_version",
            "request_id",
            "task_id",
            "created_at",
            "repo",
            "workspace",
            "branch",
            "paths",
            "components",
            "task",
            "operation",
            "evidence_refs",
        }
        if unknown:
            raise ValueError(f"unknown ActivationRequest keys: {sorted(unknown)}")
        for field in ("request_id", "task_id", "created_at"):
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"invalid {field}: {value!r}")
        return cls(
            request_id=data["request_id"],
            task_id=data["task_id"],
            created_at=data["created_at"],
            repo=data.get("repo"),
            workspace=data.get("workspace"),
            branch=data.get("branch"),
            paths=tuple(data.get("paths", [])),
            components=tuple(data.get("components", [])),
            task=data.get("task"),
            operation=data.get("operation"),
            evidence_refs=tuple(data.get("evidence_refs", [])),
        )


@dataclass(frozen=True)
class ActivationPolicy:
    """Versioned activation policy. The policy identifies itself in every
    decision. It never contains fixture answers."""

    policy_id: str = "activation-policy-v1"
    policy_version: str = "1"
    mode: ActivationMode = ActivationMode.TYPED
    newest_keep: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVATION_POLICY_SCHEMA,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "mode": self.mode.value,
            "newest_keep": self.newest_keep,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivationPolicy":
        version = data.get("schema_version", ACTIVATION_POLICY_SCHEMA)
        if version != ACTIVATION_POLICY_SCHEMA:
            raise ValueError(f"unsupported ActivationPolicy schema: {version!r}")
        unknown = set(data) - {
            "schema_version",
            "policy_id",
            "policy_version",
            "mode",
            "newest_keep",
        }
        if unknown:
            raise ValueError(f"unknown ActivationPolicy keys: {sorted(unknown)}")
        return cls(
            policy_id=data.get("policy_id", "activation-policy-v1"),
            policy_version=data.get("policy_version", "1"),
            mode=ActivationMode(data.get("mode", "typed")),
            newest_keep=int(data.get("newest_keep", 3)),
        )


@dataclass(frozen=True)
class ActivationDecision:
    """The activation verdict for one ledger item. `matched_scope` names
    the scope dimensions that overlapped; `epistemic` preserves the
    item's knowledge status for later framing (set for assumptions and
    pending verification, else None) and never promotes it."""

    item_id: str
    state: ActivationState
    reason_codes: tuple[str, ...]
    matched_scope: dict[str, Any]
    matched_dependencies: tuple[str, ...]
    request_features_used: tuple[str, ...]
    epistemic: str | None
    policy_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVATION_DECISION_SCHEMA,
            "item_id": self.item_id,
            "state": self.state.value,
            "reason_codes": list(self.reason_codes),
            "matched_scope": dict(self.matched_scope),
            "matched_dependencies": list(self.matched_dependencies),
            "request_features_used": list(self.request_features_used),
            "epistemic": self.epistemic,
            "policy_id": self.policy_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivationDecision":
        version = data.get("schema_version", ACTIVATION_DECISION_SCHEMA)
        if version != ACTIVATION_DECISION_SCHEMA:
            raise ValueError(f"unsupported ActivationDecision schema: {version!r}")
        return cls(
            item_id=data["item_id"],
            state=ActivationState(data["state"]),
            reason_codes=tuple(data.get("reason_codes", [])),
            matched_scope=dict(data.get("matched_scope", {})),
            matched_dependencies=tuple(data.get("matched_dependencies", [])),
            request_features_used=tuple(data.get("request_features_used", [])),
            epistemic=data.get("epistemic"),
            policy_id=data.get("policy_id", ""),
        )


@dataclass(frozen=True)
class ActivationResult:
    """The activation verdict for every item in the ledger state, in
    item-id order (a neutral stable ordering, not a ranking)."""

    request_id: str
    policy_id: str
    decisions: tuple[ActivationDecision, ...]

    def active_ids(self) -> tuple[str, ...]:
        return tuple(d.item_id for d in self.decisions if d.state is ActivationState.ACTIVE)

    def decision_for(self, item_id: str) -> ActivationDecision:
        for decision in self.decisions:
            if decision.item_id == item_id:
                return decision
        raise KeyError(item_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVATION_RESULT_SCHEMA,
            "request_id": self.request_id,
            "policy_id": self.policy_id,
            "decisions": [d.to_dict() for d in self.decisions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivationResult":
        version = data.get("schema_version", ACTIVATION_RESULT_SCHEMA)
        if version != ACTIVATION_RESULT_SCHEMA:
            raise ValueError(f"unsupported ActivationResult schema: {version!r}")
        return cls(
            request_id=data["request_id"],
            policy_id=data.get("policy_id", ""),
            decisions=tuple(ActivationDecision.from_dict(raw) for raw in data.get("decisions", [])),
        )
