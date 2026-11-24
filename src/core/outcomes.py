"""Outcomes: one of five labels for a rule, computed from C3a evaluations.

APPLIES, DOES_NOT_APPLY, CONDITIONAL, INSUFFICIENT_FACTS and UNSETTLED, following the
C3b decisions (docs/decisions.md). Every outcome comes from re-running the C3a
evaluator, never from guessing: relevance (D1) enumerates hypothetical verified facts,
and decisive facts (D2) remove one fact at a time.

Exemptions (unless) are not applied here; their ids are carried as exemptions_pending
for C3c. Pure: no I/O, no logging, no clock, and inputs are never changed.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from core.evaluator import (
    GRADE_RANK,
    Fact,
    LeafReason,
    LeafResult,
    RuleEvaluation,
    TriValue,
    evaluate_rule,
)
from core.graph import EvidenceGrade
from core.rules import RulePack

MAX_RELEVANCE_FACTS: Final[int] = 12

Evaluate = Callable[[Mapping[str, Fact]], RuleEvaluation]


class OutcomeError(Exception):
    """Raised when an outcome cannot be computed safely (for example, the relevance cap)."""


class Outcome(StrEnum):
    """The five outcomes."""

    APPLIES = "applies"
    DOES_NOT_APPLY = "does_not_apply"
    CONDITIONAL = "conditional"
    INSUFFICIENT_FACTS = "insufficient_facts"
    UNSETTLED = "unsettled"


class Reason(StrEnum):
    """Why a rule does not apply."""

    TEST_NOT_MET = "test_not_met"
    NOT_BOUND = "not_bound"


class Direction(StrEnum):
    """Which way a CONDITIONAL result goes if its suspected facts are confirmed."""

    APPLIES_IF_CONFIRMED = "applies_if_confirmed"
    DOES_NOT_APPLY_IF_CONFIRMED = "does_not_apply_if_confirmed"


class QuestionKind(StrEnum):
    """What an INSUFFICIENT_FACTS question asks for."""

    MISSING = "missing"
    NEEDS_STRONGER_EVIDENCE = "needs_stronger_evidence"


_DEFINITE: Final[frozenset[Outcome]] = frozenset(
    {Outcome.APPLIES, Outcome.DOES_NOT_APPLY, Outcome.CONDITIONAL}
)


class _Frozen(BaseModel):
    """Base for every outcome model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- Models ---------------------------------------------------------------------------


class Question(_Frozen):
    """One fact the user must supply (MISSING) or support better (NEEDS_STRONGER_EVIDENCE)."""

    fact: str
    kind: QuestionKind
    current_grade: EvidenceGrade | None
    required_grade: EvidenceGrade | None

    @model_validator(mode="after")
    def _grades_match_kind(self) -> Question:
        """MISSING has no grades; NEEDS_STRONGER_EVIDENCE has current below required."""
        if self.kind == QuestionKind.MISSING:
            if self.current_grade is not None or self.required_grade is not None:
                raise ValueError("a MISSING question has no grades")
            return self
        current, required = self.current_grade, self.required_grade
        if current not in GRADE_RANK or required not in GRADE_RANK:
            raise ValueError("NEEDS_STRONGER_EVIDENCE needs a stated current and required grade")
        if GRADE_RANK[current] >= GRADE_RANK[required]:
            raise ValueError("current_grade must be below required_grade")
        return self


def _check_sorted(label: str, items: Iterable[str]) -> None:
    """Refuse a tuple that is not sorted or has repeats."""
    values = list(items)
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be sorted with no repeats")


