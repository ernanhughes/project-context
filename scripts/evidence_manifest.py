"""Digest-pinned evidence manifests for frozen runs.

The frozen run artifacts under `.local/runs/` are local-only and git-ignored
(specs/privacy.md: publication needs sanitisation plus recorded human
approval). This tool makes the book's claims about them auditable without
publishing them: for each run it writes a committed manifest holding

  - the run identity (experiment, run, code commit, fixture/policy versions);
  - the SHA-256 and byte size of every artifact file;
  - the environment as recorded (reader model alias, decoding, ...);
  - the headline numbers RECOMPUTED from the artifacts (never typed in);
  - known limitations of the recorded run.

`--verify` recomputes everything from the local artifacts and fails if a
committed manifest no longer matches, so silent drift in a frozen run, or a
book number that no longer agrees with the run, is detectable. Verification
needs the local artifacts; without them the tool says so and exits 2.

Read-only over `.local/runs/`: it never writes into a run directory
(specs/evidence-model.md: append-only evidence).

    python scripts/evidence_manifest.py            # write manifests
    python scripts/evidence_manifest.py --verify   # check committed manifests
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
RUNS_ROOT = REPO / ".local" / "runs"
OUT_DIR = REPO / "evidence" / "manifests"
SCHEMA = "project_context.evidence_manifest.v1"

# (experiment, run, chapters of the companion book that cite it)
RUNS: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("compiler-v1", "run-001", (23, 24)),
    ("compiler-behavior-v1", "run-003", (24,)),
    ("compiler-behavior-v1", "run-003-transfer", (24,)),
)

VIOLATION_KEYS = (
    "authority_violations",
    "dependency_violations",
    "floor_violations",
    "freshness_violations",
    "group_violations",
    "scope_violations",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def compiler_v1_summary(run_dir: Path) -> dict[str, Any]:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    per_strategy: dict[str, Counter] = defaultdict(Counter)
    for row in results["evaluations"]:
        totals = per_strategy[row["strategy"]]
        totals["combinations"] += 1
        totals["status_correct"] += bool(row["status_correct"])
        totals["distractor_admission"] += int(row["distractor_admission"])
        totals["harmful_admission"] += int(row["harmful_admission"])
        totals["illegal_admission"] += int(row["illegal_admission"])
        for key in VIOLATION_KEYS:
            totals[key] += int(row[key])
    fixtures = sorted({row["fixture"] for row in results["evaluations"]})
    return {
        "combinations": len(results["evaluations"]),
        "fixtures": len(fixtures),
        "budgets": len(results["budgets"]),
        "strategies": len(results["strategies"]),
        "per_strategy": {name: dict(sorted(t.items())) for name, t in sorted(per_strategy.items())},
    }


def _record_key(rec: dict[str, Any]) -> tuple[Any, ...]:
    action = rec.get("parsed_action") or {}
    return (
        action.get("action"),
        action.get("target"),
        action.get("value"),
        action.get("reason_code"),
    )


def behavior_summary(run_dir: Path) -> dict[str, Any]:
    behavior = read_jsonl(run_dir / "behavior.jsonl")
    observations = read_jsonl(run_dir / "observations.jsonl")
    score: dict[str, float] = {}
    harmful: dict[str, bool] = {}
    for obs in observations:
        case = obs["target_id"]
        if obs["metric"].endswith(":task_score"):
            score[case] = float(obs["value"])
        elif obs["metric"].endswith(":harmful_action"):
            harmful[case] = obs["value"] == "True"
    cases: dict[str, dict[str, Any]] = {}
    for entry in behavior:
        rec = entry["record"]
        case_id = rec["experiment_case_id"]
        cases[case_id] = {
            "fixture": rec["fixture_id"],
            "condition": rec["condition_id"],
            "repeat": rec["repeat_index"],
            "parse_status": rec["parse_status"],
            "action": (rec.get("parsed_action") or {}).get("action"),
            "score": score.get(case_id),
            "harmful": harmful.get(case_id),
            "_record": _record_key(rec),
        }
    ladder = {(c["fixture"], c["condition"]): c for c in cases.values() if c["repeat"] == 0}

    def pair(a: str, b: str) -> dict[str, int]:
        out = Counter()
        for (fixture, condition), left in ladder.items():
            if condition != a or (fixture, b) not in ladder:
                continue
            right = ladder[(fixture, b)]
            out["pairs"] += 1
            out["records_changed"] += left["_record"] != right["_record"]
            out["action_names_changed"] += left["action"] != right["action"]
            if left["score"] is not None and right["score"] is not None:
                out["score_improved"] += right["score"] > left["score"]
                out["score_degraded"] += right["score"] < left["score"]
                out["score_same"] += right["score"] == left["score"]
        return dict(sorted(out.items()))

    public_cases = {
        case_id: {k: v for k, v in c.items() if k != "_record"}
        for case_id, c in sorted(cases.items())
    }
    return {
        "cases": len(cases),
        "parse_ok": sum(c["parse_status"] == "ok" for c in cases.values()),
        "harmful_case_observations": sum(bool(c["harmful"]) for c in cases.values()),
        "matched_pairs_repeat0": {
            "B0_to_B5": pair("B0", "B5"),
            "B4_to_B5": pair("B4", "B5"),
            "B5_to_BO": pair("B5", "BO"),
        },
        "cases_detail": public_cases,
    }


def git_subject(commit: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%s", commit],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def limitations(experiment: str, environment: dict[str, str]) -> list[str]:
    notes = [
        "Local-only artifact: the run directory is git-ignored and not published; "
        "this manifest pins it by digest so the book's numbers are checkable by "
        "anyone holding a copy.",
        "The run's own README (frozen, never edited) reads 'NOT A BOOK RESULT'. "
        "That was the label at freeze time; promotion to a book result is made by "
        "the book chapters that cite this manifest.",
        "Recorded timestamps are the fixed placeholder 2026-09-23T00:00:00Z, not wall-clock times.",
    ]
    if experiment == "compiler-behavior-v1":
        notes.append(
            "fixtures/compiler-behavior-v1/manifest.json is a frozen fixture record with two "
            "stale documentation fields: prompt_version reads 'behavior-prompt-v1' and "
            "evidence_note reads 'No model has run'. The prompt actually used, recorded in "
            "every behaviour record and in the code, is 'behavior-prompt-v2' (its "
            "version_notes explain the amendment). The fixture was not edited."
        )
        notes.append(
            "The run manifest's model/provider fields read 'synthetic-deterministic-v1' / "
            "'synthetic' because they describe the synthetic fixtures; the reader that "
            "produced the responses is recorded only in environment.reader_model."
        )
        if environment.get("reader_model", "").endswith(":latest"):
            notes.append(
                "The reader model was a moving alias (':latest'). No immutable model "
                "identity was captured: model_version is null and no digest was recorded. "
                "This cannot be recovered after the fact; a rerun is a new run."
            )
    return notes


def build_manifest(experiment: str, run: str, chapters: tuple[int, ...]) -> dict[str, Any]:
    run_dir = RUNS_ROOT / experiment / run
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    environment = {str(k): str(v) for k, v in run_manifest.get("environment", [])}
    files = [
        {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(run_dir.iterdir())
        if path.is_file()
    ]
    summary = (
        compiler_v1_summary(run_dir) if experiment == "compiler-v1" else behavior_summary(run_dir)
    )
    return {
        "schema_version": SCHEMA,
        "experiment_id": experiment,
        "run_id": run,
        "cited_by_book_chapters": list(chapters),
        "code_commit": run_manifest["git_commit"],
        "code_commit_subject": git_subject(run_manifest["git_commit"]),
        "run_manifest": {
            "evidence_class": run_manifest.get("evidence_class"),
            "experiment_version": run_manifest.get("experiment_version"),
            "fixture_version": run_manifest.get("fixture_version"),
            "policy_version": run_manifest.get("policy_version"),
            "environment": environment,
        },
        "artifact_location": f".local/runs/{experiment}/{run}/ (local-only, git-ignored)",
        "artifact_files": files,
        "recomputed_summary": summary,
        "known_limitations": limitations(experiment, environment),
    }


def dump(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="check committed manifests")
    args = parser.parse_args()

    status = 0
    for experiment, run, chapters in RUNS:
        target = OUT_DIR / f"{experiment}__{run}.json"
        try:
            current = dump(build_manifest(experiment, run, chapters))
        except FileNotFoundError as exc:
            print(f"UNVERIFIABLE {experiment}/{run}: local artifact missing ({exc})")
            status = max(status, 2)
            continue
        if args.verify:
            if not target.is_file():
                print(f"FAIL {experiment}/{run}: no committed manifest at {target.name}")
                status = 1
            elif target.read_text(encoding="utf-8") != current:
                print(f"FAIL {experiment}/{run}: local artifacts differ from committed manifest")
                status = 1
            else:
                print(f"OK   {experiment}/{run}: matches committed manifest")
        else:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            target.write_text(current, encoding="utf-8")
            print(f"wrote {target.name}")
    return status


if __name__ == "__main__":
    sys.exit(main())
