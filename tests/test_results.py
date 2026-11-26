"""Tests for src/core/results.py: exemptions, clocks and the result model (C3c).

Every rule and fact here is synthetic (regimes TEST and TEST-B, example.org URLs,
"test." fact names). Expected values are written out literally, never computed by the
code under test. T12 and T13 are properties checked over a fixed set of rules and facts.
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

from core.evaluator import EvaluationError, ExprResult, Fact, RuleEvaluation, TriValue
from core.graph import EvidenceGrade
from core.outcomes import (
    Direction,
    Outcome,
    Question,
    QuestionKind,
    Reason,
    RuleOutcome,
    assess_rule,
)
from core.results import (
    ClockNote,
    ClockStatus,
    ExemptionResult,
    RegimeResult,
    ResultError,
    RuleResult,
    SubjectResult,
    assess_rule_final,
    assess_subject,
)
from core.rules import Rule, RulePack, load_rule_pack

TODAY = date(2026, 11, 24)
LAST_VERIFIED = date(2026, 11, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64
EFFECTIVE_FROM = date(2026, 1, 1)
NOTE = "Start date not computed; when the clock starts is for counsel."

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
EXEMPT = Reason.EXEMPT

IF_APPLIES = Direction.APPLIES_IF_CONFIRMED
IF_NOT = Direction.DOES_NOT_APPLY_IF_CONFIRMED

CLOCK_30 = {"amount": 30, "unit": "calendar_days", "trigger": "Test event occurs."}
CLOCK_72 = {"amount": 72, "unit": "hours", "trigger": "Test notice is received."}


# ---- Helpers (pack writing copied from tests/test_outcomes.py, extended) --------------


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
    clock: dict[str, Any] | None = None,
    applies_to: str = "model",
    law_status: str = "in_force",
    regime: str = "TEST",
) -> dict[str, Any]:
    """A minimal synthetic TEST- rule as a dict."""
    rule: dict[str, Any] = {
        "id": rule_id,
        "version": "1.0.0",
        "regime": regime,
        "title": "Synthetic result test rule",
        "law_status": law_status,
        "applies_to": applies_to,
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
        "clock": clock,
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


def hand_built(rules: list[dict[str, Any]]) -> RulePack:
    """A pack that skips the loader's reference checks (for guards against bad packs)."""
    return RulePack.model_construct(rules=tuple(Rule.model_validate(r) for r in rules), warnings=())


