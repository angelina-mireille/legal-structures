"""Tests for src/core/outcomes.py: five outcomes over the C3a evaluator.

Every rule and fact here is synthetic (regime TEST, example.org URLs, "test." fact names).
Expected outcomes are written out literally, never computed by the code under test.
T9 and T10 are properties checked over a fixed set of rules and fact assignments.
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
    EvaluationError,
    ExprResult,
    Fact,
    RuleEvaluation,
    TriValue,
    evaluate_rule,
)
from core.graph import EvidenceGrade
from core.outcomes import (
    Direction,
    InterpretationOutcome,
    Outcome,
    OutcomeError,
    Question,
    QuestionKind,
    Reason,
    RuleOutcome,
    assess_rule,
    decisive_facts,
    relevant_facts,
)
from core.rules import RulePack, load_rule_pack

TODAY = date(2026, 11, 9)
LAST_VERIFIED = date(2026, 11, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64
EFFECTIVE_FROM = date(2026, 1, 1)

T = TriValue.TRUE
F = TriValue.FALSE
U = TriValue.UNKNOWN

A, B, C, D = "test.alpha", "test.beta", "test.gamma", "test.delta"

APPLIES = Outcome.APPLIES
DOES_NOT_APPLY = Outcome.DOES_NOT_APPLY
CONDITIONAL = Outcome.CONDITIONAL
INSUFFICIENT = Outcome.INSUFFICIENT_FACTS
UNSETTLED = Outcome.UNSETTLED

TEST_NOT_MET = Reason.TEST_NOT_MET
NOT_BOUND = Reason.NOT_BOUND

IF_APPLIES = Direction.APPLIES_IF_CONFIRMED
IF_NOT = Direction.DOES_NOT_APPLY_IF_CONFIRMED


# ---- Helpers (pack writing copied from tests/test_evaluator.py) ---------------------


def fact_of(value: TriValue, grade: str = "verified") -> Fact:
    """A Fact: TRUE/FALSE get the grade; UNKNOWN gets no grade."""
    if value is U:
        return Fact(value=U, grade=None)
    return Fact(value=value, grade=grade)


def f_(name: str, min_grade: str | None = None) -> dict[str, Any]:
    """A fact leaf as a rule-file dict."""
    return {"fact": name} if min_grade is None else {"fact": name, "min_grade": min_grade}


def all_(*children: dict[str, Any]) -> dict[str, Any]:
    """An all-expression as a rule-file dict."""
    return {"all": list(children)}


def any_(*children: dict[str, Any]) -> dict[str, Any]:
    """An any-expression as a rule-file dict."""
    return {"any": list(children)}


def not_(child: dict[str, Any]) -> dict[str, Any]:
    """A not-expression as a rule-file dict."""
    return {"not": child}


def rule_dict(
    rule_id: str,
    trigger: dict[str, Any] | None = None,
    binding: str | None = None,
    interpretations: list[dict[str, Any]] | None = None,
    unless: list[str] | None = None,
) -> dict[str, Any]:
    """A minimal synthetic TEST- rule as a dict."""
    rule: dict[str, Any] = {
        "id": rule_id,
        "version": "1.0.0",
        "regime": "TEST",
        "title": "Synthetic outcome test rule",
        "law_status": "in_force",
        "applies_to": "model",
        "binding": binding,
        "effect": "TEST_EFFECT",
        "unless": unless or [],
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
        "effective": {"from": EFFECTIVE_FROM, "basis": "synthetic test fixture"},
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


def readings(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Two interpretations, reading_a and reading_b, with the given triggers."""
    return [
        {"id": "reading_a", "summary": "Test reading A.", "trigger": a},
        {"id": "reading_b", "summary": "Test reading B.", "trigger": b},
    ]


def missing(name: str) -> Question:
    """A MISSING question for name."""
    return Question(fact=name, kind=QuestionKind.MISSING, current_grade=None, required_grade=None)


def stronger(name: str, current: str, required: str) -> Question:
    """A NEEDS_STRONGER_EVIDENCE question for name."""
    return Question(
        fact=name,
        kind=QuestionKind.NEEDS_STRONGER_EVIDENCE,
        current_grade=current,
        required_grade=required,
    )


