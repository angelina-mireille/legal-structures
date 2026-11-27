"""Tests for C3d: effective dates and as-of evaluation (D9-D13).

Every rule and fact here is synthetic (regime TEST, example.org URLs, "test." fact
names, invented dates). Expected values are written out literally, never computed by
the code under test.
"""

import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.evaluator import Fact, TriValue
from core.outcomes import Direction, Outcome, Reason
from core.results import ResultError, SubjectResult, assess_rule_final, assess_subject
from core.rules import RuleError, RulePack, load_rule_pack

TODAY = date(2026, 11, 25)
LAST_VERIFIED = date(2026, 11, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64

T = TriValue.TRUE
F = TriValue.FALSE
U = TriValue.UNKNOWN

A, B, C, D = "test.alpha", "test.beta", "test.gamma", "test.delta"

FROM = date(2026, 1, 1)
TO = date(2026, 7, 1)
PUBLISHED = date(2026, 3, 1)
BASIS = "synthetic test fixture"

IN_FORCE = {"from": FROM, "basis": BASIS}
WINDOW = {"from": FROM, "to": TO, "basis": BASIS}
UNPUBLISHED = {"from": FROM, "published": PUBLISHED, "basis": BASIS}


# ---- Helpers (pack writing copied from tests/test_results.py, with effective) -----------


def fact_of(value: TriValue, grade: str = "verified") -> Fact:
    """A Fact: TRUE/FALSE get the grade; UNKNOWN gets no grade."""
    if value is U:
        return Fact(value=U, grade=None)
    return Fact(value=value, grade=grade)


def f_(name: str) -> dict[str, Any]:
    """A fact leaf as a rule-file dict."""
    return {"fact": name}


def readings(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Two interpretations, reading_a and reading_b, with the given triggers."""
    return [
        {"id": "reading_a", "summary": "Test reading A.", "trigger": a},
        {"id": "reading_b", "summary": "Test reading B.", "trigger": b},
    ]


def rule_dict(
    rule_id: str,
    trigger: dict[str, Any] | None = None,
    effective: dict[str, Any] | None = IN_FORCE,
    binding: str | None = None,
    interpretations: list[dict[str, Any]] | None = None,
    unless: list[str] | None = None,
    law_status: str = "in_force",
) -> dict[str, Any]:
    """A minimal synthetic TEST- rule as a dict; effective=None leaves the block out."""
    rule: dict[str, Any] = {
        "id": rule_id,
        "version": "1.0.0",
        "regime": "TEST",
        "title": "Synthetic effective-date test rule",
        "law_status": law_status,
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
    }
    if effective is not None:
        rule["effective"] = effective
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


def load_error(tmp_path: Path, rule: dict[str, Any]) -> str:
    """Write one rule, expect RuleError on load, and return its message."""
    with pytest.raises(RuleError) as caught:
        write_pack(tmp_path, [rule])
    return str(caught.value)


def rule_ids(result: SubjectResult) -> list[list[str]]:
    """The rule ids in each regime, in order."""
    return [[r.rule_id for r in regime.rules] for regime in result.regimes]


FACTS = {A: fact_of(T)}


@pytest.fixture(scope="module")
def window_pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """One always-in-force rule and one rule in force from FROM until TO."""
    return write_pack(
        tmp_path_factory.mktemp("window"),
        [
            rule_dict("TEST-W-ALWAYS", f_(A)),
            rule_dict("TEST-W-WINDOW", f_(A), effective=WINDOW),
        ],
    )


# ---- T1-T3: the effective window (from inclusive, to exclusive) --------------------------


def test_t1_day_before_from(window_pack: RulePack) -> None:
    """The day before from: neither rule is in effect; both are listed, sorted."""
    result = assess_subject("test-subject-1", "model", window_pack, FACTS, as_of=date(2025, 12, 31))
    assert rule_ids(result) == []
    assert result.not_in_effect == ("TEST-W-ALWAYS", "TEST-W-WINDOW")


def test_t2_on_from(window_pack: RulePack) -> None:
    """as_of equal to from: in effect (from is inclusive)."""
    result = assess_subject("test-subject-1", "model", window_pack, FACTS, as_of=date(2026, 1, 1))
    assert rule_ids(result) == [["TEST-W-ALWAYS", "TEST-W-WINDOW"]]
    assert result.not_in_effect == ()


@pytest.mark.parametrize("as_of", [date(2026, 7, 1), date(2026, 7, 2)], ids=["on-to", "after-to"])
def test_t3_on_or_after_to(window_pack: RulePack, as_of: date) -> None:
    """as_of equal to to, or after it: not in effect (to is exclusive)."""
    result = assess_subject("test-subject-1", "model", window_pack, FACTS, as_of=as_of)
    assert rule_ids(result) == [["TEST-W-ALWAYS"]]
    assert result.not_in_effect == ("TEST-W-WINDOW",)


def test_t3_day_before_to(window_pack: RulePack) -> None:
    """Control: the day before to is still in effect."""
    result = assess_subject("test-subject-1", "model", window_pack, FACTS, as_of=date(2026, 6, 30))
    assert rule_ids(result) == [["TEST-W-ALWAYS", "TEST-W-WINDOW"]]
    assert result.not_in_effect == ()


# ---- T4-T6: loader checks (D9) ----------------------------------------------------------


@pytest.mark.parametrize(
    "effective",
    [None, {"from": None, "basis": BASIS}, {"to": TO, "basis": BASIS}],
    ids=["block-omitted", "from-null", "only-to"],
)
def test_t4_in_force_without_from_fails(tmp_path: Path, effective: dict[str, Any] | None) -> None:
    """An in_force rule with no effective.from does not load."""
    message = load_error(tmp_path, rule_dict("TEST-NOFROM", f_(A), effective=effective))
    assert "TEST-NOFROM.yaml" in message
    assert "in_force rule needs effective.from" in message


@pytest.mark.parametrize(
    "to", [date(2026, 1, 1), date(2025, 12, 31)], ids=["from-equals-to", "from-after-to"]
)
def test_t5_from_on_or_after_to_fails(tmp_path: Path, to: date) -> None:
    """from on or after to does not load."""
    effective = {"from": FROM, "to": to, "basis": BASIS}
    message = load_error(tmp_path, rule_dict("TEST-BADWIN", f_(A), effective=effective))
    assert "TEST-BADWIN.yaml" in message
    assert "effective.from must be before effective.to" in message


@pytest.mark.parametrize("law_status", ["in_force", "proposed"])
def test_t6_from_without_basis_fails(tmp_path: Path, law_status: str) -> None:
    """from without basis does not load, whatever the law_status."""
    rule = rule_dict("TEST-NOBASIS", f_(A), effective={"from": FROM}, law_status=law_status)
    message = load_error(tmp_path, rule)
    assert "TEST-NOBASIS.yaml" in message
    assert "effective.from needs effective.basis" in message


# ---- T7: proposed rule with no from ----------------------------------------------------


@pytest.mark.parametrize("effective", [None, {"from": None}], ids=["block-omitted", "from-null"])
def test_t7_proposed_without_from_included(
    tmp_path: Path, effective: dict[str, Any] | None
) -> None:
    """A proposed rule with no from loads and is included with include_proposed=True."""
    pack = write_pack(
        tmp_path, [rule_dict("TEST-PROP", f_(A), effective=effective, law_status="proposed")]
    )
    result = assess_subject(
        "test-subject-1", "model", pack, FACTS, as_of=date(2026, 2, 1), include_proposed=True
    )
    assert rule_ids(result) == [["TEST-PROP"]]
    assert result.not_in_effect == ()
    assert result.excluded_proposed == ()


def test_t7_proposed_out_of_dates_listed_as_proposed(tmp_path: Path) -> None:
    """Settlement 2: proposed and out of dates, include_proposed=False: excluded_proposed only."""
    pack = write_pack(
        tmp_path,
        [rule_dict("TEST-PROP", f_(A), effective=WINDOW, law_status="proposed")],
    )
    result = assess_subject("test-subject-1", "model", pack, FACTS, as_of=date(2026, 8, 1))
    assert rule_ids(result) == []
    assert result.excluded_proposed == ("TEST-PROP",)
    assert result.not_in_effect == ()


# ---- T8: helper rules outside their dates ------------------------------------------------

HELPER_CASES = {
    "binding": [
        rule_dict("TEST-H-TOP", f_(A), binding="TEST-H-OLD"),
        rule_dict("TEST-H-OLD", f_(B), effective=WINDOW),
    ],
    "unless": [
        rule_dict("TEST-H-TOP", f_(A), unless=["TEST-H-OLD"]),
        rule_dict("TEST-H-OLD", f_(B), effective=WINDOW),
    ],
    "behind-helper": [
        rule_dict("TEST-H-TOP", f_(A), unless=["TEST-H-MID"]),
        rule_dict("TEST-H-MID", f_(C), binding="TEST-H-OLD"),
        rule_dict("TEST-H-OLD", f_(B), effective=WINDOW),
    ],
}

HELPER_FACTS = {A: fact_of(T), B: fact_of(T), C: fact_of(T)}


@pytest.mark.parametrize("case", list(HELPER_CASES))
def test_t8_helper_out_of_dates_raises(tmp_path: Path, case: str) -> None:
    """A helper outside its dates raises ResultError naming both rules, from both entry points."""
    pack = write_pack(tmp_path, HELPER_CASES[case])
    as_of = date(2026, 8, 1)
    with pytest.raises(ResultError, match="TEST-H-TOP") as caught:
        assess_subject("test-subject-1", "model", pack, HELPER_FACTS, as_of=as_of)
    assert "TEST-H-OLD" in str(caught.value)
    with pytest.raises(ResultError, match="TEST-H-TOP") as caught:
        assess_rule_final("TEST-H-TOP", pack, HELPER_FACTS, as_of=as_of)
    assert "TEST-H-OLD" in str(caught.value)


@pytest.mark.parametrize("case", list(HELPER_CASES))
def test_t8_helper_in_dates_is_fine(tmp_path: Path, case: str) -> None:
    """Control: the same packs inside the helper's window give a result."""
    pack = write_pack(tmp_path, HELPER_CASES[case])
    result = assess_subject("test-subject-1", "model", pack, HELPER_FACTS, as_of=date(2026, 2, 1))
    assert rule_ids(result) == [["TEST-H-TOP"]]


def test_t8b_static_check_raises_even_when_helper_not_reached(tmp_path: Path) -> None:
    """Settlement 3: a DOES_NOT_APPLY base never evaluates its exemption, yet the check fires."""
    pack = write_pack(tmp_path, HELPER_CASES["unless"])
    with pytest.raises(ResultError, match="TEST-H-OLD"):
        assess_rule_final("TEST-H-TOP", pack, {A: fact_of(F)}, as_of=date(2026, 8, 1))


@pytest.mark.parametrize(
    "as_of", [date(2025, 12, 31), date(2026, 7, 1)], ids=["before-from", "on-to"]
)
def test_t8c_assess_rule_final_out_of_dates_raises(window_pack: RulePack, as_of: date) -> None:
    """Settlement 1: assess_rule_final on a rule outside its dates names the rule and as_of."""
    with pytest.raises(ResultError, match="TEST-W-WINDOW") as caught:
        assess_rule_final("TEST-W-WINDOW", window_pack, FACTS, as_of=as_of)
    assert as_of.isoformat() in str(caught.value)


# ---- T9: in force but unpublished (D12) --------------------------------------------------


@pytest.fixture(scope="module")
def published_pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """A rule with a published date after from, one with none, and a proposed one."""
    return write_pack(
        tmp_path_factory.mktemp("published"),
        [
            rule_dict("TEST-P-LATE", f_(A), effective=UNPUBLISHED),
            rule_dict("TEST-P-NONE", f_(A)),
            rule_dict("TEST-P-PROP", f_(A), effective=UNPUBLISHED, law_status="proposed"),
        ],
    )


@pytest.mark.parametrize(
    ("rule_id", "as_of", "flag"),
    [
        ("TEST-P-LATE", date(2026, 1, 1), True),
        ("TEST-P-LATE", date(2026, 2, 28), True),
        ("TEST-P-LATE", date(2026, 3, 1), False),
        ("TEST-P-LATE", date(2026, 4, 1), False),
        ("TEST-P-NONE", date(2026, 2, 1), False),
    ],
    ids=["on-from", "day-before-published", "on-published", "after-published", "published-null"],
)
def test_t9_in_force_unpublished(
    published_pack: RulePack, rule_id: str, as_of: date, flag: bool
) -> None:
    """The flag is display only: the outcome stays APPLIES either way."""
    result = assess_rule_final(rule_id, published_pack, FACTS, as_of=as_of)
    assert result.in_force_unpublished is flag
    assert (result.outcome, result.reason, result.direction) == (Outcome.APPLIES, None, None)


def test_t9_flag_carried_in_subject_result(published_pack: RulePack) -> None:
    """assess_subject carries the flag on each RuleResult."""
    result = assess_subject(
        "test-subject-1", "model", published_pack, FACTS, as_of=date(2026, 2, 1)
    )
    flags = {r.rule_id: r.in_force_unpublished for g in result.regimes for r in g.rules}
    assert flags == {"TEST-P-LATE": True, "TEST-P-NONE": False}


def test_t9_proposed_never_flagged(published_pack: RulePack) -> None:
    """Settlement 4: a proposed rule in its window with a later published date gives False."""
    result = assess_subject(
        "test-subject-1",
        "model",
        published_pack,
        FACTS,
        as_of=date(2026, 2, 1),
        include_proposed=True,
    )
    flags = {r.rule_id: r.in_force_unpublished for g in result.regimes for r in g.rules}
    assert flags == {"TEST-P-LATE": True, "TEST-P-NONE": False, "TEST-P-PROP": False}


# ---- T10: JSON round trip ---------------------------------------------------------------


def test_t10_round_trip(window_pack: RulePack) -> None:
    """as_of and not_in_effect survive model_dump_json / model_validate_json."""
    result = assess_subject("test-subject-1", "model", window_pack, FACTS, as_of=date(2026, 7, 1))
    back = SubjectResult.model_validate_json(result.model_dump_json())
    assert back == result
    assert back.as_of == date(2026, 7, 1)
    assert back.not_in_effect == ("TEST-W-WINDOW",)


# ---- T11: outcomes unchanged for rules in effect -----------------------------------------


@pytest.fixture(scope="module")
def outcome_pack(tmp_path_factory: pytest.TempPathFactory) -> RulePack:
    """One rule with one trigger and one with two readings, both in effect."""
    return write_pack(
        tmp_path_factory.mktemp("outcomes"),
        [
            rule_dict("TEST-O-ONE", f_(A)),
            rule_dict("TEST-O-SPLIT", interpretations=readings(f_(A), f_(D))),
        ],
    )


@pytest.mark.parametrize(
    ("rule_id", "facts", "expected"),
    [
        ("TEST-O-ONE", {A: fact_of(T)}, (Outcome.APPLIES, None, None)),
        (
            "TEST-O-ONE",
            {A: fact_of(F)},
            (Outcome.DOES_NOT_APPLY, Reason.TEST_NOT_MET, None),
        ),
        (
            "TEST-O-ONE",
            {A: fact_of(T, "suspected")},
            (Outcome.CONDITIONAL, None, Direction.APPLIES_IF_CONFIRMED),
        ),
        ("TEST-O-ONE", {}, (Outcome.INSUFFICIENT_FACTS, None, None)),
        (
            "TEST-O-SPLIT",
            {A: fact_of(T), D: fact_of(F)},
            (Outcome.UNSETTLED, None, None),
        ),
    ],
    ids=["applies", "does-not-apply", "conditional", "insufficient", "unsettled"],
)
def test_t11_outcome_unchanged(
    outcome_pack: RulePack,
    rule_id: str,
    facts: dict[str, Fact],
    expected: tuple[Outcome, Reason | None, Direction | None],
) -> None:
    """For a rule in effect, (outcome, reason, direction) is what C3c gave."""
    result = assess_rule_final(rule_id, outcome_pack, facts, as_of=date(2026, 2, 1))
    assert (result.outcome, result.reason, result.direction) == expected
    assert result.in_force_unpublished is False


# ---- as_of must be a date, not a datetime ------------------------------------------------


def test_as_of_datetime_rejected(window_pack: RulePack) -> None:
    """Both entry points raise TypeError for a datetime, like load_rule_pack's today."""
    moment = datetime(2026, 2, 1, 12, 0)
    with pytest.raises(TypeError, match="as_of must be a date"):
        assess_subject("test-subject-1", "model", window_pack, FACTS, as_of=moment)
    with pytest.raises(TypeError, match="as_of must be a date"):
        assess_rule_final("TEST-W-ALWAYS", window_pack, FACTS, as_of=moment)
