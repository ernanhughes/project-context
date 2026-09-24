"""Generate the V2 golden fixture (SYNTHETIC). Run from repo root with the
project venv: .venv/Scripts/python.exe scripts/make_v2_golden.py
"""

import hashlib
import json
from pathlib import Path

OPENCODE_VERSION = "2.0.16"
PLUGIN_API_VERSION = "@opencode/plugin 2.0.16"
ADAPTER_VERSION = "0.3.0"
SCHEMA = "project_context.opencode_capture.v2"
STAGE = "opencode.v2.model_context"


def canonicalize(value):
    if isinstance(value, list):
        return [canonicalize(v) for v in value]
    if isinstance(value, dict):
        return {k: canonicalize(value[k]) for k in sorted(value)}
    return value


def sha256_hex(value) -> str:
    # Compact separators match TypeScript JSON.stringify (no spaces).
    # ASCII-only fixture content keeps both implementations byte-identical.
    return hashlib.sha256(
        json.dumps(canonicalize(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


SYS = [
    {"type": "text", "text": "You are a test assistant."},
    {"type": "text", "text": "Follow project rules."},
]

U1 = "Fix the login bug."
U1_CHANGED = "Fix the login bug urgently."
A1 = "I will inspect the code."
A1_LATER = "I inspected the code already."
R1 = "STATIC-REPEATED-OUTPUT"
U2 = "Run the tests."
U2_GROWN = "Run the full test suite now."
R2_SMALL = "3 passed"
R2_GROWN = "3 passed, 47 more lines of output follow in this grown tool result"


def text_msg(role, text, mid, pid, session):
    return {
        "info": {"id": mid, "sessionID": session, "role": role},
        "parts": [
            {"id": pid, "sessionID": session, "messageID": mid, "type": "text", "text": text}
        ],
    }


def tool_msg(role, mid, pid, session, tool, call, output, title):
    return {
        "info": {"id": mid, "sessionID": session, "role": role},
        "parts": [
            {
                "id": pid,
                "sessionID": session,
                "messageID": mid,
                "type": "tool",
                "callID": call,
                "tool": tool,
                "state": {"status": "completed", "output": output, "title": title},
            }
        ],
    }


def tool_def(tool, description, extra_props):
    return {
        "description": description,
        "input": {
            "type": "object",
            "properties": extra_props,
            "required": sorted(extra_props),
            "additionalProperties": False,
        },
    }


SES = "ses-v2-gold-1"
READ = tool_def("read", "Read a file.", {"filePath": {"type": "string"}})
BASH = tool_def("bash", "Run a shell command.", {"command": {"type": "string"}})
GREP = tool_def("grep", "Search file contents.", {"pattern": {"type": "string"}})

inputs = [
    {
        "request_kind": "context",
        "session_id": SES,
        "invocation_sequence": 1,
        "agent": "build",
        "model": {"provider_id": "test-provider", "id": "test-model", "variant": None},
        "model_limits": {"context": 200000, "output": 32000, "source": "ctx.model"},
        "system": SYS,
        "messages": [text_msg("user", U1, "msg-1", "part-1", SES)],
        "tools": {"bash": BASH, "read": READ},
        "options": {},
        "captured_at": "2026-09-24T00:00:01Z",
        "capture_id": "cap-v2-001",
    },
    {
        "request_kind": "context",
        "session_id": SES,
        "invocation_sequence": 2,
        "agent": "build",
        "model": {"provider_id": "test-provider", "id": "test-model", "variant": None},
        "model_limits": {"context": 200000, "output": 32000, "source": "ctx.model"},
        "system": SYS,
        "messages": [
            text_msg("user", U1, "msg-1", "part-1", SES),
            text_msg("assistant", A1, "msg-2", "part-2", SES),
            tool_msg("assistant", "msg-3", "part-3", SES, "read", "call-1", R1, "read src/app.ts"),
            tool_msg("assistant", "msg-4", "part-4", SES, "bash", "call-2", R2_SMALL, "npm test"),
            text_msg("user", U2, "msg-5", "part-5", SES),
        ],
        "tools": {"bash": BASH, "read": READ},
        "options": {"temperature": 0.2},
        "captured_at": "2026-09-24T00:00:02Z",
        "capture_id": "cap-v2-002",
    },
    {
        "request_kind": "context",
        "session_id": SES,
        "invocation_sequence": 3,
        "agent": "build",
        "model": {"provider_id": "test-provider", "id": "test-model", "variant": None},
        "model_limits": {"context": 200000, "output": 32000, "source": "ctx.model"},
        "system": SYS,
        "messages": [
            text_msg("user", U1_CHANGED, "msg-1", "part-1", SES),
            text_msg("assistant", A1_LATER, "msg-2", "part-2", SES),
            tool_msg("assistant", "msg-3", "part-3", SES, "read", "call-1", R1, "read src/app.ts"),
            tool_msg("assistant", "msg-4", "part-4", SES, "bash", "call-2", R2_GROWN, "npm test"),
            text_msg("user", U2_GROWN, "msg-5", "part-5", SES),
            text_msg("assistant", "Tests pass.", "msg-6", "part-6", SES),
        ],
        "tools": {"grep": GREP, "read": READ},
        "options": {"temperature": 0.2},
        "captured_at": "2026-09-24T00:00:03Z",
        "capture_id": "cap-v2-003",
    },
]

records = []
for inp in inputs:
    observed = {
        "system": inp["system"],
        "messages": inp["messages"],
        "tools": inp["tools"],
        "options": inp["options"],
    }
    records.append(
        {
            "schema": SCHEMA,
            "capture_id": inp["capture_id"],
            "captured_at": inp["captured_at"],
            "capture_stage": STAGE,
            "request_kind": inp["request_kind"],
            "session_id": inp["session_id"],
            "invocation_sequence": inp["invocation_sequence"],
            "agent": inp["agent"],
            "model": inp["model"],
            "model_limits": inp["model_limits"],
            "system": inp["system"],
            "messages": inp["messages"],
            "tools": inp["tools"],
            "options": inp["options"],
            "adapter_version": ADAPTER_VERSION,
            "opencode_version": OPENCODE_VERSION,
            "plugin_api_version": PLUGIN_API_VERSION,
            "observer_position": "context-hook",
            "integrity": {"sha256": sha256_hex(observed)},
            "timings_ms": {"serialize": 0, "write": 0, "total": 0},
            "evidence_class": "opencode_capture",
        }
    )

doc = {
    "schema": "project_context.opencode_capture.v2.golden",
    "evidence_class": "synthetic",
    "note": (
        "SYNTHETIC -- NOT BOOK RESULT. Three consecutive primary model "
        "requests sharing the TypeScript adapter tests (inputs to expected "
        "records) and the Python debugger tests (records to bundles/views). "
        "Content is ASCII-only so the TypeScript and Python canonical "
        "hashes agree byte-for-byte; integrity hashes are producer-local "
        "and must not be compared across implementations on non-ASCII "
        "content. Designed conditions: stable system context; byte-identical "
        "repeated tool result (call-1); growing tool result (call-2); early "
        "change at record 3 (stable prefix then churn); tool-definition "
        "removal (bash) plus addition (grep) at record 3."
    ),
    "inputs": inputs,
    "records": records,
}

out = Path("fixtures/opencode-capture-v2/session-three-requests.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(records)} records)")
for record in records:
    print(record["capture_id"], record["integrity"]["sha256"][:12])
