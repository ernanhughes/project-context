"""Order uploader with resilience to transient failures.

Orders are posted to the fulfilment endpoint. Network blips are common,
so failed posts are retried with a short pause between attempts.
"""

from __future__ import annotations

import time
import urllib.request

ENDPOINT = "https://fulfilment.example.invalid/v1/orders"
MAX_ATTEMPTS = 3


def post(order: dict[str, str]) -> int:
    """Post one order, retrying transient failures. Returns attempts used."""
    body = str(order).encode("utf-8")
    attempt = 0
    while True:
        attempt += 1
        try:
            request = urllib.request.Request(ENDPOINT, data=body, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                return attempt if response.status == 200 else attempt
        except Exception:
            if attempt >= MAX_ATTEMPTS:
                raise
            time.sleep(1)