def want(
    outcome: Outcome,
    *,
    reason: Reason | None = None,
    direction: Direction | None = None,
    binding_unresolved: bool = False,
    decisive: tuple[str, ...] = (),
    confirm: tuple[str, ...] = (),
    questions: tuple[Question, ...] = (),
    readings_agree: bool | None = None,
    exemptions: tuple[str, ...] = (),
) -> dict[str, Any]:
    """The expected summary fields of a RuleOutcome; unspecified fields take empty values."""
    return {
        "outcome": outcome,
        "reason": reason,
        "direction": direction,
        "binding_unresolved": binding_unresolved,
        "decisive_facts": decisive,
        "facts_to_confirm": confirm,
        "questions": questions,
        "readings_agree": readings_agree,
        "exemptions_pending": exemptions,
    }


def got(result: RuleOutcome) -> dict[str, Any]:
    """The summary fields of a RuleOutcome, for comparison with want()."""
    return {
        "outcome": result.outcome,
        "reason": result.reason,
        "direction": result.direction,
        "binding_unresolved": result.binding_unresolved,
        "decisive_facts": result.decisive_facts,
        "facts_to_confirm": result.facts_to_confirm,
        "questions": result.questions,
        "readings_agree": result.readings_agree,
        "exemptions_pending": result.exemptions_pending,
    }


def per_reading(result: RuleOutcome) -> list[tuple[Any, ...]]:
    """(id, outcome, reason, direction, decisive, confirm, questions) for each reading."""
    return [
        (
            item.interpretation_id,
            item.outcome,
            item.reason,
            item.direction,
            item.decisive_facts,
            item.facts_to_confirm,
            item.questions,
        )
        for item in result.interpretations
    ]


WIDE_12 = tuple(f"test.f{i:02d}" for i in range(1, 13))
WIDE_13 = tuple(f"test.f{i:02d}" for i in range(1, 14))


@pytest.fixture(scope="module")
def pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """One pack holding every hand-written rule used by T1-T8 and T11-T13."""
    return write_pack(
        tmp_path_factory.mktemp("outcomes"),
        [
            rule_dict("TEST-ONE", f_(A)),
            rule_dict("TEST-ALL2", all_(f_(A), f_(B))),
            rule_dict("TEST-ANY2", any_(f_(A), f_(B))),
            rule_dict("TEST-NOT", not_(f_(A))),
            rule_dict("TEST-BIND", f_(C)),
            rule_dict("TEST-BOUND", f_(A), binding="TEST-BIND"),
            rule_dict("TEST-ROOT", f_(D)),
            rule_dict("TEST-MID", f_(C), binding="TEST-ROOT"),
            rule_dict("TEST-LEAF", f_(A), binding="TEST-MID"),
            rule_dict("TEST-MIN", f_(A, "documented")),
            rule_dict("TEST-NESTED", any_(all_(f_(A), f_(B)), f_(C))),
            rule_dict("TEST-TWOMIN-HI", all_(f_(A, "verified"), f_(A, "declared"))),
            rule_dict("TEST-TWOMIN-LO", all_(f_(A, "declared"), f_(A, "verified"))),
            rule_dict("TEST-SPLIT", interpretations=readings(f_(A), f_(B))),
            rule_dict("TEST-SPLIT2", interpretations=readings(all_(f_(A), f_(B)), f_(A))),
            rule_dict("TEST-SPLITB", binding="TEST-BIND", interpretations=readings(f_(A), f_(B))),
            rule_dict("TEST-OUTER", binding="TEST-SPLIT", interpretations=readings(f_(A), f_(B))),
            rule_dict("TEST-EXEMPT", f_(A), unless=["TEST-X2", "TEST-X1"]),
            rule_dict("TEST-X1", f_(B)),
            rule_dict("TEST-X2", f_(C)),
            rule_dict("TEST-WIDE12", all_(*(f_(n) for n in WIDE_12))),
            rule_dict("TEST-WIDE13", all_(*(f_(n) for n in WIDE_13))),
        ],
    )


