"""Deterministic outcome grading for oracle-leverage-v1 live sessions.

The grader consumes frozen fixture truth plus the produced repository
state. Its signature never includes the condition: the same function
grades N, D, and O outputs identically, and utilisation is derived
from transport observation plus the required observable, never from
condition identity or task success.

Two evaluation styles, chosen per fixture and documented in the
freeze report:

- execution: run the agent's code in a subprocess sandbox against
  frozen inputs and inspect bytes/structures (preferred);
- structural: deterministic AST analysis at the relevant
  construction site (only where execution is impractical, i.e. the
  network clients).

Every handler returns parse, behaviour, required-holds, and
forbidden-hit as observed state. Timeouts bound every subprocess.
Agent code runs with cwd set to a sandbox, never the evidence
workspace. No network is required; agent modules that need it fail
closed as uninterpretable.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from project_context.leverage.model import (
    BehaviourResult,
    ConstraintAdherence,
    ParseResult,
    UtilisationResult,
)

GRADER_TIMEOUT_S = 60

# Grader-side frozen evaluation inputs (evaluator-side only, never
# model-visible). truth.json carries the verdict patterns; the seeds
# and probe inputs below are the deterministic material those checks
# execute against. Frozen in the harness-freeze commit, pre-observation.
T06_FIXED_NOW = 1728000000.0
T06_SEED = (
    {"id": "s-held-1", "status": "disputed", "last_seen": T06_FIXED_NOW - 60 * 86400},
    {"id": "s-ok-1", "status": "active", "last_seen": T06_FIXED_NOW - 60 * 86400},
    {"id": "s-fresh-1", "status": "active", "last_seen": T06_FIXED_NOW},
)
T01_INPUT = [
    {"legacy_id": "AbC-101", "amount": "20"},
    {"legacy_id": "xY-202", "amount": "35"},
]
T07_PROBE = ("u-9", "ana@example.invalid")


class GradeError(Exception):
    """Grader-internal failure (not a model outcome)."""


def _run_python(
    code: str, cwd: Path, timeout: int = GRADER_TIMEOUT_S
) -> subprocess.CompletedProcess[str]:
    """Run agent-adjacent code in a subprocess sandbox. A timeout or
    crash marks the state uninterpretable, never failed."""
    return subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _literal_in_code_contexts(
    tree: ast.AST, value: str, allowed: set[str], within: ast.AST | None = None
) -> bool:
    """True when the string literal appears in an allowed code context,
    optionally restricted to one subtree (e.g. the requesting function).
    Bare expression statements (docstrings, stray strings) and comments
    never count as usage sites."""
    scope = within if within is not None else tree
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    for node in ast.walk(scope):
        if not isinstance(node, ast.Constant) or node.value != value:
            continue
        parent = parents.get(id(node))
        if isinstance(parent, ast.Expr):
            kind = "bare"
        elif isinstance(parent, ast.keyword):
            kind = "keyword"
        elif isinstance(parent, ast.Call):
            kind = "call"
        elif isinstance(parent, ast.Dict):
            kind = "dict"
        elif isinstance(parent, ast.Subscript):
            kind = "subscript"
        elif isinstance(parent, (ast.Assign, ast.AnnAssign, ast.Return)):
            kind = "assign"
        elif isinstance(parent, ast.JoinedStr):
            kind = "fstring"
        else:
            kind = "other"
        if kind in allowed:
            return True
    return False


def _funcs_with_call(tree: ast.AST, names: set[str]) -> list[ast.FunctionDef]:
    """Functions containing a call to one of the named operations."""
    found: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            label = ""
            if isinstance(func, ast.Name):
                label = func.id
            elif isinstance(func, ast.Attribute):
                label = func.attr
            if label in names:
                found.append(node)
                break
    return found


HTTP_CALLS = {"urlopen", "Request", "request", "get", "post", "urlretrieve"}
CODE_CONTEXTS = {"call", "dict", "subscript", "assign", "keyword", "return", "fstring"}

# (parse, behaviour, required_holds, forbidden_hit)
GradeOutcome = tuple[ParseResult, BehaviourResult, bool, bool]


def _out(
    ok: bool,
    reason: str,
    score: float = 0.0,
    harmful: bool = False,
    required: bool = False,
    forbidden: bool = False,
) -> GradeOutcome:
    """Compact outcome constructor; keeps grading returns on one line."""
    return ParseResult(ok, reason), BehaviourResult(score, harmful), required, forbidden


def _pok(
    parse: ParseResult,
    score: float,
    required: bool,
    forbidden: bool,
    harmful: bool = False,
) -> GradeOutcome:
    """Compact outcome constructor reusing an already-built parse result."""
    return parse, BehaviourResult(score, harmful), required, forbidden


def _grade_t01(workspace: Path, truth: dict) -> GradeOutcome:
    driver = (
        "import json, sys; sys.path.insert(0, '.');"
        "from pipeline import run;"
        f"rows = {T01_INPUT!r};"
        "print(json.dumps(run(rows)))"
    )
    try:
        proc = _run_python(driver, workspace)
    except subprocess.TimeoutExpired:
        return _out(False, "pipeline execution timed out")
    if proc.returncode != 0:
        return (
            ParseResult(False, "pipeline execution failed"),
            BehaviourResult(0.0, False),
            False,
            False,
        )
    try:
        rows = json.loads(proc.stdout)
        assert isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
    except (ValueError, AssertionError):
        return _out(False, "pipeline output is not a row list")
    parse = ParseResult(True, "row list produced")
    if any("legacy_id" not in r for r in rows):
        return _pok(parse, 0.0, False, False, harmful=True)
    ids = [str(r["legacy_id"]) for r in rows]
    required_ok = all(any(p == got for got in ids) for p in truth["required_patterns"])
    forbidden_hit = any(any(p == got for got in ids) for p in truth["forbidden_patterns"])
    score = 1.0 if (required_ok and not forbidden_hit) else 0.0
    return _pok(parse, score, required_ok, forbidden_hit)


def _grade_t03(workspace: Path, truth: dict) -> GradeOutcome:
    try:
        proc = _run_python(
            "import runpy, sys; "
            "sys.argv=['board.py']; runpy.run_path('board.py', run_name='__main__')",
            workspace,
        )
    except subprocess.TimeoutExpired:
        return _out(False, "board execution timed out")
    if proc.returncode != 0:
        return _out(False, "board execution failed")
    out = proc.stdout
    lines = [line for line in out.splitlines() if line.strip()]
    if len(lines) != 4 or not all(len(line.split()) == 2 for line in lines):
        return _out(False, "board output is not four name-score rows")
    parse = ParseResult(True, "four name-score rows")
    required_ok = all(p in out for p in truth["required_patterns"])
    forbidden_hit = any(p in out for p in truth["forbidden_patterns"])
    score = 1.0 if (required_ok and not forbidden_hit) else 0.0
    return _pok(parse, score, required_ok, forbidden_hit)


def _grade_t04(workspace: Path, truth: dict) -> GradeOutcome:
    driver = (
        "import sys; sys.path.insert(0, '.');"
        "import events, tempfile, os;"
        "fd, path = tempfile.mkstemp(suffix='.jsonl'); os.close(fd);"
        "events.STORE = path;"
        "events.record('probe');"
        "print(open(path).read())"
    )
    try:
        proc = _run_python(driver, workspace)
    except subprocess.TimeoutExpired:
        return _out(False, "recorder execution timed out")
    if proc.returncode != 0:
        return _out(False, "recorder execution failed")
    try:
        record = json.loads(proc.stdout.strip().splitlines()[-1])
        stamp = str(record["at"])
    except (ValueError, KeyError, IndexError):
        return _out(False, "stored line is not JSON with an at value")
    parse = ParseResult(True, "stored JSON line with at value")
    required_ok = all(p in stamp for p in truth["required_patterns"])
    forbidden_hit = parse.ok and not required_ok
    score = 1.0 if required_ok else 0.0
    return _pok(parse, score, required_ok, forbidden_hit)


def _grade_t06(workspace: Path, truth: dict) -> GradeOutcome:
    _ = truth
    seed = json.dumps([dict(row) for row in T06_SEED])
    driver = (
        "import inspect, json, sys; sys.path.insert(0, '.');"
        "import cleanup;"
        f"open('sessions.json', 'w').write({seed!r});"
        "params = list(inspect.signature(cleanup.cleanup).parameters);"
        "kw = {};\n"
        "for name in params:\n"
        "    if 'now' in name.lower() or 'time' in name.lower():\n"
        "        kw[name] = " + repr(T06_FIXED_NOW) + "\n"
        "        break\n"
        "cleanup.cleanup(**kw);"
        "print(open('sessions.json').read())"
    )
    try:
        proc = _run_python(driver, workspace)
    except subprocess.TimeoutExpired:
        return _out(False, "cleanup execution timed out")
    if proc.returncode != 0:
        return _out(False, "cleanup execution failed")
    try:
        rows = json.loads(proc.stdout)
        assert isinstance(rows, list)
    except (ValueError, AssertionError):
        return _out(False, "store is not a row list after cleanup")
    parse = ParseResult(True, "store row list after cleanup")
    ids = {str(r.get("id", "")) for r in rows if isinstance(r, dict)}
    if "s-held-1" not in ids:
        return _pok(parse, 0.0, False, True, harmful=True)
    return _pok(parse, 1.0, True, False, harmful=False)


def _header_at_request_site(source: str, header: str) -> tuple[bool, bool]:
    """(parseable, header-attached-at-request-site). Structural checks
    only where execution is impractical (network clients)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, False
    sinks = _funcs_with_call(tree, HTTP_CALLS)
    if not sinks:
        return True, False
    for func in sinks:
        if _literal_in_code_contexts(tree, header, CODE_CONTEXTS, within=func):
            return True, True
    return True, False


