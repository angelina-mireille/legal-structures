"""Tests for src/core/divergence.py: the divergence table (C4, decisions D17, D18).

Every rule and fact here is synthetic (regimes TEST and TEST-B, example.org URLs,
"test." fact names). Expected rows are written out literally. The table lists one row
per assessed rule and never aggregates across regimes.
"""

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from core.divergence import (
    DivergenceError,
    DivergenceRow,
    DivergenceTable,
    ReadingRow,
    divergence_table,
)
from core.evaluator import Fact, TriValue
from core.outcomes import Outcome, Reason
from core.results import SubjectResult, assess_subject
from core.rules import RulePack, load_rule_pack

TODAY = date(2026, 11, 24)
LAST_VERIFIED = date(2026, 11, 1)
AS_OF = date(2026, 6, 1)
EFFECTIVE_FROM = date(2026, 1, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64
BASIS = "synthetic test fixture"
SUBJECT = "TEST-SUBJ-001"
KIND = "model"

T = TriValue.TRUE
F = TriValue.FALSE

A, B, D = "test.alpha", "test.beta", "test.delta"


# ---- Helpers (local copies of tests/test_results.py helpers, extended) ---------------


def fact_of(value: TriValue, grade: str = "verified") -> Fact:
    """A TRUE or FALSE Fact with a grade."""
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
    interpretations: list[dict[str, Any]] | None = None,
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
        "title": "Synthetic divergence test rule",
        "law_status": law_status,
        "applies_to": "model",
        "binding": None,
        "effect": effect,
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
        "effective": (
            effective if effective is not None else {"from": EFFECTIVE_FROM, "basis": BASIS}
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


# ---- Pack and expected rows -------------------------------------------------------------

DIV_000 = rule_dict("TEST-DIV-000", f_(D), regime="TEST-B", effect="TEST_EFFECT_A")
DIV_001 = rule_dict(
    "TEST-DIV-001",
    f_(A),
    effect="TEST_EFFECT_A",
    effective={"from": EFFECTIVE_FROM, "published": date(2026, 9, 1), "basis": BASIS},
)
DIV_002 = rule_dict("TEST-DIV-002", interpretations=readings(f_(A), f_(B)), effect="TEST_EFFECT_B")
DIV_003 = rule_dict("TEST-DIV-003", f_(A), effective={"from": date(2027, 1, 1), "basis": BASIS})
DIV_004 = rule_dict("TEST-DIV-004", f_(A), law_status="proposed", effective={})
RULES = [DIV_000, DIV_001, DIV_002, DIV_003, DIV_004]

FACTS = {A: fact_of(T), B: fact_of(F), D: fact_of(F)}

ROW_001 = DivergenceRow(
    regime="TEST",
    rule_id="TEST-DIV-001",
    effect="TEST_EFFECT_A",
    law_status="in_force",
    outcome=Outcome.APPLIES,
    reason=None,
    direction=None,
    decisive_facts=(A,),
    exempted_by=(),
    in_force_unpublished=True,
    readings=(),
)
ROW_002 = DivergenceRow(
    regime="TEST",
    rule_id="TEST-DIV-002",
    effect="TEST_EFFECT_B",
    law_status="in_force",
    outcome=Outcome.UNSETTLED,
    reason=None,
    direction=None,
    decisive_facts=(),
    exempted_by=(),
    in_force_unpublished=False,
    readings=(
        ReadingRow(
            interpretation_id="reading_a", outcome=Outcome.APPLIES, reason=None, direction=None
        ),
        ReadingRow(
            interpretation_id="reading_b",
            outcome=Outcome.DOES_NOT_APPLY,
            reason=Reason.TEST_NOT_MET,
            direction=None,
        ),
    ),
)
ROW_000 = DivergenceRow(
    regime="TEST-B",
    rule_id="TEST-DIV-000",
    effect="TEST_EFFECT_A",
    law_status="in_force",
    outcome=Outcome.DOES_NOT_APPLY,
    reason=Reason.TEST_NOT_MET,
    direction=None,
    decisive_facts=(D,),
    exempted_by=(),
    in_force_unpublished=False,
    readings=(),
)


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[RulePack, SubjectResult]:
    """The pack and the subject result at AS_OF."""
    pack = write_pack(tmp_path_factory.mktemp("div"), RULES)
    return pack, assess_subject(SUBJECT, KIND, pack, FACTS, as_of=AS_OF)


# ---- 8 Tests ----------------------------------------------------------------------------


def test_table(result: tuple[RulePack, SubjectResult]) -> None:
    """Rows sorted by (regime, rule_id), effect from the pack, readings for UNSETTLED,
    not_in_effect and excluded_proposed copied. TEST-DIV-000 sorts first by id alone,
    but its regime TEST-B puts it last."""
    pack, subject = result
    assert divergence_table(subject, pack) == DivergenceTable(
        subject_id=SUBJECT,
        subject_kind=KIND,
        as_of=AS_OF,
        rows=(ROW_001, ROW_002, ROW_000),
        not_in_effect=("TEST-DIV-003",),
        excluded_proposed=("TEST-DIV-004",),
    )


def test_no_aggregate_fields() -> None:
    """No field aggregates across regimes: the field sets are exactly these."""
    assert set(DivergenceTable.model_fields) == {
        "subject_id",
        "subject_kind",
        "as_of",
        "rows",
        "not_in_effect",
        "excluded_proposed",
    }
    assert set(DivergenceRow.model_fields) == {
        "regime",
        "rule_id",
        "effect",
        "law_status",
        "outcome",
        "reason",
        "direction",
        "decisive_facts",
        "exempted_by",
        "in_force_unpublished",
        "readings",
    }
    assert set(ReadingRow.model_fields) == {"interpretation_id", "outcome", "reason", "direction"}


def test_rule_missing_from_pack(result: tuple[RulePack, SubjectResult], tmp_path: Path) -> None:
    """A result rule id absent from the pack raises DivergenceError."""
    _, subject = result
    other = write_pack(tmp_path, [DIV_000, DIV_001, DIV_003, DIV_004])
    with pytest.raises(DivergenceError):
        divergence_table(subject, other)


def test_rule_regime_differs(result: tuple[RulePack, SubjectResult], tmp_path: Path) -> None:
    """A result rule whose regime differs from the pack's raises DivergenceError."""
    _, subject = result
    moved = rule_dict("TEST-DIV-001", f_(A), regime="TEST-B", effect="TEST_EFFECT_A")
    other = write_pack(tmp_path, [DIV_000, moved, DIV_002, DIV_003, DIV_004])
    with pytest.raises(DivergenceError):
        divergence_table(subject, other)


def test_unsorted_rows_rejected() -> None:
    """Rows must be sorted by (regime, rule_id) with no repeats."""
    with pytest.raises(ValidationError):
        DivergenceTable(
            subject_id=SUBJECT,
            subject_kind=KIND,
            as_of=AS_OF,
            rows=(ROW_000, ROW_001),
        )


def test_unsorted_readings_rejected() -> None:
    """Readings must be sorted by interpretation id."""
    with pytest.raises(ValidationError):
        ROW_002.model_validate({**ROW_002.model_dump(), "readings": ROW_002.readings[::-1]})


@pytest.mark.parametrize("label", ["not_in_effect", "excluded_proposed"])
def test_unsorted_ids_rejected(label: str) -> None:
    """not_in_effect and excluded_proposed must be sorted."""
    with pytest.raises(ValidationError):
        DivergenceTable(
            subject_id=SUBJECT,
            subject_kind=KIND,
            as_of=AS_OF,
            rows=(),
            **{label: ("TEST-Y-001", "TEST-X-001")},
        )


def test_round_trip(result: tuple[RulePack, SubjectResult]) -> None:
    """A DivergenceTable survives a JSON round trip."""
    pack, subject = result
    table = divergence_table(subject, pack)
    assert DivergenceTable.model_validate_json(table.model_dump_json()) == table
