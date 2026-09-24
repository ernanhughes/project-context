"""Catalogue client with paged fetching.

Fetches catalogue items page by page from the catalogue service and
returns the combined list.
"""

from __future__ import annotations

import urllib.request

BASE = "https://catalogue.example.invalid/v2/items"
PAGE_SIZE = 50


def fetch_all() -> list[dict]:
    """Fetch every catalogue page and return the combined items."""
    import json

    items: list[dict] = []
    page = 1
    while True:
        url = f"{BASE}?page={page}&size={PAGE_SIZE}"
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.load(response)
        items.extend(payload["items"])
        if len(payload["items"]) < PAGE_SIZE:
            break
        page += 1
    return items
