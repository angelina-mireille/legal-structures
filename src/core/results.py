"""Results: exemptions, clock notes and the result model by subject and regime (C3c).

Builds on C3b's assess_rule (the base outcome) following the C3c decisions
(docs/decisions.md):
- D6 exemptions are strict: one applies only if its final outcome is APPLIES;
  open exemptions are flagged, never applied. D6a: an exemption with an open
  exemption of its own (a carve-back) does not apply either. D6b: an UNSETTLED
  exemption carries what its readings ask for.
- D7 clocks are display only: amount, unit and trigger are copied; no dates.
- D8 assess_subject picks the top-level rules for a subject kind, filters proposed
  law, and groups results by regime.

Pure: no I/O, no logging, no clock, and inputs are never changed. EvaluationError and
OutcomeError from lower layers propagate unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from core.evaluator import Fact
from core.outcomes import (
    Direction,
    Outcome,
    Question,
    Reason,
    RuleOutcome,
    _merge_questions,
    assess_rule,
)
from core.rules import NODE_KINDS, Rule, RulePack

CLOCK_NOTE: Final[str] = "Start date not computed; when the clock starts is for counsel."

_OPEN: Final[frozenset[Outcome]] = frozenset(
    {Outcome.CONDITIONAL, Outcome.INSUFFICIENT_FACTS, Outcome.UNSETTLED}
)


class ResultError(Exception):
    """Raised when a result cannot be built (bad subject kind, chain, or pending law)."""


class ClockStatus(StrEnum):
    """Why a clock note is shown (D7)."""

    APPLIES = "applies"
    IF_CONFIRMED = "if_confirmed"
    UNDER_READINGS = "under_readings"


class _Frozen(BaseModel):
    """Base for every result model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_sorted(label: str, items: Iterable[str]) -> None:
    """Refuse a tuple that is not sorted or has repeats."""
    values = list(items)
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be sorted with no repeats")


# ---- Models ---------------------------------------------------------------------------


class ClockNote(_Frozen):
    """A rule's clock, copied for display, with why it is shown. No date is computed."""

    amount: int
    unit: str
    trigger: str
    status: ClockStatus
    readings: tuple[str, ...] = ()
    note: str = CLOCK_NOTE

    @model_validator(mode="after")
    def _check(self) -> ClockNote:
        """readings exactly with UNDER_READINGS, sorted; the note text is fixed."""
        if bool(self.readings) != (self.status == ClockStatus.UNDER_READINGS):
            raise ValueError("readings are listed exactly when the status is UNDER_READINGS")
        _check_sorted("readings", self.readings)
        if self.note != CLOCK_NOTE:
            raise ValueError(f"note must be {CLOCK_NOTE!r}")
        return self


class ExemptionResult(_Frozen):
    """One exemption of a rule: its final outcome, whether it applied, whether it is open."""

    rule_id: str
    outcome: Outcome
    applied: bool
    unresolved: bool
    questions: tuple[Question, ...] = ()
    facts_to_confirm: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> ExemptionResult:
        """D6/D6a flags; questions and facts_to_confirm only when unresolved, sorted."""
        if self.outcome == Outcome.APPLIES:
            if self.applied == self.unresolved:
                raise ValueError("an APPLIES exemption is exactly one of applied or unresolved")
        elif self.outcome == Outcome.DOES_NOT_APPLY:
            if self.applied or self.unresolved:
                raise ValueError("a DOES_NOT_APPLY exemption is neither applied nor unresolved")
        elif self.applied or not self.unresolved:
            raise ValueError("an open exemption is unresolved and not applied")
        if (self.questions or self.facts_to_confirm) and not self.unresolved:
            raise ValueError("questions and facts_to_confirm only for an unresolved exemption")
        _check_sorted("questions", (q.fact for q in self.questions))
        _check_sorted("facts_to_confirm", self.facts_to_confirm)
        return self


def _expected_clock(
    outcome: Outcome, direction: Direction | None, base: RuleOutcome
) -> tuple[ClockStatus, tuple[str, ...]] | None:
    """D7: the clock status and readings a final result calls for, or None for no clock."""
    if outcome == Outcome.APPLIES:
        return ClockStatus.APPLIES, ()
    if outcome == Outcome.CONDITIONAL and direction == Direction.APPLIES_IF_CONFIRMED:
        return ClockStatus.IF_CONFIRMED, ()
    if outcome == Outcome.UNSETTLED:
        ids = tuple(
            item.interpretation_id
            for item in base.interpretations
            if item.outcome == Outcome.APPLIES
            or (
                item.outcome == Outcome.CONDITIONAL
                and item.direction == Direction.APPLIES_IF_CONFIRMED
            )
        )
        if ids:
            return ClockStatus.UNDER_READINGS, ids
    return None