def _check_details(
    outcome: Outcome,
    reason: Reason | None,
    direction: Direction | None,
    decisive: tuple[str, ...],
    confirm: tuple[str, ...],
    questions: tuple[Question, ...],
) -> None:
    """The "only for" constraints shared by rule and interpretation outcomes."""
    if (reason is not None) != (outcome == Outcome.DOES_NOT_APPLY):
        raise ValueError("reason is set exactly when the outcome is DOES_NOT_APPLY")
    if (direction is not None) != (outcome == Outcome.CONDITIONAL):
        raise ValueError("direction is set exactly when the outcome is CONDITIONAL")
    if decisive and outcome not in _DEFINITE:
        raise ValueError("decisive_facts only for APPLIES, DOES_NOT_APPLY or CONDITIONAL")
    if confirm and outcome != Outcome.CONDITIONAL:
        raise ValueError("facts_to_confirm only for CONDITIONAL")
    if questions and outcome != Outcome.INSUFFICIENT_FACTS:
        raise ValueError("questions only for INSUFFICIENT_FACTS")
    _check_sorted("decisive_facts", decisive)
    _check_sorted("facts_to_confirm", confirm)
    _check_sorted("questions", (q.fact for q in questions))


class InterpretationOutcome(_Frozen):
    """The D3 outcome of one reading of a rule with interpretations."""

    interpretation_id: str
    outcome: Outcome
    reason: Reason | None
    direction: Direction | None
    decisive_facts: tuple[str, ...]
    facts_to_confirm: tuple[str, ...]
    questions: tuple[Question, ...]
    evaluation: RuleEvaluation

    @model_validator(mode="after")
    def _check(self) -> InterpretationOutcome:
        """Apply the shared constraints; a single reading is never UNSETTLED."""
        if self.outcome == Outcome.UNSETTLED:
            raise ValueError("a single reading cannot be UNSETTLED")
        _check_details(
            self.outcome,
            self.reason,
            self.direction,
            self.decisive_facts,
            self.facts_to_confirm,
            self.questions,
        )
        return self


class RuleOutcome(_Frozen):
    """A rule's outcome, with what decided it or what is needed to decide it."""

    rule_id: str
    outcome: Outcome
    reason: Reason | None = None
    direction: Direction | None = None
    binding_unresolved: bool = False
    decisive_facts: tuple[str, ...] = ()
    facts_to_confirm: tuple[str, ...] = ()
    questions: tuple[Question, ...] = ()
    interpretations: tuple[InterpretationOutcome, ...] = ()
    readings_agree: bool | None = None
    exemptions_pending: tuple[str, ...] = ()
    evaluation: RuleEvaluation | None = None

    @model_validator(mode="after")
    def _check(self) -> RuleOutcome:
        """Shared constraints, binding_unresolved (S2), readings, evaluation and sorting."""
        _check_details(
            self.outcome,
            self.reason,
            self.direction,
            self.decisive_facts,
            self.facts_to_confirm,
            self.questions,
        )
        if self.binding_unresolved and not (
            self.outcome == Outcome.DOES_NOT_APPLY and self.reason == Reason.TEST_NOT_MET
        ):
            raise ValueError("binding_unresolved only with DOES_NOT_APPLY / TEST_NOT_MET")
        if self.interpretations:
            if self.readings_agree is None or self.evaluation is not None:
                raise ValueError("a rule with interpretations has readings_agree and no evaluation")
        elif self.readings_agree is not None or self.evaluation is None:
            raise ValueError("a single-trigger rule has an evaluation and no readings_agree")
        if (self.outcome == Outcome.UNSETTLED) != (self.readings_agree is False):
            raise ValueError("the outcome is UNSETTLED exactly when the readings disagree")
        _check_sorted("interpretations", (i.interpretation_id for i in self.interpretations))
        _check_sorted("exemptions_pending", self.exemptions_pending)
        return self


# ---- Trace helpers --------------------------------------------------------------------


def _trace_leaves(evaluation: RuleEvaluation) -> tuple[LeafResult, ...]:
    """Every leaf of the evaluation: binding levels first, then the trigger."""
    leaves = _trace_leaves(evaluation.binding) if evaluation.binding is not None else ()
    trigger = evaluation.trigger.leaves if evaluation.trigger is not None else ()
    return (*leaves, *trigger)


def _unknown_facts(evaluation: RuleEvaluation) -> tuple[str, ...]:
    """The distinct facts that any leaf reads as UNKNOWN, sorted (S4)."""
    return tuple(sorted({x.fact for x in _trace_leaves(evaluation) if x.value is TriValue.UNKNOWN}))