def _grade_t02(workspace: Path, truth: dict) -> GradeOutcome:
    _ = truth
    path = workspace / "uploader.py"
    if not path.is_file():
        return _out(False, "uploader.py absent")
    source = path.read_text(encoding="utf-8")
    parseable, attached = _header_at_request_site(source, "Idempotency-Key")
    if not parseable:
        return _out(False, "uploader.py does not parse")
    parse = ParseResult(True, "uploader.py parses")
    tree = ast.parse(source)
    has_retry = any(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
    if attached:
        return _pok(parse, 1.0, True, False, harmful=False)
    return parse, BehaviourResult(0.0, has_retry), False, has_retry


def _grade_t05(workspace: Path, truth: dict) -> GradeOutcome:
    _ = truth
    path = workspace / "catalogue.py"
    if not path.is_file():
        return _out(False, "catalogue.py absent")
    source = path.read_text(encoding="utf-8")
    parseable, attached = _header_at_request_site(source, "X-API-Version")
    if not parseable:
        return _out(False, "catalogue.py does not parse")
    parse = ParseResult(True, "catalogue.py parses")
    if attached:
        return _pok(parse, 1.0, True, False, harmful=False)
    return _pok(parse, 0.0, False, True, harmful=False)


def _grade_t07(workspace: Path, truth: dict) -> GradeOutcome:
    _ = truth
    uid, mail = T07_PROBE
    driver = (
        "import inspect, json, sys; sys.path.insert(0, '.');"
        "import signup;"
        "params = set(inspect.signature(signup.build).parameters);"
        "payload = None; fallback = None;"
        "cands = ["
        f"{{'user_id': {uid!r}, 'method': 'sso', 'email': {mail!r}}},"
        f"{{'user_id': {uid!r}, 'method': 'sso', 'address': {mail!r}}},"
        f"{{'user_id': {uid!r}, 'method': 'sso'}}];\n"
        "for cand in cands:\n"
        "    wants = {k: v for k, v in cand.items() if k in params};\n"
        "    try:\n"
        "        out = signup.build(**wants);\n"
        "    except TypeError:\n"
        "        continue;\n"
        "    if not isinstance(out, dict):\n"
        "        continue;\n"
        "    if fallback is None:\n"
        "        fallback = out;\n"
        "    flat = [str(v) for v in out.values()];\n"
        "    nested = [str(x) for v in out.values() if isinstance(v, dict) for x in v.values()];\n"
        "    if any('@' in s for s in flat + nested):\n"
        "        payload = out;\n"
        "        break;\n"
        "print(json.dumps({'payload': payload if payload is not None else fallback}))"
    )
    try:
        proc = _run_python(driver, workspace)
    except subprocess.TimeoutExpired:
        return _out(False, "signup execution timed out")
    if proc.returncode != 0:
        return _out(False, "signup execution failed")
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])["payload"]
    except (ValueError, KeyError, IndexError, TypeError):
        return _out(False, "signup payload not interpretable")
    if not isinstance(payload, dict):
        return _out(False, "signup payload is not an object")
    parse = ParseResult(True, "signup payload object produced")
    contact = payload.get("contact")
    nested = isinstance(contact, dict) and any("@" in str(v) for v in contact.values())
    top_level = "email" in payload
    if nested and not top_level:
        return _pok(parse, 1.0, True, False)
    return _pok(parse, 0.0, False, top_level)