# ---- T1: APPLIES ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "decisive"),
    [
        ("TEST-ONE", {A: fact_of(T)}, (A,)),
        ("TEST-ALL2", {A: fact_of(T), B: fact_of(T)}, (A, B)),
        ("TEST-ANY2", {A: fact_of(T), B: fact_of(U)}, (A,)),
        ("TEST-ANY2", {A: fact_of(T)}, (A,)),
        ("TEST-NOT", {A: fact_of(F)}, (A,)),
    ],
    ids=["single-leaf", "all-two-true", "any-true-unknown", "any-true-absent", "not-false"],
)
def test_t1_applies(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], decisive: tuple[str, ...]
) -> None:
    """A definite TRUE resting on verified facts applies; decisive facts are listed."""
    result = assess_rule(rule_id, pack, facts)
    assert got(result) == want(APPLIES, decisive=decisive)
    assert result.rule_id == rule_id
    assert result.interpretations == ()
    assert result.evaluation is not None
    assert result.evaluation.value is T


# ---- T2: DOES_NOT_APPLY / TEST_NOT_MET ------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "decisive"),
    [
        ("TEST-ONE", {A: fact_of(F)}, (A,)),
        ("TEST-ALL2", {A: fact_of(F), B: fact_of(U)}, (A,)),
        ("TEST-ALL2", {A: fact_of(F)}, (A,)),
        ("TEST-ANY2", {A: fact_of(F), B: fact_of(F)}, (A, B)),
        ("TEST-NOT", {A: fact_of(T)}, (A,)),
    ],
    ids=["single-leaf", "all-false-unknown", "all-false-absent", "any-two-false", "not-true"],
)
def test_t2_does_not_apply_test_not_met(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], decisive: tuple[str, ...]
) -> None:
    """A definite FALSE trigger gives DOES_NOT_APPLY / TEST_NOT_MET."""
    result = assess_rule(rule_id, pack, facts)
    assert got(result) == want(DOES_NOT_APPLY, reason=TEST_NOT_MET, decisive=decisive)


# ---- T3: DOES_NOT_APPLY / NOT_BOUND ---------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "decisive"),
    [
        ("TEST-BOUND", {C: fact_of(F)}, (C,)),
        ("TEST-LEAF", {D: fact_of(F), C: fact_of(T), A: fact_of(T)}, (D,)),
        ("TEST-BOUND", {C: fact_of(F), A: fact_of(T)}, (C,)),
    ],
    ids=["binding-false", "chained-binding-false", "binding-false-trigger-true"],
)
def test_t3_does_not_apply_not_bound(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], decisive: tuple[str, ...]
) -> None:
    """A verified FALSE binding gives DOES_NOT_APPLY / NOT_BOUND, whatever the trigger."""
    result = assess_rule(rule_id, pack, facts)
    assert got(result) == want(DOES_NOT_APPLY, reason=NOT_BOUND, decisive=decisive)


# ---- T4: binding UNKNOWN --------------------------------------------------------------


def test_t4_binding_unknown_trigger_false(pack: RulePack) -> None:
    """Binding UNKNOWN, trigger FALSE: DOES_NOT_APPLY / TEST_NOT_MET, binding unresolved."""
    result = assess_rule("TEST-BOUND", pack, {A: fact_of(F)})
    assert got(result) == want(
        DOES_NOT_APPLY, reason=TEST_NOT_MET, binding_unresolved=True, decisive=(A,)
    )


def test_t4_binding_unknown_trigger_true(pack: RulePack) -> None:
    """Binding UNKNOWN, trigger TRUE: INSUFFICIENT_FACTS asking for the binding fact."""
    result = assess_rule("TEST-BOUND", pack, {A: fact_of(T)})
    assert got(result) == want(INSUFFICIENT, questions=(missing(C),))


# ---- T5: CONDITIONAL ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "direction", "confirm", "decisive"),
    [
        ("TEST-ONE", {A: fact_of(T, "suspected")}, IF_APPLIES, (A,), (A,)),
        (
            "TEST-ALL2",
            {A: fact_of(F, "suspected"), B: fact_of(T)},
            IF_NOT,
            (A,),
            (A,),
        ),
        (
            "TEST-BOUND",
            {C: fact_of(T, "suspected"), A: fact_of(T)},
            IF_APPLIES,
            (C,),
            (A, C),
        ),
    ],
    ids=["suspected-true-leaf", "suspected-false-decides-all", "suspected-in-binding"],
)
def test_t5_conditional(
    pack: RulePack,
    rule_id: str,
    facts: dict[str, Fact],
    direction: Direction,
    confirm: tuple[str, ...],
    decisive: tuple[str, ...],
) -> None:
    """A definite result that needs a suspected fact is CONDITIONAL, either way."""
    result = assess_rule(rule_id, pack, facts)
    assert got(result) == want(CONDITIONAL, direction=direction, confirm=confirm, decisive=decisive)


