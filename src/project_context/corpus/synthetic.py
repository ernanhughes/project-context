"""Synthetic capture builders for the F1 dry runs. Nothing here is ecological evidence.

Every session built here carries the reserved identifier prefix ``synthetic-`` or
``dry-run-``, which the ecological ledger refuses. The sessions come in two kinds:

* **measurement sessions**, whose composition is chosen so that every quantity F1 reports
  has a value that can be worked out by hand and written into a test;
* **the privacy session**, a fake session with planted material of every kind the privacy
  pipeline exists to stop, used to test the pipeline and nothing else.

The ground truth for a measurement session is the list of part texts the builder wrote, so
the expected values are derived from what was constructed, not from the analyser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from project_context.opencode.bridge import integrity_of

SCHEMA = "project_context.opencode_capture.v2"
STAGE = "opencode.v2.model_context"


def definition(name: str, description: str) -> dict[str, Any]:
    return {"description": description, "input": {}}


def definition_text(name: str, description: str) -> str:
    """The rendered text of a tool definition, written out by hand (not via the ingester)."""
    return '{"description": "' + description + '", "input": {}, "tool": "' + name + '"}'


def tool_text(tool: str, call: str, title: str, body: str) -> str:
    return f"[tool:{tool} call:{call} title:{title}]\n{body}"


@dataclass
class Msg:
    role: str  # user | assistant | tool
    text: str = ""
    tool: str = ""
    call: str = ""
    title: str = ""
    body: str = ""

    def rendered(self) -> str:
        return (
            tool_text(self.tool, self.call, self.title, self.body)
            if self.role == "tool"
            else self.text
        )


@dataclass
class Req:
    messages: list[Msg]
    system: list[str] = field(default_factory=lambda: ["S" * 100])
    tools: dict[str, str] = field(default_factory=dict)  # name -> description
    kind: str = "context"
    window: int | None = None


def _message(session: str, n: int, msg: Msg) -> dict[str, Any]:
    info = {
        "id": f"m{n}",
        "sessionID": session,
        "role": "assistant" if msg.role == "tool" else msg.role,
    }
    if msg.role == "tool":
        part = {
            "id": f"p{n}",
            "sessionID": session,
            "messageID": f"m{n}",
            "type": "tool",
            "callID": msg.call,
            "tool": msg.tool,
            "state": {"status": "completed", "output": msg.body, "title": msg.title},
        }
    else:
        part = {
            "id": f"p{n}",
            "sessionID": session,
            "messageID": f"m{n}",
            "type": "text",
            "text": msg.text,
        }
    return {"info": info, "parts": [part]}


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
                {"context": req.window, "output": 1000, "source": "synthetic"}
                if req.window
                else None
            ),
            "system": [{"type": "text", "text": t} for t in req.system],
            "messages": [_message(session, n, m) for n, m in enumerate(req.messages, start=1)],
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
TOOLS = {"read": "r" * 20, "bash": "b" * 30}
U1 = Msg("user", "u" * 40)
A1 = Msg("assistant", "a" * 60)
T1 = Msg("tool", tool="read", call="c1", title="f1", body="x" * 500)
T2 = Msg("tool", tool="bash", call="c2", title="npm test", body="y" * 300)
U2 = Msg("user", "v" * 30)
T3 = Msg("tool", tool="read", call="c3", title="f1", body="x" * 500)  # same body as T1
A2 = Msg("assistant", "b" * 20)
T4 = Msg("tool", tool="bash", call="c4", title="npm test", body="z" * 350)  # bytes differ from T2


def growth_session() -> tuple[list[dict[str, Any]], list[list[Msg]]]:
    """Five requests. History only ever grows; T3 repeats T1's output; T4 changes T2's bytes.

    Returns (records, the message lists that were written, for hand-derived expectations).
    """
    histories = [
        [U1],
        [U1, A1, T1],
        [U1, A1, T1, T2, U2],
        [U1, A1, T1, T2, U2, T3, A2],
        [U1, A1, T1, T2, U2, T3, A2, T4],
    ]
    reqs = [Req(list(h), tools=TOOLS, window=1000) for h in histories]
    return build_session("synthetic-growth", reqs), histories


def rewrite_session() -> list[dict[str, Any]]:
    """Four requests plus a compaction record. The third rewrites earlier history and the
    fourth changes the system prompt, which breaks the prefix early."""
    summary = Msg("assistant", "s" * 25)
    reqs = [
        Req([U1], tools=TOOLS, window=1000),
        Req([U1, A1, T1], tools=TOOLS, window=1000),
        Req([], tools=TOOLS, window=1000, kind="compaction"),
        Req([summary, T1, U2], tools=TOOLS, window=1000),
        Req([summary, T1, U2, A2], tools=TOOLS, window=1000, system=["S" * 90 + "-changed"]),
    ]
    return build_session("synthetic-rewrite", reqs)


def no_tools_session() -> list[dict[str, Any]]:
    """No tool definitions and no window in any record: both must be UNOBSERVED, not zero."""
    reqs = [Req([U1]), Req([U1, A1]), Req([U1, A1, U2])]
    return build_session("synthetic-notools", reqs)


def long_session(requests: int = 45, *, repeat_every: int = 3) -> list[dict[str, Any]]:
    """A long session for the S6 rule: history grows one message pair per request, and every
    `repeat_every`-th tool result repeats an earlier one."""
    reqs, history = [], [U1]
    for i in range(1, requests + 1):
        reqs.append(Req(list(history), tools=TOOLS, window=100000))
        body = "k" * 200 if i % repeat_every == 0 else f"{i:04d}" + "q" * 196
        history += [
            Msg("assistant", "a" * 30),
            Msg("tool", tool="read", call=f"c{i}", title=f"f{i % 5}", body=body),
        ]
    return build_session("synthetic-long", reqs)


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
        history = [
            Msg("user", "check the deploy notes for the " + SCANNER_BLIND_SPOT + " rotation")
        ]
    else:
        system = [
            f"You are a coding agent working in {p['fake_paths'][0]} for "
            f"the team at {p['fake_emails'][0]}. Build host {p['fake_hostnames'][0]}.",
            "Project rules: never print " + p["api_key_shaped"][0] + ".",
        ]
        history = [
            Msg("user", p["user_free_text"][0]),
            Msg("assistant", "Looking at " + p["fake_paths"][1] + " first."),
            Msg(
                "tool",
                tool="read",
                call=p["identifiers"][2],
                title="read " + p["fake_paths"][0],
                body=".env\n"
                + "\n".join(
                    [
                        p["repo_secrets"][0],
                        p["repo_secrets"][1],
                        p["api_key_shaped"][1],
                        p["api_key_shaped"][2],
                    ]
                ),
            ),
            Msg(
                "tool",
                tool="read",
                call="call-2",
                title="read invoice_export.py",
                body="\n".join(p["source_like"])
                + "\n# owner: "
                + p["fake_emails"][1]
                + " host "
                + p["fake_hostnames"][1],
            ),
            Msg("user", "run the export against " + p["fake_hostnames"][0]),
        ]
    reqs = [Req(history[:1], system=system, tools=TOOLS, window=1000)]
    for n in range(2, len(history) + 1):
        reqs.append(Req(history[:n], system=system, tools=TOOLS, window=1000))
    session = "dry-run-ses-7f3a91"
    records = build_session(session, reqs)
    if not with_blind_spot_only:
        for i, r in enumerate(records, start=1):
            r["capture_id"] = f"cap-dry-{i:04d}-9c2e"
            r["integrity"] = {"sha256": integrity_of(r)}
    return records


# Worked out by hand from the part texts above (system 100 bytes; two definitions of 68 and 78;
# tool results of 529, 335 and 385 bytes), not by running the analyser.
GROWTH_EXPECTED = {
    "bytes": [286, 875, 1240, 1789, 2174],
    "new_bytes": [286, 589, 365, 549, 385],
    "carry_over_bytes": [0, 286, 875, 1240, 1789],
    "redundant_payload_bytes": [0, 0, 0, 529, 529],
    "prefix_bytes": [None, 286, 875, 1240, 1789],
    "identities_with_differing_bytes": [0, 0, 0, 0, 1],
    "first_request_tool_definition_share": round(146 / 286, 6),
    "last_request_redundant_payload_share": round(529 / 2174, 6),
    "last_request_tool_result_share": round(1778 / 2174, 6),
}
