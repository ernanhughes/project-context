"""Digest-pinned manifests for frozen findings that are not `evidence/runs/` runs.

`scripts/evidence_manifest.py` pins runs. This tool pins the other kinds of
frozen finding the companion book cites: live transport qualifications, the
instrumentation-failure result of a behavioural wave, and the cross-language
parity of the compiler. For each finding it writes a committed manifest under
`evidence/manifests/` holding

  - the finding's short name (the name the book uses);
  - the SHA-256 and byte size of every artifact file;
  - headline values RECOMPUTED from those artifacts, never typed in;
  - the known limitations of the recorded finding.

It is read-only over every artifact. It never edits a frozen file. The one
write it performs on artifacts is `publish-live`, which copies the small
synthetic files of a live compile, inject and observe run out of a scratch
directory, byte for byte, after the same sanitisation scan that
`publish_evidence_runs.py` applies, and refuses to overwrite a differing file.

    python scripts/evidence_findings.py                    # write manifests
    python scripts/evidence_findings.py --verify           # check them
    python scripts/evidence_findings.py publish-live SRC   # freeze a live run

The parity finding is external: its artifacts live in the compiler repository.
It is verified only when a sibling checkout is present (exit code 2 otherwise).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "evidence" / "manifests"
SCHEMA = "project_context.evidence_manifest.v1"
COMPILER_CHECKOUT = REPO.parent / "project-context-compiler"

LIVE_DIR = "evidence/qualifications/compile-inject-observe-live"
LIVE_FILES = (
    "compiler-canary.json",
    "receipt.json",
    "request.json",
    "candidates.json",
    "policy.json",
    "runtime-trace.jsonl",
)
PRIVATE_DIGESTS = "private-artifacts.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def file_table(paths: list[Path], base: Path) -> list[dict[str, Any]]:
    return [
        {
            "name": p.relative_to(base).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(paths)
    ]


def dump(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- live run


def summarise_live(directory: Path) -> dict[str, Any]:
    canary = read_json(directory / "compiler-canary.json")
    receipt = read_json(directory / "receipt.json")
    trace = read_jsonl(directory / "runtime-trace.jsonl")
    hooks = [r for r in trace if r.get("kind") == "hook"]
    if len(hooks) != 1:
        raise ValueError(
            f"expected exactly one hook record in the runtime trace, found {len(hooks)}"
        )
    hook = hooks[0]
    problems = []
    if canary["transport"]["pre_blocks"] != hook["preBlocks"]:
        problems.append("canary pre_blocks disagrees with the runtime trace")
    if canary["transport"]["post_blocks"] != hook["postBlocks"]:
        problems.append("canary post_blocks disagrees with the runtime trace")
    if canary["compilation"]["bundle_hash"] != receipt["bundle_hash"]:
        problems.append("canary and receipt disagree on the bundle hash")
    if canary["observer"]["session_id"] != hook["sessionID"]:
        problems.append("canary observer session differs from the runtime trace session")
    if problems:
        raise ValueError("; ".join(problems))
    request = read_json(directory / "request.json")
    candidates = read_json(directory / "candidates.json")["candidates"]
    return {
        "canary_status": canary["status"],
        "receipt_status": receipt["status"],
        "compilation_success": canary["compilation"]["success"],
        "candidate_count": len(candidates),
        "usable_token_budget": request["usable_token_budget"],
        "runtime_outcome": hook["outcome"],
        "system_blocks_before": hook["preBlocks"],
        "system_blocks_after": hook["postBlocks"],
        "observer_sequence": canary["observer"]["sequence"],
        "marker_count": canary["observer"]["marker_count"],
        "reconciliation": canary["reconciliation"],
        "requested_model_equals_observed": receipt["model_match"],
        "failures": canary["failures"],
        "compiler_revision": canary["compiler"]["revision"],
    }


def live_limitations(directory: Path) -> list[str]:
    notes = [
        "One trivial synthetic request with a single one-item bundle. It establishes that the "
        "compile, inject and observe chain works end to end at the OpenCode model-context hook. "
        "It says nothing about behaviour.",
        "Observation is at the model-context hook, not the provider wire request. Provider-side "
        "rewriting, added material, cache decisions and the model's internal representation are "
        "not observed.",
        "Token counts in the bundle are the compiler's word-based estimate and the candidate's "
        "declared count, not provider-reported counts.",
        "The observer's capture record contains the full model context, including system "
        "prompts, and stays private. Its digest is recorded in private-artifacts.json so the "
        "local original can be checked against this frozen finding by its owner.",
        "The scratch directory's evidence.json and model output are not published: the first "
        "holds a machine path and the second is diagnostic only.",
    ]
    return notes


# ---------------------------------------------------------------- failed wave


def summarise_wave(result_path: Path) -> dict[str, Any]:
    result = read_json(result_path)
    runs = result["runs"]
    reasons = Counter(r["transport"]["reason"] for r in runs)
    return {
        "experiment": result["experiment_id"],
        "planned_runs": result["run_count"],
        "completed_runs": len(runs),
        "valid_behavioural_runs": sum(bool(r["graded"].get("valid")) for r in runs),
        "transport_fail_runs": sum(r["transport"]["status"] == "FAIL" for r in runs),
        "observed_context_records": sum(int(r["transport"].get("records", 0)) for r in runs),
        "transport_failure_reasons": dict(sorted(reasons.items())),
        "hard_stop": result.get("hard_stop"),
    }


WAVE_LIMITATIONS = [
    "Inconclusive, not a failed behavioural hypothesis. The transport layer failed on every "
    "run, so the behavioural question was never tested and nothing here measures whether "
    "context helps.",
    "Per-run graded contents are preserved in the artifact as excluded records for audit only.",
    "The result file was frozen as recorded; its hard_stop field was appended after its "
    "own digest was computed, as the companion result document notes.",
]


# ---------------------------------------------------------------- earlier qualifications


def summarise_qualifications(directory: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in ("runtime-live-6dl", "runtime-live-6dr1"):
        q = read_json(directory / f"{name}.json")
        record = (q.get("observed", {}).get("records") or [{}])[0]
        out[name] = {
            "verdict": q["verdict"],
            "attempt": q["attempt"],
            "synthetic": q["synthetic"],
            "expected_marker_occurrences_observed": record.get("marker_occurrences"),
            "all_context_records_pass": q["required"]["all_context_records_pass"],
            "runtime_revision": q["runtime_implementation"]["git_revision"],
        }
    return out


QUAL_LIMITATIONS = [
    "Marker probes of an earlier plugin layout (separate observer and runtime plugins, since "
    "replaced by one package). They show injection and independent observation of a fixed "
    "marker. They do not involve the compiler.",
    "The first attempt failed (the marker never reached the observed context) and the second "
    "passed after the runtime was repaired. Both are kept.",
    "Observation is at the OpenCode model-context hook, not the provider wire request.",
    "Loader and execution gates rest on a server log and an opt-in runtime trace that are "
    "local-only and digest-recorded.",
]


# ---------------------------------------------------------------- parity (external)


def parity_digests(checkout: Path) -> dict[str, Any]:
    golden = sorted((checkout / "conformance" / "golden" / "python-v0.1.0").glob("*.json"))
    fixtures = sorted((checkout / "conformance" / "compiler-v1").glob("*.json"))

    def combined(paths: list[Path]) -> str:
        digest = hashlib.sha256()
        for p in paths:
            digest.update(f"{p.name} {sha256_file(p)}\n".encode())
        return digest.hexdigest()

    return {
        "golden_case_files": sum(p.name != "manifest.json" for p in golden),
        "golden_files_including_index": len(golden),
        "golden_set_sha256": combined(golden),
        "fixture_files": len(fixtures),
        "fixture_set_sha256": combined(fixtures),
    }


# Recorded when the finding was frozen (the compiler checkout at that revision was run).
PARITY_RECORDED = {
    "compiler_repository": "https://github.com/ernanhughes/project-context-compiler",
    "compiler_revision": "49f726575f685ddbf839f9b4a53d3f39b8759b2e",
    "reference_implementation": "Python, tag python-v0.1.0 in the same repository",
    "conformance_cli_output": {
        "fixtures": 14,
        "budgets": 3,
        "cases": 42,
        "success_cases": 34,
        "expected_failure_cases": 8,
        "semantic_mismatches": 0,
        "serialization_mismatches": 0,
        "budget_violations": 0,
        "result": "PASS",
    },
    "parity_test": "node --test tests/conformance/parity.test.ts: 44 tests, 44 pass, 0 fail",
}

PARITY_LIMITATIONS = [
    "Parity shows the TypeScript implementation reproduces the frozen Python outputs on 42 "
    "compilations. It is a statement of equivalence, not of correctness.",
    "The frozen Python outputs include two trace defects that the port reproduced faithfully: "
    "every dependency_closure is empty, and budget_after equals budget_before. Both are "
    "recorded here as part of what parity means. A later corrected trace is a new schema, not "
    "a rewrite of these goldens.",
    "External artifacts: the goldens and fixtures live in the compiler repository. This "
    "manifest pins them by digest and records the run of the conformance command at the "
    "recorded revision; it cannot re-run Node.",
    "The 252-way strategy comparison of the compiler-v1 run was produced by the Python "
    "implementation and is not part of this parity finding.",
]


# ---------------------------------------------------------------- findings table

FINDINGS: tuple[dict[str, Any], ...] = (
    {
        "slug": "compile-inject-observe-live",
        "name": "Live compile-to-observe qualification",
        "kind": "transport qualification",
        "chapters": (25,),
        "dir": LIVE_DIR,
        "files": list(LIVE_FILES) + [PRIVATE_DIGESTS],
        "summary": summarise_live,
        "limitations": live_limitations,
    },
    {
        "slug": "instrumentation-failure",
        "name": "Instrumentation failure",
        "kind": "inconclusive behavioural wave",
        "chapters": (25, 26),
        "dir": "evidence/oracle-leverage-v1",
        "files": ["result.json"],
        "summary": lambda d: summarise_wave(d / "result.json"),
        "limitations": lambda d: WAVE_LIMITATIONS,
    },
    {
        "slug": "earlier-runtime-qualifications",
        "name": "Earlier runtime qualifications",
        "kind": "transport qualification",
        "chapters": (25,),
        "dir": "evidence/qualifications",
        "files": ["runtime-live-6dl.json", "runtime-live-6dr1.json"],
        "summary": summarise_qualifications,
        "limitations": lambda d: QUAL_LIMITATIONS,
    },
)


def build_manifest(finding: dict[str, Any]) -> dict[str, Any]:
    directory = REPO / finding["dir"]
    paths = [directory / name for name in finding["files"]]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(", ".join(str(p) for p in missing))
    return {
        "schema_version": SCHEMA,
        "finding_name": finding["name"],
        "finding_kind": finding["kind"],
        "cited_by_book_chapters": list(finding["chapters"]),
        "artifact_location": finding["dir"] + "/",
        "artifact_files": file_table(paths, directory),
        "recomputed_summary": finding["summary"](directory),
        "known_limitations": finding["limitations"](directory),
    }


def build_parity_manifest() -> dict[str, Any]:
    if not COMPILER_CHECKOUT.is_dir():
        raise FileNotFoundError(COMPILER_CHECKOUT)
    return {
        "schema_version": SCHEMA,
        "finding_name": "Implementation parity",
        "finding_kind": "structural: cross-language conformance",
        "cited_by_book_chapters": [24],
        "artifact_location": "external: conformance/ in the compiler repository",
        "recorded_at_freeze": PARITY_RECORDED,
        "recomputed_summary": parity_digests(COMPILER_CHECKOUT),
        "known_limitations": PARITY_LIMITATIONS,
    }


def all_targets() -> list[tuple[str, Callable[[], dict[str, Any]]]]:
    targets: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        (f["slug"], (lambda f=f: build_manifest(f))) for f in FINDINGS
    ]
    targets.append(("implementation-parity", build_parity_manifest))
    return targets


# ---------------------------------------------------------------- publication of a live run


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location(
        "publish_evidence_runs", Path(__file__).resolve().parent / "publish_evidence_runs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _src(source: Path, name: str) -> Path:
    """The runtime trace sits in a trace/ sub-directory of a smoke run."""
    nested = source / "trace" / name
    return nested if name == "runtime-trace.jsonl" and nested.is_file() else source / name


def publish_live(source: Path, private_captures: Path | None) -> int:
    gate = _load_gate()
    problems: list[str] = []
    for name in LIVE_FILES:
        path = _src(source, name)
        if not path.is_file():
            problems.append(f"missing {name}")
            continue
        for label in gate.scan(path):
            problems.append(f"{name}: matches '{label}'")
    if problems:
        print("REFUSED: sanitisation gate failed")
        for p in problems:
            print(f"  - {p}")
        return 1
    target = REPO / LIVE_DIR
    target.mkdir(parents=True, exist_ok=True)
    for name in LIVE_FILES:
        data = _src(source, name).read_bytes()
        dest = target / name
        if dest.exists() and dest.read_bytes() != data:
            raise SystemExit(f"refusing to overwrite differing published file: {dest}")
        if not dest.exists():
            shutil.copyfile(_src(source, name), dest)
            print(f"copied {name}")
    digests = target / PRIVATE_DIGESTS
    if private_captures is not None and not digests.exists():
        payload = {
            "note": "Digests of private local artifacts that back this finding. The artifacts "
            "themselves are not published because they contain full model context.",
            "artifacts": {
                "observer capture record (captures.jsonl)": {
                    "bytes": private_captures.stat().st_size,
                    "sha256": sha256_file(private_captures),
                }
            },
        }
        digests.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {PRIVATE_DIGESTS}")
    return 0


# ---------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="check committed manifests")
    sub = parser.add_subparsers(dest="command")
    pub = sub.add_parser("publish-live", help="freeze a live compile-inject-observe run")
    pub.add_argument("source", type=Path)
    pub.add_argument("--private-captures", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.command == "publish-live":
        return publish_live(args.source, args.private_captures)

    status = 0
    for slug, build in all_targets():
        target = OUT_DIR / f"{slug}.json"
        try:
            current = dump(build())
        except FileNotFoundError as exc:
            print(f"UNVERIFIABLE {slug}: artifact missing ({exc})")
            status = max(status, 2)
            continue
        if args.verify:
            if not target.is_file():
                print(f"FAIL {slug}: no committed manifest at {target.name}")
                status = 1
            elif target.read_text(encoding="utf-8") != current:
                print(f"FAIL {slug}: artifacts differ from committed manifest")
                status = 1
            else:
                print(f"OK   {slug}: matches committed manifest")
        else:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            target.write_text(current, encoding="utf-8")
            print(f"wrote {target.name}")
    return status


if __name__ == "__main__":
    sys.exit(main())