def readings(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Two interpretations, reading_a and reading_b, with the given triggers."""
    return [
        {"id": "reading_a", "summary": "Test reading A.", "trigger": a},
        {"id": "reading_b", "summary": "Test reading B.", "trigger": b},
    ]


def missing(name: str) -> Question:
    """A MISSING question for name."""
    return Question(fact=name, kind=QuestionKind.MISSING, current_grade=None, required_grade=None)


def ex(
    rule_id: str,
    outcome: Outcome,
    *,
    applied: bool = False,
    unresolved: bool = False,
    questions: tuple[Question, ...] = (),
    confirm: tuple[str, ...] = (),
) -> ExemptionResult:
    """An expected ExemptionResult, written out literally."""
    return ExemptionResult(
        rule_id=rule_id,
        outcome=outcome,
        applied=applied,
        unresolved=unresolved,
        questions=questions,
        facts_to_confirm=confirm,
    )


def clock_note(
    status: ClockStatus, readings_: tuple[str, ...] = (), spec: dict[str, Any] = CLOCK_30
) -> ClockNote:
    """An expected ClockNote, with the fixed note text written out literally."""
    return ClockNote(
        amount=spec["amount"],
        unit=spec["unit"],
        trigger=spec["trigger"],
        status=status,
        readings=readings_,
        note=NOTE,
    )


def want(
    outcome: Outcome,
    *,
    reason: Reason | None = None,
    direction: Direction | None = None,
    exempted_by: tuple[str, ...] = (),
    exemptions: tuple[ExemptionResult, ...] = (),
    clock: ClockNote | None = None,
) -> dict[str, Any]:
    """The expected final fields of a RuleResult; unspecified fields take empty values."""
    return {
        "outcome": outcome,
        "reason": reason,
        "direction": direction,
        "exempted_by": exempted_by,
        "exemptions": exemptions,
        "clock": clock,
    }


def got(result: RuleResult) -> dict[str, Any]:
    """The final fields of a RuleResult, for comparison with want()."""
    return {
        "outcome": result.outcome,
        "reason": result.reason,
        "direction": result.direction,
        "exempted_by": result.exempted_by,
        "exemptions": result.exemptions,
        "clock": result.clock,
    }


@pytest.fixture(scope="module")
def pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """One pack holding the hand-written rules for T1-T8, T11 and T15."""
    return write_pack(
        tmp_path_factory.mktemp("results"),
        [
            rule_dict("TEST-R", f_(A), unless=["TEST-E1"]),
            rule_dict("TEST-RS", interpretations=readings(f_(A), f_(D)), unless=["TEST-E1"]),
            rule_dict("TEST-RU", f_(A), unless=["TEST-EU"]),
            rule_dict("TEST-RB", f_(A), binding="TEST-BIND", unless=["TEST-E1"]),
            rule_dict("TEST-R2", f_(A), unless=["TEST-E2", "TEST-E1"]),
            rule_dict("TEST-RN", f_(A), unless=["TEST-EN"]),
            rule_dict("TEST-K", f_(A), unless=["TEST-KX"], clock=CLOCK_30),
            rule_dict("TEST-KS", interpretations=readings(f_(A), f_(D)), clock=CLOCK_72),
            rule_dict("TEST-E1", f_(B)),
            rule_dict("TEST-E2", f_(C)),
            rule_dict("TEST-EU", interpretations=readings(f_(B), all_(f_(C), f_(D)))),
            rule_dict("TEST-BIND", f_(C)),
            rule_dict("TEST-EN", f_(B), unless=["TEST-FN"]),
            rule_dict("TEST-FN", f_(C)),
            rule_dict("TEST-KX", f_(B)),
        ],
    )


# ---- T1: an applying exemption turns every base into DOES_NOT_APPLY / EXEMPT -------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "base"),
    [
        ("TEST-R", {A: fact_of(T), B: fact_of(T)}, APPLIES),
        ("TEST-R", {A: fact_of(T, "suspected"), B: fact_of(T)}, CONDITIONAL),
        ("TEST-R", {B: fact_of(T)}, INSUFFICIENT),
        ("TEST-RS", {A: fact_of(T), D: fact_of(F), B: fact_of(T)}, UNSETTLED),
    ],
    ids=["base-applies", "base-conditional", "base-insufficient", "base-unsettled"],
)
def test_t1_applying_exemption_exempts(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], base: Outcome
) -> None:
    """Strict: an exemption whose final outcome is APPLIES displaces any open base."""
    result = assess_rule_final(rule_id, pack, facts, as_of=TODAY)
    assert result.base.outcome is base
    assert got(result) == want(
        DOES_NOT_APPLY,
        reason=EXEMPT,
        exempted_by=("TEST-E1",),
        exemptions=(ex("TEST-E1", APPLIES, applied=True),),
    )
    assert result.rule_id == rule_id
    assert result.regime == "TEST"


# ---- T2: a non-applying exemption leaves the base, unflagged --------------------------


def test_t2_exemption_does_not_apply(pack: RulePack) -> None:
    """An exemption that is DOES_NOT_APPLY is listed, not flagged; the base stands."""
    result = assess_rule_final("TEST-R", pack, {A: fact_of(T), B: fact_of(F)}, as_of=TODAY)
    assert got(result) == want(APPLIES, exemptions=(ex("TEST-E1", DOES_NOT_APPLY),))
    assert result.base.outcome is APPLIES


# ---- T3: an open exemption leaves the base, flagged ------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "exemption"),
    [
        (
            "TEST-R",
            {A: fact_of(T), B: fact_of(T, "suspected")},
            ex("TEST-E1", CONDITIONAL, unresolved=True, confirm=(B,)),
        ),
        (
            "TEST-R",
            {A: fact_of(T)},
            ex("TEST-E1", INSUFFICIENT, unresolved=True, questions=(missing(B),)),
        ),
        (
            "TEST-RU",
            {A: fact_of(T), B: fact_of(T, "suspected")},
            ex(
                "TEST-EU",
                UNSETTLED,
                unresolved=True,
                questions=(missing(D), missing(C)),
                confirm=(B,),
            ),
        ),
    ],
    ids=["conditional", "insufficient", "unsettled-merges-readings"],
)
def test_t3_open_exemption_is_flagged(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], exemption: ExemptionResult
) -> None:
    """An open exemption does not apply; it is flagged with what would resolve it (D6b)."""
    result = assess_rule_final(rule_id, pack, facts, as_of=TODAY)
    assert got(result) == want(APPLIES, exemptions=(exemption,))


# ---- T4: a DOES_NOT_APPLY base is kept and exemptions are not evaluated ------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "reason"),
    [
        ("TEST-RB", {C: fact_of(F), A: fact_of(T), B: fact_of(T)}, NOT_BOUND),
        ("TEST-R", {A: fact_of(F), B: fact_of(T)}, TEST_NOT_MET),
    ],
    ids=["not-bound", "test-not-met"],
)
def test_t4_does_not_apply_base_kept(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], reason: Reason
) -> None:
    """NOT_BOUND and TEST_NOT_MET stand; no exemption is listed, even one that would apply."""
    result = assess_rule_final(rule_id, pack, facts, as_of=TODAY)
    assert got(result) == want(DOES_NOT_APPLY, reason=reason)


def test_t4_exemptions_not_evaluated() -> None:
    """With a missing exemption rule, a TEST_NOT_MET base still succeeds: it never looks."""
    ghost = hand_built([rule_dict("TEST-R", f_(A), unless=["TEST-GHOST"])])
    result = assess_rule_final("TEST-R", ghost, {A: fact_of(F)}, as_of=TODAY)
    assert got(result) == want(DOES_NOT_APPLY, reason=TEST_NOT_MET)
    with pytest.raises(EvaluationError):
        assess_rule_final("TEST-R", ghost, {A: fact_of(T)}, as_of=TODAY)


# ---- T5: two exemptions ----------------------------------------------------------------


def test_t5_one_of_two_applies(pack: RulePack) -> None:
    """exempted_by names only the applying exemption; both are listed, sorted."""
    result = assess_rule_final(
        "TEST-R2", pack, {A: fact_of(T), B: fact_of(T), C: fact_of(F)}, as_of=TODAY
    )
    assert got(result) == want(
        DOES_NOT_APPLY,
        reason=EXEMPT,
        exempted_by=("TEST-E1",),
        exemptions=(ex("TEST-E1", APPLIES, applied=True), ex("TEST-E2", DOES_NOT_APPLY)),
    )


def test_t5_both_apply(pack: RulePack) -> None:
    """Both applying: both in exempted_by, sorted."""
    result = assess_rule_final(
        "TEST-R2", pack, {A: fact_of(T), B: fact_of(T), C: fact_of(T)}, as_of=TODAY
    )
    assert got(result) == want(
        DOES_NOT_APPLY,
        reason=EXEMPT,
        exempted_by=("TEST-E1", "TEST-E2"),
        exemptions=(
            ex("TEST-E1", APPLIES, applied=True),
            ex("TEST-E2", APPLIES, applied=True),
        ),
    )


# ---- T6: nested exemptions (D6, D6a) ---------------------------------------------------


def test_t6_exempted_exemption_does_not_apply(pack: RulePack) -> None:
    """The exemption's own exemption applies, so the exemption is DOES_NOT_APPLY."""
    result = assess_rule_final(
        "TEST-RN", pack, {A: fact_of(T), B: fact_of(T), C: fact_of(T)}, as_of=TODAY
    )
    assert got(result) == want(APPLIES, exemptions=(ex("TEST-EN", DOES_NOT_APPLY),))


def test_t6_open_carve_back_insufficient(pack: RulePack) -> None:
    """D6a: an open sub-exemption stops the exemption applying; it carries the question."""
    result = assess_rule_final("TEST-RN", pack, {A: fact_of(T), B: fact_of(T)}, as_of=TODAY)
    assert got(result) == want(
        APPLIES,
        exemptions=(ex("TEST-EN", APPLIES, unresolved=True, questions=(missing(C),)),),
    )


def test_t6_open_carve_back_conditional(pack: RulePack) -> None:
    """D6a: a CONDITIONAL sub-exemption passes its facts to confirm up to the exemption."""
    facts = {A: fact_of(T), B: fact_of(T), C: fact_of(T, "suspected")}
    result = assess_rule_final("TEST-RN", pack, facts, as_of=TODAY)
    assert got(result) == want(
        APPLIES, exemptions=(ex("TEST-EN", APPLIES, unresolved=True, confirm=(C,)),)
    )


def test_t6_carve_back_does_not_apply(pack: RulePack) -> None:
    """The sub-exemption is DOES_NOT_APPLY, so the exemption applies and exempts the rule."""
    result = assess_rule_final(
        "TEST-RN", pack, {A: fact_of(T), B: fact_of(T), C: fact_of(F)}, as_of=TODAY
    )
    assert got(result) == want(
        DOES_NOT_APPLY,
        reason=EXEMPT,
        exempted_by=("TEST-EN",),
        exemptions=(ex("TEST-EN", APPLIES, applied=True),),
    )


def test_t6_removing_carve_back_fact_stays_insufficient(pack: RulePack) -> None:
    """The plan's counterexample: removing gamma no longer yields DOES_NOT_APPLY (D6a)."""
    before = assess_rule_final("TEST-RN", pack, {B: fact_of(T), C: fact_of(T)}, as_of=TODAY)
    after = assess_rule_final("TEST-RN", pack, {B: fact_of(T)}, as_of=TODAY)
    assert got(before) == want(INSUFFICIENT, exemptions=(ex("TEST-EN", DOES_NOT_APPLY),))
    assert got(after) == want(
        INSUFFICIENT,
        exemptions=(ex("TEST-EN", APPLIES, unresolved=True, questions=(missing(C),)),),
    )


# ---- T7: repeated id in the exemption chain ---------------------------------------------


def test_t7_exemption_cycle_raises() -> None:
    """A hand-built pack with an unless cycle raises ResultError, not a recursion error."""
    cyclic = hand_built(
        [
            rule_dict("TEST-CA", f_(A), unless=["TEST-CB"]),
            rule_dict("TEST-CB", f_(B), unless=["TEST-CA"]),
        ]
    )
    with pytest.raises(ResultError, match="TEST-CA"):
        assess_rule_final("TEST-CA", cyclic, {A: fact_of(T), B: fact_of(T)}, as_of=TODAY)


# ---- T8: clocks (D7) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "facts", "outcome", "direction", "clock"),
    [
        ("TEST-K", {A: fact_of(T)}, APPLIES, None, clock_note(ClockStatus.APPLIES)),
        (
            "TEST-K",
            {A: fact_of(T, "suspected")},
            CONDITIONAL,
            IF_APPLIES,
            clock_note(ClockStatus.IF_CONFIRMED),
        ),
        ("TEST-K", {A: fact_of(F, "suspected")}, CONDITIONAL, IF_NOT, None),
        (
            "TEST-KS",
            {A: fact_of(T), D: fact_of(F)},
            UNSETTLED,
            None,
            clock_note(ClockStatus.UNDER_READINGS, ("reading_a",), CLOCK_72),
        ),
        (
            "TEST-KS",
            {A: fact_of(T, "suspected"), D: fact_of(F)},
            UNSETTLED,
            None,
            clock_note(ClockStatus.UNDER_READINGS, ("reading_a",), CLOCK_72),
        ),
        (
            "TEST-KS",
            {A: fact_of(F), D: fact_of(T)},
            UNSETTLED,
            None,
            clock_note(ClockStatus.UNDER_READINGS, ("reading_b",), CLOCK_72),
        ),
        ("TEST-KS", {D: fact_of(F)}, UNSETTLED, None, None),
        (
            "TEST-KS",
            {A: fact_of(T), D: fact_of(T)},
            APPLIES,
            None,
            clock_note(ClockStatus.APPLIES, (), CLOCK_72),
        ),
        ("TEST-K", {A: fact_of(T), B: fact_of(T)}, DOES_NOT_APPLY, None, None),
        ("TEST-K", {}, INSUFFICIENT, None, None),
        ("TEST-R", {A: fact_of(T), B: fact_of(F)}, APPLIES, None, None),
    ],
    ids=[
        "applies",
        "conditional-if-applies",
        "conditional-if-not",
        "unsettled-applying-reading",
        "unsettled-conditional-reading",
        "unsettled-reading-b",
        "unsettled-no-qualifying-reading",
        "readings-agree-applies",
        "exempt",
        "insufficient",
        "rule-without-clock",
    ],
)
def test_t8_clocks(
    pack: RulePack,
    rule_id: str,
    facts: dict[str, Fact],
    outcome: Outcome,
    direction: Direction | None,
    clock: ClockNote | None,
) -> None:
    """Display-only clocks: amount, unit and trigger copied, status from the final outcome."""
    result = assess_rule_final(rule_id, pack, facts, as_of=TODAY)
    assert (result.outcome, result.direction, result.clock) == (outcome, direction, clock)


