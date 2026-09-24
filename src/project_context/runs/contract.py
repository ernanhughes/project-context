"""Evidence-run contract (specs/experiment-contract.md).

A run intended to support a published claim records a small set of reserved
keys in `RunManifest.environment`, on top of the fields the manifest already
has. This module says which keys, and checks a manifest for them. It adds no
new record type: the manifest, invocation and observation records keep their
existing shapes.

Exploratory runs are exempt from the preregistration requirement, and can never
be cited as confirmatory evidence.
"""

from __future__ import annotations

from typing import Any

# Needed by every evidence run.
REQUIRED_EVIDENCE_KEYS: tuple[str, ...] = (
    "run_purpose",
    "experiment_family",
    "preregistration",  # "<path>@<commit>" of the frozen preregistration
    "fixture_revision",
    "configuration_revision",
    "task_population",
)

# Needed in addition when a live model produced the responses.
REQUIRED_LIVE_KEYS: tuple[str, ...] = (
    "reader_model",
    "reader_model_digest",
    "reader_model_identity_source",
    "reader_model_alias_moving",
    "temperature",
    "decoding_seed",
)

PURPOSES = ("evidence", "exploratory")


def check_evidence_manifest(manifest: dict[str, Any], *, live: bool) -> list[str]:
    """Return the problems that stop this manifest from supporting a claim.

    An empty list means the manifest satisfies the contract. `manifest` is the
    dict form of a `RunManifest`.
    """
    env = {str(k): str(v) for k, v in manifest.get("environment", [])}
    problems: list[str] = []
    purpose = env.get("run_purpose")
    if purpose not in PURPOSES:
        return [f"run_purpose must be one of {PURPOSES}, got {purpose!r}"]
    if purpose == "exploratory":
        # Exploratory runs stay local and are labelled; only the label is required.
        return []
    for key in REQUIRED_EVIDENCE_KEYS:
        if not env.get(key):
            problems.append(f"missing environment key: {key}")
    prereg = env.get("preregistration", "")
    if prereg and "@" not in prereg:
        problems.append("preregistration must be '<path>@<commit>'")
    if live:
        for key in REQUIRED_LIVE_KEYS:
            if not env.get(key):
                problems.append(f"missing environment key for a live run: {key}")
        if env.get("reader_model_alias_moving") == "True":
            problems.append("evidence run used a moving model alias")
        if env.get("reader_model_digest") == "unavailable":
            problems.append("evidence run has no recorded reader model digest")
    for field in ("git_commit", "experiment_id", "experiment_version", "evidence_class"):
        if not manifest.get(field):
            problems.append(f"missing manifest field: {field}")
    return problems
