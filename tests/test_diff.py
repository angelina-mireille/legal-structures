"""Tests for src/core/diff.py: the diff engine (C4, decisions D14-D16, D18).

Every rule and fact here is synthetic (regimes TEST and TEST-B, example.org URLs,
"test." fact names). Expected values are written out literally from the C3b-C3d
rules, never computed by the code under test. The changed facts a rule lists are
facts it refers to; nothing here says they caused a change.
"""

import copy
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from core.diff import (
    ChangedFact,
    DiffError,
    FactRead,
    RuleChange,
    SubjectDiff,
    _compare_rule,
    diff_subjects,
)
from core.evaluator import Fact, TriValue
from core.outcomes import Direction, Outcome, Question, QuestionKind, Reason
from core.results import ExemptionResult, SubjectResult, assess_rule_final
from core.rules import RulePack, load_rule_pack

TODAY = date(2026, 11, 24)
LAST_VERIFIED = date(2026, 11, 1)
AS_OF = date(2026, 6, 1)
EFFECTIVE_FROM = date(2026, 1, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64
SUBJECT = "TEST-SUBJ-001"
KIND = "model"

T = TriValue.TRUE
F = TriValue.FALSE
U = TriValue.UNKNOWN

A, B, G, D, E = "test.alpha", "test.beta", "test.gamma", "test.delta", "test.epsilon"

APPLIES = Outcome.APPLIES
DOES_NOT_APPLY = Outcome.DOES_NOT_APPLY
INSUFFICIENT = Outcome.INSUFFICIENT_FACTS
UNSETTLED = Outcome.UNSETTLED

TEST_NOT_MET = Reason.TEST_NOT_MET
NOT_BOUND = Reason.NOT_BOUND
EXEMPT = Reason.EXEMPT

CLOCK_30 = {"amount": 30, "unit": "calendar_days", "trigger": "Test event occurs."}

Final3 = tuple[Outcome, Reason | None, Direction | None]


# ---- Helpers (local copies of tests/test_results.py helpers, extended) ---------------


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


def readings(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Two interpretations, reading_a and reading_b, with the given triggers."""
    return [
        {"id": "reading_a", "summary": "Test reading A.", "trigger": a},
        {"id": "reading_b", "summary": "Test reading B.", "trigger": b},
    ]


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
    effect: str = "TEST_EFFECT",
    effective: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A minimal synthetic TEST- rule as a dict, with effect and effective parameters."""
    rule: dict[str, Any] = {
        "id": rule_id,
        "version": "1.0.0",
        "regime": regime,
        "title": "Synthetic diff test rule",
        "law_status": law_status,
        "applies_to": applies_to,
        "binding": binding,
        "effect": effect,
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
        "effective": (
            effective
            if effective is not None
            else {"from": EFFECTIVE_FROM, "basis": "synthetic test fixture"}
        ),
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


def read(rule_id: str, via: str, interpretation_id: str | None = None) -> FactRead:
    """An expected FactRead."""
    return FactRead(rule_id=rule_id, via=via, interpretation_id=interpretation_id)


def changed(fact: str, before: Fact | None, after: Fact | None, *reads: FactRead) -> ChangedFact:
    """An expected ChangedFact."""
    return ChangedFact(fact=fact, before=before, after=after, reads=reads)


def change(rule_id: str, fields: tuple[str, ...], *facts: ChangedFact) -> RuleChange:
    """An expected RuleChange."""
    return RuleChange(rule_id=rule_id, changed_fields=fields, changed_facts=facts)


def missing(name: str) -> Question:
    """A MISSING question for name."""
    return Question(fact=name, kind=QuestionKind.MISSING, current_grade=None, required_grade=None)


def empty_result(subject_id: str = SUBJECT, subject_kind: str = KIND) -> SubjectResult:
    """A SubjectResult with no regimes, for model tests."""
    return SubjectResult(subject_id=subject_id, subject_kind=subject_kind, as_of=AS_OF, regimes=())


def finals(result: SubjectResult) -> dict[str, Final3]:
    """Each assessed rule's final (outcome, reason, direction), by rule id."""
    return {
        r.rule_id: (r.outcome, r.reason, r.direction)
        for regime in result.regimes
        for r in regime.rules
    }


# ---- The ten pairs ----------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    """One hand-made fact pair at AS_OF, with every expected diff field written out."""

    rules: list[dict[str, Any]]
    before: dict[str, Fact]
    after: dict[str, Fact]
    flips: tuple[RuleChange, ...] = ()
    details: tuple[RuleChange, ...] = ()
    unchanged: tuple[str, ...] = ()
    finals_before: dict[str, Final3] = field(default_factory=dict)
    finals_after: dict[str, Final3] = field(default_factory=dict)


CASES: dict[str, Case] = {
    # P1 one trigger fact: APPLIES to DOES_NOT_APPLY / TEST_NOT_MET. The clock note goes.
    "P1": Case(
        rules=[rule_dict("TEST-P1-001", f_(A), clock=CLOCK_30)],
        before={A: fact_of(T)},
        after={A: fact_of(F)},
        flips=(
            change(
                "TEST-P1-001",
                ("base", "clock"),
                changed(A, fact_of(T), fact_of(F), read("TEST-P1-001", "self")),
            ),
        ),
        finals_before={"TEST-P1-001": (APPLIES, None, None)},
        finals_after={"TEST-P1-001": (DOES_NOT_APPLY, TEST_NOT_MET, None)},
    ),
    # P2 two facts change (alpha, epsilon); epsilon is referred to by no rule and
    # appears nowhere in the diff. Decisive facts go from [alpha, beta] to [alpha].
    "P2": Case(
        rules=[rule_dict("TEST-P2-001", all_(f_(A), f_(B)))],
        before={A: fact_of(T), B: fact_of(T), E: fact_of(T)},
        after={A: fact_of(F), B: fact_of(T), E: fact_of(F)},
        flips=(
            change(
                "TEST-P2-001",
                ("base", "decisive_facts"),
                changed(A, fact_of(T), fact_of(F), read("TEST-P2-001", "self")),
            ),
        ),
        finals_before={"TEST-P2-001": (APPLIES, None, None)},
        finals_after={"TEST-P2-001": (DOES_NOT_APPLY, TEST_NOT_MET, None)},
    ),
    # P3 grade only: TRUE verified drops to TRUE declared, below min_grade documented.
    # By C3b D3 step 4 the leaf is UNKNOWN, so INSUFFICIENT_FACTS with a
    # NEEDS_STRONGER_EVIDENCE question.
    "P3": Case(
        rules=[rule_dict("TEST-P3-001", f_(A, "documented"))],
        before={A: fact_of(T, "verified")},
        after={A: fact_of(T, "declared")},
        flips=(
            change(
                "TEST-P3-001",
                ("base", "decisive_facts", "questions"),
                changed(
                    A, fact_of(T, "verified"), fact_of(T, "declared"), read("TEST-P3-001", "self")
                ),
            ),
        ),
        finals_before={"TEST-P3-001": (APPLIES, None, None)},
        finals_after={"TEST-P3-001": (INSUFFICIENT, None, None)},
    ),
    # P4 absent versus UNKNOWN for the same fact (beta): not a change, empty diff.
    "P4": Case(
        rules=[rule_dict("TEST-P4-001", all_(f_(A), f_(B)))],
        before={A: fact_of(T)},
        after={A: fact_of(T), B: fact_of(U)},
        finals_before={"TEST-P4-001": (INSUFFICIENT, None, None)},
        finals_after={"TEST-P4-001": (INSUFFICIENT, None, None)},
    ),
    # P5 binding fact: APPLIES to DOES_NOT_APPLY / NOT_BOUND, read via "binding".
    "P5": Case(
        rules=[
            rule_dict("TEST-P5-001", f_(A), binding="TEST-P5-BIND-001"),
            rule_dict("TEST-P5-BIND-001", f_(B)),
        ],
        before={A: fact_of(T), B: fact_of(T)},
        after={A: fact_of(T), B: fact_of(F)},
        flips=(
            change(
                "TEST-P5-001",
                ("base", "decisive_facts"),
                changed(B, fact_of(T), fact_of(F), read("TEST-P5-BIND-001", "binding")),
            ),
        ),
        finals_before={"TEST-P5-001": (APPLIES, None, None)},
        finals_after={"TEST-P5-001": (DOES_NOT_APPLY, NOT_BOUND, None)},
    ),
    # P6 exemption fact: APPLIES to DOES_NOT_APPLY / EXEMPT, read via "unless".
    # The base stays APPLIES on both sides.
    "P6": Case(
        rules=[
            rule_dict("TEST-P6-001", f_(A), unless=["TEST-P6-EX-001"]),
            rule_dict("TEST-P6-EX-001", f_(B)),
        ],
        before={A: fact_of(T), B: fact_of(F)},
        after={A: fact_of(T), B: fact_of(T)},
        flips=(
            change(
                "TEST-P6-001",
                ("exempted_by", "exemptions"),
                changed(B, fact_of(F), fact_of(T), read("TEST-P6-EX-001", "unless")),
            ),
        ),
        finals_before={"TEST-P6-001": (APPLIES, None, None)},
        finals_after={"TEST-P6-001": (DOES_NOT_APPLY, EXEMPT, None)},
    ),
    # P7 a sub-exemption (carve-back) fact under D6a: gamma FALSE to absent makes the
    # carve-back INSUFFICIENT_FACTS, so the exemption is unresolved and the rule goes
    # from EXEMPT to APPLIES. The FactRead names the carve-back, via "unless".
    "P7": Case(
        rules=[
            rule_dict("TEST-P7-001", f_(A), unless=["TEST-P7-EX-001"]),
            rule_dict("TEST-P7-EX-001", f_(B), unless=["TEST-P7-CB-001"]),
            rule_dict("TEST-P7-CB-001", f_(G)),
        ],
        before={A: fact_of(T), B: fact_of(T), G: fact_of(F)},
        after={A: fact_of(T), B: fact_of(T)},
        flips=(
            change(
                "TEST-P7-001",
                ("exempted_by", "exemptions"),
                changed(G, fact_of(F), None, read("TEST-P7-CB-001", "unless")),
            ),
        ),
        finals_before={"TEST-P7-001": (DOES_NOT_APPLY, EXEMPT, None)},
        finals_after={"TEST-P7-001": (APPLIES, None, None)},
    ),
    # P8 one reading's fact: agreed APPLIES to UNSETTLED; the FactRead carries reading_b.
    "P8": Case(
        rules=[rule_dict("TEST-P8-001", interpretations=readings(f_(A), all_(f_(A), f_(B))))],
        before={A: fact_of(T), B: fact_of(T)},
        after={A: fact_of(T), B: fact_of(F)},
        flips=(
            change(
                "TEST-P8-001",
                ("base", "decisive_facts", "readings"),
                changed(B, fact_of(T), fact_of(F), read("TEST-P8-001", "self", "reading_b")),
            ),
        ),
        finals_before={"TEST-P8-001": (APPLIES, None, None)},
        finals_after={"TEST-P8-001": (UNSETTLED, None, None)},
    ),
    # P9 detail only: still INSUFFICIENT_FACTS, but the questions go from
    # [alpha, beta] to [beta]. A detail change, not a flip.
    "P9": Case(
        rules=[rule_dict("TEST-P9-001", all_(f_(A), f_(B)))],
        before={},
        after={A: fact_of(T)},
        details=(
            change(
                "TEST-P9-001",
                ("questions",),
                changed(A, None, fact_of(T), read("TEST-P9-001", "self")),
            ),
        ),
        finals_before={"TEST-P9-001": (INSUFFICIENT, None, None)},
        finals_after={"TEST-P9-001": (INSUFFICIENT, None, None)},
    ),
    # P10 overdetermined: any(alpha, beta, gamma) all TRUE, alpha turns FALSE. Decisive
    # facts stay empty on both sides (C3b D2), so no change; the rule refers to a changed
    # fact and is in unchanged_despite_changes. The TEST-B rule refers to no changed fact
    # and appears in no diff field. (any(alpha, beta) would be a decisive_facts change.)
    "P10": Case(
        rules=[
            rule_dict("TEST-P10-001", any_(f_(A), f_(B), f_(G))),
            rule_dict("TEST-P10-B-001", f_(D), regime="TEST-B"),
        ],
        before={A: fact_of(T), B: fact_of(T), G: fact_of(T), D: fact_of(T)},
        after={A: fact_of(F), B: fact_of(T), G: fact_of(T), D: fact_of(T)},
        unchanged=("TEST-P10-001",),
        finals_before={
            "TEST-P10-001": (APPLIES, None, None),
            "TEST-P10-B-001": (APPLIES, None, None),
        },
        finals_after={
            "TEST-P10-001": (APPLIES, None, None),
            "TEST-P10-B-001": (APPLIES, None, None),
        },
    ),
}


def run(case: Case, tmp_path: Path, *, swap: bool = False) -> SubjectDiff:
    """Write the case's pack and diff its facts at AS_OF (sides swapped if asked)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    pack = write_pack(tmp_path, case.rules)
    before, after = (case.after, case.before) if swap else (case.before, case.after)
    return diff_subjects(SUBJECT, KIND, pack, before, after, as_of_before=AS_OF, as_of_after=AS_OF)


def changes_json(diff: SubjectDiff) -> str:
    """The diff's own fields as JSON, without the two carried SubjectResults."""
    return diff.model_dump_json(exclude={"before", "after"})


@pytest.mark.parametrize("name", list(CASES))
def test_pairs(name: str, tmp_path: Path) -> None:
    """The done-when test: exactly the expected flips, details and changed facts."""
    case = CASES[name]
    diff = run(case, tmp_path)
    assert diff.flips == case.flips
    assert diff.detail_changes == case.details
    assert diff.unchanged_despite_changes == case.unchanged
    assert diff.entered_effect == ()
    assert diff.left_effect == ()
    assert finals(diff.before) == case.finals_before
    assert finals(diff.after) == case.finals_after


def test_p2_unreferenced_fact_nowhere(tmp_path: Path) -> None:
    """P2: epsilon changes but no rule refers to it; it is absent from the whole diff."""
    diff = run(CASES["P2"], tmp_path)
    assert E not in diff.model_dump_json()


def test_p3_after_question(tmp_path: Path) -> None:
    """P3: the after side asks for stronger evidence, declared up to documented."""
    diff = run(CASES["P3"], tmp_path)
    rule = diff.after.regimes[0].rules[0]
    assert rule.base.questions == (
        Question(
            fact=A,
            kind=QuestionKind.NEEDS_STRONGER_EVIDENCE,
            current_grade="declared",
            required_grade="documented",
        ),
    )


def test_p7_exemption_unresolved(tmp_path: Path) -> None:
    """P7: after the change the exemption is APPLIES, not applied, and unresolved (D6a)."""
    diff = run(CASES["P7"], tmp_path)
    rule = diff.after.regimes[0].rules[0]
    assert rule.exemptions == (
        ExemptionResult(
            rule_id="TEST-P7-EX-001",
            outcome=APPLIES,
            applied=False,
            unresolved=True,
            questions=(missing(G),),
        ),
    )


def test_p10_test_b_rule_in_no_diff_field(tmp_path: Path) -> None:
    """P10: the TEST-B rule is in the carried results but in no field of the diff itself."""
    diff = run(CASES["P10"], tmp_path)
    assert "TEST-P10-B-001" not in changes_json(diff)
    assert "TEST-P10-B-001" in finals(diff.before)


# ---- Beyond P1-P10 ----------------------------------------------------------------------


def test_base_change_under_exemption(tmp_path: Path) -> None:
    """An exemption applies on both sides; alpha going absent moves the base from
    APPLIES to INSUFFICIENT_FACTS (exemptions are still evaluated, D6). The final result
    stays DOES_NOT_APPLY / EXEMPT: no flip, a detail change that includes "base"."""
    rules = [
        rule_dict("TEST-BX-001", f_(A), unless=["TEST-BX-EX-001"]),
        rule_dict("TEST-BX-EX-001", f_(B)),
    ]
    case = Case(rules=rules, before={A: fact_of(T), B: fact_of(T)}, after={B: fact_of(T)})
    diff = run(case, tmp_path)
    assert diff.flips == ()
    assert diff.detail_changes == (
        change(
            "TEST-BX-001",
            ("base", "decisive_facts", "questions"),
            changed(A, fact_of(T), None, read("TEST-BX-001", "self")),
        ),
    )
    assert diff.unchanged_despite_changes == ()
    assert finals(diff.before) == {"TEST-BX-001": (DOES_NOT_APPLY, EXEMPT, None)}
    assert finals(diff.after) == {"TEST-BX-001": (DOES_NOT_APPLY, EXEMPT, None)}
    assert diff.before.regimes[0].rules[0].base.outcome == APPLIES
    assert diff.after.regimes[0].rules[0].base.outcome == INSUFFICIENT


def test_grade_only_no_effect(tmp_path: Path) -> None:
    """alpha TRUE verified to TRUE documented, no min_grade: a changed fact, no change."""
    case = Case(
        rules=[rule_dict("TEST-GR-001", f_(A))],
        before={A: fact_of(T, "verified")},
        after={A: fact_of(T, "documented")},
    )
    diff = run(case, tmp_path)
    assert diff.flips == ()
    assert diff.detail_changes == ()
    assert diff.unchanged_despite_changes == ("TEST-GR-001",)


def test_exemption_questions_change(tmp_path: Path) -> None:
    """The exemption all(beta, gamma) is INSUFFICIENT_FACTS, so unresolved, on both
    sides (D6); the rule stays APPLIES. beta going from absent to TRUE narrows the
    exemption's questions from [beta, gamma] to [gamma]: a detail change in
    "exemptions", not unchanged_despite_changes."""
    rules = [
        rule_dict("TEST-EQ-001", f_(A), unless=["TEST-EQ-EX-001"]),
        rule_dict("TEST-EQ-EX-001", all_(f_(B), f_(G))),
    ]
    case = Case(rules=rules, before={A: fact_of(T)}, after={A: fact_of(T), B: fact_of(T)})
    diff = run(case, tmp_path)
    assert diff.flips == ()
    assert diff.detail_changes == (
        change(
            "TEST-EQ-001",
            ("exemptions",),
            changed(B, None, fact_of(T), read("TEST-EQ-EX-001", "unless")),
        ),
    )
    assert diff.unchanged_despite_changes == ()
    assert finals(diff.before) == {"TEST-EQ-001": (APPLIES, None, None)}
    assert finals(diff.after) == {"TEST-EQ-001": (APPLIES, None, None)}
    assert diff.before.regimes[0].rules[0].exemptions == (
        ExemptionResult(
            rule_id="TEST-EQ-EX-001",
            outcome=INSUFFICIENT,
            applied=False,
            unresolved=True,
            questions=(missing(B), missing(G)),
        ),
    )
    assert diff.after.regimes[0].rules[0].exemptions == (
        ExemptionResult(
            rule_id="TEST-EQ-EX-001",
            outcome=INSUFFICIENT,
            applied=False,
            unresolved=True,
            questions=(missing(G),),
        ),
    )


# ---- 2 Dates ----------------------------------------------------------------------------

DATE_1 = date(2026, 3, 1)
DATE_2 = date(2026, 9, 1)
SWITCH = date(2026, 6, 1)


def test_dates(tmp_path: Path) -> None:
    """Same facts at two dates: one rule enters, one leaves, one only loses the flag."""
    basis = "synthetic test fixture"
    rules = [
        rule_dict("TEST-DATE-ENTER-001", f_(A), effective={"from": SWITCH, "basis": basis}),
        rule_dict(
            "TEST-DATE-LEAVE-001",
            f_(A),
            effective={"from": EFFECTIVE_FROM, "to": SWITCH, "basis": basis},
        ),
        rule_dict(
            "TEST-DATE-PUB-001",
            f_(A),
            effective={"from": EFFECTIVE_FROM, "published": SWITCH, "basis": basis},
        ),
    ]
    pack = write_pack(tmp_path, rules)
    facts = {A: fact_of(T)}
    diff = diff_subjects(SUBJECT, KIND, pack, facts, facts, as_of_before=DATE_1, as_of_after=DATE_2)
    assert diff.entered_effect == ("TEST-DATE-ENTER-001",)
    assert diff.left_effect == ("TEST-DATE-LEAVE-001",)
    assert diff.flips == ()
    assert diff.detail_changes == (change("TEST-DATE-PUB-001", ("in_force_unpublished",)),)
    assert diff.unchanged_despite_changes == ()


# ---- 3 Symmetry -------------------------------------------------------------------------


def swapped(rc: RuleChange) -> RuleChange:
    """The expected RuleChange with before and after swapped in every changed fact."""
    facts = tuple(
        ChangedFact(fact=c.fact, before=c.after, after=c.before, reads=c.reads)
        for c in rc.changed_facts
    )
    return RuleChange(rule_id=rc.rule_id, changed_fields=rc.changed_fields, changed_facts=facts)


@pytest.mark.parametrize("name", list(CASES))
def test_symmetry(name: str, tmp_path: Path) -> None:
    """Swapping the sides swaps before and after and keeps the same names."""
    case = CASES[name]
    forward = run(case, tmp_path / "forward")
    reverse = run(case, tmp_path / "reverse", swap=True)
    assert reverse.flips == tuple(swapped(rc) for rc in case.flips)
    assert reverse.detail_changes == tuple(swapped(rc) for rc in case.details)
    assert reverse.unchanged_despite_changes == case.unchanged
    assert reverse.before == forward.after
    assert reverse.after == forward.before


# ---- 4 Purity ---------------------------------------------------------------------------


def test_pure(tmp_path: Path) -> None:
    """The facts mappings are unchanged, and the same call twice gives equal diffs."""
    case = CASES["P7"]
    pack = write_pack(tmp_path, case.rules)
    before, after = copy.deepcopy(case.before), copy.deepcopy(case.after)
    first = diff_subjects(SUBJECT, KIND, pack, before, after, as_of_before=AS_OF, as_of_after=AS_OF)
    second = diff_subjects(
        SUBJECT, KIND, pack, before, after, as_of_before=AS_OF, as_of_after=AS_OF
    )
    assert before == case.before
    assert after == case.after
    assert first == second


# ---- 5 The DiffError guard --------------------------------------------------------------


@pytest.fixture(scope="module")
def guard_pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """Rules for the guard tests, assessed outside diff_subjects."""
    basis = "synthetic test fixture"
    return write_pack(
        tmp_path_factory.mktemp("guard"),
        [
            rule_dict("TEST-G-001", f_(A)),
            rule_dict("TEST-G-002", all_(f_(A), f_(B))),
            rule_dict(
                "TEST-G-PUB-001",
                f_(A),
                effective={"from": EFFECTIVE_FROM, "published": SWITCH, "basis": basis},
            ),
        ],
    )


def test_guard_flip_without_changed_fact(guard_pack: RulePack) -> None:
    """A flip that refers to no changed fact is a bug: DiffError."""
    before = assess_rule_final("TEST-G-001", guard_pack, {A: fact_of(T)}, as_of=AS_OF)
    after = assess_rule_final("TEST-G-001", guard_pack, {A: fact_of(F)}, as_of=AS_OF)
    with pytest.raises(DiffError):
        _compare_rule(before, after, ())


def test_guard_detail_without_changed_fact(guard_pack: RulePack) -> None:
    """A questions-only detail change that refers to no changed fact: DiffError."""
    before = assess_rule_final("TEST-G-002", guard_pack, {}, as_of=AS_OF)
    after = assess_rule_final("TEST-G-002", guard_pack, {A: fact_of(T)}, as_of=AS_OF)
    with pytest.raises(DiffError):
        _compare_rule(before, after, ())


def test_guard_allows_unpublished_only(guard_pack: RulePack) -> None:
    """A detail change in in_force_unpublished alone can come from the dates: no error."""
    facts = {A: fact_of(T)}
    before = assess_rule_final("TEST-G-PUB-001", guard_pack, facts, as_of=DATE_1)
    after = assess_rule_final("TEST-G-PUB-001", guard_pack, facts, as_of=DATE_2)
    assert _compare_rule(before, after, ()) == (
        "detail",
        change("TEST-G-PUB-001", ("in_force_unpublished",)),
    )


# ---- 6 as_of type -----------------------------------------------------------------------


@pytest.mark.parametrize("side", ["before", "after"])
def test_datetime_as_of(side: str, tmp_path: Path) -> None:
    """A datetime for either as_of raises TypeError, as in assess_subject."""
    pack = write_pack(tmp_path, CASES["P1"].rules)
    moment = datetime(2026, 6, 1, 12, 0)
    dates = {"as_of_before": AS_OF, "as_of_after": AS_OF, f"as_of_{side}": moment}
    with pytest.raises(TypeError):
        diff_subjects(SUBJECT, KIND, pack, {}, {}, **dates)


# ---- 7 Models ---------------------------------------------------------------------------

X = "TEST-X-001"
Y = "TEST-Y-001"


def subject_diff(**changes: Any) -> SubjectDiff:
    """A SubjectDiff with empty results and no changes, with some fields replaced."""
    kwargs: dict[str, Any] = {
        "before": empty_result(),
        "after": empty_result(),
        "flips": (),
        "detail_changes": (),
        "entered_effect": (),
        "left_effect": (),
        "unchanged_despite_changes": (),
    }
    return SubjectDiff(**{**kwargs, **changes})


def test_valid_models_accepted() -> None:
    """Sorted input is accepted, including a FactRead with no reading before one with."""
    changed(A, None, fact_of(T), read(X, "self"), read(X, "self", "reading_a"), read(Y, "binding"))
    change(X, ("base", "questions"), changed(A, None, fact_of(T)), changed(B, None, fact_of(T)))
    subject_diff(flips=(change(X, ()), change(Y, ())), entered_effect=(X, Y))


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: changed(A, None, None, read(Y, "self"), read(X, "self")), id="reads"),
        pytest.param(
            lambda: changed(A, None, None, read(X, "self", "reading_a"), read(X, "self")),
            id="reads_none_first",
        ),
        pytest.param(lambda: changed(A, None, None, read(X, "self"), read(X, "self")), id="repeat"),
        pytest.param(lambda: change(X, ("questions", "base")), id="changed_fields"),
        pytest.param(
            lambda: change(X, (), changed(B, None, None), changed(A, None, None)),
            id="changed_facts",
        ),
        pytest.param(lambda: subject_diff(flips=(change(Y, ()), change(X, ()))), id="flips"),
        pytest.param(
            lambda: subject_diff(detail_changes=(change(Y, ()), change(X, ()))), id="details"
        ),
        pytest.param(lambda: subject_diff(entered_effect=(Y, X)), id="entered"),
        pytest.param(lambda: subject_diff(left_effect=(Y, X)), id="left"),
        pytest.param(lambda: subject_diff(unchanged_despite_changes=(Y, X)), id="unchanged"),
    ],
)
def test_unsorted_rejected(build: Any) -> None:
    """Every tuple must be sorted with no repeats."""
    with pytest.raises(ValidationError):
        build()


@pytest.mark.parametrize(
    "after",
    [
        pytest.param(empty_result(subject_id="TEST-SUBJ-002"), id="subject_id"),
        pytest.param(empty_result(subject_kind="entity"), id="subject_kind"),
    ],
)
def test_subject_mismatch_rejected(after: SubjectResult) -> None:
    """D18 (amended): both results must be for the same subject id and kind."""
    with pytest.raises(ValidationError):
        subject_diff(after=after)


@pytest.mark.parametrize("name", list(CASES))
def test_round_trip(name: str, tmp_path: Path) -> None:
    """A SubjectDiff survives a JSON round trip."""
    diff = run(CASES[name], tmp_path)
    assert SubjectDiff.model_validate_json(diff.model_dump_json()) == diff
