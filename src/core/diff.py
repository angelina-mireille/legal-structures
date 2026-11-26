"""Diff engine: one subject's results under two sets of facts and two dates (C4).

Follows the C4 decisions (docs/decisions.md):
- D14 diff_subjects calls assess_subject once per side, with the same pack, subject and
  include_proposed, so a result is never paired with the wrong facts. Both as_of dates
  are required; the code never reads the clock.
- D15 a rule assessed on both sides is a flip when its final (outcome, reason,
  direction) differs, a detail change when only listed detail fields differ, and
  otherwise unchanged. A rule assessed on one side only is listed in entered_effect or
  left_effect.
- D16 changed facts compare (value, grade); absent counts as UNKNOWN. The facts a rule
  refers to are read statically from the pack. A changed rule lists the changed facts
  it refers to; the diff makes no claim about which of them made the difference.
- D18 frozen models, sorted tuples, JSON round trip.

Pure: no I/O, no logging, no clock, and inputs are never changed.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from core.evaluator import Fact, TriValue
from core.graph import EvidenceGrade
from core.results import RuleResult, SubjectResult, assess_subject
from core.rules import AllExpr, AnyExpr, FactExpr, NotExpr, Rule, RulePack

Via = Literal["self", "binding", "unless"]
DetailField = Literal[
    "base",
    "binding_unresolved",
    "clock",
    "decisive_facts",
    "exempted_by",
    "exemptions",
    "facts_to_confirm",
    "in_force_unpublished",
    "questions",
    "readings",
]
ChangeKind = Literal["flip", "detail", "unchanged"]


class DiffError(Exception):
    """Raised when a diff is internally inconsistent (reaching it means a bug)."""


class _Frozen(BaseModel):
    """Base for every diff model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_sorted(label: str, items: Iterable[str | tuple[str, ...]]) -> None:
    """Refuse a tuple that is not sorted or has repeats."""
    values = list(items)
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be sorted with no repeats")


# ---- Models ---------------------------------------------------------------------------


class FactRead(_Frozen):
    """One place a rule refers to a fact.

    rule_id is the rule whose expression holds the leaf; via is the first step from
    the changed rule ("self", "binding" or "unless"); interpretation_id is the reading
    holding the leaf, or None for a plain trigger.
    """

    rule_id: str
    via: Via
    interpretation_id: str | None


def _read_key(read: FactRead) -> tuple[str, str, str]:
    """Sort key for FactRead: rule id, via, then reading id with None first."""
    return (read.rule_id, read.via, read.interpretation_id or "")


class ChangedFact(_Frozen):
    """A changed fact a rule refers to: before and after (None when absent), and where."""

    fact: str
    before: Fact | None
    after: Fact | None
    reads: tuple[FactRead, ...]

    @model_validator(mode="after")
    def _check(self) -> ChangedFact:
        """reads sorted with no repeats."""
        _check_sorted("reads", (_read_key(r) for r in self.reads))
        return self


class RuleChange(_Frozen):
    """A changed rule: the detail fields that differ (names only) and its changed facts."""

    rule_id: str
    changed_fields: tuple[DetailField, ...]
    changed_facts: tuple[ChangedFact, ...]

    @model_validator(mode="after")
    def _check(self) -> RuleChange:
        """changed_fields and changed_facts sorted with no repeats."""
        _check_sorted("changed_fields", self.changed_fields)
        _check_sorted("changed_facts", (c.fact for c in self.changed_facts))
        return self