# ---- T6: suspected but not needed -----------------------------------------------------


def test_t6_suspected_not_needed_applies(pack: RulePack) -> None:
    """any(suspected TRUE, verified TRUE) applies; it is overdetermined, so nothing is decisive."""
    facts = {A: fact_of(T, "suspected"), B: fact_of(T)}
    assert got(assess_rule("TEST-ANY2", pack, facts)) == want(APPLIES, decisive=())


def test_t6_two_suspected_both_to_confirm(pack: RulePack) -> None:
    """any(suspected TRUE, suspected TRUE) is CONDITIONAL with both facts to confirm."""
    facts = {A: fact_of(T, "suspected"), B: fact_of(T, "suspected")}
    assert got(assess_rule("TEST-ANY2", pack, facts)) == want(
        CONDITIONAL, direction=IF_APPLIES, confirm=(A, B), decisive=()
    )


# ---- T7: INSUFFICIENT_FACTS -----------------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "questions"),
    [
        ("TEST-ONE", {}, (missing(A),)),
        ("TEST-MIN", {A: fact_of(T, "declared")}, (stronger(A, "declared", "documented"),)),
        ("TEST-NESTED", {B: fact_of(F)}, (missing(C),)),
        ("TEST-ALL2", {A: fact_of(U)}, (missing(A), missing(B))),
    ],
    ids=["absent", "below-min-grade", "irrelevant-fact-not-asked", "all-asks-both-sorted"],
)
def test_t7_insufficient_facts(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], questions: tuple[Question, ...]
) -> None:
    """An UNKNOWN result asks one question per relevant unknown fact, sorted by fact."""
    assert got(assess_rule(rule_id, pack, facts)) == want(INSUFFICIENT, questions=questions)


# ---- T8: required_grade is the highest ------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "grade", "question"),
    [
        ("TEST-TWOMIN-HI", "suspected", stronger(A, "suspected", "verified")),
        ("TEST-TWOMIN-LO", "suspected", stronger(A, "suspected", "verified")),
        ("TEST-TWOMIN-LO", "documented", stronger(A, "documented", "verified")),
    ],
    ids=["high-first", "low-first", "only-high-downgrades"],
)
def test_t8_required_grade_is_highest(
    pack: RulePack, rule_id: str, grade: str, question: Question
) -> None:
    """One fact in two leaves: required_grade is the higher min_grade that downgraded it."""
    result = assess_rule(rule_id, pack, {A: fact_of(T, grade)})
    assert got(result) == want(INSUFFICIENT, questions=(question,))


# ---- S1 (revised): bound FALSE resting on a suspected fact ----------------------------


def test_s1_suspected_false_binding_trigger_true(pack: RulePack) -> None:
    """Suspected FALSE binding, verified TRUE trigger: CONDITIONAL, confirm the binding fact."""
    facts = {C: fact_of(F, "suspected"), A: fact_of(T)}
    assert got(assess_rule("TEST-BOUND", pack, facts)) == want(
        CONDITIONAL, direction=IF_NOT, confirm=(C,), decisive=(C,)
    )


def test_s1_suspected_false_binding_trigger_false(pack: RulePack) -> None:
    """Suspected FALSE binding, verified FALSE trigger: TEST_NOT_MET, binding unresolved."""
    facts = {C: fact_of(F, "suspected"), A: fact_of(F)}
    assert got(assess_rule("TEST-BOUND", pack, facts)) == want(
        DOES_NOT_APPLY, reason=TEST_NOT_MET, binding_unresolved=True, decisive=()
    )


def test_s1_verified_false_binding(pack: RulePack) -> None:
    """Verified FALSE binding: NOT_BOUND."""
    facts = {C: fact_of(F), A: fact_of(T)}
    assert got(assess_rule("TEST-BOUND", pack, facts)) == want(
        DOES_NOT_APPLY, reason=NOT_BOUND, decisive=(C,)
    )


# ---- T9 / T10: properties over a fixed set -------------------------------------------

