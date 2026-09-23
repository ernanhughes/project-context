"""contextlab CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from project_context.fixtures.base import render_visible_text
from project_context.fixtures.reference import FIXTURE_ID, get_fixture
from project_context.opencode.bridge import (
    BRIDGE_SCHEMA_V1,
    load_capture_dir,
    load_capture_file,
    validate_record,
)
from project_context.opencode.ingest import SequenceTracker, ingest_record
from project_context.opencode.prevalence import (
    analyse_bundles,
    assert_exportable,
    bundle_bytes,
    bundle_chars,
    export_report,
    repetition_report,
    structural_shared_prefix,
)

FIXTURES = {FIXTURE_ID: get_fixture}

CREATED_AT = "2026-09-23T00:00:00Z"


def cmd_fixture_list() -> int:
    for name in sorted(FIXTURES):
        fixture = FIXTURES[name]()
        print(f"{fixture.fixture_id} v{fixture.fixture_version}")
    return 0


def _report_text(fixture_id: str) -> str:
    fixture = FIXTURES[fixture_id]()
    built = fixture.build(created_at=CREATED_AT)
    bundle = built.bundle
    sources = Counter(item.source for item in bundle.items)
    kinds = Counter(item.kind for item in bundle.items)
    order_lines = [
        f"  {index:02d} {item.id} ({item.source}/{item.kind})"
        for index, item in enumerate(bundle.items)
    ]
    lines = [
        f"fixture: {built.fixture_id} v{built.fixture_version} [SYNTHETIC]",
        f"bundle: {bundle.id}",
        f"items: {len(bundle.items)}",
        "order:",
        *order_lines,
        "source counts:",
        *[f"  {source}: {count}" for source, count in sorted(sources.items())],
        "kind counts:",
        *[f"  {kind}: {count}" for kind, count in sorted(kinds.items())],
        "token counts (local approximation):",
        *[f"  {item.id}: {item.token_count} [{item.token_provenance}]" for item in bundle.items],
        f"bundle total: {bundle.rendered_token_total()}",
        f"content hash: {bundle.content_hash()}",
        f"probes (hidden, not rendered): {len(fixture.probes())}",
    ]
    return "\n".join(lines) + "\n"


def _report_json(fixture_id: str) -> str:
    fixture = FIXTURES[fixture_id]()
    built = fixture.build(created_at=CREATED_AT)
    bundle = built.bundle
    return (
        json.dumps(
            {
                "fixture_id": built.fixture_id,
                "fixture_version": built.fixture_version,
                "evidence_class": "synthetic",
                "bundle": bundle.to_dict(),
                "rendered_text": render_visible_text(bundle),
                "probe_count": len(fixture.probes()),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def cmd_fixture_inspect(fixture_id: str, output_format: str) -> int:
    if fixture_id not in FIXTURES:
        print(f"unknown fixture: {fixture_id}", file=sys.stderr)
        return 2
    if output_format == "json":
        sys.stdout.write(_report_json(fixture_id))
    else:
        sys.stdout.write(_report_text(fixture_id))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextlab", description="Context Lab instrument (Stage 0)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fixture = sub.add_parser("fixture", help="Work with deterministic fixtures.")
    fixture_sub = fixture.add_subparsers(dest="fixture_command", required=True)
    fixture_sub.add_parser("list", help="List available fixtures.")
    inspect_parser = fixture_sub.add_parser("inspect", help="Inspect a fixture bundle.")
    inspect_parser.add_argument("fixture_id", help="Fixture to inspect.")
    inspect_parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="Report format."
    )

    opencode = sub.add_parser("opencode", help="OpenCode capture records.")
    opencode_sub = opencode.add_subparsers(dest="opencode_command", required=True)
    op_inspect = opencode_sub.add_parser(
        "inspect", help="Structural summary of a capture file (no raw content)."
    )
    op_inspect.add_argument("path", help="Capture .jsonl file or spool directory.")
    op_inspect.add_argument(
        "--show-content",
        action="store_true",
        help="LOCAL ONLY: also print raw item contents. Never use in shared logs.",
    )
    op_ingest = opencode_sub.add_parser(
        "ingest", help="Ingest captures into bundles (derived records only)."
    )
    op_ingest.add_argument("path", help="Capture .jsonl file or spool directory.")

    corpus = sub.add_parser("corpus", help="Corpus-level analysis.")
    corpus_sub = corpus.add_subparsers(dest="corpus_command", required=True)
    prevalence = corpus_sub.add_parser(
        "prevalence", help="Aggregate-only prevalence over captures."
    )
    prevalence.add_argument("path", help="Spool directory of capture .jsonl files.")
    prevalence.add_argument(
        "--export", default=None, help="Write gated aggregate JSON here (checked)."
    )
    return parser


def _load_records(path_str: str) -> tuple[list[dict], dict[str, int]]:
    path = Path(path_str)
    if path.is_dir():
        return load_capture_dir(path)
    records, skipped = load_capture_file(path)
    return records, {"files": 1, "skipped_lines": skipped}


def cmd_opencode_inspect(path_str: str, show_content: bool) -> int:
    records, stats = _load_records(path_str)
    print(f"bridge schema: {BRIDGE_SCHEMA_V1}")
    print(
        f"records: {len(records)} "
        f"(files: {stats['files']}, skipped lines: {stats['skipped_lines']})"
    )
    kinds: Counter[str] = Counter()
    sessions: set[str] = set()
    for record in records:
        errors = validate_record(record)
        status = "ok" if not errors else f"INVALID: {errors[0]}"
        kinds[str(record.get("hook_kind", "?"))] += 1
        session = record.get("session_id")
        if isinstance(session, str):
            sessions.add(session)
        payload = record.get("payload", {})
        parts = 0
        if isinstance(payload, dict):
            messages = payload.get("messages")
            if isinstance(messages, list):
                parts = sum(
                    len(m.get("parts", []))
                    for m in messages
                    if isinstance(m, dict) and isinstance(m.get("parts"), list)
                )
            system = payload.get("system")
            if isinstance(system, list):
                parts = len(system)
            admission = payload.get("admission")
            if isinstance(admission, dict):
                apart = admission.get("parts")
                if isinstance(apart, list):
                    parts = len(apart)
        print(
            f"- {record.get('capture_id')} [{record.get('hook_kind')}] "
            f"session={session} parts={parts} {status}"
        )
        if show_content:
            print("  LOCAL-CONTENT-BEGIN")
            print(json.dumps(payload, indent=2, sort_keys=True)[:4000])
            print("  LOCAL-CONTENT-END")
    print(f"hook kinds: {dict(sorted(kinds.items()))}")
    print(f"sessions observed: {len(sessions)}")
    if show_content:
        print("WARNING: raw content printed locally only. Never share this output.")
    return 0


def cmd_opencode_ingest(path_str: str) -> int:
    records, stats = _load_records(path_str)
    tracker = SequenceTracker()
    bundles = []
    invocations = []
    invalid = 0
    for record in records:
        if validate_record(record):
            invalid += 1
            continue
        bundle, invocation = ingest_record(record, tracker)
        bundles.append(bundle)
        invocations.append(invocation)
    print(f"records: {len(records)} invalid: {invalid} skipped_lines: {stats['skipped_lines']}")
    print(f"bundles: {len(bundles)} invocations: {len(invocations)}")
    for bundle in bundles:
        print(
            f"- {bundle.id}: {len(bundle.items)} items, "
            f"{bundle_bytes(bundle)} bytes / {bundle_chars(bundle)} chars, "
            f"session={bundle.provenance.session_ref if bundle.provenance else None}"
        )
    return 0


def cmd_corpus_prevalence(path_str: str, export: str | None) -> int:
    records, stats = _load_records(path_str)
    tracker = SequenceTracker()
    bundles = []
    for record in records:
        if validate_record(record):
            continue
        bundle, _invocation = ingest_record(record, tracker)
        bundles.append(bundle)
    analysis = analyse_bundles(bundles)
    analysis["load"] = {
        "records": len(records),
        "skipped_lines": stats["skipped_lines"],
        "evidence_note": "SMOKE/ECOLOGICAL OBSERVATION — NOT BOOK RESULT",
    }
    analysis["repetition"] = repetition_report(bundles)
    by_session: dict[str, list] = {}
    for bundle in bundles:
        session = bundle.provenance.session_ref if bundle.provenance else None
        if session:
            by_session.setdefault(session, []).append(bundle)
    prefixes = []
    for ordered in by_session.values():
        for earlier, later in zip(ordered, ordered[1:]):
            prefixes.append(structural_shared_prefix(earlier, later))
    analysis["consecutive_shared_prefix"] = prefixes
    print(json.dumps(analysis, indent=2, sort_keys=True))
    if export is not None:
        exported = export_report(analysis)
        problems = assert_exportable(exported)
        if problems:
            print(f"export refused: {problems}", file=sys.stderr)
            return 3
        Path(export).write_text(
            json.dumps(exported, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"exported gated aggregate to {export}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fixture" and args.fixture_command == "list":
        return cmd_fixture_list()
    if args.command == "fixture" and args.fixture_command == "inspect":
        return cmd_fixture_inspect(args.fixture_id, args.format)
    if args.command == "opencode" and args.opencode_command == "inspect":
        return cmd_opencode_inspect(args.path, args.show_content)
    if args.command == "opencode" and args.opencode_command == "ingest":
        return cmd_opencode_ingest(args.path)
    if args.command == "corpus" and args.corpus_command == "prevalence":
        return cmd_corpus_prevalence(args.path, args.export)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