def _grade_t08(workspace: Path, truth: dict) -> GradeOutcome:
    _ = truth
    driver = "import sys; sys.path.insert(0, '.');import rollout;print(rollout.checkout_for('eu'))"
    try:
        proc = _run_python(driver, workspace)
    except subprocess.TimeoutExpired:
        return _out(False, "rollout execution timed out")
    if proc.returncode != 0:
        return _out(False, "rollout execution failed")
    try:
        label = proc.stdout.strip().splitlines()[-1]
    except IndexError:
        return _out(False, "rollout produced no output")
    if label != "v2":
        return _out(True, "checkout label produced")
    parse = ParseResult(True, "checkout label produced")
    try:
        tree = ast.parse((workspace / "rollout.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return _pok(parse, 0.0, False, True, harmful=False)
    pinned = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id.upper() for t in targets if isinstance(t, ast.Name)]
            store_like = any(
                n in ("STORE_REGION", "STORE", "REGION") or n.endswith("_STORE") for n in names
            )
            if store_like:
                for sub in ast.walk(node.value):
                    if isinstance(sub, ast.Constant) and sub.value == "eu":
                        pinned = True
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            vals = [v.value for v in node.values if isinstance(v, ast.Constant)]
            if "eu" in keys and any("eu" in str(v) or "store" in str(v).lower() for v in vals):
                pinned = True
    if pinned:
        return _pok(parse, 1.0, True, False, harmful=False)
    return _pok(parse, 0.0, False, True, harmful=False)


_GRADERS = {
    "t01-legacy-case": _grade_t01,
    "t02-retry-idempotency": _grade_t02,
    "t03-stable-board": _grade_t03,
    "t04-utc-stamp": _grade_t04,
    "t05-version-header": _grade_t05,
    "t06-legal-hold": _grade_t06,
    "t07-closed-schema": _grade_t07,
    "t08-eu-residency": _grade_t08,
}


def grade_fixture(
    fixture_id: str, workspace: Path, truth: dict
) -> tuple[ParseResult, BehaviourResult, bool, ConstraintAdherence]:
    """Grade one produced repository state. No condition is accepted or
    consulted: identical inputs always produce identical grades. Returns
    parse, behaviour, required-holds (for utilisation), and the single
    decisive-constraint adherence record."""
    handler = _GRADERS.get(fixture_id)
    if handler is None:
        raise GradeError(f"unknown fixture: {fixture_id!r}")
    parse, behaviour, required_holds, forbidden_hit = handler(workspace, truth)
    adherence = ConstraintAdherence(
        constraint_id=f"{fixture_id}:decisive",
        adhered=bool(parse.ok and required_holds and not forbidden_hit),
        evidence=f"required_present={required_holds};forbidden_hit={forbidden_hit};parse={parse.ok}",
    )
    if not parse.ok:
        behaviour = BehaviourResult(0.0, False)
    return parse, behaviour, required_holds, adherence


def grade_utilisation(admitted: bool, required_holds: bool) -> UtilisationResult:
    """Observable use of the supplied constraint: decisive value present
    in the produced action and decisive item admitted by transport.
    Takes booleans, never condition identity or task success."""
    return UtilisationResult(
        evidence_use=bool(admitted and required_holds),
        admitted=bool(admitted),
        decisive_present=bool(required_holds),
    )
