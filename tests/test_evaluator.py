"""Tests for src/core/evaluator.py: strong Kleene logic, grades, binding rules first.

Every rule and fact here is synthetic (regime TEST, example.org URLs, "test." fact names).
Expected values in truth tables are written out literally, never computed by the code
under test.
"""

import copy
import itertools
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from core.evaluator import (
    GRADE_RANK,
    EvaluationError,
    Fact,
    LeafReason,
    TriValue,
    evaluate_expression,
    evaluate_rule,
)
from core.graph import EvidenceGrade
from core.rules import (
    AllExpr,
    AnyExpr,
    FactExpr,
    NotExpr,
    Rule,
    RulePack,
    expr_depth,
    load_rule_pack,
)

TODAY = date(2026, 11, 9)
LAST_VERIFIED = date(2026, 11, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64

T = TriValue.TRUE
F = TriValue.FALSE
U = TriValue.UNKNOWN
VALUES = (T, F, U)

A, B, C = "test.alpha", "test.beta", "test.gamma"

OK = LeafReason.OK
MISSING = LeafReason.MISSING
BELOW = LeafReason.BELOW_MIN_GRADE


# ---- Helpers --------------------------------------------------------------------


def leaf(name: str, min_grade: str | None = None) -> FactExpr:
    """A fact leaf, optionally with a min_grade."""
    return FactExpr(fact=name, min_grade=min_grade)


def all_(*children: Any) -> AllExpr:
    """An all-expression over children."""
    return AllExpr(all=children)


def any_(*children: Any) -> AnyExpr:
    """An any-expression over children."""
    return AnyExpr(any=children)


def not_(child: Any) -> NotExpr:
    """A not-expression ("not" is an alias, so it is passed by name)."""
    return NotExpr(**{"not": child})


def fact_of(value: TriValue, grade: str = "verified") -> Fact:
    """A Fact: TRUE/FALSE get the grade; UNKNOWN gets no grade."""
    if value is U:
        return Fact(value=U, grade=None)
    return Fact(value=value, grade=grade)


def facts_of(**values: TriValue) -> dict[str, Fact]:
    """Facts keyed "test.<name>" from keyword values, e.g. facts_of(alpha=T)."""
    return {f"test.{name}": fact_of(value) for name, value in values.items()}


def value_of(expr: Any, a: TriValue = U, b: TriValue = U, c: TriValue = U) -> TriValue:
    """Evaluate expr with alpha, beta, gamma set to a, b, c (all verified)."""
    return evaluate_expression(expr, facts_of(alpha=a, beta=b, gamma=c)).value


def rule_dict(
    rule_id: str,
    trigger: dict[str, Any] | None = None,
    binding: str | None = None,
    interpretations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal synthetic TEST- rule as a dict."""
    rule: dict[str, Any] = {
        "id": rule_id,
        "version": "1.0.0",
        "regime": "TEST",
        "title": "Synthetic evaluator test rule",
        "law_status": "in_force",
        "applies_to": "model",
        "binding": binding,
        "effect": "TEST_EFFECT",
        "unless": [],
        "citation": {
            "primary": "Test Source s. 1",
            "source_id": "test-source-1",
            "source_url": SOURCE_URL,
            "pinpoint_quote_hash": ZERO_HASH,
        },
        "verification": {
            "status": "verified",
            "last_verified": LAST_VERIFIED,
            "verified_by": "user",
        },
        "clock": None,
    }
    if interpretations is not None:
        rule["interpretations"] = interpretations
    else:
        rule["trigger"] = trigger
    return rule


def write_pack(tmp_path: Path, rules: list[dict[str, Any]]) -> RulePack:
    """Write rules into tmp_path, copy the synthetic source record, and load the pack."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    sources_dir = tmp_path / "sources"
    shutil.copytree(FIXTURE_SOURCES, sources_dir)
    for rule in rules:
        text = yaml.safe_dump(rule, sort_keys=False)
        (rules_dir / f"{rule['id']}.yaml").write_text(text, encoding="utf-8")
    return load_rule_pack(rules_dir, sources_dir, TODAY)


TWO_READINGS = [
    {"id": "reading_a", "summary": "Test reading A.", "trigger": {"fact": A}},
    {"id": "reading_b", "summary": "Test reading B.", "trigger": {"fact": B}},
]


# ---- T1: not ------------------------------------------------------------------------


@pytest.mark.parametrize(("a", "expected"), [(T, F), (F, T), (U, U)])
def test_t1_not(a: TriValue, expected: TriValue) -> None:
    """not swaps TRUE and FALSE and keeps UNKNOWN."""
    assert value_of(not_(leaf(A)), a) is expected


# ---- T2: all and any over two leaves ---------------------------------------------------

TWO_LEAF_ROWS = [
    # a, b, all, any
    (T, T, T, T),
    (T, F, F, T),
    (T, U, U, T),
    (F, T, F, T),
    (F, F, F, F),
    (F, U, F, U),
    (U, T, U, T),
    (U, F, F, U),
    (U, U, U, U),
]


@pytest.mark.parametrize(("a", "b", "expected_all", "expected_any"), TWO_LEAF_ROWS)
def test_t2_all_and_any_two_leaves(
    a: TriValue, b: TriValue, expected_all: TriValue, expected_any: TriValue
) -> None:
    """Literal strong Kleene tables for all and any."""
    assert value_of(all_(leaf(A), leaf(B)), a, b) is expected_all
    assert value_of(any_(leaf(A), leaf(B)), a, b) is expected_any


# ---- T3: all and any over three leaves, against a counting oracle -----------------------


def oracle_all(values: tuple[TriValue, ...]) -> TriValue:
    """FALSE if any FALSE; TRUE if all TRUE; otherwise UNKNOWN (by counting)."""
    if values.count(F) > 0:
        return F
    if values.count(T) == len(values):
        return T
    return U


def oracle_any(values: tuple[TriValue, ...]) -> TriValue:
    """TRUE if any TRUE; FALSE if all FALSE; otherwise UNKNOWN (by counting)."""
    if values.count(T) > 0:
        return T
    if values.count(F) == len(values):
        return F
    return U


@pytest.mark.parametrize("abc", list(itertools.product(VALUES, repeat=3)))
def test_t3_all_and_any_three_leaves(abc: tuple[TriValue, TriValue, TriValue]) -> None:
    """All 27 combinations match the counting oracle."""
    assert value_of(all_(leaf(A), leaf(B), leaf(C)), *abc) is oracle_all(abc)
    assert value_of(any_(leaf(A), leaf(B), leaf(C)), *abc) is oracle_any(abc)


def test_t3_covers_27_combinations() -> None:
    """The parametrisation above really has 27 rows."""
    assert len(list(itertools.product(VALUES, repeat=3))) == 27


# ---- T4: one child --------------------------------------------------------------------


@pytest.mark.parametrize("a", VALUES)
def test_t4_single_child_equals_child(a: TriValue) -> None:
    """all and any with one child give the child's value."""
    assert value_of(all_(leaf(A)), a) is a
    assert value_of(any_(leaf(A)), a) is a


# ---- T5: laws, exhaustive over two leaves ---------------------------------------------


@pytest.mark.parametrize(("a", "b"), list(itertools.product(VALUES, repeat=2)))
def test_t5_laws(a: TriValue, b: TriValue) -> None:
    """De Morgan (both), double negation and commutativity."""
    x, y = leaf(A), leaf(B)
    assert value_of(not_(all_(x, y)), a, b) is value_of(any_(not_(x), not_(y)), a, b)
    assert value_of(not_(any_(x, y)), a, b) is value_of(all_(not_(x), not_(y)), a, b)
    assert value_of(not_(not_(x)), a, b) is a
    assert value_of(all_(x, y), a, b) is value_of(all_(y, x), a, b)
    assert value_of(any_(x, y), a, b) is value_of(any_(y, x), a, b)


# ---- T6: monotonicity ----------------------------------------------------------------

MONOTONE_EXPRESSIONS = {
    "not a": not_(leaf(A)),
    "all(a,b)": all_(leaf(A), leaf(B)),
    "any(a,b)": any_(leaf(A), leaf(B)),
    "all(b,a)": all_(leaf(B), leaf(A)),
    "any(b,a)": any_(leaf(B), leaf(A)),
    "all(a,b,c)": all_(leaf(A), leaf(B), leaf(C)),
    "any(a,b,c)": any_(leaf(A), leaf(B), leaf(C)),
    "all(a)": all_(leaf(A)),
    "any(a)": any_(leaf(A)),
    "not all(a,b)": not_(all_(leaf(A), leaf(B))),
    "any(not a,not b)": any_(not_(leaf(A)), not_(leaf(B))),
    "not any(a,b)": not_(any_(leaf(A), leaf(B))),
    "all(not a,not b)": all_(not_(leaf(A)), not_(leaf(B))),
    "not not a": not_(not_(leaf(A))),
    "nested": any_(all_(leaf(A), not_(leaf(B))), not_(any_(leaf(B), leaf(C)))),
}


@pytest.mark.parametrize("name", list(MONOTONE_EXPRESSIONS))
def test_t6_monotonicity(name: str) -> None:
    """Replacing any UNKNOWN input by TRUE or FALSE never changes a definite result."""
    expr = MONOTONE_EXPRESSIONS[name]
    for abc in itertools.product(VALUES, repeat=3):
        result = value_of(expr, *abc)
        if result is U:
            continue
        for position, current in enumerate(abc):
            if current is not U:
                continue
            for replacement in (T, F):
                refined = list(abc)
                refined[position] = replacement
                assert value_of(expr, *refined) is result, (name, abc, position, replacement)


# ---- T7: grades -----------------------------------------------------------------------

GRADE_ROWS = [
    # min_grade, supplied grade, supplied value, expected value, expected reason
    ("suspected", "suspected", T, T, OK),
    ("suspected", "suspected", F, F, OK),
    ("suspected", "declared", T, T, OK),
    ("suspected", "declared", F, F, OK),
    ("suspected", "documented", T, T, OK),
    ("suspected", "documented", F, F, OK),
    ("suspected", "verified", T, T, OK),
    ("suspected", "verified", F, F, OK),
    ("declared", "suspected", T, U, BELOW),
    ("declared", "suspected", F, U, BELOW),
    ("declared", "declared", T, T, OK),
    ("declared", "declared", F, F, OK),
    ("declared", "documented", T, T, OK),
    ("declared", "documented", F, F, OK),
    ("declared", "verified", T, T, OK),
    ("declared", "verified", F, F, OK),
    ("documented", "suspected", T, U, BELOW),
    ("documented", "suspected", F, U, BELOW),
    ("documented", "declared", T, U, BELOW),
    ("documented", "declared", F, U, BELOW),
    ("documented", "documented", T, T, OK),
    ("documented", "documented", F, F, OK),
    ("documented", "verified", T, T, OK),
    ("documented", "verified", F, F, OK),
    ("verified", "suspected", T, U, BELOW),
    ("verified", "suspected", F, U, BELOW),
    ("verified", "declared", T, U, BELOW),
    ("verified", "declared", F, U, BELOW),
    ("verified", "documented", T, U, BELOW),
    ("verified", "documented", F, U, BELOW),
    ("verified", "verified", T, T, OK),
    ("verified", "verified", F, F, OK),
]


def test_t7_grade_table_has_32_rows() -> None:
    """4 min_grades x 4 grades x 2 values."""
    assert len(GRADE_ROWS) == 32
    assert len({row[:3] for row in GRADE_ROWS}) == 32


@pytest.mark.parametrize(("min_grade", "grade", "value", "expected", "reason"), GRADE_ROWS)
def test_t7_grade_table(
    min_grade: str, grade: str, value: TriValue, expected: TriValue, reason: LeafReason
) -> None:
    """A leaf below its min_grade is UNKNOWN for TRUE and FALSE alike."""
    result = evaluate_expression(leaf(A, min_grade), {A: Fact(value=value, grade=grade)})
    assert result.value is expected
    (only,) = result.leaves
    assert only.value is expected
    assert only.reason is reason


@pytest.mark.parametrize("grade", ["suspected", "declared", "documented", "verified"])
@pytest.mark.parametrize("value", [T, F])
def test_t7_no_min_grade_accepts_every_grade(grade: str, value: TriValue) -> None:
    """Without min_grade, any stated grade gives the supplied value and OK."""
    result = evaluate_expression(leaf(A), {A: Fact(value=value, grade=grade)})
    assert result.value is value
    assert result.leaves[0].reason is OK


def test_t7_grade_rank_keys_and_order() -> None:
    """GRADE_RANK covers every grade except missing, ranked as D2 says."""
    assert set(GRADE_RANK) == set(EvidenceGrade) - {EvidenceGrade.MISSING}
    assert sorted(GRADE_RANK, key=GRADE_RANK.__getitem__) == [
        EvidenceGrade.SUSPECTED,
        EvidenceGrade.DECLARED,
        EvidenceGrade.DOCUMENTED,
        EvidenceGrade.VERIFIED,
    ]


# ---- T8: missing facts --------------------------------------------------------------


def test_t8_absent_fact_is_unknown_missing() -> None:
    """A fact absent from the mapping is UNKNOWN with reason MISSING and nothing supplied."""
    result = evaluate_expression(leaf(A), {})
    assert result.value is U
    assert result.leaves[0].reason is MISSING
    assert result.leaves[0].supplied is None


def test_t8_fact_supplied_as_unknown_is_missing() -> None:
    """A fact supplied as UNKNOWN is UNKNOWN with reason MISSING; the Fact is kept."""
    supplied = Fact(value=U, grade=None)
    result = evaluate_expression(leaf(A, "declared"), {A: supplied})
    assert result.value is U
    assert result.leaves[0].reason is MISSING
    assert result.leaves[0].supplied == supplied


# ---- T9: negation safety ------------------------------------------------------------


def test_t9_not_over_below_grade_true_is_unknown() -> None:
    """Weak evidence for TRUE does not become a definite FALSE under not."""
    facts = {A: Fact(value=T, grade="declared")}
    assert evaluate_expression(not_(leaf(A, "verified")), facts).value is U


def test_t9_not_over_absent_is_unknown() -> None:
    """A missing fact does not become a definite TRUE under not."""
    assert evaluate_expression(not_(leaf(A)), {}).value is U


# ---- T10: trace ---------------------------------------------------------------------


def test_t10_leaf_order_and_repeats() -> None:
    """Leaves come depth-first, left to right, one per occurrence."""
    expr = all_(leaf(A), any_(leaf(B), not_(leaf(A))), not_(all_(leaf(C), leaf(A))))
    result = evaluate_expression(expr, facts_of(alpha=T, beta=F, gamma=U))
    assert [item.fact for item in result.leaves] == [A, B, A, C, A]


def test_t10_below_grade_keeps_supplied_value_and_grade() -> None:
    """A BELOW_MIN_GRADE leaf keeps the Fact as supplied and its min_grade."""
    supplied = Fact(value=F, grade="suspected")
    (item,) = evaluate_expression(leaf(A, "documented"), {A: supplied}).leaves
    assert item.fact == A
    assert item.supplied == supplied
    assert item.supplied.value is F
    assert item.supplied.grade is EvidenceGrade.SUSPECTED
    assert item.min_grade is EvidenceGrade.DOCUMENTED
    assert item.value is U
    assert item.reason is BELOW


def test_t10_no_short_circuit() -> None:
    """Every child is evaluated even when the first one decides the result."""
    result = evaluate_expression(all_(leaf(A), leaf(B), leaf(C)), facts_of(alpha=F))
    assert result.value is F
    assert [item.fact for item in result.leaves] == [A, B, C]


# ---- T11: Fact validation ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": U, "grade": "declared"},
        {"value": T, "grade": None},
        {"value": F, "grade": None},
        {"value": T, "grade": "missing"},
        {"value": T, "grade": "declared", "note": "extra"},
        {"value": True, "grade": "declared"},
        {"value": False, "grade": "declared"},
        {"value": "true", "grade": "declared"},
    ],
    ids=[
        "unknown-with-grade",
        "true-without-grade",
        "false-without-grade",
        "grade-missing",
        "extra-field",
        "python-true",
        "python-false",
        "string-value",
    ],
)
def test_t11_bad_facts_rejected(kwargs: dict[str, Any]) -> None:
    """Each malformed Fact is a validation error."""
    with pytest.raises(ValidationError):
        Fact(**kwargs)