def test_t8_note_text_exact(pack: RulePack) -> None:
    """The fixed note text, character for character."""
    result = assess_rule_final("TEST-K", pack, {A: fact_of(T)}, as_of=TODAY)
    assert result.clock is not None
    assert result.clock.note == "Start date not computed; when the clock starts is for counsel."
    assert (result.clock.amount, result.clock.unit, result.clock.trigger) == (
        30,
        "calendar_days",
        "Test event occurs.",
    )


# ---- T9: filtering (D8) ---------------------------------------------------------------


@pytest.fixture(scope="module")
def filter_pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """Rules of two node kinds, proposed rules, and helper rules."""
    return write_pack(
        tmp_path_factory.mktemp("filtering"),
        [
            rule_dict("TEST-M1", f_(A)),
            rule_dict("TEST-M2", f_(A), applies_to="entity"),
            rule_dict("TEST-MP", f_(A), law_status="proposed"),
            rule_dict("TEST-EP", f_(A), applies_to="entity", law_status="proposed"),
            rule_dict("TEST-M3", f_(A), binding="TEST-MH"),
            rule_dict("TEST-MH", f_(B)),
            rule_dict("TEST-M4", f_(A), unless=["TEST-MX"]),
            rule_dict("TEST-MX", f_(C)),
        ],
    )


