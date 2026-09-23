"""Write and validate frozen run artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from project_context.corpus.manifest import scan_text_for_secrets
from project_context.domain.evaluation import EvaluationLog
from project_context.domain.runs import RunManifest

REQUIRED_FILES = ("manifest.json", "observations.jsonl", "results.json", "README.md")


def write_artifact(
    root: Path,
    manifest: RunManifest,
    log: EvaluationLog,
    results: dict,
    *,
    readme_text: str,
) -> Path:
    """Write a complete run directory. Returns the run directory path."""
    run_dir = root / manifest.experiment_id / manifest.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "observations.jsonl").write_text(
        "".join(json.dumps(obs.to_dict(), sort_keys=True) + "\n" for obs in log.observations),
        encoding="utf-8",
    )
    payload = dict(results)
    payload.setdefault("evidence_class", manifest.evidence_class)
    (run_dir / "results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / "README.md").write_text(readme_text, encoding="utf-8")
    return run_dir


def validate_artifact(run_dir: Path) -> list[str]:
    """Check an artifact directory. Returns a list of error strings;
    empty means valid. Never raises on malformed content."""
    errors: list[str] = []
    for name in REQUIRED_FILES:
        if not (run_dir / name).is_file():
            errors.append(f"missing required file: {name}")
    if errors:
        return errors
    try:
        manifest_raw = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [f"manifest.json unreadable: {exc}"]
    try:
        manifest = RunManifest.from_dict(manifest_raw)
    except (KeyError, ValueError, TypeError) as exc:
        return [f"manifest.json invalid: {exc}"]
    if not manifest.git_commit:
        errors.append("manifest git_commit is empty")
    if not manifest.experiment_id:
        errors.append("manifest experiment_id is empty")
    try:
        lines = (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.strip():
                json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"observations.jsonl unreadable: {exc}")
    try:
        results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"results.json unreadable: {exc}")
        results = {}
    if manifest.evidence_class == "synthetic":
        blob = json.dumps(results)
        if '"provider-observed"' in blob or "provider" in str(results.get("telemetry_source", "")):
            errors.append("synthetic artifact claims provider-observed evidence")
    for name in ("results.json", "README.md", "observations.jsonl"):
        text = (run_dir / name).read_text(encoding="utf-8")
        hits = scan_text_for_secrets(text)
        if hits:
            errors.append(f"{name} matches secret patterns: {', '.join(hits)}")
    return errors