def test_t11_grade_accepts_string_value() -> None:
    """grade accepts an EvidenceGrade or its string value."""
    assert Fact(value=T, grade="declared").grade is EvidenceGrade.DECLARED
    assert Fact(value=T, grade=EvidenceGrade.VERIFIED).grade is EvidenceGrade.VERIFIED


@pytest.mark.parametrize("value", VALUES)
def test_t11_trivalue_has_no_truthiness(value: TriValue) -> None:
    """bool() on a TriValue raises, so 'if value:' can never silently work."""
    with pytest.raises(TypeError):
        bool(value)


# ---- T12: binding table --------------------------------------------------------------

BINDING_ROWS = [
    # binding value, trigger value, bound, trigger result (None = not evaluated), value
    (T, T, T, T, T),
    (T, F, T, F, F),
    (T, U, T, U, U),
    (F, T, F, None, F),
    (F, F, F, None, F),
    (F, U, F, None, F),
    (U, T, U, T, U),
    (U, F, U, F, F),
    (U, U, U, U, U),
]


@pytest.fixture
def bound_pack(tmp_path: Path) -> RulePack:
    """TEST-RULE (fact test.beta) bound by TEST-BIND (fact test.alpha)."""
    return write_pack(
        tmp_path,
        [
            rule_dict("TEST-BIND", trigger={"fact": A}),
            rule_dict("TEST-RULE", trigger={"fact": B}, binding="TEST-BIND"),
        ],
    )