P_SINGLE = (
    "TEST-P-ONE",
    "TEST-P-ALL",
    "TEST-P-ANY",
    "TEST-P-NOT",
    "TEST-P-NEST",
    "TEST-P-MIN",
    "TEST-P-NOTANY",
    "TEST-P-ROOT",
    "TEST-P-BOUND",
    "TEST-P-BANY",
    "TEST-P-CHAIN",
)
P_ALL = (*P_SINGLE, "TEST-P-SPLIT")

STATES: dict[str, Fact | None] = {
    "absent": None,
    "unknown": fact_of(U),
    "true-verified": fact_of(T),
    "false-verified": fact_of(F),
    "true-suspected": fact_of(T, "suspected"),
    "false-suspected": fact_of(F, "suspected"),
    "true-declared": fact_of(T, "declared"),
}

DEFINITE = (APPLIES, DOES_NOT_APPLY, CONDITIONAL)
CERTAINTY = {APPLIES: 2, DOES_NOT_APPLY: 2, CONDITIONAL: 1, INSUFFICIENT: 0}
ONE_STEP_DOWN = {
    EvidenceGrade.VERIFIED: EvidenceGrade.DOCUMENTED,
    EvidenceGrade.DOCUMENTED: EvidenceGrade.DECLARED,
    EvidenceGrade.DECLARED: EvidenceGrade.SUSPECTED,
}


@pytest.fixture(scope="module")
def p_pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """The fixed rule set for T9 and T10 (facts alpha, beta, gamma)."""
    return write_pack(
        tmp_path_factory.mktemp("properties"),
        [
            rule_dict("TEST-P-ONE", f_(A)),
            rule_dict("TEST-P-ALL", all_(f_(A), f_(B))),
            rule_dict("TEST-P-ANY", any_(f_(A), f_(B))),
            rule_dict("TEST-P-NOT", not_(f_(A))),
            rule_dict("TEST-P-NEST", any_(all_(f_(A), f_(B)), f_(C))),
            rule_dict("TEST-P-MIN", all_(f_(A, "documented"), f_(B))),
            rule_dict("TEST-P-NOTANY", not_(any_(f_(A), f_(B, "verified")))),
            rule_dict("TEST-P-ROOT", f_(C)),
            rule_dict("TEST-P-BOUND", all_(f_(A), f_(B)), binding="TEST-P-ROOT"),
            rule_dict("TEST-P-BANY", any_(f_(A), not_(f_(B))), binding="TEST-P-ROOT"),
            rule_dict("TEST-P-CHAIN", f_(A, "declared"), binding="TEST-P-BOUND"),
            rule_dict("TEST-P-SPLIT", interpretations=readings(f_(A), all_(f_(A), f_(B)))),
        ],
    )


def assignments() -> list[dict[str, Fact]]:
    """Every combination of STATES for alpha, beta and gamma (343 mappings)."""
    found = []
    for combo in itertools.product(STATES.values(), repeat=3):
        found.append({n: v for n, v in zip((A, B, C), combo, strict=True) if v is not None})
    return found


def weakened(facts: dict[str, Fact]) -> list[tuple[str, dict[str, Fact]]]:
    """Each one-fact weakening of facts: one grade step down, or removal."""
    found = []
    for name, item in facts.items():
        rest = {k: v for k, v in facts.items() if k != name}
        found.append((f"remove {name}", rest))
        if item.grade in ONE_STEP_DOWN:
            lower = Fact(value=item.value, grade=ONE_STEP_DOWN[item.grade])
            found.append((f"downgrade {name}", {**rest, name: lower}))
    return found


def test_t9_set_size() -> None:
    """The property set has at least 10 rules and 343 assignments each."""
    assert len(P_ALL) >= 10
    assert len(assignments()) == 343


@pytest.mark.parametrize("rule_id", P_ALL)
def test_t9_removing_a_decisive_fact_gives_insufficient(p_pack: RulePack, rule_id: str) -> None:
    """Done-when: for every definite result, removing any decisive fact gives INSUFFICIENT."""
    checked = 0
    for facts in assignments():
        result = assess_rule(rule_id, p_pack, facts)
        if result.outcome not in DEFINITE:
            continue
        for name in result.decisive_facts:
            rest = {k: v for k, v in facts.items() if k != name}
            after = assess_rule(rule_id, p_pack, rest)
            assert after.outcome is INSUFFICIENT, (rule_id, facts, name)
            checked += 1
    assert checked > 0, f"{rule_id}: property never exercised"


