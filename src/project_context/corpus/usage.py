"""The harness's own record of what each request cost, read after the fact.

The capture hook runs before a request is sent, so it cannot see usage. OpenCode records,
for every assistant message, the provider-reported token counts (input, output, reasoning,
cache read and write), the cost and the timing, in its local database. The calibration run
found this (`specs/f1-calibration.md`). Joined to a session it turns four quantities that
were unobservable at the capture boundary into measured ones: prompt tokens, provider-reported
cache reads, cost and latency.

Discipline:

* **Read-only.** The database is opened in read-only mode and nothing is written.
* **One table, three fields.** Only `session_message` is queried, and only the `tokens`,
  `cost`, `time` and `type` of assistant messages. The same database holds account and
  credential tables; this module never names them, and a test checks that.
* **Numbers out.** Nothing textual is returned, and none of it reaches a derivative except as
  a number.
* **No guessing.** Usage is joined to a session's primary requests by order and only if the
  counts are equal. Otherwise the join is recorded as a mismatch and usage stays unobserved.

Usage is the *provider-reported* figure. It includes material the provider adds after the
observation point, which is exactly why it is preferred to any estimate for window pressure.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_QUERY = "SELECT data FROM session_message WHERE session_id = ? AND type = 'assistant' ORDER BY seq"


def _number(value: Any) -> int | float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def read_session_usage(db_path: Path, session_id: str) -> list[dict[str, Any]] | None:
    """Per-assistant-message usage for one session, oldest first, or None if unreadable.

    `prompt_tokens` is everything the provider counted as the prompt: fresh input plus
    cache reads plus cache writes.
    """
    if not db_path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = con.execute(_QUERY, (session_id,)).fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    usage: list[dict[str, Any]] = []
    for (raw,) in rows:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        stamps = data.get("time") if isinstance(data.get("time"), dict) else {}
        created, completed = stamps.get("created"), stamps.get("completed")
        latency = (
            completed - created
            if isinstance(created, (int, float)) and isinstance(completed, (int, float))
            else None
        )
        usage.append(
            {
                "prompt_tokens": int(
                    _number(tokens.get("input"))
                    + _number(cache.get("read"))
                    + _number(cache.get("write"))
                ),
                "output_tokens": int(_number(tokens.get("output"))),
                "cache_read_tokens": int(_number(cache.get("read"))),
                "cost": float(_number(data.get("cost"))),
                "latency_ms": latency if latency is not None else "UNOBSERVED",
            }
        )
    return usage
