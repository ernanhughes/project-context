"""Synthetic capture builders for the F1 dry runs. Nothing here is ecological evidence.

Every session built here carries the reserved identifier prefix ``synthetic-`` or
``dry-run-``, which the ecological ledger refuses. The sessions come in two kinds:

* **measurement sessions**, whose composition is chosen so that every quantity F1 reports
  has a value that can be worked out by hand and written into a test;
* **the privacy session**, a fake session with planted material of every kind the privacy
  pipeline exists to stop, used to test the pipeline and nothing else.

The record shape is the one OpenCode 2.0.16 really produces (see `specs/f1-calibration.md`),
not the shape the first version of these builders assumed: messages are `{role, content}` and a
part is `text`, `reasoning`, `tool-call` or `tool-result`. Structure only is copied from the
calibration run; none of its content is.

The ground truth for a measurement session is the list of part texts the builder wrote, so
the expected values are derived from what was constructed, not from the analyser.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from project_context.opencode.bridge import integrity_of

SCHEMA = "project_context.opencode_capture.v2"
STAGE = "opencode.v2.model_context"


def definition(name: str, description: str) -> dict[str, Any]:
    return {"description": description, "input": {}}


def definition_text(name: str, description: str) -> str:
    """The rendered text of a tool definition, written out by hand (not via the analyser)."""
    return '{"description": "' + description + '", "input": {}, "tool": "' + name + '"}'


@dataclass
class Msg:
    """One part of a message. `kind` is user, assistant, reasoning, call or result."""

    kind: str
    text: str = ""
    call_id: str = ""
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    def rendered(self) -> str:
        """The text this part contributes, written by hand rather than by the analyser."""
        if self.kind == "call":
            return f"{self.tool} {json.dumps(self.args, sort_keys=True)}"
        return self.text


def U(text: str) -> Msg:
    return Msg("user", text)


def A(text: str) -> Msg:
    return Msg("assistant", text)


def Think(text: str) -> Msg:
    return Msg("reasoning", text)


def Call(call_id: str, tool: str, **args: Any) -> Msg:
    return Msg("call", call_id=call_id, tool=tool, args=args)


def Result(call_id: str, tool: str, value: str) -> Msg:
    return Msg("result", value, call_id=call_id, tool=tool)


@dataclass
class Req:
    messages: list[Msg]
    system: list[str] = field(default_factory=lambda: ["S" * 100])
    tools: dict[str, str] = field(default_factory=dict)  # name -> description
    kind: str = "context"
    limits: dict[str, int] | None = None


def _message(n: int, msg: Msg) -> dict[str, Any]:
    if msg.kind == "user":
        return {
            "id": f"m{n}",
            "role": "user",
            "content": [{"type": "text", "text": msg.text}],
            "metadata": {},
        }
    if msg.kind == "assistant":
        return {"id": f"m{n}", "role": "assistant", "content": [{"type": "text", "text": msg.text}]}
    if msg.kind == "reasoning":
        return {
            "id": f"m{n}",
            "role": "assistant",
            "content": [{"type": "reasoning", "text": msg.text, "providerMetadata": {}}],
        }
    if msg.kind == "call":
        return {
            "id": f"m{n}",
            "role": "assistant",
            "content": [
                {
                    "type": "tool-call",
                    "id": msg.call_id,
                    "name": msg.tool,
                    "input": msg.args,
                    "providerExecuted": False,
                }
            ],
        }
    return {
        "role": "tool",
        "content": [
            {
                "type": "tool-result",
                "id": msg.call_id,
                "name": msg.tool,
                "result": {"type": "text", "value": msg.text},
                "providerExecuted": False,
            }
        ],
    }


def build_session(
    session: str, requests: list[Req], *, minutes_apart: float = 1.0
) -> list[dict[str, Any]]:
    """V2 records for a list of requests, with valid integrity hashes and sequence numbers."""
    records = []
    for i, req in enumerate(requests, start=1):
        seconds = int(i * minutes_apart * 60)
        record = {
            "schema": SCHEMA,
            "capture_id": f"{session}-cap-{i:03d}",
            "captured_at": f"2030-01-01T00:{seconds // 60:02d}:{seconds % 60:02d}Z",
            "capture_stage": STAGE,
            "request_kind": req.kind,
            "session_id": session,
            "invocation_sequence": i,
            "agent": "build",
            "model": {
                "provider_id": "synthetic-provider",
                "id": "synthetic-model",
                "variant": None,
            },
            "model_limits": (
                {
                    **{"context": None, "input": None, "output": 1000},
                    **req.limits,
                    "source": "synthetic",
                }
                if req.limits
                else None
            ),
            "system": [{"type": "text", "text": t} for t in req.system],
            "messages": [_message(n, m) for n, m in enumerate(req.messages, start=1)],
            "tools": {name: definition(name, desc) for name, desc in req.tools.items()},
            "options": {},
            "adapter_version": "synthetic",
            "opencode_version": "synthetic",
            "plugin_api_version": "synthetic",
            "observer_position": "context-hook",
            "timings_ms": {"serialize": 0, "write": 0, "total": 0},
            "evidence_class": "synthetic",
        }
        record["integrity"] = {"sha256": integrity_of(record)}
        records.append(record)
    return records


# ---------------------------------------------------------------- measurement session
TOOLS = {"read": "r" * 20, "shell": "b" * 30}
WINDOW = {"context": 1000}
U1 = U("u" * 40)
A1 = A("a" * 60)
C1 = Call("c1", "read", path="f1")
R1 = Result("c1", "read", "x" * 500)
C2 = Call("c2", "shell", command="npm test")
R2 = Result("c2", "shell", "y" * 300)
U2 = U("v" * 30)
C3 = Call("c3", "read", path="f1")  # the same call again
R3 = Result("c3", "read", "x" * 500)  # and the same output again
A2 = A("b" * 20)
C4 = Call("c4", "shell", command="npm test")  # the same command again
R4 = Result("c4", "shell", "z" * 350)  # but different bytes come back


def growth_session() -> tuple[list[dict[str, Any]], list[list[Msg]]]:
    """Five requests. History only ever grows; R3 repeats R1's output; R4 changes R2's bytes.

    Returns (records, the message lists that were written, for hand-derived expectations).
    """
    histories = [
        [U1],
        [U1, A1, C1, R1],
        [U1, A1, C1, R1, C2, R2, U2],
        [U1, A1, C1, R1, C2, R2, U2, C3, R3, A2],
        [U1, A1, C1, R1, C2, R2, U2, C3, R3, A2, C4, R4],
    ]
    reqs = [Req(list(h), tools=TOOLS, limits=WINDOW) for h in histories]
    return build_session("synthetic-growth", reqs), histories


def rewrite_session() -> list[dict[str, Any]]:
    """Four primary requests and a compaction record. After the compaction the history is
    replaced by a summary (a rewrite), and the last request changes the system prompt, which
    breaks the prefix early."""
    summary = A("s" * 25)
    reqs = [
        Req([U1], tools=TOOLS, limits=WINDOW),
        Req([U1, A1, C1, R1], tools=TOOLS, limits=WINDOW),
        Req([], tools=TOOLS, limits=WINDOW, kind="compaction"),
        Req([summary, U2], tools=TOOLS, limits=WINDOW),
        Req([summary, U2, A2], tools=TOOLS, limits=WINDOW, system=["S" * 90 + "-changed"]),
    ]
    return build_session("synthetic-rewrite", reqs)


def no_tools_session() -> list[dict[str, Any]]:
    """No tool definitions and no window in any record: both must be UNOBSERVED, not zero."""
    reqs = [Req([U1]), Req([U1, A1]), Req([U1, A1, U2])]
    return build_session("synthetic-notools", reqs)


def long_session(requests: int = 45, *, repeat_every: int = 3) -> list[dict[str, Any]]:
    """A long session for the S6 rule: history grows by a call and its result each request, and
    every `repeat_every`-th result repeats an earlier one."""
    reqs, history = [], [U1]
    for i in range(1, requests + 1):
        reqs.append(Req(list(history), tools=TOOLS, limits={"context": 100000}))
        body = "k" * 200 if i % repeat_every == 0 else f"{i:04d}" + "q" * 196
        history += [Call(f"c{i}", "read", path=f"f{i % 5}"), Result(f"c{i}", "read", body)]
    return build_session("synthetic-long", reqs)


def edit_session(files: int, requests: int = 6) -> list[dict[str, Any]]:
    """Edits `files` distinct files, one edit call per request from the first."""
    history, reqs = [U1], []
    for i in range(requests):
        reqs.append(Req(list(history), tools={"edit": "e" * 10}))
        if i < files:
            history += [
                Call(f"e{i}", "edit", path=f"file{i}.py", old="a", new="b"),
                Result(f"e{i}", "edit", "Edited"),
            ]
        else:
            history.append(A("a" * 20))
    return build_session("synthetic-edits", reqs)


def repeated_test_run_session(runs: int = 3) -> list[dict[str, Any]]:
    """Runs the test command `runs` times through the shell tool."""
    history, reqs = [U1], []
    for i in range(runs + 1):
        reqs.append(Req(list(history), tools={"shell": "s" * 10}))
        history += [
            Call(f"t{i}", "shell", command="pytest -q"),
            Result(f"t{i}", "shell", "." * (i + 1)),
        ]
    return build_session("synthetic-tests", reqs)


# ---------------------------------------------------------------- privacy session
@dataclass(frozen=True)
class Planted:
    """Strings planted into the privacy session, by class. None may reach a derivative."""

    classes: dict[str, tuple[str, ...]]

    def all(self) -> tuple[str, ...]:
        return tuple(s for group in self.classes.values() for s in group)


PLANTED = Planted(
    {
        "fake_paths": (
            r"C:\Users\jdoe\clients\contoso-billing\src\invoice_export.py",
            "/home/jdoe/work/contoso-billing/config/prod.yaml",
        ),
        "fake_emails": (
            "jane.doe@contoso-billing.test",
            "ops-oncall@internal.contoso-billing.test",
        ),
        "fake_hostnames": ("build-01.internal.contoso-billing.test", "10.44.7.213"),
        "api_key_shaped": (
            "sk-ant-api03-FAKEFAKEFAKEFAKE0000",
            "AKIAZZZZZZZZZZZZZZZZ",
            "ghp_FAKEFAKEFAKEFAKEFAKE0123456789",
        ),
        "repo_secrets": (
            "postgres://admin:hunter2-fake@db.internal.contoso-billing.test:5432/prod",
            "STRIPE_WEBHOOK_SECRET=whsec_notarealsecret_000111222",
        ),
        "user_free_text": (
            "please do not mention to Priya Ramanathan that the Contoso Ltd invoice export broke",
        ),
        "source_like": (
            "def compute_quarterly_bonus_for_contoso(ledger_rows, region_multiplier):",
            "return sum(row.amount * region_multiplier for row in ledger_rows)",
        ),
        "identifiers": ("dry-run-ses-7f3a91", "cap-dry-0001-9c2e", "call_d41d8cd98f00b204"),
    }
)

# A shape the credential patterns do not recognise. The scan will not flag it; the
# derivative must be clean anyway, because it has nowhere to carry it.
SCANNER_BLIND_SPOT = "correct-horse-battery-staple-fake-passphrase"


def privacy_session(*, with_blind_spot_only: bool = False) -> list[dict[str, Any]]:
    """A completely synthetic session salted with every class of planted material.

    With `with_blind_spot_only`, only the string the credential scan cannot recognise is
    planted, to show the derivative does not depend on the scan catching things.
    """
    p = PLANTED.classes
    if with_blind_spot_only:
        system = ["You are a coding agent. Team passphrase: " + SCANNER_BLIND_SPOT]
        history = [U("check the deploy notes for the " + SCANNER_BLIND_SPOT + " rotation")]
    else:
        secrets = [
            p["repo_secrets"][0],
            p["repo_secrets"][1],
            p["api_key_shaped"][1],
            p["api_key_shaped"][2],
        ]
        system = [
            f"You are a coding agent working in {p['fake_paths'][0]} for "
            f"the team at {p['fake_emails'][0]}. Build host {p['fake_hostnames'][0]}.",
            "Project rules: never print " + p["api_key_shaped"][0] + ".",
        ]
        history = [
            U(p["user_free_text"][0]),
            A("Looking at " + p["fake_paths"][1] + " first."),
            Think("The user mentioned " + p["fake_emails"][0] + " so I should be careful."),
            Call(p["identifiers"][2], "read", path=p["fake_paths"][0]),
            Result(p["identifiers"][2], "read", ".env\n" + "\n".join(secrets)),
            Call("call-2", "read", path="invoice_export.py"),
            Result(
                "call-2",
                "read",
                "\n".join(p["source_like"])
                + "\n# owner: "
                + p["fake_emails"][1]
                + " host "
                + p["fake_hostnames"][1],
            ),
            U("run the export against " + p["fake_hostnames"][0]),
        ]
    reqs = [
        Req(history[:n], system=system, tools=TOOLS, limits=WINDOW)
        for n in range(1, len(history) + 1)
    ]
    records = build_session("dry-run-ses-7f3a91", reqs)
    if not with_blind_spot_only:
        for i, r in enumerate(records, start=1):
            r["capture_id"] = f"cap-dry-{i:04d}-9c2e"
            r["integrity"] = {"sha256": integrity_of(r)}
    return records


# Worked out by hand from the part texts above: system 100 bytes; definitions of 68 (read) and
# 79 (shell) bytes; part sizes user 40 and 30, assistant 60 and 20, calls 19 (read) and 29
# (shell), results 500 (read, twice), 300 and 350 (shell).
GROWTH_EXPECTED = {
    "bytes": [287, 866, 1225, 1764, 2143],
    "new_bytes": [287, 579, 359, 539, 379],
    "carry_over_bytes": [0, 287, 866, 1225, 1764],
    "redundant_payload_bytes": [0, 0, 0, 500, 500],
    "duplicate_part_bytes": [0, 0, 0, 519, 548],
    "prefix_bytes": [None, 287, 866, 1225, 1764],
    "identities_with_differing_bytes": [0, 0, 0, 0, 1],
    "max_calls_per_identity": [0, 1, 1, 2, 2],
    "first_request_tool_definition_share": round(147 / 287, 6),
    "last_request_redundant_payload_share": round(500 / 2143, 6),
    "last_request_tool_result_share": round(1650 / 2143, 6),
    "last_request_category_bytes": {
        "tool_definition": 147,
        "system": 100,
        "user": 70,
        "assistant": 80,
        "tool_call": 96,
        "tool_result": 1650,
    },
}
