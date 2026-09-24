"""Stage 6D-L / 6D-R1 live qualification tooling (offline phases only).

This script never makes a model call and never touches a live session.
It implements the deterministic offline phases of the frozen probe specs
`experiments/runtime-live-6dl/spec.md` and
`experiments/runtime-live-6dr1/spec.md`:

- `render`: pre-flight checks, synthetic bundle construction through
  the frozen Stage 6D domain/render code, exact-byte block file, intent
  record, and probe spool inventory snapshot.
- `reconcile`: reads only spool bytes appended after the snapshot,
  checks every new observed record structurally, privacy-scans the
  artifact, and writes the frozen qualification record with a verdict.
  With `--r1` it additionally evaluates the staged gate ladder
  (loader, execution, mutation, observation, reconciliation) from the
  server log and the runtime trace file.

The live calls (`opencode run` in the throwaway directory with the
child-only probe environment) happen between the two phases, run
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
PROBE_TAG = "RUNTIME-LIVE-PROBE-6D-L"
PROMPT = "Reply with exactly the word READY and nothing else."


def _item_content(tag: str, marker: str) -> str:
    return f"{tag}\nFor this synthetic qualification request only,\nthe marker value is {marker}."


ITEM_CONTENT = _item_content(PROBE_TAG, EXPECTED_MARKER)


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

    spec_id = args.spec_id or SPEC_ID
    bundle_id = args.bundle_id or BUNDLE_ID
    item_id = args.item_id or ITEM_ID
    marker = args.marker or EXPECTED_MARKER
    tag = "RUNTIME-LIVE-PROBE-6D-R1" if spec_id == "runtime-live-6dr1" else PROBE_TAG
    item = ContextItem(
        id=item_id,
        source="ledger",
        kind="test_constraint",
        content=_item_content(tag, marker),
        token_provenance="approximation",
    )
    bundle = ContextBundle(
        id=bundle_id,
        items=(item,),
        created_at="2026-09-24T12:00:00Z",
        layout_trace=(item_id,),
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
        "spec_id": spec_id,
        "synthetic": True,
        "bundle_id": bundle.id,
        "bundle_digest": bundle_digest,
        "render_policy_id": rendered.policy_id,
        "rendered_digest": rendered.digest,
        "rendered_text": rendered.text,
        "expected_marker": marker,
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
        "qualification_id": intent.get("spec_id", SPEC_ID),
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
    if args.r1:
        gates, gate_detail = _evaluate_gates(args, per_record, context_records)
        artifact["mode"] = "6dr1"
        artifact["prev_qualification"] = args.prev_qualification
        artifact["gates"] = gates
        artifact["gate_detail"] = gate_detail
        artifact["ordering"] = _ordering(gates, gate_detail)
        artifact["verdict"] = "PASS" if all(gates.values()) else "FAIL"
        artifact["limitations"] = artifact["limitations"] + [
            "Loader and execution gates rest on the server log and the "
            "opt-in runtime trace, both local-only and digest-recorded.",
            "Mutation-before-observer is inferred from trace plus capture, "
            "not from registration order.",
        ]
        verdict = artifact["verdict"]
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


def _evaluate_gates(
    args: argparse.Namespace, per_record: list[dict], context_records: int
) -> tuple[dict[str, bool], dict]:
    """Staged gate ladder for 6D-R1. Server-log text and trace content
    stay local; only digests, booleans, and outcome summaries enter."""
    entrypoint_found = False
    server_log_digest = None
    if args.server_log:
        raw = Path(args.server_log).read_bytes()
        server_log_digest = hashlib.sha256(raw).hexdigest()
        blob = raw.decode("utf-8", errors="replace").replace("\\", "/")
        entrypoint_found = f"{args.plugin_dir}/index.ts" in blob and "loading plugin" in blob
    setup_found = False
    outcomes: list[str] = []
    deltas: list[int] = []
    hook_records = 0
    trace_digest = None
    if args.trace_file and Path(args.trace_file).exists():
        trace_digest = _sha256_file(Path(args.trace_file))
        for line in Path(args.trace_file).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("kind") == "setup" and rec.get("hookRegistered") is True:
                setup_found = True
            if rec.get("kind") == "hook":
                hook_records += 1
                outcomes.append(str(rec.get("outcome")))
                try:
                    deltas.append(int(rec.get("postBlocks", 0)) - int(rec.get("preBlocks", 0)))
                except (TypeError, ValueError):
                    deltas.append(-99)
    injected = any(o == "injected" and d == 1 for o, d in zip(outcomes, deltas))
    context_pass = context_records >= 1 and all(
        e["passed"] for e in per_record if e["request_kind"] == "context"
    )
    observed_marker = context_records >= 1 and all(
        e["checks"]["markers_present"]
        and e["checks"]["block_exact"]
        and e["checks"]["block_once"]
        and e["checks"]["order_preserved"]
        for e in per_record
        if e["request_kind"] == "context"
    )
    gates = {
        "loader": entrypoint_found and setup_found,
        "execution": hook_records >= 1,
        "mutation": injected,
        "observation": observed_marker,
        "reconciliation": context_pass,
    }
    detail = {
        "server_log_digest": server_log_digest,
        "entrypoint_found": entrypoint_found,
        "setup_record_found": setup_found,
        "trace_digest": trace_digest,
        "hook_records": hook_records,
        "hook_outcomes": sorted(set(outcomes)),
        "injected_with_single_block_growth": injected,
    }
    return gates, detail


def _ordering(gates: dict[str, bool], detail: dict) -> str:
    if gates["mutation"] and gates["observation"]:
        return "runtime-before-observer"
    if gates["mutation"] and not gates["observation"]:
        return "observer-before-runtime-or-nonpersistent"
    return "unknown"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage 6D-L probe tooling (offline phases).")
    sub = parser.add_subparsers(dest="command", required=True)
    p_render = sub.add_parser("render", help="pre-flight and render the probe block")
    p_render.add_argument("--workdir", required=True)
    p_render.add_argument("--spec-id", default=None)
    p_render.add_argument("--bundle-id", default=None)
    p_render.add_argument("--item-id", default=None)
    p_render.add_argument("--marker", default=None)
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
    p_reconcile.add_argument("--r1", action="store_true")
    p_reconcile.add_argument("--server-log", default=None)
    p_reconcile.add_argument("--trace-file", default=None)
    p_reconcile.add_argument("--plugin-dir", default=None)
    p_reconcile.add_argument("--prev-qualification", default=None)
    args = parser.parse_args(argv)
    if args.command == "render":
        return cmd_render(args)
    return cmd_reconcile(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
