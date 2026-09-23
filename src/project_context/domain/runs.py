"""Run identity: everything needed to reconstruct an experiment run.

A run can be reconstructed from (experiment_id, experiment_version,
fixture/corpus version, provider, model, model parameters, policy version,
seed, environment) plus the git commit that contained the runner. Timestamps
are recorded but excluded from identity: two manifests differing only in
timestamp describe the same run configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "project_context.run_manifest.v1"


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    experiment_id: str
    experiment_version: str
    git_commit: str
    timestamp: str
    provider: str
    model: str
    evidence_class: str
    model_params: tuple[tuple[str, str], ...] = ()
    policy_version: str | None = None
    fixture_id: str | None = None
    fixture_version: str | None = None
    corpus_ref: str | None = None
    seed: int | None = None
    environment: tuple[tuple[str, str], ...] = ()

    def identity_key(self) -> tuple[Any, ...]:
        """Reconstruction identity. Timestamp deliberately excluded."""
        return (
            self.experiment_id,
            self.experiment_version,
            self.git_commit,
            self.provider,
            self.model,
            self.model_params,
            self.policy_version,
            self.fixture_id,
            self.fixture_version,
            self.corpus_ref,
            self.seed,
        )

    def same_configuration(self, other: "RunManifest") -> bool:
        return self.identity_key() == other.identity_key()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "experiment_version": self.experiment_version,
            "git_commit": self.git_commit,
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "evidence_class": self.evidence_class,
            "model_params": [list(pair) for pair in self.model_params],
            "policy_version": self.policy_version,
            "fixture_id": self.fixture_id,
            "fixture_version": self.fixture_version,
            "corpus_ref": self.corpus_ref,
            "seed": self.seed,
            "environment": [list(pair) for pair in self.environment],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunManifest":
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported RunManifest schema: {version!r}")
        return cls(
            run_id=data["run_id"],
            experiment_id=data["experiment_id"],
            experiment_version=data["experiment_version"],
            git_commit=data["git_commit"],
            timestamp=data["timestamp"],
            provider=data["provider"],
            model=data["model"],
            evidence_class=data.get("evidence_class", "synthetic"),
            model_params=tuple(tuple(pair) for pair in data.get("model_params", [])),
            policy_version=data.get("policy_version"),
            fixture_id=data.get("fixture_id"),
            fixture_version=data.get("fixture_version"),
            corpus_ref=data.get("corpus_ref"),
            seed=data.get("seed"),
            environment=tuple(tuple(pair) for pair in data.get("environment", [])),
        )
