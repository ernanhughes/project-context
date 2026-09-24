"""Manage the F1 ecological ledger. Reads and writes only counts, states and coarse structure.

    f1_session.py init      create the empty ecological ledger (once, before any capture)
    f1_session.py status    what the ledger holds, and whether the stopping rule has fired
    f1_session.py project   write the public projection (ordinals, structure, states)
    f1_session.py process   run one captured spool file through the pipeline

`process` reads a raw spool file that stays local; it refuses synthetic or dry-run material
and refuses a sidecar that is not in the closed vocabulary. `init`, `status` and `project`
never touch raw material.

The ledger lives in .local/f1/ledger.json (git-ignored). The public projection is written
to experiments/f1/ledger.public.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from project_context.corpus.f1_pipeline import derivative_bytes, process_session
from project_context.corpus.ledger import ECOLOGICAL, Ledger, LedgerError
from project_context.opencode.bridge import load_capture_file

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / ".local" / "f1" / "ledger.json"
PUBLIC = ROOT / "experiments" / "f1" / "ledger.public.json"
DERIVATIVES = ROOT / ".local" / "f1" / "derivatives"
CAMPAIGN = "f1-ecological"


def write_public(ledger: Ledger) -> None:
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(ledger.public_projection(), indent=2, sort_keys=True) + "\n"
    PUBLIC.write_text(body, encoding="utf-8")


def cmd_init(_args: argparse.Namespace) -> int:
    ledger = Ledger.create(LEDGER, ECOLOGICAL, CAMPAIGN)
    write_public(ledger)
    print(f"created empty ecological ledger ({len(ledger.entries)} sessions)")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    ledger = Ledger.load(LEDGER, ECOLOGICAL)
    first = min((e.captured_at for e in ledger.entries), default=None)
    weeks = 0.0
    if first:
        started = datetime.fromisoformat(first.replace("Z", "+00:00"))
        weeks = (datetime.now(timezone.utc) - started).days / 7
    status = ledger.stopping_status(weeks)
    print(
        json.dumps(
            {"kind": ledger.kind, "genuine_sessions": ledger.genuine_count(), **status}, indent=2
        )
    )
    return 0


def cmd_project(_args: argparse.Namespace) -> int:
    write_public(Ledger.load(LEDGER, ECOLOGICAL))
    print(f"wrote {PUBLIC.relative_to(ROOT)}")
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    ledger = Ledger.load(LEDGER, ECOLOGICAL)
    records, skipped = load_capture_file(Path(args.spool))
    sidecar = json.loads(Path(args.sidecar).read_text(encoding="utf-8"))
    terms = tuple(t for t in (args.sensitive_terms or "").split(",") if t)
    first = min((e.captured_at for e in ledger.entries), default=None)
    outcome = process_session(
        records,
        session_key=args.session_key,
        sidecar=sidecar,
        ledger=ledger,
        first_capture_at=first,
        skipped_lines=skipped,
        sensitive_terms=terms,
    )
    if outcome.l1 is not None and not outcome.excluded:
        DERIVATIVES.mkdir(parents=True, exist_ok=True)
        (DERIVATIVES / f"session-{outcome.ledger_ordinal:03d}.json").write_bytes(
            derivative_bytes(outcome)
        )
    write_public(ledger)
    print(
        json.dumps(
            {
                "ordinal": outcome.ledger_ordinal,
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
    process.add_argument("--spool", required=True, help="raw JSONL spool file (stays local)")
    process.add_argument("--sidecar", required=True, help="JSON file in the closed vocabulary")
    process.add_argument("--session-key", required=True, help="local key; never published")
    process.add_argument("--sensitive-terms", help="comma-separated literals to look for")
    process.set_defaults(fn=cmd_process)
    args = parser.parse_args()
    try:
        return args.fn(args)
    except (LedgerError, FileNotFoundError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
