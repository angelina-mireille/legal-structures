"""Trigger evaluation: strong Kleene three-valued logic, binding rules first.

The evaluator reads an abstract facts mapping (fact name -> Fact); it never reads the
graph. It returns raw TRUE, FALSE or UNKNOWN values with a trace of every leaf. Turning
those values into outcomes (and handling unless, interpretations and clocks) is C3b.

Pure: no I/O, no logging, no clock, and inputs are never changed.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.graph import EvidenceGrade
from core.rules import AllExpr, AnyExpr, FactExpr, NotExpr, Rule, RulePack

TriggerExpr = AllExpr | AnyExpr | NotExpr | FactExpr


class TriValue(Enum):
    """A three-valued truth value. It has no truthiness: compare with 'is'."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    def __bool__(self) -> bool:
        """Refuse bool(), so 'if value:' can never silently treat UNKNOWN as true."""
        raise TypeError("TriValue has no truth value; compare with 'is TriValue.TRUE'")


# D2: how the evaluator reads grades, weakest first. graph.py's member order is not a rank.
GRADE_RANK: Final[Mapping[EvidenceGrade, int]] = MappingProxyType(
    {
        EvidenceGrade.SUSPECTED: 0,
        EvidenceGrade.DECLARED: 1,
        EvidenceGrade.DOCUMENTED: 2,
        EvidenceGrade.VERIFIED: 3,
    }
)


class EvaluationError(Exception):
    """Raised when a rule or expression cannot be evaluated as given."""


class _Frozen(BaseModel):
    """Base for every evaluator model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Fact(_Frozen):
    """One supplied fact: TRUE or FALSE with a grade, or UNKNOWN with no grade."""

    value: TriValue = Field(strict=True)  # a TriValue member only: no bool or string
    grade: EvidenceGrade | None

    @field_validator("grade", mode="before")
    @classmethod
    def _reject_missing(cls, value: Any) -> Any:
        """Refuse "missing": an unstated fact is left out or supplied as UNKNOWN."""
        if value == EvidenceGrade.MISSING:
            raise ValueError("grade cannot be 'missing'; leave the fact out or use UNKNOWN")
        return value

    @model_validator(mode="after")
    def _grade_matches_value(self) -> Fact:
        """UNKNOWN has no grade; TRUE and FALSE must have one."""
        if self.value is TriValue.UNKNOWN and self.grade is not None:
            raise ValueError("an UNKNOWN fact cannot have a grade")
        if self.value is not TriValue.UNKNOWN and self.grade is None:
            raise ValueError("a TRUE or FALSE fact needs a grade")
        return self


class LeafReason(StrEnum):
    """Why a leaf has its effective value."""

    OK = "ok"
    MISSING = "missing"  # absent from the mapping, or supplied as UNKNOWN
    BELOW_MIN_GRADE = "below_min_grade"


class LeafResult(_Frozen):
    """One leaf occurrence: what was supplied, the threshold, and the effective value."""

    fact: str
    supplied: Fact | None
    min_grade: EvidenceGrade | None
    value: TriValue
    reason: LeafReason


class ExprResult(_Frozen):
    """An expression's value and its leaves, depth-first, left to right."""

    value: TriValue
    leaves: tuple[LeafResult, ...]


class RuleEvaluation(_Frozen):
    """A rule's binding result, its trigger result (None when not bound) and its value."""

    rule_id: str
    binding: RuleEvaluation | None
    bound: TriValue
    trigger: ExprResult | None
    value: TriValue

    @model_validator(mode="after")
    def _trigger_skipped_only_when_unbound(self) -> RuleEvaluation:
        """trigger is None exactly when bound is FALSE."""
        if (self.trigger is None) != (self.bound is TriValue.FALSE):
            raise ValueError("trigger must be None exactly when bound is FALSE")
        return self


# ---- Kleene operators -------------------------------------------------------------


def _kleene_and(values: tuple[TriValue, ...]) -> TriValue:
    """FALSE if any is FALSE, else TRUE if all are TRUE, else UNKNOWN."""
    if any(v is TriValue.FALSE for v in values):
        return TriValue.FALSE
    if all(v is TriValue.TRUE for v in values):
        return TriValue.TRUE
    return TriValue.UNKNOWN


def _kleene_or(values: tuple[TriValue, ...]) -> TriValue:
    """TRUE if any is TRUE, else FALSE if all are FALSE, else UNKNOWN."""
    if any(v is TriValue.TRUE for v in values):
        return TriValue.TRUE
    if all(v is TriValue.FALSE for v in values):
        return TriValue.FALSE
    return TriValue.UNKNOWN


