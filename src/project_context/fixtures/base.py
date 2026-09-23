"""Deterministic fixture abstraction. Every fixture separates what the
model may see from what only the evaluator may see:

    Fixture
    ├── visible_context   -> rendered into a ContextBundle
    └── hidden_ground_truth -> probes, oracle labels; NEVER rendered
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from project_context.domain.bundles import ContextBundle, build_bundle
from project_context.domain.items import ContextItem

SCHEMA_VERSION = "project_context.fixture.v1"


@dataclass(frozen=True)
class Probe:
    """One hidden evaluation question. The model never sees `question` or
    `expected`; it sees only the visible bundle."""

    id: str
    question: str
    expected: str
    group: str


@dataclass(frozen=True)
class HiddenTruth:
    """Evaluator-only ground truth. probe_expectations maps probe id to
    the expected answer string. oracle_keep_ids names items a perfect
    policy would retain."""

    probe_expectations: tuple[tuple[str, str], ...]
    critical_item_ids: tuple[str, ...]
    oracle_keep_ids: tuple[str, ...]

    def expected_for(self, probe_id: str) -> str | None:
        mapping = dict(self.probe_expectations)
        return mapping.get(probe_id)


@dataclass(frozen=True)
class BuiltFixture:
    fixture_id: str
    fixture_version: str
    bundle: ContextBundle
    hidden_truth: HiddenTruth


def render_visible_text(bundle: ContextBundle) -> str:
    """Exactly what a model would see: ordered item contents joined by a
    fixed separator. No probe text, no labels, no oracle data."""
    return "\n---\n".join(item.content for item in bundle.items)


class FixtureDefinition(ABC):
    fixture_id: str = "undefined"
    fixture_version: str = "0"

    @abstractmethod
    def visible_items(self) -> list[ContextItem]:
        """Model-visible items in render order."""

    @abstractmethod
    def probes(self) -> list[Probe]:
        """Hidden probes. Must never appear in visible items."""

    @abstractmethod
    def hidden_truth(self) -> HiddenTruth:
        """Evaluator-only truth."""

    def build(self, *, created_at: str) -> BuiltFixture:
        bundle = build_bundle(
            self.visible_items(),
            bundle_id=f"{self.fixture_id}-{self.fixture_version}",
            created_at=created_at,
            evidence_class="synthetic",
        )
        visible = render_visible_text(bundle)
        for probe in self.probes():
            if probe.question in visible:
                raise ValueError(f"probe question leaked into visible context: {probe.id}")
        return BuiltFixture(
            fixture_id=self.fixture_id,
            fixture_version=self.fixture_version,
            bundle=bundle,
            hidden_truth=self.hidden_truth(),
        )
