"""Manage the F1 session index. Reads and writes only counts, states and coarse structure.

    f1_session.py init      create the empty session index (once, before any capture)
    f1_session.py status    what the index holds, and whether the stopping rule has fired
    f1_session.py project   write the public projection (ordinals, structure, states)
    f1_session.py process   run one captured spool file through the pipeline

`process` reads a raw spool file that stays local; it refuses synthetic or dry-run material
and refuses a sidecar that is not in the closed vocabulary. `init`, `status` and `project`
never touch raw material.

The index lives in .local/f1/session-index.json (git-ignored). The public projection is
written to experiments/f1/session-index.public.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from project_context.corpus.completeness import select_session
from project_context.corpus.f1_pipeline import derivative_bytes, process_session
from project_context.corpus.session_index import ECOLOGICAL, SessionIndex, SessionIndexError
from project_context.corpus.usage import read_session_usage
from project_context.opencode.bridge import load_capture_dir, load_capture_file

ROOT = Path(__file__).resolve().parent.parent
SESSION_INDEX = ROOT / ".local" / "f1" / "session-index.json"
PUBLIC = ROOT / "experiments" / "f1" / "session-index.public.json"
DERIVATIVES = ROOT / ".local" / "f1" / "derivatives"
CAMPAIGN = "f1-ecological"
CALIBRATION_DIR = ROOT / ".local" / "f1" / "calibration"
CALIBRATION_REGISTRY = CALIBRATION_DIR / "sessions.json"


def calibration_session_ids() -> frozenset[str]:
    """Harness session ids of deliberate calibration sessions. They can never enter the corpus."""
    if not CALIBRATION_REGISTRY.exists():
        return frozenset()
    return frozenset(json.loads(CALIBRATION_REGISTRY.read_text(encoding="utf-8")))


def write_public(index: SessionIndex) -> None:
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(index.public_projection(), indent=2, sort_keys=True) + "\n"
    PUBLIC.write_text(body, encoding="utf-8")


def cmd_init(_args: argparse.Namespace) -> int:
    index = SessionIndex.create(SESSION_INDEX, ECOLOGICAL, CAMPAIGN)
    write_public(index)
    print(f"created empty ecological session index ({len(index.entries)} sessions)")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    index = SessionIndex.load(SESSION_INDEX, ECOLOGICAL)
    first = min((e.captured_at for e in index.entries), default=None)
    weeks = 0.0
    if first:
        started = datetime.fromisoformat(first.replace("Z", "+00:00"))
        weeks = (datetime.now(timezone.utc) - started).days / 7
    status = index.stopping_status(weeks)
    print(
        json.dumps(
            {"kind": index.kind, "genuine_sessions": index.genuine_count(), **status}, indent=2
        )
    )
    return 0


def cmd_project(_args: argparse.Namespace) -> int:
    write_public(SessionIndex.load(SESSION_INDEX, ECOLOGICAL))
    print(f"wrote {PUBLIC.relative_to(ROOT)}")
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    spool = Path(args.spool).resolve()
    if CALIBRATION_DIR.resolve() in (spool, *spool.parents):
        raise SessionIndexError("the calibration spool is not a source for the ecological corpus")
    index = SessionIndex.load(SESSION_INDEX, ECOLOGICAL)
    if spool.is_dir():
        all_records, meta = load_capture_dir(spool)
        skipped = meta["skipped_lines"]
    else:
        all_records, skipped = load_capture_file(spool)
    records = select_session(all_records, args.session_id)
    if not records:
        raise SessionIndexError("no records for that session id in the spool")
    usage = (
        read_session_usage(Path(args.opencode_db), args.session_id) if args.opencode_db else None
    )
    sidecar = json.loads(Path(args.sidecar).read_text(encoding="utf-8"))
    terms = tuple(t for t in (args.sensitive_terms or "").split(",") if t)
    first = min((e.captured_at for e in index.entries), default=None)
    outcome = process_session(
        records,
        session_key=args.session_key,
        sidecar=sidecar,
        session_index=index,
        first_capture_at=first,
        skipped_lines=skipped,
        sensitive_terms=terms,
        usage=usage,
        refuse_session_ids=calibration_session_ids(),
    )
    if outcome.l1 is not None and not outcome.excluded:
        DERIVATIVES.mkdir(parents=True, exist_ok=True)
        (DERIVATIVES / f"session-{outcome.session_ordinal:03d}.json").write_bytes(
            derivative_bytes(outcome)
        )
    write_public(index)
    print(
        json.dumps(
            {
                "ordinal": outcome.session_ordinal,
                "excluded": outcome.excluded,
                "reason": outcome.exclusion_reason,
                "stage": outcome.stage_reached,
            }
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("project").set_defaults(fn=cmd_project)
    process = sub.add_parser("process")
    process.add_argument("--spool", required=True, help="raw spool file or directory (stays local)")
    process.add_argument("--session-id", required=True, help="the harness session id to process")
    process.add_argument(
        "--opencode-db",
        help="the harness database, read-only, to join provider-reported usage (optional)",
    )
    process.add_argument("--sidecar", required=True, help="JSON file in the closed vocabulary")
    process.add_argument("--session-key", required=True, help="local key; never published")
    process.add_argument("--sensitive-terms", help="comma-separated literals to look for")
    process.set_defaults(fn=cmd_process)
    args = parser.parse_args()
    try:
        return args.fn(args)
    except (SessionIndexError, FileNotFoundError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
