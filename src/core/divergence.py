"""Divergence table: one subject's results laid out by regime, one row per rule (C4).

Follows decision D17 (docs/decisions.md): rows are sorted by (regime, rule_id) and
carry what each rule's result says, with its effect looked up in the pack. Nothing is
aggregated across regimes: no "regimes disagree" flag, no grouping by effect, no
winner. RegimeResult.conflict stays reserved. Rendering is C6 and DS6.

Pure: no I/O, no logging, no clock, and inputs are never changed.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from core.outcomes import Direction, Outcome, Reason
from core.results import RuleResult, SubjectResult
from core.rules import RulePack


class DivergenceError(Exception):
    """Raised when a result does not match the pack (missing rule or other regime)."""


class _Frozen(BaseModel):
    """Base for every table model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_sorted(label: str, items: Iterable[str | tuple[str, ...]]) -> None:
    """Refuse a tuple that is not sorted or has repeats."""
    values = list(items)
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be sorted with no repeats")


class ReadingRow(_Frozen):
    """One reading of an UNSETTLED rule."""

    interpretation_id: str
    outcome: Outcome
    reason: Reason | None
    direction: Direction | None


class DivergenceRow(_Frozen):
    """One assessed rule's result, as it stands in its own regime."""

    regime: str
    rule_id: str
    effect: str
    law_status: Literal["in_force", "proposed"]
    outcome: Outcome
    reason: Reason | None
    direction: Direction | None
    decisive_facts: tuple[str, ...]
    exempted_by: tuple[str, ...]
    in_force_unpublished: bool
    readings: tuple[ReadingRow, ...]

    @model_validator(mode="after")
    def _check(self) -> DivergenceRow:
        """decisive_facts, exempted_by and readings sorted with no repeats."""
        _check_sorted("decisive_facts", self.decisive_facts)
        _check_sorted("exempted_by", self.exempted_by)
        _check_sorted("readings", (r.interpretation_id for r in self.readings))
        return self


class DivergenceTable(_Frozen):
    """Every assessed rule for one subject, one row each, sorted by (regime, rule_id)."""

    subject_id: str
    subject_kind: str
    as_of: date
    rows: tuple[DivergenceRow, ...]
    not_in_effect: tuple[str, ...] = ()
    excluded_proposed: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> DivergenceTable:
        """Rows sorted by (regime, rule_id); id lists sorted; no repeats."""
        _check_sorted("rows", ((r.regime, r.rule_id) for r in self.rows))
        _check_sorted("not_in_effect", self.not_in_effect)
        _check_sorted("excluded_proposed", self.excluded_proposed)
        return self


def _row(result: RuleResult, effect: str) -> DivergenceRow:
    """One row from a rule result; readings only for an UNSETTLED result."""
    readings = ()
    if result.outcome == Outcome.UNSETTLED:
        readings = tuple(
            ReadingRow(
                interpretation_id=i.interpretation_id,
                outcome=i.outcome,
                reason=i.reason,
                direction=i.direction,
            )
            for i in result.base.interpretations
        )
    return DivergenceRow(
        regime=result.regime,
        rule_id=result.rule_id,
        effect=effect,
        law_status=result.law_status,
        outcome=result.outcome,
        reason=result.reason,
        direction=result.direction,
        decisive_facts=result.base.decisive_facts,
        exempted_by=result.exempted_by,
        in_force_unpublished=result.in_force_unpublished,
        readings=readings,
    )


def divergence_table(result: SubjectResult, pack: RulePack) -> DivergenceTable:
    """Lay out a subject result as one row per assessed rule (D17).

    A rule id missing from the pack, or whose regime differs from the pack's, raises
    DivergenceError.
    """
    by_id = {rule.id: rule for rule in pack.rules}
    rows: list[DivergenceRow] = []
    for regime in result.regimes:
        for item in regime.rules:
            rule = by_id.get(item.rule_id)
            if rule is None:
                raise DivergenceError(f"{item.rule_id} is not in the pack")
            if rule.regime != item.regime:
                raise DivergenceError(
                    f"{item.rule_id} is in regime {item.regime} in the result"
                    f" but {rule.regime} in the pack"
                )
            rows.append(_row(item, rule.effect))
    return DivergenceTable(
        subject_id=result.subject_id,
        subject_kind=result.subject_kind,
        as_of=result.as_of,
        rows=tuple(sorted(rows, key=lambda r: (r.regime, r.rule_id))),
        not_in_effect=result.not_in_effect,
        excluded_proposed=result.excluded_proposed,
    )
