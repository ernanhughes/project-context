"""Preregistration structure checks. Text only; no git."""

import importlib.util
from pathlib import Path

SCRIPT = Path("scripts") / "check_preregistration.py"
spec = importlib.util.spec_from_file_location("check_preregistration", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def _doc(status="draft", drop=None, empty=None, calls="none"):
    sections = [s for s in tool.REQUIRED_SECTIONS if s != drop]
    parts = [
        "---",
        "family: F5",
        "title: x",
        "version: 1",
        f"status: {status}",
        "depends_on: []",
        f"model_calls: {calls}",
        "---",
        "",
        "# F5 - x",
        "",
    ]
    for section in sections:
        parts.append(f"## {section}")
        parts.append("" if section == empty else "Some content.")
        parts.append("")
    return "\n".join(parts)


def test_complete_draft_passes():
    assert tool.check_text(_doc()) == []


def test_missing_and_empty_sections_are_named():
    assert tool.check_text(_doc(drop="Stopping rule")) == ["missing section: Stopping rule"]
    assert tool.check_text(_doc(empty="Analysis plan")) == ["empty section: Analysis plan"]


def test_front_matter_is_validated():
    assert tool.check_text("# no front matter") == ["missing front matter"]
    assert "status must be one of ('draft', 'frozen')" in tool.check_text(_doc(status="maybe"))
    assert "model_calls must be one of ('none', 'local', 'paid')" in tool.check_text(
        _doc(calls="lots")
    )


def test_deviations_may_be_empty_but_must_exist():
    assert tool.check_text(_doc(empty="Deviations")) == []
    assert tool.check_text(_doc(drop="Deviations")) == ["missing section: Deviations"]


def test_every_required_section_is_in_the_spec_template():
    spec_text = Path("specs/preregistration.md").read_text(encoding="utf-8")
    for section in tool.REQUIRED_SECTIONS:
        assert f"## {section}" in spec_text