class RuleResult(_Frozen):
    """A rule's final result: the C3b base, its exemptions (D6) and its clock note (D7)."""

    rule_id: str
    regime: str
    outcome: Outcome
    reason: Reason | None
    direction: Direction | None
    base: RuleOutcome
    exemptions: tuple[ExemptionResult, ...] = ()
    exempted_by: tuple[str, ...] = ()
    clock: ClockNote | None = None

    @model_validator(mode="after")
    def _check(self) -> RuleResult:
        """Final fields consistent with the base, the exemptions (D6) and the clock (D7)."""
        if self.base.rule_id != self.rule_id:
            raise ValueError("base is for a different rule")
        _check_sorted("exemptions", (e.rule_id for e in self.exemptions))
        _check_sorted("exempted_by", self.exempted_by)
        if self.base.outcome == Outcome.DOES_NOT_APPLY and self.exemptions:
            raise ValueError("exemptions are not evaluated when the base is DOES_NOT_APPLY")
        applied = tuple(e.rule_id for e in self.exemptions if e.applied)
        if (self.reason == Reason.EXEMPT) != bool(self.exempted_by):
            raise ValueError("reason is EXEMPT exactly when exempted_by is non-empty")
        if self.reason == Reason.EXEMPT:
            if self.outcome != Outcome.DOES_NOT_APPLY or self.direction is not None:
                raise ValueError("EXEMPT is DOES_NOT_APPLY with no direction")
            if self.exempted_by != applied:
                raise ValueError("exempted_by must be the applied exemptions")
        else:
            final = (self.outcome, self.reason, self.direction)
            if final != (self.base.outcome, self.base.reason, self.base.direction):
                raise ValueError("without an applying exemption the base outcome stands")
            if applied:
                raise ValueError("an applied exemption makes the result EXEMPT")
        if self.clock is not None:
            expected = _expected_clock(self.outcome, self.direction, self.base)
            if expected != (self.clock.status, self.clock.readings):
                raise ValueError("clock status and readings do not match the final outcome")
        return self


class RegimeResult(_Frozen):
    """The results for one regime. conflict is reserved for v1 and is always None."""

    regime: str
    rules: tuple[RuleResult, ...]
    conflict: None = None

    @model_validator(mode="after")
    def _check(self) -> RegimeResult:
        """Rules sorted by id, all of this regime."""
        _check_sorted("rules", (r.rule_id for r in self.rules))
        if any(r.regime != self.regime for r in self.rules):
            raise ValueError("every rule must be of this regime")
        return self


class SubjectResult(_Frozen):
    """Every top-level result for one subject, grouped by regime (D8)."""

    subject_id: str
    subject_kind: str
    regimes: tuple[RegimeResult, ...]
    excluded_proposed: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> SubjectResult:
        """Regimes and excluded ids sorted with no repeats."""
        _check_sorted("regimes", (r.regime for r in self.regimes))
        _check_sorted("excluded_proposed", self.excluded_proposed)
        return self


# ---- D6 exemptions and D7 clocks --------------------------------------------------------


def _rule(pack: RulePack, rule_id: str) -> Rule:
    """The rule with this id (assess_rule has already refused unknown ids)."""
    return next(r for r in pack.rules if r.id == rule_id)


def _open_details(base: RuleOutcome) -> tuple[tuple[Question, ...], tuple[str, ...]]:
    """An open outcome's questions and facts_to_confirm; for UNSETTLED, across readings (D6b)."""
    if base.outcome == Outcome.UNSETTLED:
        readings = base.interpretations
        confirm = sorted({n for item in readings for n in item.facts_to_confirm})
        return _merge_questions(item.questions for item in readings), tuple(confirm)
    return base.questions, base.facts_to_confirm


def _exemption(
    rule_id: str, pack: RulePack, facts: Mapping[str, Fact], chain: tuple[str, ...]
) -> ExemptionResult:
    """Assess one exemption with the full C3c logic and decide whether it applies (D6, D6a)."""
    result = _final(rule_id, pack, facts, chain)
    if result.outcome == Outcome.DOES_NOT_APPLY:
        return ExemptionResult(
            rule_id=rule_id, outcome=result.outcome, applied=False, unresolved=False
        )
    if result.outcome == Outcome.APPLIES:
        carve_backs = [e for e in result.exemptions if e.unresolved]
        if not carve_backs:
            return ExemptionResult(
                rule_id=rule_id, outcome=result.outcome, applied=True, unresolved=False
            )
        confirm = sorted({n for e in carve_backs for n in e.facts_to_confirm})
        return ExemptionResult(
            rule_id=rule_id,
            outcome=result.outcome,
            applied=False,
            unresolved=True,
            questions=_merge_questions(e.questions for e in carve_backs),
            facts_to_confirm=tuple(confirm),
        )
    questions, confirm = _open_details(result.base)
    return ExemptionResult(
        rule_id=rule_id,
        outcome=result.outcome,
        applied=False,
        unresolved=True,
        questions=questions,
        facts_to_confirm=confirm,
    )