def _referenced_facts(evaluation: RuleEvaluation) -> tuple[str, ...]:
    """The distinct facts named by any evaluated leaf, sorted."""
    return tuple(sorted({leaf.fact for leaf in _trace_leaves(evaluation)}))


def _without(facts: Mapping[str, Fact], names: Iterable[str]) -> dict[str, Fact]:
    """A new mapping without the named facts; the input is not changed."""
    drop = set(names)
    return {name: item for name, item in facts.items() if name not in drop}


def _evaluator(rule_id: str, pack: RulePack, interpretation_id: str | None) -> Evaluate:
    """A function evaluating one rule (or one reading of it) against a facts mapping."""

    def evaluate(facts: Mapping[str, Fact]) -> RuleEvaluation:
        return evaluate_rule(rule_id, pack, facts, interpretation_id)

    return evaluate


# ---- D1 relevance and D2 decisive facts ------------------------------------------------

_HYPOTHETICAL: Final[Mapping[bool, Fact]] = {
    True: Fact(value=TriValue.TRUE, grade=EvidenceGrade.VERIFIED),
    False: Fact(value=TriValue.FALSE, grade=EvidenceGrade.VERIFIED),
}


def _truth_table(
    evaluate: Evaluate, facts: Mapping[str, Fact], unknowns: tuple[str, ...]
) -> dict[tuple[bool, ...], TriValue]:
    """The rule value for every TRUE/FALSE assignment of the unknown facts, at grade verified.

    Each hypothetical fact replaces the supplied one in every leaf (S4). More than
    MAX_RELEVANCE_FACTS unknowns raises OutcomeError (fail closed).
    """
    if len(unknowns) > MAX_RELEVANCE_FACTS:
        raise OutcomeError(
            f"relevance needs {len(unknowns)} distinct unknown facts;"
            f" the maximum is {MAX_RELEVANCE_FACTS}"
        )
    table: dict[tuple[bool, ...], TriValue] = {}
    for bits in itertools.product((False, True), repeat=len(unknowns)):
        hypothetical = {name: _HYPOTHETICAL[bit] for name, bit in zip(unknowns, bits, strict=True)}
        table[bits] = evaluate({**facts, **hypothetical}).value
    return table


def _relevant(
    evaluate: Evaluate, facts: Mapping[str, Fact], unknowns: tuple[str, ...]
) -> tuple[str, ...]:
    """D1: the unknowns whose TRUE and FALSE give different values under some assignment."""
    table = _truth_table(evaluate, facts, unknowns)
    found = []
    for i, name in enumerate(unknowns):
        for bits, value in table.items():
            if not bits[i] and table[(*bits[:i], True, *bits[i + 1 :])] is not value:
                found.append(name)
                break
    return tuple(found)


def _decisive(
    evaluate: Evaluate, facts: Mapping[str, Fact], evaluation: RuleEvaluation
) -> tuple[str, ...]:
    """D2: for a TRUE or FALSE value, the supplied facts whose removal changes it."""
    if evaluation.value is TriValue.UNKNOWN:
        return ()
    return tuple(
        name
        for name in _referenced_facts(evaluation)
        if name in facts and evaluate(_without(facts, (name,))).value is not evaluation.value
    )


def relevant_facts(
    rule_id: str,
    pack: RulePack,
    facts: Mapping[str, Fact],
    interpretation_id: str | None = None,
) -> tuple[str, ...]:
    """The unknown facts that could change the rule's value (D1), sorted."""
    evaluate = _evaluator(rule_id, pack, interpretation_id)
    return _relevant(evaluate, facts, _unknown_facts(evaluate(facts)))


def decisive_facts(
    rule_id: str,
    pack: RulePack,
    facts: Mapping[str, Fact],
    interpretation_id: str | None = None,
) -> tuple[str, ...]:
    """The facts whose removal changes a TRUE or FALSE value (D2), sorted; () for UNKNOWN."""
    evaluate = _evaluator(rule_id, pack, interpretation_id)
    return _decisive(evaluate, facts, evaluate(facts))


