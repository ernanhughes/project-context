"""The checker must not share code, or a defect, with the mechanism it judges.

These are structural tests over the source, so they fail the moment someone makes
the verdict depend on the thing under test.
"""

import ast
from pathlib import Path

import project_context

ROOT = Path(project_context.__file__).parent


def imports_of(package: str) -> set[str]:
    found: set[str] = set()
    for path in (ROOT / package).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
    return found


def touching(package: str, *fragments: str) -> set[str]:
    return {m for m in imports_of(package) if any(f in m for f in fragments)}


def test_the_checker_does_not_import_the_mechanism():
    assert touching("checking", "governance", "compiler", "assembly", "strategies") == set()


def test_the_mechanism_does_not_import_truth_or_the_checker():
    assert touching("governance", "generation", "checking") == set()


def test_the_generator_does_not_import_the_mechanism_or_the_checker():
    """Truth is written by construction; it must never be computed by the resolver.

    The generator shares the metadata vocabulary (plain dataclasses in governance.model)
    with the resolver, because both must speak about the same candidates. It shares none
    of the deciding logic.
    """
    shared_vocabulary = {"project_context.governance.model"}
    assert touching("generation", "governance", "checking") <= shared_vocabulary


def test_the_resolver_source_never_names_truth():
    for path in (ROOT / "governance").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in ("HiddenTruth", "truth_as_dict", "item_truth", "critical_evidence"):
            assert word not in text.replace("hidden truth", ""), (path.name, word)


def test_the_checker_reads_no_explanations():
    text = (ROOT / "checking" / "checker.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for forbidden in ("explanation", "rationale", "reasoning", "self_report", "claims_rule"):
        assert forbidden not in attributes