FILTER_FACTS = {A: fact_of(T), B: fact_of(T), C: fact_of(F)}


def rule_ids(result: SubjectResult) -> list[list[str]]:
    """The rule ids in each regime, in order."""
    return [[r.rule_id for r in regime.rules] for regime in result.regimes]


def test_t9_model_subject(filter_pack: RulePack) -> None:
    """applies_to mismatches and helpers are skipped; a proposed rule is excluded and listed."""
    result = assess_subject("test-subject-1", "model", filter_pack, FILTER_FACTS, as_of=TODAY)
    assert rule_ids(result) == [["TEST-M1", "TEST-M3", "TEST-M4"]]
    assert result.excluded_proposed == ("TEST-MP",)
    assert [r.outcome for r in result.regimes[0].rules] == [APPLIES, APPLIES, APPLIES]
    assert (result.subject_id, result.subject_kind) == ("test-subject-1", "model")


def test_t9_entity_subject(filter_pack: RulePack) -> None:
    """The other node kind sees only its own rules and its own proposed rule."""
    result = assess_subject("test-subject-2", "entity", filter_pack, FILTER_FACTS, as_of=TODAY)
    assert rule_ids(result) == [["TEST-M2"]]
    assert result.excluded_proposed == ("TEST-EP",)


def test_t9_include_proposed(filter_pack: RulePack) -> None:
    """include_proposed=True reports the proposed rule and lists nothing as excluded."""
    result = assess_subject(
        "test-subject-1",
        "model",
        filter_pack,
        FILTER_FACTS,
        include_proposed=True,
        as_of=TODAY,
    )
    assert rule_ids(result) == [["TEST-M1", "TEST-M3", "TEST-M4", "TEST-MP"]]
    assert result.excluded_proposed == ()