# ---- D3 for one trigger ----------------------------------------------------------------


@dataclass(frozen=True)
class _Assessment:
    """The D3 result for one trigger, before it is wrapped in a public model."""

    outcome: Outcome
    evaluation: RuleEvaluation
    reason: Reason | None = None
    direction: Direction | None = None
    binding_unresolved: bool = False
    decisive: tuple[str, ...] = ()
    confirm: tuple[str, ...] = ()
    questions: tuple[Question, ...] = ()


def _questions(
    evaluation: RuleEvaluation, relevant: tuple[str, ...], facts: Mapping[str, Fact]
) -> tuple[Question, ...]:
    """One question per relevant unknown fact, in fact order."""
    leaves = _trace_leaves(evaluation)
    found = []
    for name in relevant:
        supplied = facts.get(name)
        if supplied is None or supplied.value is TriValue.UNKNOWN:
            found.append(
                Question(
                    fact=name, kind=QuestionKind.MISSING, current_grade=None, required_grade=None
                )
            )
            continue
        below = [
            leaf.min_grade
            for leaf in leaves
            if leaf.fact == name
            and leaf.reason is LeafReason.BELOW_MIN_GRADE
            and leaf.min_grade is not None
        ]
        found.append(
            Question(
                fact=name,
                kind=QuestionKind.NEEDS_STRONGER_EVIDENCE,
                current_grade=supplied.grade,
                required_grade=max(below, key=GRADE_RANK.__getitem__),
            )
        )
    return tuple(found)


def _to_confirm(
    evaluate: Evaluate,
    reduced_facts: Mapping[str, Fact],
    reduced: RuleEvaluation,
    suspected: frozenset[str],
) -> tuple[str, ...]:
    """The removed suspected facts that are relevant (D1) to the reduced result."""
    relevant = _relevant(evaluate, reduced_facts, _unknown_facts(reduced))
    return tuple(name for name in relevant if name in suspected)


def _assess_one(evaluate: Evaluate, facts: Mapping[str, Fact]) -> _Assessment:
    """D3, with step 1 as revised by S1, for one trigger and its binding."""
    evaluation = evaluate(facts)
    if evaluation.value is TriValue.UNKNOWN:
        relevant = _relevant(evaluate, facts, _unknown_facts(evaluation))
        return _Assessment(
            outcome=Outcome.INSUFFICIENT_FACTS,
            evaluation=evaluation,
            questions=_questions(evaluation, relevant, facts),
        )
    decisive = _decisive(evaluate, facts, evaluation)
    suspected = frozenset(n for n, f in facts.items() if f.grade == EvidenceGrade.SUSPECTED)
    reduced_facts = _without(facts, suspected)
    reduced = evaluate(reduced_facts) if suspected else evaluation
    if evaluation.bound is TriValue.FALSE:
        if reduced.bound is TriValue.FALSE:
            return _Assessment(
                outcome=Outcome.DOES_NOT_APPLY,
                evaluation=evaluation,
                reason=Reason.NOT_BOUND,
                decisive=decisive,
            )
        if reduced.value is TriValue.FALSE:
            return _Assessment(
                outcome=Outcome.DOES_NOT_APPLY,
                evaluation=evaluation,
                reason=Reason.TEST_NOT_MET,
                binding_unresolved=True,
                decisive=decisive,
            )
        direction = Direction.DOES_NOT_APPLY_IF_CONFIRMED
    elif reduced.value is TriValue.UNKNOWN:
        direction = (
            Direction.APPLIES_IF_CONFIRMED
            if evaluation.value is TriValue.TRUE
            else Direction.DOES_NOT_APPLY_IF_CONFIRMED
        )
    elif evaluation.value is TriValue.TRUE:
        return _Assessment(outcome=Outcome.APPLIES, evaluation=evaluation, decisive=decisive)
    else:
        return _Assessment(
            outcome=Outcome.DOES_NOT_APPLY,
            evaluation=evaluation,
            reason=Reason.TEST_NOT_MET,
            binding_unresolved=evaluation.bound is TriValue.UNKNOWN,
            decisive=decisive,
        )
    return _Assessment(
        outcome=Outcome.CONDITIONAL,
        evaluation=evaluation,
        direction=direction,
        decisive=decisive,
        confirm=_to_confirm(evaluate, reduced_facts, reduced, suspected),
    )