@pytest.mark.parametrize("rule_id", P_SINGLE)
def test_t10_weakening_never_increases_certainty(p_pack: RulePack, rule_id: str) -> None:
    """Metamorphic: one grade step down, or removal, never makes a result more certain."""
    for facts in assignments():
        before = CERTAINTY[assess_rule(rule_id, p_pack, facts).outcome]
        for label, changed in weakened(facts):
            after = CERTAINTY[assess_rule(rule_id, p_pack, changed).outcome]
            assert after <= before, (rule_id, facts, label)


# ---- T11: interpretations -------------------------------------------------------------


def test_t11_unsettled_applies_vs_does_not_apply(pack: RulePack) -> None:
    """Readings that give APPLIES and DOES_NOT_APPLY are UNSETTLED."""
    result = assess_rule("TEST-SPLIT", pack, {A: fact_of(T), B: fact_of(F)})
    assert got(result) == want(UNSETTLED, readings_agree=False)
    assert result.evaluation is None
    assert per_reading(result) == [
        ("reading_a", APPLIES, None, None, (A,), (), ()),
        ("reading_b", DOES_NOT_APPLY, TEST_NOT_MET, None, (B,), (), ()),
    ]


def test_t11_unsettled_applies_vs_insufficient(pack: RulePack) -> None:
    """Readings that give APPLIES and INSUFFICIENT_FACTS are UNSETTLED."""
    result = assess_rule("TEST-SPLIT", pack, {A: fact_of(T)})
    assert got(result) == want(UNSETTLED, readings_agree=False)
    assert per_reading(result) == [
        ("reading_a", APPLIES, None, None, (A,), (), ()),
        ("reading_b", INSUFFICIENT, None, None, (), (), (missing(B),)),
    ]


def test_t11_unsettled_conditional_vs_applies(pack: RulePack) -> None:
    """Readings that give CONDITIONAL and APPLIES are UNSETTLED."""
    result = assess_rule("TEST-SPLIT", pack, {A: fact_of(T, "suspected"), B: fact_of(T)})
    assert got(result) == want(UNSETTLED, readings_agree=False)
    assert per_reading(result) == [
        ("reading_a", CONDITIONAL, None, IF_APPLIES, (A,), (A,), ()),
        ("reading_b", APPLIES, None, None, (B,), (), ()),
    ]


def test_t11_collapse_both_does_not_apply(pack: RulePack) -> None:
    """Both readings DOES_NOT_APPLY: collapse; decisive facts are those shared by every reading."""
    result = assess_rule("TEST-SPLIT2", pack, {A: fact_of(F), B: fact_of(T)})
    assert got(result) == want(
        DOES_NOT_APPLY, reason=TEST_NOT_MET, decisive=(A,), readings_agree=True
    )
    assert result.evaluation is None
    assert per_reading(result) == [
        ("reading_a", DOES_NOT_APPLY, TEST_NOT_MET, None, (A,), (), ()),
        ("reading_b", DOES_NOT_APPLY, TEST_NOT_MET, None, (A,), (), ()),
    ]


def test_t11_collapse_binding_false(pack: RulePack) -> None:
    """A FALSE binding makes every reading NOT_BOUND, so they collapse."""
    result = assess_rule("TEST-SPLITB", pack, {C: fact_of(F), A: fact_of(T)})
    assert got(result) == want(DOES_NOT_APPLY, reason=NOT_BOUND, decisive=(C,), readings_agree=True)


def test_t11_collapse_insufficient_unions_questions(pack: RulePack) -> None:
    """Both readings INSUFFICIENT_FACTS: the questions are the union, sorted."""
    result = assess_rule("TEST-SPLIT", pack, {})
    assert got(result) == want(
        INSUFFICIENT, questions=(missing(A), missing(B)), readings_agree=True
    )


# ---- T12: exemptions pending ----------------------------------------------------------


def test_t12_exemptions_pending(pack: RulePack) -> None:
    """unless ids are carried, sorted; the outcome ignores them even when they would hold."""
    facts = {A: fact_of(T), B: fact_of(T), C: fact_of(T)}
    result = assess_rule("TEST-EXEMPT", pack, facts)
    assert got(result) == want(APPLIES, decisive=(A,), exemptions=("TEST-X1", "TEST-X2"))


