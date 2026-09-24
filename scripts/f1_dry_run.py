"""F1 dry runs on SYNTHETIC data. Pipeline tests, never evidence, never the corpus.

    .venv/Scripts/python.exe scripts/f1_dry_run.py

Two runs, both deterministic:

1. **Privacy dry run.** A fully synthetic session salted with planted paths, addresses,
   hostnames, key-shaped strings, repository secrets, user-like text and source-like text
   goes through capture -> scan -> structural extraction -> derivative -> publication gate.
   It must show that none of the planted material reaches the public derivative, whether or
   not the scan noticed it, and that a derivative that leaks is blocked.
2. **Measurement dry run.** A synthetic session whose quantities were worked out by hand is
   analysed, and each reported quantity is reconciled against the worked-out value.

Exit status is non-zero on any failure. The session index used is a throwaway dry-run
index in a temporary directory; the ecological session index is never opened.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from project_context.corpus.f1_analysis import analyse_session, dumps, reconcile
from project_context.corpus.f1_pipeline import derivative_bytes, process_session
from project_context.corpus.privacy import gate, scan_raw
from project_context.corpus.session_index import (
    DRY_RUN,
    ECOLOGICAL,
    SessionIndex,
    SessionIndexError,
)
from project_context.corpus.synthetic import (
    GROWTH_EXPECTED,
    PLANTED,
    SCANNER_BLIND_SPOT,
    growth_session,
    privacy_session,
)

SIDECAR = {"language_family": "python", "size_band": "small", "has_tests": True}
SENSITIVE = ("contoso", "jdoe", "Priya Ramanathan")


def fragments() -> list[str]:
    pieces = set(PLANTED.all())
    for text in PLANTED.all():
        pieces.update(t for t in text.replace("\\", " ").replace("/", " ").split() if len(t) >= 8)
    return sorted(pieces)


def privacy_dry_run(work: Path) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    index = SessionIndex.create(work / "dry-run-index.json", DRY_RUN, "dry-run-campaign")
    records = privacy_session()

    scan = scan_raw(records, SENSITIVE)
    checks.append(
        (
            "scan sees the planted credentials",
            scan.excludes_session,
            f"credential classes {sorted(scan.credentials)}",
        )
    )
    checks.append(
        (
            "scan sees the planted identifiers",
            {"windows-path", "posix-home-path", "email", "ipv4", "hostname"}
            <= set(scan.identifiers),
            f"identifier classes {sorted(scan.identifiers)}",
        )
    )
    out = process_session(
        records,
        session_key="dry-run-ses-7f3a91",
        sidecar=SIDECAR,
        session_index=index,
        sensitive_terms=SENSITIVE,
    )
    checks.append(
        (
            "session excluded before extraction",
            out.excluded and out.exclusion_reason == "secret_or_identifier_hit" and out.l1 is None,
            f"reason {out.exclusion_reason}",
        )
    )

    forced = process_session(
        records,
        session_key="dry-run-ses-forced",
        sidecar=SIDECAR,
        session_index=index,
        sensitive_terms=SENSITIVE,
        force_derivative=True,
    )
    blob = derivative_bytes(forced).decode("ascii")
    leaked = [f for f in fragments() if f in blob]
    lowered = [
        w for w in ("contoso", "jdoe", "priya", "hunter2", "whsec", "invoice") if w in blob.lower()
    ]
    checks.append(
        (
            "derivative built with the scan bypassed contains no planted material",
            forced.gate.content_clean and not leaked and not lowered,
            f"{len(fragments())} planted strings and fragments checked, "
            f"{len(leaked) + len(lowered)} found",
        )
    )
    checks.append(
        (
            "clean content is still not publishable without approval",
            not forced.gate.publishable,
            "publishable = clean content AND recorded approval",
        )
    )

    blind = privacy_session(with_blind_spot_only=True)
    blind_scan = scan_raw(blind)
    blind_out = process_session(
        blind, session_key="dry-run-ses-blind", sidecar=SIDECAR, session_index=index
    )
    blind_blob = derivative_bytes(blind_out).decode("ascii")
    checks.append(
        (
            "a secret the scan cannot recognise still does not reach the derivative",
            not blind_scan.excludes_session
            and blind_out.gate.content_clean
            and SCANNER_BLIND_SPOT not in blind_blob,
            "the scan is blind to it by construction; the derivative has nowhere to carry it",
        )
    )

    leaky = json.loads(json.dumps(analyse_session(records)))
    leaky["session"]["growth_shape"] = PLANTED.classes["fake_paths"][0]
    checks.append(
        (
            "a derivative that does leak is blocked",
            not gate(leaky, records, scan).content_clean,
            "planted path placed in a field",
        )
    )
    public = json.dumps(index.public_projection())
    private = ("dry-run-ses", "2030-01-01", "session_key", "captured_at", "link")
    checks.append(
        (
            "public session-index projection carries no identity, time or digest",
            not any(p in public for p in private),
            f"{len(index.entries)} dry-run rows",
        )
    )
    try:
        SessionIndex.load(work / "dry-run-index.json", ECOLOGICAL)
        refused = False
    except SessionIndexError:
        refused = True
    checks.append(
        (
            "the dry-run session index cannot be opened as the ecological corpus",
            refused,
            "kind mismatch refused; the ecological session index was not opened",
        )
    )
    return checks


def measurement_dry_run() -> list[tuple[str, bool, str]]:
    records, _ = growth_session()
    l1 = analyse_session(records)
    req, session = l1["requests"], l1["session"]
    checks: list[tuple[str, bool, str]] = []
    for key in ("bytes", "new_bytes", "carry_over_bytes", "redundant_payload_bytes"):
        got = [r[key] for r in req]
        checks.append((f"{key} per request", got == GROWTH_EXPECTED[key], f"{got}"))
    got = [r["prefix"]["bytes"] if r["prefix"] else None for r in req]
    checks.append(
        ("stable-prefix bytes per request", got == GROWTH_EXPECTED["prefix_bytes"], f"{got}")
    )
    got = [r["identities_with_differing_bytes"] for r in req]
    checks.append(
        (
            "same call (tool and arguments), different bytes",
            got == GROWTH_EXPECTED["identities_with_differing_bytes"],
            f"{got}",
        )
    )
    for key in (
        "first_request_tool_definition_share",
        "last_request_redundant_payload_share",
        "last_request_tool_result_share",
    ):
        checks.append((key, session[key] == GROWTH_EXPECTED[key], f"{session[key]}"))
    checks.append(
        ("derivative reconciles with its source", reconcile(records, l1) == [], "exact bytes")
    )
    checks.append(
        (
            "deterministic to the byte",
            dumps(l1) == dumps(analyse_session(json.loads(json.dumps(records)))),
            "two runs, canonical serialisation",
        )
    )
    return checks


def main() -> int:
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for title, checks in (
            ("PRIVACY DRY RUN (synthetic; pipeline test only)", privacy_dry_run(Path(tmp))),
            ("MEASUREMENT DRY RUN (synthetic; worked-out values)", measurement_dry_run()),
        ):
            print(f"\n{title}")
            for name, ok, detail in checks:
                print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
                failed += 0 if ok else 1
    print(f"\n{'ALL PASSED' if not failed else f'{failed} FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
