"""Publish approved synthetic frozen runs, byte for byte.

Frozen runs are first written under `.local/runs/` (git-ignored). A run that
backs a published claim is copied, unmodified, to `evidence/runs/` so that a
fresh clone can inspect and verify it (`evidence/README.md`).

This tool is deliberately narrow:

  - it publishes only runs listed in APPROVED, each approved by the author
    and recorded in `specs/privacy.md`;
  - it refuses a run whose manifest is not `evidence_class: synthetic`;
  - it scans every file for machine paths, hostnames, addresses, key-like
    strings and personal identifiers, and refuses on any hit;
  - it copies bytes exactly (never rewrites a historical artifact) and
    refuses to overwrite a published file whose bytes differ;
  - it never touches `.local/`.

    python scripts/publish_evidence_runs.py            # copy
    python scripts/publish_evidence_runs.py --check    # scan only, copy nothing
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCAL = REPO / ".local" / "runs"
PUBLISHED = REPO / "evidence" / "runs"

# Runs approved for publication (see specs/privacy.md, "Approved publications").
APPROVED: tuple[tuple[str, str], ...] = (
    ("compiler-v1", "run-001"),
    ("compiler-behavior-v1", "run-003"),
    ("compiler-behavior-v1", "run-003-transfer"),
)

# Patterns that must not appear in any published file. Deliberately broad:
# a false positive costs a review, a false negative costs a leak.
FORBIDDEN = {
    "windows user path": re.compile(r"[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]", re.I),
    "posix home path": re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"),
    "e-mail address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "loopback / host": re.compile(r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b", re.I),
    "ip address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "api key": re.compile(r"\b(?:sk|pk|ghp|gho|xox[abps]|AKIA)[-_A-Za-z0-9]{12,}"),
    "bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}"),
    "credential word": re.compile(r"\b(?:api[_-]?key|secret|passwd|password)\b\s*[:=]", re.I),
}


def scan(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [label for label, pattern in FORBIDDEN.items() if pattern.search(text)]


def check_run(experiment: str, run: str) -> list[str]:
    source = LOCAL / experiment / run
    problems: list[str] = []
    if not source.is_dir():
        return [f"{experiment}/{run}: local original not found at {source}"]
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("evidence_class") != "synthetic":
        problems.append(f"{experiment}/{run}: evidence_class is not synthetic")
    for path in sorted(source.iterdir()):
        if not path.is_file():
            problems.append(f"{experiment}/{run}: unexpected sub-directory {path.name}")
            continue
        for label in scan(path):
            problems.append(f"{experiment}/{run}/{path.name}: matches '{label}'")
    return problems


def publish(experiment: str, run: str) -> list[str]:
    source = LOCAL / experiment / run
    target = PUBLISHED / experiment / run
    target.mkdir(parents=True, exist_ok=True)
    notes = []
    for path in sorted(source.iterdir()):
        dest = target / path.name
        data = path.read_bytes()
        if dest.exists() and dest.read_bytes() != data:
            raise SystemExit(f"refusing to overwrite differing published file: {dest}")
        if not dest.exists():
            shutil.copyfile(path, dest)
            notes.append(f"copied {experiment}/{run}/{path.name}")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="scan only; copy nothing")
    args = parser.parse_args()

    problems: list[str] = []
    for experiment, run in APPROVED:
        problems.extend(check_run(experiment, run))
    if problems:
        print("REFUSED: sanitisation gate failed")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"sanitisation gate passed for {len(APPROVED)} runs")
    if args.check:
        return 0
    for experiment, run in APPROVED:
        for note in publish(experiment, run):
            print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