DEPENDENCY_CASES = {
    "proposed-binding": [
        rule_dict("TEST-D1", f_(A), binding="TEST-DP"),
        rule_dict("TEST-DP", f_(B), law_status="proposed"),
    ],
    "proposed-exemption": [
        rule_dict("TEST-D1", f_(A), unless=["TEST-DP"]),
        rule_dict("TEST-DP", f_(B), law_status="proposed"),
    ],
    "proposed-behind-helper": [
        rule_dict("TEST-D1", f_(A), binding="TEST-DH"),
        rule_dict("TEST-DH", f_(C), binding="TEST-DP"),
        rule_dict("TEST-DP", f_(B), law_status="proposed"),
    ],
}


@pytest.mark.parametrize("case", list(DEPENDENCY_CASES))
def test_t9_proposed_dependency_raises(tmp_path: Path, case: str) -> None:
    """An included rule relying on a proposed rule raises, naming both; allowed if included."""
    dep_pack = write_pack(tmp_path, DEPENDENCY_CASES[case])
    with pytest.raises(ResultError, match="TEST-D1") as caught:
        assess_subject("test-subject-1", "model", dep_pack, FILTER_FACTS, as_of=TODAY)
    assert "TEST-DP" in str(caught.value)
    result = assess_subject(
        "test-subject-1",
        "model",
        dep_pack,
        FILTER_FACTS,
        include_proposed=True,
        as_of=TODAY,
    )
    assert rule_ids(result) == [["TEST-D1"]]
    assert result.excluded_proposed == ()


# ---- T10: grouping by regime -------------------------------------------------------------


def test_t10_two_regimes(tmp_path: Path) -> None:
    """Two regimes give two RegimeResults sorted by regime, rules sorted by id, no conflict."""
    regime_pack = write_pack(
        tmp_path,
        [
            rule_dict("TEST-G1", f_(A), regime="TEST-B"),
            rule_dict("TEST-G3", f_(B)),
            rule_dict("TEST-G2", f_(A)),
        ],
    )
    result = assess_subject("test-subject-1", "model", regime_pack, {A: fact_of(T)}, as_of=TODAY)
    assert [r.regime for r in result.regimes] == ["TEST", "TEST-B"]
    assert rule_ids(result) == [["TEST-G2", "TEST-G3"], ["TEST-G1"]]
    assert [r.conflict for r in result.regimes] == [None, None]


def test_t10_conflict_must_be_none() -> None:
    """conflict is reserved for v1: anything but None is rejected."""
    with pytest.raises(ValidationError):
        RegimeResult(regime="TEST", rules=(), conflict="CONFLICT")


# ---- T11: done-when, JSON round trip -----------------------------------------------------


SUBJECTS = {
    "interpretations": {A: fact_of(T), D: fact_of(F)},
    "exemptions": {A: fact_of(T), B: fact_of(T), C: fact_of(T)},
    "clocks": {A: fact_of(T, "suspected")},
}