class SubjectDiff(_Frozen):
    """Both subject results and what differs between them (D14-D16)."""

    before: SubjectResult
    after: SubjectResult
    flips: tuple[RuleChange, ...]
    detail_changes: tuple[RuleChange, ...]
    entered_effect: tuple[str, ...]
    left_effect: tuple[str, ...]
    unchanged_despite_changes: tuple[str, ...]

    @model_validator(mode="after")
    def _check(self) -> SubjectDiff:
        """Same subject on both sides; every tuple sorted with no repeats."""
        if (self.before.subject_id, self.before.subject_kind) != (
            self.after.subject_id,
            self.after.subject_kind,
        ):
            raise ValueError("before and after must be for the same subject id and kind")
        _check_sorted("flips", (c.rule_id for c in self.flips))
        _check_sorted("detail_changes", (c.rule_id for c in self.detail_changes))
        _check_sorted("entered_effect", self.entered_effect)
        _check_sorted("left_effect", self.left_effect)
        _check_sorted("unchanged_despite_changes", self.unchanged_despite_changes)
        return self


# ---- D16 facts a rule refers to (static) ------------------------------------------------


def _leaves(expr: AllExpr | AnyExpr | NotExpr | FactExpr) -> Iterator[str]:
    """Every fact name in an expression."""
    if isinstance(expr, FactExpr):
        yield expr.fact
    elif isinstance(expr, NotExpr):
        yield from _leaves(expr.not_)
    else:
        for child in expr.all if isinstance(expr, AllExpr) else expr.any:
            yield from _leaves(child)


def _rule_leaves(rule: Rule) -> Iterator[tuple[str, str | None]]:
    """(fact, reading id or None) for every leaf in the rule's trigger or readings."""
    if rule.trigger is not None:
        for name in _leaves(rule.trigger):
            yield name, None
    for item in rule.interpretations or ():
        for name in _leaves(item.trigger):
            yield name, item.id


def _fact_reads(rule_id: str, by_id: Mapping[str, Rule]) -> dict[str, frozenset[FactRead]]:
    """Every fact the rule refers to, with each place it appears.

    The rule's own trigger and readings are "self"; its binding chain (binding links
    only, since unless on a binding rule is never applied) is "binding"; each unless
    rule at any depth, with its binding chain and its own unless rules, is "unless".
    """
    found: dict[str, set[FactRead]] = {}

    def add(rule: Rule, via: Via) -> None:
        for name, reading in _rule_leaves(rule):
            read = FactRead(rule_id=rule.id, via=via, interpretation_id=reading)
            found.setdefault(name, set()).add(read)

    def binding_chain(rule: Rule, via: Via) -> None:
        seen: set[str] = set()
        ref = rule.binding
        while ref is not None and ref in by_id and ref not in seen:
            seen.add(ref)
            add(by_id[ref], via)
            ref = by_id[ref].binding

    def exemption(ref: str, seen: set[str]) -> None:
        if ref in seen or ref not in by_id:
            return
        seen.add(ref)
        rule = by_id[ref]
        add(rule, "unless")
        binding_chain(rule, "unless")
        for inner in sorted(rule.unless):
            exemption(inner, seen)

    root = by_id[rule_id]
    add(root, "self")
    binding_chain(root, "binding")
    seen: set[str] = {rule_id}
    for ref in sorted(root.unless):
        exemption(ref, seen)
    return {name: frozenset(reads) for name, reads in found.items()}


def _state(item: Fact | None) -> tuple[TriValue, EvidenceGrade | None]:
    """A fact's (value, grade); absent counts as UNKNOWN with no grade."""
    return (TriValue.UNKNOWN, None) if item is None else (item.value, item.grade)


def _changed(
    before: Mapping[str, Fact], after: Mapping[str, Fact]
) -> dict[str, tuple[Fact | None, Fact | None]]:
    """The facts whose (value, grade) differs, with the before and after Fact."""
    return {
        name: (before.get(name), after.get(name))
        for name in sorted(before.keys() | after.keys())
        if _state(before.get(name)) != _state(after.get(name))
    }


# ---- D15 comparing one rule -------------------------------------------------------------