def _clock(
    rule: Rule, outcome: Outcome, direction: Direction | None, base: RuleOutcome
) -> ClockNote | None:
    """D7: a ClockNote copying the rule's clock, when the final result calls for one."""
    expected = _expected_clock(outcome, direction, base)
    if rule.clock is None or expected is None:
        return None
    status, readings = expected
    return ClockNote(
        amount=rule.clock.amount,
        unit=rule.clock.unit,
        trigger=rule.clock.trigger,
        status=status,
        readings=readings,
    )


def _final(
    rule_id: str, pack: RulePack, facts: Mapping[str, Fact], chain: tuple[str, ...]
) -> RuleResult:
    """D6 over the C3b base, recursively through unless; chain guards against repeats."""
    if rule_id in chain:
        raise ResultError("exemption chain repeats a rule: " + " -> ".join((*chain, rule_id)))
    base = assess_rule(rule_id, pack, facts)
    rule = _rule(pack, rule_id)
    exemptions: tuple[ExemptionResult, ...] = ()
    if base.outcome != Outcome.DOES_NOT_APPLY:
        exemptions = tuple(
            _exemption(ref, pack, facts, (*chain, rule_id)) for ref in sorted(rule.unless)
        )
    exempted_by = tuple(e.rule_id for e in exemptions if e.applied)
    if exempted_by:
        outcome, reason, direction = Outcome.DOES_NOT_APPLY, Reason.EXEMPT, None
    else:
        outcome, reason, direction = base.outcome, base.reason, base.direction
    return RuleResult(
        rule_id=rule_id,
        regime=rule.regime,
        outcome=outcome,
        reason=reason,
        direction=direction,
        base=base,
        exemptions=exemptions,
        exempted_by=exempted_by,
        clock=_clock(rule, outcome, direction, base),
    )


def assess_rule_final(rule_id: str, pack: RulePack, facts: Mapping[str, Fact]) -> RuleResult:
    """The final result of one rule: C3b base, exemptions applied (D6), clock note (D7)."""
    return _final(rule_id, pack, facts, ())


# ---- D8 subjects ------------------------------------------------------------------------


def _references(rule: Rule) -> tuple[str, ...]:
    """The rule ids named in binding and unless, sorted."""
    refs = {*rule.unless, *((rule.binding,) if rule.binding else ())}
    return tuple(sorted(refs))


def _check_no_proposed(rule: Rule, by_id: Mapping[str, Rule]) -> None:
    """Raise if rule relies, through binding or unless at any depth, on a proposed rule."""
    seen: set[str] = set()
    stack = list(reversed(_references(rule)))
    while stack:
        ref = stack.pop()
        if ref in seen or ref not in by_id:  # unknown ids are refused when evaluated
            continue
        seen.add(ref)
        if by_id[ref].law_status == "proposed":
            raise ResultError(
                f"{rule.id} depends on proposed rule {ref} through binding or unless;"
                " pending-law dependencies are not handled yet (DS8)"
            )
        stack.extend(reversed(_references(by_id[ref])))


def assess_subject(
    subject_id: str,
    subject_kind: str,
    pack: RulePack,
    facts: Mapping[str, Fact],
    include_proposed: bool = False,
) -> SubjectResult:
    """Every top-level rule for this subject kind, assessed and grouped by regime (D8).

    Top-level rules have applies_to equal to subject_kind and are not named in any
    rule's binding or unless. Proposed rules are left out (and listed) unless
    include_proposed is True; an included rule relying on a proposed one raises.
    """
    if subject_kind not in NODE_KINDS:
        raise ResultError(
            f"unknown subject kind {subject_kind!r}; expected one of {', '.join(NODE_KINDS)}"
        )
    by_id = {rule.id: rule for rule in pack.rules}
    helpers = {ref for rule in pack.rules for ref in _references(rule)}
    candidates = sorted(
        (r for r in pack.rules if r.applies_to == subject_kind and r.id not in helpers),
        key=lambda r: r.id,
    )
    included = [r for r in candidates if include_proposed or r.law_status != "proposed"]
    excluded = tuple(r.id for r in candidates if r not in included)
    if not include_proposed:
        for rule in included:
            _check_no_proposed(rule, by_id)
    results = [assess_rule_final(rule.id, pack, facts) for rule in included]
    regimes = tuple(
        RegimeResult(regime=regime, rules=tuple(r for r in results if r.regime == regime))
        for regime in sorted({r.regime for r in results})
    )
    return SubjectResult(
        subject_id=subject_id,
        subject_kind=subject_kind,
        regimes=regimes,
        excluded_proposed=excluded,
    )
