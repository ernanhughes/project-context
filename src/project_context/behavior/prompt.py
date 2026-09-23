"""Frozen reader prompt wrapper v1. Identical across conditions; B0 gets
the same wrapper with an empty context section. The bundle carries its
own earned metadata — the wrapper adds none."""

from __future__ import annotations

PROMPT_VERSION = "behavior-prompt-v2"

SYSTEM_TEXT = (
    "You are completing a controlled software-engineering task. "
    "Use only the task description and the supplied project context. "
    "Return exactly one JSON object matching the output schema, using "
    "exactly these keys and no others: "
    "action, target, value, reason_code. "
    "Do not invent project facts that are not present."
)

EMPTY_CONTEXT_MARKER = "(no project context supplied)"


def build_user_text(task_text: str, context_text: str, schema_text: str) -> str:
    context = context_text if context_text else EMPTY_CONTEXT_MARKER
    return (
        "<TASK>\n" + task_text + "\n</TASK>\n\n"
        "<PROJECT_CONTEXT>\n" + context + "\n</PROJECT_CONTEXT>\n\n"
        "<OUTPUT_SCHEMA>\n" + schema_text + "\n</OUTPUT_SCHEMA>"
    )


def action_schema_text(actions: list[str]) -> str:
    names = ", ".join(f'"{name}"' for name in actions)
    return (
        '{"action": one of [' + names + "], "
        '"target": string or null, "value": string or null, '
        '"reason_code": string or null}'
    )