def _details(result: RuleResult) -> dict[DetailField, object]:
    """The comparable value of each detail field (D15, amended with base)."""
    base = result.base
    clock = result.clock
    return {
        "base": (base.outcome, base.reason, base.direction),
        "binding_unresolved": base.binding_unresolved,
        "clock": None if clock is None else (clock.status, clock.readings),
        "decisive_facts": base.decisive_facts,
        "exempted_by": result.exempted_by,
        "exemptions": tuple(
            (e.rule_id, e.outcome, e.applied, e.unresolved, e.questions, e.facts_to_confirm)
            for e in result.exemptions
        ),
        "facts_to_confirm": base.facts_to_confirm,
        "in_force_unpublished": result.in_force_unpublished,
        "questions": base.questions,
        "readings": tuple(
            (i.interpretation_id, i.outcome, i.reason, i.direction) for i in base.interpretations
        ),
    }


def _compare_rule(
    before: RuleResult, after: RuleResult, changed_facts: tuple[ChangedFact, ...]
) -> tuple[ChangeKind, RuleChange | None]:
    """Classify one rule assessed on both sides; changed_facts are those it refers to.

    A flip, or a detail change other than in_force_unpublished alone, that refers to
    no changed fact raises DiffError: with one pack it cannot happen.
    """
    flip = (before.outcome, before.reason, before.direction) != (
        after.outcome,
        after.reason,
        after.direction,
    )
    old, new = _details(before), _details(after)
    fields = tuple(sorted(name for name in old if old[name] != new[name]))
    if not flip and not fields:
        return "unchanged", None
    if not changed_facts and (flip or fields != ("in_force_unpublished",)):
        kind = "flip" if flip else "detail change"
        raise DiffError(f"{before.rule_id}: a {kind} that refers to no changed fact")
    change = RuleChange(rule_id=before.rule_id, changed_fields=fields, changed_facts=changed_facts)
    return ("flip" if flip else "detail"), change


# ---- D14 the public entry point ---------------------------------------------------------


def _by_rule(result: SubjectResult) -> dict[str, RuleResult]:
    """Every assessed rule's result, by rule id."""
    return {r.rule_id: r for regime in result.regimes for r in regime.rules}


def diff_subjects(
    subject_id: str,
    subject_kind: str,
    pack: RulePack,
    facts_before: Mapping[str, Fact],
    facts_after: Mapping[str, Fact],
    *,
    as_of_before: date,
    as_of_after: date,
    include_proposed: bool = False,
) -> SubjectDiff:
    """Assess the subject on each side and say what differs (D14-D16).

    Errors from assess_subject (a datetime as_of, an unknown subject kind, bad facts)
    propagate unchanged.
    """
    before = assess_subject(
        subject_id,
        subject_kind,
        pack,
        facts_before,
        as_of=as_of_before,
        include_proposed=include_proposed,
    )
    after = assess_subject(
        subject_id,
        subject_kind,
        pack,
        facts_after,
        as_of=as_of_after,
        include_proposed=include_proposed,
    )
    by_id = {rule.id: rule for rule in pack.rules}
    changed = _changed(facts_before, facts_after)
    old, new = _by_rule(before), _by_rule(after)
    flips: list[RuleChange] = []
    details: list[RuleChange] = []
    unchanged: list[str] = []
    for rule_id in sorted(old.keys() & new.keys()):
        reads = _fact_reads(rule_id, by_id)
        facts = tuple(
            ChangedFact(
                fact=name,
                before=changed[name][0],
                after=changed[name][1],
                reads=tuple(sorted(reads[name], key=_read_key)),
            )
            for name in sorted(changed.keys() & reads.keys())
        )
        kind, change = _compare_rule(old[rule_id], new[rule_id], facts)
        if change is not None:
            (flips if kind == "flip" else details).append(change)
        elif facts:
            unchanged.append(rule_id)
    return SubjectDiff(
        before=before,
        after=after,
        flips=tuple(flips),
        detail_changes=tuple(details),
        entered_effect=tuple(sorted(new.keys() - old.keys())),
        left_effect=tuple(sorted(old.keys() - new.keys())),
        unchanged_despite_changes=tuple(unchanged),
    )