@pytest.mark.parametrize("name", list(SUBJECTS))
def test_t11_round_trip(pack: RulePack, name: str) -> None:
    """SubjectResult survives model_dump_json / model_validate_json unchanged."""
    result = assess_subject(f"test-subject-{name}", "model", pack, SUBJECTS[name], as_of=TODAY)
    assert SubjectResult.model_validate_json(result.model_dump_json()) == result


def test_t11_subjects_cover_features(pack: RulePack) -> None:
    """The three subjects really exercise interpretations, exemptions and clocks."""
    by_id = {
        name: {
            r.rule_id: r
            for g in assess_subject(name, "model", pack, facts, as_of=TODAY).regimes
            for r in g.rules
        }
        for name, facts in SUBJECTS.items()
    }
    assert by_id["interpretations"]["TEST-RS"].outcome is UNSETTLED
    assert by_id["interpretations"]["TEST-KS"].clock == clock_note(
        ClockStatus.UNDER_READINGS, ("reading_a",), CLOCK_72
    )
    assert by_id["exemptions"]["TEST-R2"].exempted_by == ("TEST-E1", "TEST-E2")
    assert by_id["exemptions"]["TEST-RN"].outcome is APPLIES
    assert by_id["clocks"]["TEST-K"].clock == clock_note(ClockStatus.IF_CONFIRMED)
    assert sorted(by_id["clocks"]) == [
        "TEST-K",
        "TEST-KS",
        "TEST-R",
        "TEST-R2",
        "TEST-RB",
        "TEST-RN",
        "TEST-RS",
        "TEST-RU",
    ]


# ---- T12 / T13: properties over a fixed set with exemptions ------------------------------

Q_TOP = (
    "TEST-Q-ONE",
    "TEST-Q-NEST",
    "TEST-Q-TWO",
    "TEST-Q-SHARED",
    "TEST-Q-BOUND",
    "TEST-Q-MIN",
)
Q_HELPERS = ("TEST-Q-X1", "TEST-Q-XN", "TEST-Q-XF", "TEST-Q-X3", "TEST-Q-XA", "TEST-Q-BIND")
Q_ALL = (*Q_TOP, *Q_HELPERS, "TEST-Q-XM")

STATES: dict[str, Fact | None] = {
    "absent": None,
    "unknown": fact_of(U),
    "true-verified": fact_of(T),
    "false-verified": fact_of(F),
    "true-suspected": fact_of(T, "suspected"),
    "false-suspected": fact_of(F, "suspected"),
    "true-declared": fact_of(T, "declared"),
}

CERTAINTY = {APPLIES: 2, DOES_NOT_APPLY: 2, CONDITIONAL: 1, INSUFFICIENT: 0}
ONE_STEP_DOWN = {
    EvidenceGrade.VERIFIED: EvidenceGrade.DOCUMENTED,
    EvidenceGrade.DOCUMENTED: EvidenceGrade.DECLARED,
    EvidenceGrade.DECLARED: EvidenceGrade.SUSPECTED,
}