def _kleene_not(value: TriValue) -> TriValue:
    """Swap TRUE and FALSE; keep UNKNOWN."""
    if value is TriValue.TRUE:
        return TriValue.FALSE
    if value is TriValue.FALSE:
        return TriValue.TRUE
    return TriValue.UNKNOWN


# ---- Expressions ----------------------------------------------------------------------


def _check_facts(facts: Mapping[Any, Any]) -> None:
    """Every key is a str and every value a Fact."""
    for name, item in facts.items():
        if not isinstance(name, str):
            raise EvaluationError(f"fact name must be a str, not {type(name).__name__}")
        if not isinstance(item, Fact):
            raise EvaluationError(f"fact {name!r} must be a Fact, not {type(item).__name__}")


def _eval_leaf(leaf: FactExpr, facts: Mapping[str, Fact]) -> LeafResult:
    """Apply D1 (absent is UNKNOWN) and D2 (below min_grade is UNKNOWN) to one leaf."""
    supplied = facts.get(leaf.fact)
    if supplied is None or supplied.value is TriValue.UNKNOWN:
        value, reason = TriValue.UNKNOWN, LeafReason.MISSING
    elif leaf.min_grade is not None and (
        supplied.grade is None or GRADE_RANK[supplied.grade] < GRADE_RANK[leaf.min_grade]
    ):
        value, reason = TriValue.UNKNOWN, LeafReason.BELOW_MIN_GRADE
    else:
        value, reason = supplied.value, LeafReason.OK
    return LeafResult(
        fact=leaf.fact, supplied=supplied, min_grade=leaf.min_grade, value=value, reason=reason
    )


def _walk(expr: TriggerExpr, facts: Mapping[str, Fact], leaves: list[LeafResult]) -> TriValue:
    """Evaluate expr, appending each leaf to leaves. Every child is visited (no short-circuit)."""
    if isinstance(expr, FactExpr):
        result = _eval_leaf(expr, facts)
        leaves.append(result)
        return result.value
    if isinstance(expr, NotExpr):
        return _kleene_not(_walk(expr.not_, facts, leaves))
    is_all = isinstance(expr, AllExpr)
    children = expr.all if is_all else expr.any
    if not children:
        raise EvaluationError(f"empty {'all' if is_all else 'any'} list")
    values = tuple(_walk(child, facts, leaves) for child in children)
    return _kleene_and(values) if is_all else _kleene_or(values)


def _expression(expr: TriggerExpr, facts: Mapping[str, Fact]) -> ExprResult:
    """Evaluate expr against already-checked facts."""
    leaves: list[LeafResult] = []
    value = _walk(expr, facts, leaves)
    return ExprResult(value=value, leaves=tuple(leaves))


def evaluate_expression(expr: TriggerExpr, facts: Mapping[str, Fact]) -> ExprResult:
    """Evaluate a trigger expression with strong Kleene logic, keeping a leaf trace."""
    _check_facts(facts)
    return _expression(expr, facts)


# ---- Rules ------------------------------------------------------------------------------


def _require_trigger(rule: Rule) -> TriggerExpr:
    """The rule's trigger; a rule with interpretations is not evaluated until C3b."""
    if rule.trigger is None:
        raise EvaluationError(
            f"{rule.id}: has interpretations instead of a trigger;"
            " interpretations are handled in C3b"
        )
    return rule.trigger


def _evaluate_rule(
    rule_id: str,
    by_id: Mapping[str, Rule],
    facts: Mapping[str, Fact],
    seen: tuple[str, ...],
) -> RuleEvaluation:
    """Apply D3: the binding rule first (recursively), then the trigger unless unbound."""
    if rule_id in seen:
        raise EvaluationError("binding cycle: " + " -> ".join((*seen, rule_id)))
    rule = by_id.get(rule_id)
    if rule is None:
        raise EvaluationError(f"rule {rule_id} is not in the pack")
    trigger_expr = _require_trigger(rule)
    binding: RuleEvaluation | None = None
    bound = TriValue.TRUE
    if rule.binding is not None:
        binding = _evaluate_rule(rule.binding, by_id, facts, (*seen, rule_id))
        bound = binding.value
    if bound is TriValue.FALSE:
        return RuleEvaluation(
            rule_id=rule_id, binding=binding, bound=bound, trigger=None, value=TriValue.FALSE
        )
    trigger = _expression(trigger_expr, facts)
    value = _kleene_and((bound, trigger.value))
    return RuleEvaluation(
        rule_id=rule_id, binding=binding, bound=bound, trigger=trigger, value=value
    )


def evaluate_rule(rule_id: str, pack: RulePack, facts: Mapping[str, Fact]) -> RuleEvaluation:
    """Evaluate one rule of the pack, binding rule first (D3)."""
    _check_facts(facts)
    by_id = {rule.id: rule for rule in pack.rules}
    return _evaluate_rule(rule_id, by_id, facts, ())
