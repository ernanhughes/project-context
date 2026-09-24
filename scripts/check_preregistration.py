"""Check preregistrations (specs/preregistration.md).

    python scripts/check_preregistration.py experiments/preregistrations/*.md
    python scripts/check_preregistration.py --commit experiments/preregistrations/F5.md

Drafts are checked for structure only. A frozen preregistration must also be
committed and unmodified since. Exit code 0 when every file passes.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

REQUIRED_KEYS = ("family", "title", "version", "status", "depends_on", "model_calls")
STATUSES = ("draft", "frozen")
MODEL_CALLS = ("none", "local", "paid")
REQUIRED_SECTIONS = (
    "Question",
    "Hypotheses",
    "Population",
    "Intervention and conditions",
    "Controls",
    "Measurements",
    "Trial design and rationale",
    "Exclusions",
    "Failure criteria",
    "Stopping rule",
    "Analysis plan",
    "Claims this result may support",
    "Claims this result may not support",
    "Deviations",
)


def front_matter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not match:
        return {}, text
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip()
    return data, text[match.end() :]


def check_text(text: str) -> list[str]:
    meta, body = front_matter(text)
    problems: list[str] = []
    if not meta:
        return ["missing front matter"]
    for key in REQUIRED_KEYS:
        if key not in meta:
            problems.append(f"front matter missing: {key}")
    if meta.get("status") not in STATUSES:
        problems.append(f"status must be one of {STATUSES}")
    if meta.get("model_calls") not in MODEL_CALLS:
        problems.append(f"model_calls must be one of {MODEL_CALLS}")
    headings = {h.strip().lower() for h in re.findall(r"^##\s+(.+?)\s*$", body, re.M)}
    for section in REQUIRED_SECTIONS:
        if section.lower() not in headings:
            problems.append(f"missing section: {section}")
    # A section that exists must not be empty.
    for section in REQUIRED_SECTIONS:
        pattern = rf"^##\s+{re.escape(section)}\s*$(.*?)(?=^##\s|\Z)"
        found = re.search(pattern, body, re.M | re.S | re.I)
        if found and section != "Deviations" and not found.group(1).strip():
            problems.append(f"empty section: {section}")
    return problems


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def freeze_commit(path: Path) -> str | None:
    """The last commit that touched the file, if it is committed and clean."""
    rel = str(path.resolve().relative_to(REPO)).replace("\\", "/")
    if git("status", "--porcelain", "--", rel):
        return None
    return git("log", "-1", "--format=%H", "--", rel) or None


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems = check_text(text)
    meta, _ = front_matter(text)
    if meta.get("status") == "frozen" and freeze_commit(path) is None:
        problems.append("frozen preregistration is not committed, or has changes since commit")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--commit", action="store_true", help="print the freezing commit")
    args = parser.parse_args()
    status = 0
    for name in args.files:
        path = Path(name)
        if args.commit:
            commit = freeze_commit(path)
            print(f"{name}: {commit or 'not committed or modified since commit'}")
            status = status or (0 if commit else 1)
            continue
        problems = check_file(path)
        if problems:
            status = 1
            print(f"FAIL {name}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"OK   {name}")
    return status


if __name__ == "__main__":
    sys.exit(main())