@pytest.fixture(scope="module")
def q_pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """The fixed rule set for T12 and T13 (facts alpha, beta, gamma), with exemptions."""
    return write_pack(
        tmp_path_factory.mktemp("q-properties"),
        [
            rule_dict("TEST-Q-ONE", f_(A), unless=["TEST-Q-X1"]),
            rule_dict("TEST-Q-NEST", f_(A), unless=["TEST-Q-XN"]),
            rule_dict("TEST-Q-TWO", any_(f_(A), f_(B)), unless=["TEST-Q-X1", "TEST-Q-X3"]),
            rule_dict("TEST-Q-SHARED", f_(A), unless=["TEST-Q-XA"]),
            rule_dict("TEST-Q-BOUND", f_(B), binding="TEST-Q-BIND", unless=["TEST-Q-XA"]),
            rule_dict("TEST-Q-MIN", f_(A), unless=["TEST-Q-XM"]),
            rule_dict("TEST-Q-X1", f_(B)),
            rule_dict("TEST-Q-XN", f_(B), unless=["TEST-Q-XF"]),
            rule_dict("TEST-Q-XF", f_(C)),
            rule_dict("TEST-Q-X3", not_(f_(C))),
            rule_dict("TEST-Q-XA", all_(f_(A), f_(B))),
            rule_dict("TEST-Q-BIND", f_(C)),
            rule_dict("TEST-Q-XM", f_(B, "documented")),
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


@pytest.mark.parametrize("rule_id", Q_TOP)
def test_t12_weakening_never_increases_certainty(q_pack: RulePack, rule_id: str) -> None:
    """Metamorphic: one grade step down, or removal, never makes a final outcome more certain."""
    checked = 0
    for facts in assignments():
        before = assess_rule_final(rule_id, q_pack, facts, as_of=TODAY).outcome
        if before is UNSETTLED:
            continue
        for label, changed in weakened(facts):
            after = assess_rule_final(rule_id, q_pack, changed, as_of=TODAY).outcome
            if after is UNSETTLED:
                continue
            assert CERTAINTY[after] <= CERTAINTY[before], (rule_id, facts, label)
            checked += 1
    assert checked > 0


def test_t12_set_exercises_exemptions(q_pack: RulePack) -> None:
    """The set reaches EXEMPT and flagged exemptions, so T12 is not vacuous."""
    reasons = set()
    flagged = 0
    for rule_id in Q_TOP:
        for facts in assignments():
            result = assess_rule_final(rule_id, q_pack, facts, as_of=TODAY)
            reasons.add(result.reason)
            flagged += sum(1 for e in result.exemptions if e.unresolved)
    assert EXEMPT in reasons
    assert flagged > 0


@pytest.mark.parametrize("rule_id", Q_ALL)
def test_t13_assess_rule_never_exempt(q_pack: RulePack, rule_id: str) -> None:
    """C3b's assess_rule never produces reason EXEMPT."""
    for facts in assignments():
        assert assess_rule(rule_id, q_pack, facts).reason is not EXEMPT


# ---- T14: unknown subject kind ----------------------------------------------------------


def test_t14_unknown_subject_kind(pack: RulePack) -> None:
    """A subject kind that is not a node kind raises ResultError."""
    with pytest.raises(ResultError, match="test_kind"):
        assess_subject("test-subject-1", "test_kind", pack, {}, as_of=TODAY)


# ---- T15: determinism and purity --------------------------------------------------------


def test_t15_pure_and_deterministic(pack: RulePack) -> None:
    """Two calls give equal results; the facts mapping and pack are unchanged."""
    facts = {A: fact_of(T, "suspected"), B: fact_of(T), D: fact_of(F)}
    before_facts = copy.deepcopy(facts)
    before_pack = pack.model_dump()
    first = assess_subject("test-subject-1", "model", pack, facts, as_of=TODAY)
    second = assess_subject("test-subject-1", "model", pack, facts, as_of=TODAY)
    assert first == second
    assert facts == before_facts
    assert pack.model_dump() == before_pack


# ---- RuleOutcome rejects EXEMPT (outcomes.py) -------------------------------------------

FALSE_EVALUATION = RuleEvaluation(
    rule_id="TEST-ONE",
    binding=None,
    bound=T,
    trigger=ExprResult(value=F, leaves=()),
    value=F,
)


def test_rule_outcome_accepts_test_not_met() -> None:
    """Control: the same RuleOutcome with TEST_NOT_MET is valid."""
    result = RuleOutcome(
        rule_id="TEST-ONE", outcome=DOES_NOT_APPLY, reason=TEST_NOT_MET, evaluation=FALSE_EVALUATION
    )
    assert result.reason is TEST_NOT_MET


def test_rule_outcome_rejects_exempt() -> None:
    """EXEMPT exists only at the C3c layer; a C3b RuleOutcome refuses it."""
    with pytest.raises(ValidationError):
        RuleOutcome(
            rule_id="TEST-ONE", outcome=DOES_NOT_APPLY, reason=EXEMPT, evaluation=FALSE_EVALUATION
        )


# ---- Validators: ClockNote, ExemptionResult, RuleResult ---------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": ClockStatus.APPLIES, "readings": ("reading_a",), "note": NOTE},
        {"status": ClockStatus.UNDER_READINGS, "readings": (), "note": NOTE},
        {
            "status": ClockStatus.UNDER_READINGS,
            "readings": ("reading_b", "reading_a"),
            "note": NOTE,
        },
        {"status": ClockStatus.APPLIES, "readings": (), "note": "Start date is 30 days on."},
    ],
    ids=["readings-without-under-readings", "under-readings-empty", "unsorted", "wrong-note"],
)
def test_clock_note_rejects(kwargs: dict[str, Any]) -> None:
    """readings only and always with UNDER_READINGS, sorted; the note text is fixed."""
    with pytest.raises(ValidationError):
        ClockNote(amount=30, unit="calendar_days", trigger="Test event occurs.", **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"outcome": APPLIES, "applied": False, "unresolved": False},
        {"outcome": APPLIES, "applied": True, "unresolved": True},
        {"outcome": CONDITIONAL, "applied": True, "unresolved": False},
        {"outcome": CONDITIONAL, "applied": False, "unresolved": False},
        {"outcome": DOES_NOT_APPLY, "applied": False, "unresolved": True},
        {"outcome": DOES_NOT_APPLY, "applied": True, "unresolved": False},
        {
            "outcome": DOES_NOT_APPLY,
            "applied": False,
            "unresolved": False,
            "questions": (missing(B),),
        },
        {
            "outcome": INSUFFICIENT,
            "applied": False,
            "unresolved": True,
            "questions": (missing(C), missing(B)),
        },
        {
            "outcome": CONDITIONAL,
            "applied": False,
            "unresolved": True,
            "facts_to_confirm": (C, B),
        },
    ],
    ids=[
        "applies-neither-flag",
        "applies-both-flags",
        "conditional-applied",
        "conditional-not-flagged",
        "does-not-apply-flagged",
        "does-not-apply-applied",
        "questions-when-not-unresolved",
        "unsorted-questions",
        "unsorted-confirm",
    ],
)
def test_exemption_result_rejects(kwargs: dict[str, Any]) -> None:
    """applied and unresolved follow D6/D6a; details only when unresolved, sorted."""
    with pytest.raises(ValidationError):
        ExemptionResult(**{"rule_id": "TEST-E1", "questions": (), "facts_to_confirm": (), **kwargs})