# ---- T13: relevance cap ---------------------------------------------------------------


def test_t13_twelve_unknown_facts_work(pack: RulePack) -> None:
    """12 distinct unknown facts are enumerated."""
    result = assess_rule("TEST-WIDE12", pack, {})
    assert got(result) == want(INSUFFICIENT, questions=tuple(missing(n) for n in WIDE_12))


def test_t13_thirteen_unknown_facts_fail_closed(pack: RulePack) -> None:
    """13 distinct unknown facts raise OutcomeError rather than guess."""
    with pytest.raises(OutcomeError, match="13"):
        assess_rule("TEST-WIDE13", pack, {})


# ---- Public helpers -------------------------------------------------------------------


def test_relevant_facts_direct(pack: RulePack) -> None:
    """relevant_facts follows D1: alpha cannot matter once beta is FALSE."""
    assert relevant_facts("TEST-NESTED", pack, {B: fact_of(F)}) == (C,)
    assert relevant_facts("TEST-NESTED", pack, {}) == (A, B, C)


def test_decisive_facts_direct(pack: RulePack) -> None:
    """decisive_facts follows D2, and is empty for an UNKNOWN value."""
    assert decisive_facts("TEST-ALL2", pack, {A: fact_of(F), B: fact_of(T)}) == (A,)
    assert decisive_facts("TEST-ALL2", pack, {A: fact_of(T)}) == ()


def test_helpers_take_interpretation_id(pack: RulePack) -> None:
    """Both helpers evaluate one reading when given its id."""
    facts = {A: fact_of(F), B: fact_of(T)}
    assert decisive_facts("TEST-SPLIT2", pack, facts, interpretation_id="reading_b") == (A,)
    assert relevant_facts("TEST-SPLIT", pack, {}, interpretation_id="reading_b") == (B,)


# ---- E: evaluator extension -----------------------------------------------------------


@pytest.mark.parametrize(
    "facts",
    [{C: fact_of(T), A: fact_of(T)}, {C: fact_of(F)}, {A: fact_of(F)}, {}],
    ids=["bound-true", "bound-false", "bound-unknown-false", "empty"],
)
def test_e_interpretation_matches_single_trigger(pack: RulePack, facts: dict[str, Fact]) -> None:
    """A reading evaluated with the rule's binding matches a single-trigger rule built the same."""
    reading = evaluate_rule("TEST-SPLITB", pack, facts, interpretation_id="reading_a")
    plain = evaluate_rule("TEST-BOUND", pack, facts)
    assert reading.rule_id == "TEST-SPLITB"
    assert (reading.binding, reading.bound, reading.trigger, reading.value) == (
        plain.binding,
        plain.bound,
        plain.trigger,
        plain.value,
    )


def test_e_unknown_interpretation_id(pack: RulePack) -> None:
    """An interpretation id the rule does not have is refused."""
    with pytest.raises(EvaluationError, match="reading_z"):
        evaluate_rule("TEST-SPLIT", pack, {}, interpretation_id="reading_z")


def test_e_interpretation_id_on_single_trigger_rule(pack: RulePack) -> None:
    """An interpretation id on a rule with a trigger is refused."""
    with pytest.raises(EvaluationError, match="TEST-ONE"):
        evaluate_rule("TEST-ONE", pack, {}, interpretation_id="reading_a")


def test_e_binding_rule_with_interpretations_still_raises(pack: RulePack) -> None:
    """A binding rule with interpretations still raises, through assess_rule too."""
    with pytest.raises(EvaluationError, match="C3b"):
        evaluate_rule("TEST-OUTER", pack, {}, interpretation_id="reading_a")
    with pytest.raises(EvaluationError, match="C3b"):
        assess_rule("TEST-OUTER", pack, {})


def test_e_unknown_rule_propagates(pack: RulePack) -> None:
    """An unknown rule id raises the evaluator's EvaluationError unchanged."""
    with pytest.raises(EvaluationError, match="TEST-NOPE"):
        assess_rule("TEST-NOPE", pack, {})


# ---- Validators -----------------------------------------------------------------------

EVALUATION = RuleEvaluation(
    rule_id="TEST-ONE",
    binding=None,
    bound=T,
    trigger=ExprResult(value=T, leaves=()),
    value=T,
)

