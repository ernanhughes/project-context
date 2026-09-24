"""Locate a frozen run directory.

A frozen run lives in one of two places. `.local/runs/<experiment>/<run>/`
is where a run is first written (git-ignored, machine-local). Runs that back
a published claim are also published, byte-for-byte, under
`evidence/runs/<experiment>/<run>/` (see `evidence/README.md`). Readers of
frozen runs resolve through this helper so that a fresh clone works without
private `.local` state, while a machine that still holds the local original
keeps using it.
"""

from __future__ import annotations

from pathlib import Path

LOCAL_ROOT = Path(".local") / "runs"
PUBLISHED_ROOT = Path("evidence") / "runs"


def frozen_run_dir(experiment: str, run: str, root: Path | None = None) -> Path:
    """Return the local original if present, else the published copy.

    `root` is the repository root (default: the current directory). The
    published path is returned even when absent, so a missing run fails at
    the point of use with a path that names where it should be.
    """
    base = root or Path(".")
    local = base / LOCAL_ROOT / experiment / run
    if local.is_dir():
        return local
    return base / PUBLISHED_ROOT / experiment / run