@pytest.mark.parametrize(("bind", "trig", "bound", "trigger", "value"), BINDING_ROWS)
def test_t12_binding_table(
    bound_pack: RulePack,
    bind: TriValue,
    trig: TriValue,
    bound: TriValue,
    trigger: TriValue | None,
    value: TriValue,
) -> None:
    """D3: FALSE stops; TRUE passes the trigger through; UNKNOWN is ANDed."""
    result = evaluate_rule("TEST-RULE", bound_pack, facts_of(alpha=bind, beta=trig))
    assert result.rule_id == "TEST-RULE"
    assert result.binding is not None
    assert result.binding.rule_id == "TEST-BIND"
    assert result.binding.value is bind
    assert result.bound is bound
    if trigger is None:
        assert result.trigger is None
    else:
        assert result.trigger is not None
        assert result.trigger.value is trigger
    assert result.value is value


# ---- T13: no binding ------------------------------------------------------------------


@pytest.mark.parametrize("a", VALUES)
def test_t13_no_binding(tmp_path: Path, a: TriValue) -> None:
    """Without a binding rule, bound is TRUE and value is the trigger value."""
    pack = write_pack(tmp_path, [rule_dict("TEST-SOLO", trigger={"fact": A})])
    result = evaluate_rule("TEST-SOLO", pack, facts_of(alpha=a))
    assert result.binding is None
    assert result.bound is T
    assert result.trigger is not None
    assert result.trigger.value is a
    assert result.value is a


