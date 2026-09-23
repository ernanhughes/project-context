"""Reference fixture v1. SYNTHETIC — NOT BOOK RESULT.

Tiny deterministic world proving the fixture mechanism:

- rule-001: exact project rule (must survive verbatim)
- ident-001: exact identifier (must survive verbatim)
- file-001: synthetic file observation (recoverable in-fiction)
- tool-001: tool result summary (compressible in-fiction)
- hypo-001: temporary hypothesis, explicitly UNVERIFIED (status must survive)
- req-001: current user request

Hidden probes test rule adherence, identifier recovery, and uncertainty
preservation. Nothing but visible item contents is rendered to the model.
"""

from __future__ import annotations

from project_context.domain.items import ContextItem, make_item
from project_context.fixtures.base import FixtureDefinition, HiddenTruth, Probe

FIXTURE_ID = "reference"
FIXTURE_VERSION = "1"

RULE_TEXT = "Never modify production migrations without explicit approval."
IDENT_TEXT = "Migration ID is 01947."
FILE_TEXT = "src/server.py (synthetic excerpt):\ndef health():\n    return 'ok'"
TOOL_TEXT = "Test summary (synthetic): 917 passed, 3 failed."
HYPO_TEXT = "Maybe the serializer is corrupting timestamps (unverified)."
REQUEST_TEXT = "Fix the failing checkout test."


class ReferenceFixture(FixtureDefinition):
    fixture_id = FIXTURE_ID
    fixture_version = FIXTURE_VERSION

    def visible_items(self) -> list[ContextItem]:
        return [
            make_item(
                id="rule-001",
                source="project-rules",
                kind="instruction",
                content=RULE_TEXT,
                authority="project",
                scope="global",
            ),
            make_item(
                id="ident-001",
                source="project-rules",
                kind="identifier",
                content=IDENT_TEXT,
                authority="project",
                scope="task",
            ),
            make_item(
                id="file-001",
                source="tool-result",
                kind="file-observation",
                content=FILE_TEXT,
                authority="tool-output",
                scope="task",
                semantic_id="file-src-server",
            ),
            make_item(
                id="tool-001",
                source="tool-result",
                kind="test-summary",
                content=TOOL_TEXT,
                authority="tool-output",
                scope="task",
            ),
            make_item(
                id="hypo-001",
                source="agent-note",
                kind="hypothesis",
                content=HYPO_TEXT,
                authority="agent",
                scope="task",
            ),
            make_item(
                id="req-001",
                source="user",
                kind="request",
                content=REQUEST_TEXT,
                authority="user",
                scope="turn",
            ),
        ]

    def probes(self) -> list[Probe]:
        return [
            Probe(
                id="probe-rule",
                question="What is the standing rule about production migrations?",
                expected=RULE_TEXT,
                group="exact-constraint",
            ),
            Probe(
                id="probe-ident",
                question="Which migration identifier is active?",
                expected=IDENT_TEXT,
                group="identifier",
            ),
            Probe(
                id="probe-hypo-status",
                question="What is the verification status of the serializer hypothesis?",
                expected="unverified",
                group="status",
            ),
        ]

    def hidden_truth(self) -> HiddenTruth:
        return HiddenTruth(
            probe_expectations=tuple((probe.id, probe.expected) for probe in self.probes()),
            critical_item_ids=("rule-001", "ident-001"),
            oracle_keep_ids=("rule-001", "ident-001", "tool-001", "req-001"),
        )


def get_fixture() -> ReferenceFixture:
    return ReferenceFixture()