READING = InterpretationOutcome(
    interpretation_id="reading_a",
    outcome=APPLIES,
    reason=None,
    direction=None,
    decisive_facts=(A,),
    facts_to_confirm=(),
    questions=(),
    evaluation=EVALUATION,
)

VALID_APPLIES: dict[str, Any] = {
    "rule_id": "TEST-ONE",
    "outcome": APPLIES,
    "decisive_facts": (A,),
    "evaluation": EVALUATION,
}


def test_validators_accept_valid_base() -> None:
    """The base used below is itself valid, with empty defaults."""
    result = RuleOutcome(**VALID_APPLIES)
    assert got(result) == want(APPLIES, decisive=(A,))
    assert result.interpretations == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": TEST_NOT_MET},
        {"direction": IF_APPLIES},
        {"facts_to_confirm": (A,)},
        {"questions": (missing(A),)},
        {"binding_unresolved": True},
        {"outcome": DOES_NOT_APPLY},
        {"outcome": CONDITIONAL},
        {"outcome": INSUFFICIENT},
        {"outcome": CONDITIONAL, "direction": IF_NOT, "binding_unresolved": True},
        {"outcome": DOES_NOT_APPLY, "reason": NOT_BOUND, "binding_unresolved": True},
        {"outcome": UNSETTLED, "decisive_facts": ()},
        {"readings_agree": True},
        {"evaluation": None},
        {"decisive_facts": (B, A)},
        {"interpretations": (READING,), "readings_agree": None, "evaluation": None},
        {"interpretations": (READING,), "readings_agree": True},
        {
            "outcome": UNSETTLED,
            "decisive_facts": (),
            "interpretations": (READING,),
            "readings_agree": True,
            "evaluation": None,
        },
        {"exemptions_pending": ("TEST-X2", "TEST-X1")},
        {"questions": (missing(B), missing(A)), "outcome": INSUFFICIENT, "decisive_facts": ()},
    ],
    ids=[
        "reason-on-applies",
        "direction-on-applies",
        "confirm-on-applies",
        "questions-on-applies",
        "binding-unresolved-on-applies",
        "does-not-apply-without-reason",
        "conditional-without-direction",
        "insufficient-with-decisive",
        "binding-unresolved-on-conditional",
        "binding-unresolved-with-not-bound",
        "unsettled-single-trigger",
        "readings-agree-single-trigger",
        "single-trigger-without-evaluation",
        "unsorted-decisive",
        "interpretations-without-readings-agree",
        "interpretations-with-evaluation",
        "unsettled-with-readings-agree",
        "unsorted-exemptions",
        "unsorted-questions",
    ],
)
def test_validators_reject(changes: dict[str, Any]) -> None:
    """Every "only for" constraint, and sorting, is enforced."""
    with pytest.raises(ValidationError):
        RuleOutcome(**{**VALID_APPLIES, **changes})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": QuestionKind.MISSING, "current_grade": "declared", "required_grade": None},
        {"kind": QuestionKind.MISSING, "current_grade": None, "required_grade": "verified"},
        {
            "kind": QuestionKind.NEEDS_STRONGER_EVIDENCE,
            "current_grade": None,
            "required_grade": None,
        },
        {
            "kind": QuestionKind.NEEDS_STRONGER_EVIDENCE,
            "current_grade": "verified",
            "required_grade": "declared",
        },
    ],
    ids=["missing-with-current", "missing-with-required", "stronger-without-grades", "not-lower"],
)
def test_question_validator_rejects(kwargs: dict[str, Any]) -> None:
    """MISSING carries no grades; NEEDS_STRONGER_EVIDENCE needs current below required."""
    with pytest.raises(ValidationError):
        Question(fact=A, **kwargs)


# ---- Purity ---------------------------------------------------------------------------


def test_pure_and_deterministic(pack: RulePack) -> None:
    """Inputs are unchanged and repeated calls give equal results."""
    facts = {C: fact_of(T, "suspected"), A: fact_of(T)}
    before_facts = copy.deepcopy(facts)
    before_pack = pack.model_dump()
    first = assess_rule("TEST-BOUND", pack, facts)
    second = assess_rule("TEST-BOUND", pack, facts)
    assert first == second
    assert facts == before_facts
    assert pack.model_dump() == before_pack