# ---- T14: chain ----------------------------------------------------------------------


@pytest.fixture
def chain_pack(tmp_path: Path) -> RulePack:
    """TEST-C bound by TEST-B bound by TEST-A; facts alpha, beta, gamma respectively."""
    return write_pack(
        tmp_path,
        [
            rule_dict("TEST-A", trigger={"fact": A}),
            rule_dict("TEST-B", trigger={"fact": B}, binding="TEST-A"),
            rule_dict("TEST-C", trigger={"fact": C}, binding="TEST-B"),
        ],
    )


def test_t14_chain_false_at_root_stops_both(chain_pack: RulePack) -> None:
    """TEST-A FALSE: neither TEST-B's nor TEST-C's trigger is evaluated."""
    result = evaluate_rule("TEST-C", chain_pack, facts_of(alpha=F, beta=T, gamma=T))
    b = result.binding
    assert b is not None and b.binding is not None
    a = b.binding
    assert (a.rule_id, a.bound, a.value) == ("TEST-A", T, F)
    assert a.binding is None
    assert (b.rule_id, b.bound, b.trigger, b.value) == ("TEST-B", F, None, F)
    assert (result.rule_id, result.bound, result.trigger, result.value) == ("TEST-C", F, None, F)


def test_t14_chain_unknown_at_root_propagates(chain_pack: RulePack) -> None:
    """TEST-A UNKNOWN with beta and gamma TRUE: UNKNOWN all the way up."""
    result = evaluate_rule("TEST-C", chain_pack, facts_of(alpha=U, beta=T, gamma=T))
    b = result.binding
    assert b is not None
    assert (b.bound, b.value) == (U, U)
    assert b.trigger is not None and b.trigger.value is T
    assert (result.bound, result.value) == (U, U)
    assert result.trigger is not None and result.trigger.value is T


