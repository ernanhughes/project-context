"""Deterministic bundle renderer: selected items become one marked block.

One canonical representation for integration testing, not a
representation experiment. Rules:

- compiler-selected order is preserved exactly;
- every selected item renders exactly once, with its kind header;
- item bodies are verbatim bundle content (epistemic tags assigned by
  the Stage 6C canonical payload survive untouched; the renderer never
  paraphrases, compresses, or rewrites);
- nothing unselected can enter: the renderer sees only the bundle;
- no event history, digests, run codes, or ledger identifiers enter
  the model-facing text;
- stable delimiters mark the block for detection, idempotence, and
  reconciliation.
"""

from __future__ import annotations

import hashlib

from project_context.domain.bundles import ContextBundle
from project_context.runtime.model import BLOCK_CLOSE, BLOCK_OPEN, RenderedBlock, RenderPolicy


def _kind_header(kind: str) -> str:
    return f"[{kind.replace('_', ' ').upper()}]" if kind else "[ITEM]"


def render_bundle(bundle: ContextBundle, policy: RenderPolicy) -> RenderedBlock:
    """Render every selected item once, in bundle order. Pure."""
    sections = []
    for item in bundle.items:
        sections.append(f"{_kind_header(item.kind)}\n{item.content}")
    text = ""
    if sections:
        text = BLOCK_OPEN + "\n" + "\n\n".join(sections) + "\n" + BLOCK_CLOSE
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return RenderedBlock(
        bundle_id=bundle.id,
        policy_id=policy.policy_id,
        text=text,
        item_count=len(bundle.items),
        digest=digest,
    )
