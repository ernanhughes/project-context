"""contextlab CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from project_context.fixtures.base import render_visible_text
from project_context.fixtures.reference import FIXTURE_ID, get_fixture

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fixture" and args.fixture_command == "list":
        return cmd_fixture_list()
    if args.command == "fixture" and args.fixture_command == "inspect":
        return cmd_fixture_inspect(args.fixture_id, args.format)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