def test_t14_chain_unknown_root_definite_false_trigger(chain_pack: RulePack) -> None:
    """TEST-A UNKNOWN but gamma FALSE: TEST-C is FALSE without answering the binding."""
    result = evaluate_rule("TEST-C", chain_pack, facts_of(alpha=U, beta=T, gamma=F))
    assert result.bound is U
    assert result.value is F


def test_t14_chain_unknown_root_false_middle(chain_pack: RulePack) -> None:
    """TEST-A UNKNOWN, beta FALSE: TEST-B is FALSE, so TEST-C stops."""
    result = evaluate_rule("TEST-C", chain_pack, facts_of(alpha=U, beta=F, gamma=T))
    assert result.binding is not None
    assert (result.binding.bound, result.binding.value) == (U, F)
    assert (result.bound, result.trigger, result.value) == (F, None, F)


# ---- T15: errors ---------------------------------------------------------------------


def test_t15_unknown_rule_id(bound_pack: RulePack) -> None:
    """A rule id not in the pack raises EvaluationError."""
    with pytest.raises(EvaluationError):
        evaluate_rule("TEST-NOPE", bound_pack, {})


def test_t15_rule_with_interpretations(tmp_path: Path) -> None:
    """A rule with interpretations instead of a trigger is left to C3b."""
    pack = write_pack(tmp_path, [rule_dict("TEST-SPLIT", interpretations=TWO_READINGS)])
    with pytest.raises(EvaluationError, match="C3b"):
        evaluate_rule("TEST-SPLIT", pack, {})