def rebuilt(result: RuleResult, changes: dict[str, Any]) -> RuleResult:
    """Validate a RuleResult again with some fields changed."""
    return RuleResult.model_validate({**dict(result), **changes})


def test_rule_result_rebuild_accepts_unchanged(pack: RulePack) -> None:
    """Control: rebuilding a real result with no changes is valid."""
    result = assess_rule_final("TEST-R", pack, {A: fact_of(T), B: fact_of(T)}, as_of=TODAY)
    assert rebuilt(result, {}) == result


@pytest.mark.parametrize(
    ("rule_id", "facts", "changes"),
    [
        ("TEST-R", {A: fact_of(T), B: fact_of(T)}, {"exempted_by": ()}),
        ("TEST-R", {A: fact_of(T), B: fact_of(T)}, {"exempted_by": ("TEST-E2",)}),
        ("TEST-R", {A: fact_of(T), B: fact_of(T)}, {"direction": IF_APPLIES}),
        (
            "TEST-R",
            {A: fact_of(T), B: fact_of(T)},
            {"clock": clock_note(ClockStatus.APPLIES)},
        ),
        ("TEST-R", {A: fact_of(T), B: fact_of(F)}, {"exempted_by": ("TEST-E1",)}),
        (
            "TEST-R",
            {A: fact_of(T), B: fact_of(F)},
            {"outcome": CONDITIONAL, "direction": IF_APPLIES},
        ),
        (
            "TEST-R",
            {A: fact_of(T), B: fact_of(F)},
            {"exemptions": (ex("TEST-E1", APPLIES, applied=True),)},
        ),
        ("TEST-K", {A: fact_of(T)}, {"clock": clock_note(ClockStatus.IF_CONFIRMED)}),
        (
            "TEST-KS",
            {A: fact_of(T), D: fact_of(F)},
            {"clock": clock_note(ClockStatus.UNDER_READINGS, ("reading_b",), CLOCK_72)},
        ),
        (
            "TEST-R2",
            {A: fact_of(T), B: fact_of(T), C: fact_of(F)},
            {"exemptions": (ex("TEST-E2", DOES_NOT_APPLY), ex("TEST-E1", APPLIES, applied=True))},
        ),
        (
            "TEST-R",
            {A: fact_of(F), B: fact_of(T)},
            {"exemptions": (ex("TEST-E1", DOES_NOT_APPLY),)},
        ),
    ],
    ids=[
        "exempt-without-exempted-by",
        "exempted-by-not-applied",
        "exempt-with-direction",
        "exempt-with-clock",
        "exempted-by-without-exempt",
        "outcome-differs-from-base",
        "applied-exemption-not-exempt",
        "clock-status-mismatch",
        "clock-reading-not-qualifying",
        "unsorted-exemptions",
        "exemptions-on-does-not-apply-base",
    ],
)
def test_rule_result_rejects(
    pack: RulePack, rule_id: str, facts: dict[str, Fact], changes: dict[str, Any]
) -> None:
    """RuleResult refuses field combinations that D6, D6a and D7 rule out."""
    result = assess_rule_final(rule_id, pack, facts, as_of=TODAY)
    with pytest.raises(ValidationError):
        rebuilt(result, changes)


def test_regime_result_rejects_unsorted_rules(tmp_path: Path) -> None:
    """RegimeResult rules are sorted by id."""
    regime_pack = write_pack(tmp_path, [rule_dict("TEST-G1", f_(A)), rule_dict("TEST-G2", f_(A))])
    result = assess_subject("test-subject-1", "model", regime_pack, {A: fact_of(T)}, as_of=TODAY)
    g1, g2 = result.regimes[0].rules
    with pytest.raises(ValidationError):
        RegimeResult(regime="TEST", rules=(g2, g1), conflict=None)
