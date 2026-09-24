"""Instrument calibration report for the F1 capture. Structure only; nothing here is evidence.

    .venv/Scripts/python.exe scripts/f1_calibrate.py

The calibration is one deliberate tool-testing session in a throwaway repository, run against
an isolated harness configuration and its own spool (`.local/f1/calibration/`). Its purpose
is to check what the instrument really sees against what the design assumed. This script:

* registers the calibration session ids, so the ecological corpus refuses them under any key;
* runs the session through the same pipeline into a **calibration** session index, which the
  ecological index cannot accept and which cannot be opened as the corpus;
* prints structural facts (tool names, part types, limit presence, usage alignment, estimate
  error against provider-reported tokens). It prints no content.

Nothing it reports feeds a stratum count, a routing trigger or any claim.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from project_context.corpus.completeness import assess_session, split_control
from project_context.corpus.f1_pipeline import process_session
from project_context.corpus.session_index import CALIBRATION, SessionIndex
from project_context.corpus.usage import read_session_usage
from project_context.opencode.bridge import load_capture_dir

ROOT = Path(__file__).resolve().parent.parent
CAL = ROOT / ".local" / "f1" / "calibration"
SPOOL = CAL / "spool"
DB = CAL / "home" / "data" / "opencode" / "opencode.db"
REGISTRY = CAL / "sessions.json"
INDEX = CAL / "session-index.json"


def main() -> int:
    if not SPOOL.exists():
        print("no calibration spool; nothing to report", file=sys.stderr)
        return 2
    records, meta = load_capture_dir(SPOOL)
    data, control = split_control(records)
    sessions = sorted({r["session_id"] for r in data})
    REGISTRY.write_text(json.dumps(sessions, indent=2) + "\n", encoding="utf-8")
    if INDEX.exists():
        INDEX.unlink()  # the calibration index is rebuilt each time; it holds no corpus
    index = SessionIndex.create(INDEX, CALIBRATION, "f1-calibration")

    print(
        f"records {len(data)}, control records {len(control)}, files {meta['files']}, "
        f"skipped lines {meta['skipped_lines']}, sessions {len(sessions)}"
    )
    for n, sid in enumerate(sessions, start=1):
        mine = [r for r in records if r.get("session_id") == sid]
        c = assess_session(mine, meta["skipped_lines"])
        usage = read_session_usage(DB, sid)
        out = process_session(
            mine,
            session_key=f"calibration-{n:02d}",
            sidecar={"language_family": "python", "size_band": "small", "has_tests": True},
            session_index=index,
            usage=usage,
        )
        print(
            f"\nsession {n}: complete={c.complete} reasons={list(c.reasons)} "
            f"primary={c.primary_requests} other={c.other_requests}"
        )
        print(
            f"  pipeline stage={out.stage_reached} excluded={out.excluded} "
            f"reason={out.exclusion_reason} "
            f"gate_clean={out.gate.content_clean if out.gate else None}"
        )
        print(
            f"  scan credentials={out.scan.credentials if out.scan else None} "
            f"identifiers={out.scan.identifiers if out.scan else None}"
        )
        part_types: Counter[str] = Counter()
        called: Counter[str] = Counter()
        for r in mine:
            if r.get("request_kind") != "context":
                continue
            for m in r["messages"]:
                for p in m.get("content", []):
                    part_types[p["type"]] += 1
                    if p["type"] == "tool-call":
                        called[p["name"]] += 1
        first = next(r for r in mine if r.get("request_kind") == "context")
        print(f"  tools exposed ({len(first['tools'])}): {sorted(first['tools'])}")
        print(f"  part types re-sent (summed over requests): {dict(part_types)}")
        print(f"  tool calls re-sent (summed): {dict(called)}")
        limits = Counter(json.dumps(r["model_limits"], sort_keys=True) for r in mine)
        print(f"  model_limits variants: {dict(limits)}")
        print(
            f"  usage rows {None if usage is None else len(usage)} "
            f"vs primary requests {c.primary_requests}"
        )
        if out.l1:
            s = out.l1["session"]
            print(f"  usage_join={s['usage_join']} window_limit_kind={s['window_limit_kind']}")
            errs = []
            for req in out.l1["requests"]:
                m = req["measured_prompt_tokens"]
                if isinstance(m, int) and m > 0:
                    errs.append((m, req["est_tokens_bytes"], req["est_tokens_words"]))
            if errs:
                rel_b = [(b - m) / m for m, b, _ in errs]
                rel_w = [(w - m) / m for m, _, w in errs]
                print(f"  estimate error vs provider-reported prompt tokens, {len(errs)} requests:")
                print(f"    bytes/4   min {min(rel_b):+.1%} max {max(rel_b):+.1%}")
                print(f"    words*1.3 min {min(rel_w):+.1%} max {max(rel_w):+.1%}")
            print(
                f"  derived: edit calls {s['edit_call_count']}, test-command calls "
                f"{s['test_command_call_count']}, "
                f"distinct edit targets {s['distinct_edit_targets']}, "
                f"history rewrites {s['history_rewrite_events']}"
            )
    print("\ncalibration sessions registered:", len(sessions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