def test_t15_binding_rule_with_interpretations(tmp_path: Path) -> None:
    """A binding rule with interpretations is also left to C3b."""
    pack = write_pack(
        tmp_path,
        [
            rule_dict("TEST-SPLIT", interpretations=TWO_READINGS),
            rule_dict("TEST-RULE", trigger={"fact": C}, binding="TEST-SPLIT"),
        ],
    )
    with pytest.raises(EvaluationError, match="C3b"):
        evaluate_rule("TEST-RULE", pack, {})


@pytest.mark.parametrize(
    "expr",
    [AllExpr.model_construct(all=()), AnyExpr.model_construct(any=())],
    ids=["empty-all", "empty-any"],
)
def test_t15_empty_all_or_any(expr: Any) -> None:
    """The loader rejects empty lists; one built without validation is still refused."""
    with pytest.raises(EvaluationError):
        evaluate_expression(expr, {})


BAD_FACTS = [
    {1: Fact(value=T, grade="verified")},
    {A: True},
    {A: {"value": T, "grade": "verified"}},
]


@pytest.mark.parametrize("facts", BAD_FACTS, ids=["int-key", "bool-value", "dict-value"])
def test_t15_bad_facts_mapping(bound_pack: RulePack, facts: dict[Any, Any]) -> None:
    """Non-string keys and non-Fact values raise EvaluationError from both entry points."""
    with pytest.raises(EvaluationError):
        evaluate_expression(leaf(A), facts)
    with pytest.raises(EvaluationError):
        evaluate_rule("TEST-RULE", bound_pack, facts)


def test_t15_binding_cycle_in_hand_built_pack() -> None:
    """A pack built without the loader can hold a binding cycle; it raises, not recurses."""
    first = Rule.model_validate(rule_dict("TEST-A", trigger={"fact": A}, binding="TEST-B"))
    second = Rule.model_validate(rule_dict("TEST-B", trigger={"fact": B}, binding="TEST-A"))
    pack = RulePack.model_construct(rules=(first, second), warnings=())
    with pytest.raises(EvaluationError, match="cycle"):
        evaluate_rule("TEST-A", pack, {})


# ---- T16: determinism and purity --------------------------------------------------------


def test_t16_deterministic_and_pure(chain_pack: RulePack) -> None:
    """Two calls give equal results and the facts mapping is unchanged."""
    facts = facts_of(alpha=U, beta=T, gamma=F)
    before = copy.deepcopy(facts)
    first = evaluate_rule("TEST-C", chain_pack, facts)
    second = evaluate_rule("TEST-C", chain_pack, facts)
    assert first == second
    assert facts == before
    expr = all_(leaf(A), not_(leaf(B)))
    assert evaluate_expression(expr, facts) == evaluate_expression(expr, facts)
    assert facts == before


# ---- T17: depth 8 ---------------------------------------------------------------------


def test_t17_depth_8_from_loaded_rule(tmp_path: Path) -> None:
    """A depth-8 trigger loaded from YAML evaluates to the hand-worked value."""
    level7 = {"all": [{"fact": A}]}
    level6 = {"not": level7}
    level5 = {"any": [level6, {"fact": B}]}
    level4 = {"all": [level5]}
    level3 = {"not": level4}
    level2 = {"any": [level3]}
    level1 = {"all": [level2, {"fact": C}]}
    pack = write_pack(tmp_path, [rule_dict("TEST-DEEP", trigger=level1)])
    rule = pack.rules[0]
    assert rule.trigger is not None and expr_depth(rule.trigger) == 8
    # alpha T -> all T -> not F -> any(F, beta F) F -> all F -> not T -> any T -> all(T, gamma T) T
    result = evaluate_rule("TEST-DEEP", pack, facts_of(alpha=T, beta=F, gamma=T))
    assert result.value is T
    assert result.trigger is not None
    assert [item.fact for item in result.trigger.leaves] == [A, B, C]