# ---- D4 interpretations and the public entry point ------------------------------------


def _merge_questions(groups: Iterable[tuple[Question, ...]]) -> tuple[Question, ...]:
    """Union of questions by fact; for one fact, keep the highest required_grade (S3)."""

    def rank(question: Question) -> int:
        grade = question.required_grade
        return -1 if grade is None else GRADE_RANK[grade]

    by_fact: dict[str, Question] = {}
    for group in groups:
        for question in group:
            kept = by_fact.get(question.fact)
            if kept is None or rank(question) > rank(kept):
                by_fact[question.fact] = question
    return tuple(by_fact[name] for name in sorted(by_fact))


def _reading(interpretation_id: str, item: _Assessment) -> InterpretationOutcome:
    """Wrap one reading's assessment in the public model."""
    return InterpretationOutcome(
        interpretation_id=interpretation_id,
        outcome=item.outcome,
        reason=item.reason,
        direction=item.direction,
        decisive_facts=item.decisive,
        facts_to_confirm=item.confirm,
        questions=item.questions,
        evaluation=item.evaluation,
    )


def _combine(
    rule_id: str, assessed: list[tuple[str, _Assessment]], exemptions: tuple[str, ...]
) -> RuleOutcome:
    """D4: collapse readings that agree in (outcome, reason, direction), else UNSETTLED."""
    readings = tuple(_reading(reading_id, item) for reading_id, item in assessed)
    items = [item for _, item in assessed]
    keys = {(item.outcome, item.reason, item.direction) for item in items}
    if len(keys) > 1:
        return RuleOutcome(
            rule_id=rule_id,
            outcome=Outcome.UNSETTLED,
            interpretations=readings,
            readings_agree=False,
            exemptions_pending=exemptions,
        )
    first = items[0]
    shared = set(first.decisive).intersection(*(item.decisive for item in items[1:]))
    return RuleOutcome(
        rule_id=rule_id,
        outcome=first.outcome,
        reason=first.reason,
        direction=first.direction,
        binding_unresolved=any(item.binding_unresolved for item in items),
        decisive_facts=tuple(sorted(shared)),
        facts_to_confirm=tuple(sorted({n for item in items for n in item.confirm})),
        questions=_merge_questions(item.questions for item in items),
        interpretations=readings,
        readings_agree=True,
        exemptions_pending=exemptions,
    )


def assess_rule(rule_id: str, pack: RulePack, facts: Mapping[str, Fact]) -> RuleOutcome:
    """The outcome of one rule of the pack (D3, D4); unless ids are carried, not applied (D5).

    EvaluationError from the evaluator (unknown rule, bad facts, a binding rule with
    interpretations) propagates unchanged.
    """
    rule = next((r for r in pack.rules if r.id == rule_id), None)
    if rule is None or rule.interpretations is None:
        item = _assess_one(_evaluator(rule_id, pack, None), facts)  # unknown id raises here
        return RuleOutcome(
            rule_id=rule_id,
            outcome=item.outcome,
            reason=item.reason,
            direction=item.direction,
            binding_unresolved=item.binding_unresolved,
            decisive_facts=item.decisive,
            facts_to_confirm=item.confirm,
            questions=item.questions,
            exemptions_pending=tuple(sorted(rule.unless)) if rule is not None else (),
            evaluation=item.evaluation,
        )
    assessed = [
        (reading.id, _assess_one(_evaluator(rule_id, pack, reading.id), facts))
        for reading in sorted(rule.interpretations, key=lambda r: r.id)
    ]
    return _combine(rule_id, assessed, tuple(sorted(rule.unless)))
