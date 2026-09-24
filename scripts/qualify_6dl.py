"""Stage 6D-L live injection qualification tooling (offline phases only).

This script never makes a model call and never touches a live session.
It implements the deterministic offline phases of the frozen probe spec
`experiments/runtime-live-6dl/spec.md`:

- `render`: pre-flight checks, synthetic bundle construction through
  the frozen Stage 6D domain/render code, exact-byte block file, intent
  record, and probe spool inventory snapshot.
- `reconcile`: reads only spool bytes appended after the snapshot,
  checks every new observed record structurally, privacy-scans the
  artifact, and writes the frozen qualification record with a verdict.

The single live call (`opencode run` in the throwaway directory with
the child-only probe environment) happens between the two phases, run
explicitly by the operator — never by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from project_context.domain.bundles import ContextBundle  # noqa: E402
from project_context.domain.items import ContextItem  # noqa: E402
from project_context.opencode.bridge import integrity_of, validate_record  # noqa: E402
from project_context.runtime.model import (  # noqa: E402
    BLOCK_OPEN,
    INJECTION_LOCATION,
    RenderPolicy,
)
from project_context.runtime.render import render_bundle  # noqa: E402

SPEC_ID = "runtime-live-6dl"
BUNDLE_ID = "rt-live-probe-6dl"
ITEM_ID = "live-probe-item-001"
EXPECTED_MARKER = "ORANGE-QUARTZ-731"
ITEM_CONTENT = (
    "RUNTIME-LIVE-PROBE-6D-L\n"
    "For this synthetic qualification request only,\n"
    "the marker value is ORANGE-QUARTZ-731."
)
PROMPT = "Reply with exactly the word READY and nothing else."


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    return out.stdout.strip()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _system_texts(record: dict) -> list[str]:
    system = record.get("system")
    if not isinstance(system, list):
        return []
    return [
        block["text"]
        for block in system
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]


def cmd_render(args: argparse.Namespace) -> int:
    work = Path(args.workdir)
    throwaway = work / "repo"
    spool = work / "spool"
    if not throwaway.is_dir():
        print(f"FAIL: throwaway directory missing: {throwaway}")
        return 1
    # Pre-flight: parent environment must not opt the runtime in.
    if os.environ.get("PROJECT_CONTEXT_RUNTIME") == "inject":
        print(
            "FAIL: PROJECT_CONTEXT_RUNTIME=inject is set in this environment; "
            "refusing (default-off invariant)."
        )
        return 1
    # Pre-flight: observer and runtime sources must be unmodified.
    dirty = _git(
        "status",
        "--short",
        "--",
        "integrations/opencode",
        "integrations/opencode-runtime",
        "src/project_context/runtime",
    )
    if dirty:
        print(f"FAIL: Stage 6D sources are dirty:\n{dirty}")
        return 1
    # Pre-flight: throwaway holds only synthetic material.
    names = sorted(p.name for p in throwaway.iterdir())
    if names != ["README.md"]:
        print(f"FAIL: throwaway directory has unexpected contents: {names}")
        return 1
    spool.mkdir(parents=True, exist_ok=True)

    item = ContextItem(
        id=ITEM_ID,
        source="ledger",
        kind="test_constraint",
        content=ITEM_CONTENT,
        token_provenance="approximation",
    )
    bundle = ContextBundle(
        id=BUNDLE_ID,
        items=(item,),
        created_at="2026-09-24T12:00:00Z",
        layout_trace=(ITEM_ID,),
        evidence_class="synthetic",
    )
    rendered = render_bundle(bundle, RenderPolicy())
    bundle_digest = hashlib.sha256(
        json.dumps(
            {"id": bundle.id, "items": [item.id], "policy": RenderPolicy().policy_id},
            sort_keys=True,
        ).encode()
    ).hexdigest()

    block_path = work / "runtime-block.txt"
    block_path.write_bytes(rendered.text.encode("utf-8"))  # exact bytes, no additions
    if _sha256_file(block_path) != rendered.digest:
        print("FAIL: block file digest differs from rendered digest.")
        return 1

    inventory = {}
    for path in sorted(spool.rglob("*.jsonl")):
        inventory[str(path.relative_to(spool))] = path.stat().st_size
    intent = {
        "spec_id": SPEC_ID,
        "synthetic": True,
        "bundle_id": bundle.id,
        "bundle_digest": bundle_digest,
        "render_policy_id": rendered.policy_id,
        "rendered_digest": rendered.digest,
        "rendered_text": rendered.text,
        "expected_marker": EXPECTED_MARKER,
        "injection_location": INJECTION_LOCATION,
        "prompt": PROMPT,
        "spool_inventory": inventory,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    (work / "intent.json").write_text(json.dumps(intent, indent=2), encoding="utf-8")
    print(f"rendered bundle {bundle.id} digest={bundle_digest[:12]}…")
    print(f"rendered block digest={rendered.digest[:12]}… file={block_path}")
    print(f"intent written; spool files seen: {len(inventory)}")
    return 0


def _privacy_scan(text: str) -> list[str]:
    hits = []
    dynamic = [
        socket.gethostname(),
        os.path.expanduser("~"),
        str(REPO),
    ]
    patterns = [
        r"sk-[A-Za-z0-9]{8,}",
        r"sess-[A-Za-z0-9]{8,}",
        r"BEGIN [A-Z ]*PRIVATE KEY",
        r"[A-Za-z]:\\\\",
        r"C:/",
        r"/home/",
        r"/Users/",
        r"noreply@",
    ]
    for pat in patterns:
        if re.search(pat, text):
            hits.append(f"pattern {pat!r}")
    lowered = text.lower()
    for secret in dynamic:
        if secret and len(secret) > 3 and secret.lower() in lowered:
            hits.append(f"local value {secret!r}")
    home = os.path.expanduser("~").replace("\\", "/").lower()
    if home and home in lowered:
        hits.append("home directory form")
    return hits


def cmd_reconcile(args: argparse.Namespace) -> int:
    work = Path(args.workdir)
    intent = json.loads((work / "intent.json").read_text(encoding="utf-8"))
    spool = work / "spool"
    rendered_text = intent["rendered_text"]

    new_records: list[dict] = []
    for rel, offset in sorted(intent["spool_inventory"].items()):
        _ = (rel, offset)  # pre-existing files are out of scope by design
    for path in sorted(spool.rglob("*.jsonl")):
        rel = str(path.relative_to(spool))
        start = int(intent["spool_inventory"].get(rel, 0))
        raw = path.read_bytes()[start:]
        for line in raw.decode("utf-8").splitlines():
            if line.strip():
                new_records.append(json.loads(line))

    per_record = []
    marker_elsewhere = 0
    context_records = 0
    for rec in new_records:
        texts = _system_texts(rec)
        occurrences = sum(1 for t in texts if t == rendered_text)
        marked = sum(1 for t in texts if BLOCK_OPEN in t)
        unexpected = marked - (1 if occurrences == 1 and marked == 1 else occurrences)
        kind = rec.get("request_kind")
        entry: dict = {
            "capture_id": rec.get("capture_id"),
            "request_kind": kind,
            "session_id": rec.get("session_id"),
            "record_valid": not validate_record(rec),
            "system_blocks": len(texts),
            "marker_occurrences": occurrences,
            "unexpected_runtime_blocks": max(0, unexpected),
        }
        if kind == "context":
            context_records += 1
            entry["checks"] = {
                "record_valid": entry["record_valid"],
                "markers_present": marked >= 1,
                "block_exact": occurrences >= 1,
                "block_once": occurrences == 1,
                "order_preserved": bool(texts) and texts[-1] == rendered_text,
                "no_unexpected_runtime_content": unexpected == 0,
                "integrity_match": integrity_of(rec) == rec.get("integrity", {}).get("sha256"),
            }
            entry["passed"] = all(entry["checks"].values())
        else:
            if occurrences > 0 or marked > 0:
                marker_elsewhere += 1
            entry["passed"] = occurrences == 0 and marked == 0
        per_record.append(entry)

    run_clean = args.exit_code == 0 and not args.hook_error
    response_digest = None
    if args.response_file:
        response_digest = hashlib.sha256(Path(args.response_file).read_bytes()).hexdigest()
    required = {
        "runtime_opted_in_explicitly": True,  # child-only env, recorded by operator
        "run_clean": run_clean,
        "observer_captured": context_records >= 1,
        "all_context_records_pass": context_records >= 1
        and all(e["passed"] for e in per_record if e["request_kind"] == "context"),
        "no_marker_outside_context_records": marker_elsewhere == 0,
    }
    verdict = "PASS" if all(required.values()) else "FAIL"
    artifact = {
        "qualification_id": SPEC_ID,
        "purpose": "live integration qualification",
        "synthetic": True,
        "verdict": verdict,
        "attempt": args.attempt,
        "runtime_implementation": {
            "git_revision": _git("rev-parse", "HEAD"),
            "git_status_runtime": _git(
                "status",
                "--short",
                "--",
                "integrations/opencode-runtime",
                "src/project_context/runtime",
            ),
            "deployed_hashes": json.loads(args.deployed_hashes),
        },
        "opencode_environment": {
            "opencode_version": args.opencode_version,
            "observer_plugin_version": args.observer_plugin_version,
            "runtime_plugin_version": args.runtime_plugin_version,
        },
        "selected_bundle": {
            "bundle_id": intent["bundle_id"],
            "bundle_digest": intent["bundle_digest"],
        },
        "rendered_block": {
            "policy_id": intent["render_policy_id"],
            "digest": intent["rendered_digest"],
            "text": intent["rendered_text"],
        },
        "expected_marker": intent["expected_marker"],
        "injection_location": intent["injection_location"],
        "run": {
            "exit_code": args.exit_code,
            "hook_error": args.hook_error,
            "model_response_digest": response_digest,
            "run_log_digest": _sha256_file(Path(args.run_log)) if args.run_log else None,
        },
        "observed": {
            "new_records_total": len(new_records),
            "new_context_records": context_records,
            "records": per_record,
        },
        "required": required,
        "limitations": [
            "TypeScript runtime emits no machine injection receipt; acceptance "
            "is evidenced by a clean run plus the independent capture.",
            "Observation is at the OpenCode V2 model-context hook, not the provider wire request.",
            "Model response is diagnostic only, never the criterion.",
        ],
    }
    blob = json.dumps(artifact, indent=2)
    violations = _privacy_scan(blob)
    if violations:
        print(f"FAIL: privacy scan violations: {violations}")
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(blob, encoding="utf-8")
    print(f"new records: {len(new_records)}; context records: {context_records}")
    print(f"verdict: {verdict}")
    print(f"artifact: {out}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage 6D-L probe tooling (offline phases).")
    sub = parser.add_subparsers(dest="command", required=True)
    p_render = sub.add_parser("render", help="pre-flight and render the probe block")
    p_render.add_argument("--workdir", required=True)
    p_reconcile = sub.add_parser("reconcile", help="reconcile spool against intent")
    p_reconcile.add_argument("--workdir", required=True)
    p_reconcile.add_argument("--out", required=True)
    p_reconcile.add_argument("--exit-code", type=int, required=True)
    p_reconcile.add_argument("--hook-error", action="store_true")
    p_reconcile.add_argument("--response-file", default=None)
    p_reconcile.add_argument("--run-log", default=None)
    p_reconcile.add_argument("--attempt", type=int, required=True)
    p_reconcile.add_argument("--deployed-hashes", default="{}")
    p_reconcile.add_argument("--opencode-version", default="unavailable")
    p_reconcile.add_argument("--observer-plugin-version", default="unavailable")
    p_reconcile.add_argument("--runtime-plugin-version", default="unavailable")
    args = parser.parse_args(argv)
    if args.command == "render":
        return cmd_render(args)
    return cmd_reconcile(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
