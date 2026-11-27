"""Tests for src/core/render.py and src/core/templates.py: renderers (C6, D19-D25).

Every rule and fact here is synthetic (regimes TEST and TEST-B, example.org URLs,
"test." fact names). Expected values are written out literally, never computed by the
code under test. Snapshots in tests/snapshots/ are compared byte for byte; a missing or
different snapshot fails. They are created once by a one-off command that calls
write_snapshots (not a test option), then reviewed by hand.
"""

import json
import re
import shutil
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from core import templates
from core.diff import SubjectDiff, diff_subjects
from core.divergence import DivergenceTable, divergence_table
from core.evaluator import Fact, TriValue
from core.outcomes import Direction, Outcome, Reason
from core.render import RenderError, outcome_text, render_json, render_memo, render_result_json
from core.results import SubjectResult, assess_subject
from core.rules import RulePack, load_rule_pack

TODAY = date(2026, 11, 24)
LAST_VERIFIED = date(2026, 11, 1)
STALE_VERIFIED = date(2026, 7, 1)
AS_OF = date(2026, 6, 1)
EFFECTIVE_FROM = date(2026, 1, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64
SUBJECT = "TEST-SUBJ-001"
KIND = "model"
BASIS = "synthetic test fixture"

T = TriValue.TRUE
F = TriValue.FALSE
U = TriValue.UNKNOWN

CLOCK_30 = {"amount": 30, "unit": "calendar_days", "trigger": "the test event occurs"}
CLOCK_72 = {"amount": 72, "unit": "hours", "trigger": "the test notice is received"}

DISCLAIMER = (
    "Prototype analysis, not legal advice. Each line follows from the rules and facts"
    " supplied; where readings differ, no reading is preferred."
)
NO_AGGREGATION = "Regimes are shown side by side. This memo draws no conclusion across regimes."
NO_DECISIVE_TEXT = (
    "No single fact is decisive: removing any one fact alone would not change the result."
)


# ---- Helpers (local copies of tests/test_diff.py helpers, extended) ------------------


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
    *,
    title: str = "Synthetic render test rule",
    binding: str | None = None,
    interpretations: list[dict[str, Any]] | None = None,
    unless: list[str] | None = None,
    clock: dict[str, Any] | None = None,
    applies_to: str = "model",
    law_status: str = "in_force",
    regime: str = "TEST",
    effective: dict[str, Any] | None = None,
    verification_status: str = "verified",
    last_verified: date = LAST_VERIFIED,
) -> dict[str, Any]:
    """A minimal synthetic TEST- rule as a dict, with title, verification and effective."""
    rule: dict[str, Any] = {
        "id": rule_id,
        "version": "1.0.0",
        "regime": regime,
        "title": title,
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
            "status": verification_status,
            "last_verified": last_verified,
            "verified_by": "user",
        },
        "clock": clock,
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
    """Write rules into a fresh folder under tmp_path, copy the source record, load the pack."""
    base = Path(tempfile.mkdtemp(dir=tmp_path))
    rules_dir = base / "rules"
    rules_dir.mkdir()
    sources_dir = base / "sources"
    shutil.copytree(FIXTURE_SOURCES, sources_dir)
    for rule in rules:
        text = yaml.safe_dump(rule, sort_keys=False)
        (rules_dir / f"{rule['id']}.yaml").write_text(text, encoding="utf-8")
    return load_rule_pack(rules_dir, sources_dir, TODAY)


def sections(memo: str) -> dict[str, list[str]]:
    """The non-blank lines of each rule section, keyed by the id in its "### [id]" heading."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in memo.split("\n"):
        heading = re.match(r"^### \[([A-Z][A-Z0-9-]+)\] ", line)
        if heading:
            current = found.setdefault(heading.group(1), [])
        elif line.startswith("#"):
            current = None
        elif line and current is not None:
            current.append(line)
    return found


# ---- memo_full: two regimes, every outcome template ------------------------------------

FULL_RULES: list[dict[str, Any]] = [
    # Top level, regime TEST.
    rule_dict(
        "TEST-APPLY-001",
        all_(f_("test.a1"), f_("test.a2")),
        title="Synthetic rule that applies",
        clock=CLOCK_30,
        unless=["TEST-EXA-001"],
    ),
    rule_dict(
        "TEST-ANY-001",
        any_(f_("test.o1"), f_("test.o2")),
        title="Synthetic rule met in two ways",
    ),
    rule_dict(
        "TEST-COND-001",
        f_("test.c1"),
        title="Synthetic conditional rule (applies if confirmed)",
        clock=CLOCK_72,
        unless=["TEST-EXE-001"],
    ),
    rule_dict(
        "TEST-COND-002",
        f_("test.c2"),
        title="Synthetic conditional rule (does not apply if confirmed)",
    ),
    rule_dict(
        "TEST-EXEMPT-001",
        f_("test.x1"),
        title="Synthetic rule under an applying exemption",
        unless=["TEST-EXB-001", "TEST-EXN-001"],
    ),
    rule_dict(
        "TEST-INSUF-001",
        all_(f_("test.i1"), f_("test.i2", "documented")),
        title="Synthetic rule with open questions",
        unless=["TEST-EXD-001"],
        verification_status="secondary",
    ),
    rule_dict(
        "TEST-NOTBOUND-001",
        f_("test.nb1"),
        title="Synthetic rule whose binding condition fails",
        binding="TEST-BIND-001",
    ),
    rule_dict(
        "TEST-UNRES-001",
        f_("test.u1"),
        title="Synthetic rule with an unsettled binding condition",
        binding="TEST-BIND-002",
        last_verified=STALE_VERIFIED,
    ),
    # Top level, regime TEST-B.
    rule_dict(
        "TEST-B-AGREE-001",
        title="Synthetic rule whose readings agree",
        interpretations=readings(f_("test.ra1"), f_("test.ra2")),
        regime="TEST-B",
        effective={"from": EFFECTIVE_FROM, "to": date(2027, 1, 1), "basis": BASIS},
    ),
    rule_dict(
        "TEST-B-SPLIT-001",
        title="Synthetic rule whose readings differ",
        interpretations=readings(f_("test.rs1"), f_("test.rs2")),
        clock=CLOCK_30,
        regime="TEST-B",
        effective={"from": EFFECTIVE_FROM, "published": date(2026, 7, 1), "basis": BASIS},
    ),
    rule_dict(
        "TEST-B-LATER-001",
        f_("test.l1"),
        title="Synthetic rule not yet in effect",
        regime="TEST-B",
        effective={"from": date(2026, 9, 1), "basis": BASIS},
    ),
    rule_dict(
        "TEST-B-PROP-001",
        f_("test.p1"),
        title="Synthetic proposed rule",
        regime="TEST-B",
        law_status="proposed",
        effective={},
    ),
    # Helpers (binding and unless targets), regime TEST.
    rule_dict("TEST-EXA-001", f_("test.ea1"), unless=["TEST-CB-001"]),
    rule_dict("TEST-CB-001", f_("test.cb1")),
    rule_dict("TEST-EXB-001", f_("test.eb1"), verification_status="secondary"),
    rule_dict("TEST-EXE-001", f_("test.ee1")),
    rule_dict("TEST-EXN-001", f_("test.en1")),
    rule_dict("TEST-EXD-001", all_(f_("test.ed1"), f_("test.ed2", "verified"))),
    rule_dict("TEST-BIND-001", f_("test.b1")),
    rule_dict("TEST-BIND-002", f_("test.b2")),
]

# Not supplied: test.x1, test.ed1, test.nb1, test.b2, test.l1, test.p1.
FULL_FACTS: dict[str, Fact] = {
    "test.a1": fact_of(T),
    "test.a2": fact_of(T, "documented"),
    "test.b1": fact_of(F),
    "test.c1": fact_of(T, "suspected"),
    "test.c2": fact_of(F, "suspected"),
    "test.cb1": fact_of(T, "suspected"),
    "test.ea1": fact_of(T),
    "test.eb1": fact_of(T),
    "test.ed2": fact_of(T, "documented"),
    "test.ee1": fact_of(T, "suspected"),
    "test.en1": fact_of(F),
    "test.i1": fact_of(U),
    "test.i2": fact_of(T, "declared"),
    "test.o1": fact_of(T),
    "test.o2": fact_of(T),
    "test.ra1": fact_of(T),
    "test.ra2": fact_of(T),
    "test.rs1": fact_of(T),
    "test.rs2": fact_of(F),
    "test.u1": fact_of(F),
}


def full_case(tmp_path: Path) -> tuple[SubjectResult, RulePack, dict[str, Fact]]:
    """The memo_full result, pack and facts (include_proposed False)."""
    pack = write_pack(tmp_path, FULL_RULES)
    result = assess_subject(SUBJECT, KIND, pack, FULL_FACTS, as_of=AS_OF)
    return result, pack, FULL_FACTS


# ---- Small cases --------------------------------------------------------------------------

SMALL_RULES: list[dict[str, Any]] = [
    rule_dict("TEST-SMALL-001", f_("test.s1"), title="Synthetic small rule"),
    rule_dict(
        "TEST-PROP-002",
        f_("test.p2"),
        title="Synthetic small proposed rule",
        law_status="proposed",
        effective={},
    ),
]
SMALL_FACTS: dict[str, Fact] = {"test.s1": fact_of(T)}
SMALL_FACTS_WITH_PROPOSED: dict[str, Fact] = {"test.p2": fact_of(T), "test.s1": fact_of(T)}


def small_proposed_case(tmp_path: Path) -> tuple[SubjectResult, RulePack, dict[str, Fact]]:
    """The memo_small result (include_proposed True), pack and facts."""
    pack = write_pack(tmp_path, SMALL_RULES)
    result = assess_subject(
        SUBJECT, KIND, pack, SMALL_FACTS_WITH_PROPOSED, as_of=AS_OF, include_proposed=True
    )
    return result, pack, SMALL_FACTS_WITH_PROPOSED


def small_case(tmp_path: Path) -> tuple[SubjectResult, RulePack, dict[str, Fact]]:
    """The result_small result (include_proposed False), pack and facts."""
    pack = write_pack(tmp_path, SMALL_RULES)
    result = assess_subject(SUBJECT, KIND, pack, SMALL_FACTS, as_of=AS_OF)
    return result, pack, SMALL_FACTS


def small_diff(tmp_path: Path) -> SubjectDiff:
    """test.s1 TRUE before and FALSE after, same date: TEST-SMALL-001 flips."""
    pack = write_pack(tmp_path, SMALL_RULES)
    return diff_subjects(
        SUBJECT,
        KIND,
        pack,
        {"test.s1": fact_of(T)},
        {"test.s1": fact_of(F)},
        as_of_before=AS_OF,
        as_of_after=AS_OF,
    )


def small_divergence(tmp_path: Path) -> DivergenceTable:
    """The divergence table of the result_small result."""
    result, pack, _ = small_case(tmp_path)
    return divergence_table(result, pack)


# ---- Snapshot outputs -------------------------------------------------------------------


def build_memo_full(tmp_path: Path) -> str:
    """memo_full.md."""
    return render_memo(*full_case(tmp_path))


def build_memo_small(tmp_path: Path) -> str:
    """memo_small.md."""
    return render_memo(*small_proposed_case(tmp_path))


def build_result_small(tmp_path: Path) -> str:
    """result_small.json."""
    return render_result_json(*small_case(tmp_path))


def build_diff_small(tmp_path: Path) -> str:
    """diff_small.json."""
    return render_json(small_diff(tmp_path))


def build_divergence_small(tmp_path: Path) -> str:
    """divergence_small.json."""
    return render_json(small_divergence(tmp_path))


OUTPUTS: dict[str, Callable[[Path], str]] = {
    "memo_full.md": build_memo_full,
    "memo_small.md": build_memo_small,
    "result_small.json": build_result_small,
    "diff_small.json": build_diff_small,
    "divergence_small.json": build_divergence_small,
}


def write_snapshots(tmp_dir: str) -> None:
    """One-off: write every snapshot from the renderer (D24). Not called by any test."""
    SNAPSHOTS.mkdir(exist_ok=True)
    for name, build in OUTPUTS.items():
        (SNAPSHOTS / name).write_bytes(build(Path(tmp_dir)).encode("utf-8"))


# ---- 1. Snapshots ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(OUTPUTS))
def test_snapshot(name: str, tmp_path: Path) -> None:
    """Each output equals its snapshot byte for byte; a missing snapshot fails."""
    path = SNAPSHOTS / name
    assert path.is_file(), f"missing snapshot {path}"
    assert OUTPUTS[name](tmp_path).encode("utf-8") == path.read_bytes()


# ---- 2. Templates: exact wording and coverage -----------------------------------------------

EXPECTED_TEMPLATES: dict[str, str] = {
    "TITLE": "# Assessment of {subject_id} ({subject_kind}) as of {as_of}",
    "DISCLAIMER": DISCLAIMER,
    "NO_AGGREGATION": NO_AGGREGATION,
    "REGIME_HEADING": "## Regime {regime}",
    "RULE_HEADING": "### [{id}] {title}",
    "NOT_IN_EFFECT_HEADING": "## Not in effect on {as_of}",
    "PROPOSED_HEADING": "## Proposed law not assessed",
    "RESULT": "- [{id}] Result: {label}. {sentence}",
    "LABEL_APPLIES": "APPLIES",
    "SENTENCE_APPLIES": "On the facts supplied, the conditions of this rule are met.",
    "LABEL_TEST_NOT_MET": "DOES_NOT_APPLY (TEST_NOT_MET)",
    "SENTENCE_TEST_NOT_MET": "On the facts supplied, the test in this rule is not met.",
    "LABEL_NOT_BOUND": "DOES_NOT_APPLY (NOT_BOUND)",
    "SENTENCE_NOT_BOUND": (
        "On the facts supplied, the binding condition in [{binding_id}] is not met,"
        " so this rule's test was not assessed."
    ),
    "LABEL_EXEMPT": "DOES_NOT_APPLY (EXEMPT)",
    "SENTENCE_EXEMPT": (
        "On the facts supplied, an exemption applies ({exempted_by}), so this rule does not apply."
    ),
    "LABEL_APPLIES_IF_CONFIRMED": "CONDITIONAL (APPLIES_IF_CONFIRMED)",
    "SENTENCE_APPLIES_IF_CONFIRMED": (
        "The result rests on facts graded only as suspected. If they are confirmed,"
        " the conditions of this rule are met."
    ),
    "LABEL_DOES_NOT_APPLY_IF_CONFIRMED": "CONDITIONAL (DOES_NOT_APPLY_IF_CONFIRMED)",
    "SENTENCE_DOES_NOT_APPLY_IF_CONFIRMED": (
        "The result rests on facts graded only as suspected. If they are confirmed,"
        " the conditions of this rule are not met."
    ),
    "LABEL_INSUFFICIENT_FACTS": "INSUFFICIENT_FACTS",
    "SENTENCE_INSUFFICIENT_FACTS": (
        "The facts supplied are not enough to assess this rule. The open points are listed below."
    ),
    "LABEL_UNSETTLED": "UNSETTLED",
    "SENTENCE_UNSETTLED": (
        "The readings of this rule give different results on the facts supplied."
        " Which reading is right is for counsel; this tool takes no view."
    ),
    "BASE_UNDER_EXEMPTION": (
        "- [{id}] Without the exemption, the result would be {base_label}: {base_sentence}"
    ),
    "BINDING_UNRESOLVED": (
        "- [{id}] Whether [{binding_id}] binds the subject is not settled on the facts"
        " supplied; the test is not met either way."
    ),
    "READING": "- [{id}] Reading {reading_id}: {label}.",
    "READINGS_AGREE": "- [{id}] All {count} readings of this rule give this result.",
    "DECISIVE": "- [{id}] Decisive facts (removing any one would change the result): {facts}.",
    "NO_DECISIVE": "- [{id}] " + NO_DECISIVE_TEXT,
    "DECISIVE_NONE_ALL_READINGS": "- [{id}] No single fact is decisive under every reading.",
    "FACTS_TO_CONFIRM": "- [{id}] Facts to confirm: {facts}.",
    "QUESTION_MISSING": "- [{id}] Missing fact: {fact}.",
    "QUESTION_STRONGER": (
        "- [{id}] Stronger evidence needed for {fact}: this rule requires at least {required}."
    ),
    "EXEMPTION_APPLIED": "- [{id}] Exemption [{ex_id}] applies on the facts supplied.",
    "EXEMPTION_NOT_APPLYING": "- [{id}] Exemption [{ex_id}] does not apply on the facts supplied.",
    "EXEMPTION_UNRESOLVED": (
        "- [{id}] Exemption [{ex_id}] is not resolved on the facts supplied ({ex_label}),"
        " so it is not treated as applying."
    ),
    "EXEMPTION_D6A_LABEL": "APPLIES, but an exemption to it is open",
    "EXEMPTION_LABEL_CONDITIONAL": "CONDITIONAL",
    "EXEMPTION_OPEN_MISSING": "- [{id}] Open point for exemption [{ex_id}]: missing fact {fact}.",
    "EXEMPTION_OPEN_STRONGER": (
        "- [{id}] Open point for exemption [{ex_id}]: stronger evidence needed for {fact};"
        " at least {required} is required."
    ),
    "EXEMPTION_OPEN_CONFIRM": "- [{id}] Open point for exemption [{ex_id}]: confirm {fact}.",
    "CLOCK": "- [{id}] Clock: {amount} {unit} after {trigger}. {note}",
    "CLOCK_IF_CONFIRMED": (
        " Shown because the conditions of this rule are met if the facts to confirm are confirmed."
    ),
    "CLOCK_UNDER_READINGS": (
        " Shown because this rule's conditions are met, or would be met if confirmed,"
        " under these readings: {readings}."
    ),
    "IN_FORCE_UNPUBLISHED": "- [{id}] In force on {as_of} but not published until {published}.",
    "PROPOSED_ASSESSED": (
        "- [{id}] Proposed law, not in force; assessed because proposed rules were included."
    ),
    "SOURCE": (
        "- [{id}] Source: {primary}, {source_url} (source record {source_id})."
        " Verification: {status}, last checked {last_verified}."
    ),
    "EFFECTIVE": "- [{id}] In effect from {from}. Basis for the dates: {basis}.",
    "EFFECTIVE_UNTIL": (
        "- [{id}] In effect from {from} until, but not including, {to}."
        " Basis for the dates: {basis}."
    ),
    "EFFECTIVE_NONE": "- [{id}] No effective date recorded (proposed law).",
    "WARNING": "- [{id}] Warning {code}: {message}",
    "HELPER_WARNING": (
        "- [{id}] Warning {code} on [{helper_id}], which this rule relies on: {message}"
    ),
    "NOT_IN_EFFECT": "- [{id}] Not in effect on {as_of}; not assessed.",
    "EXCLUDED_PROPOSED": "- [{id}] Proposed law; not assessed (proposed rules were not included).",
    "FACT_STATED": "{name} ({value}, {grade})",
    "FACT_UNKNOWN": "{name} (UNKNOWN)",
    "FACT_NOT_SUPPLIED": "{name} (not supplied)",
    "ID_REF": "[{id}]",
    "LIST_SEPARATOR": ", ",
}


def template_constants() -> dict[str, str]:
    """Every upper-case str constant defined in templates.py."""
    return {
        name: value
        for name, value in vars(templates).items()
        if name.isupper() and isinstance(value, str)
    }


def test_templates_worded_exactly() -> None:
    """templates.py holds exactly the approved constants, worded exactly (D22, T1-T6)."""
    assert template_constants() == EXPECTED_TEMPLATES


def test_every_template_appears_in_a_snapshot() -> None:
    """Each template, with its placeholders filled, appears in at least one memo snapshot."""
    text = (SNAPSHOTS / "memo_full.md").read_text(encoding="utf-8") + (
        SNAPSHOTS / "memo_small.md"
    ).read_text(encoding="utf-8")
    missing = []
    for name, template in template_constants().items():
        parts = re.split(r"\{[a-z_]+\}", template)
        pattern = ".+?".join(re.escape(part) for part in parts)
        if not re.search(pattern, text):
            missing.append(name)
    assert missing == []


# ---- 3. Every statement carries its rule ID (the done-when) ----------------------------------

BOILERPLATE = (
    re.compile(r"^# Assessment of TEST-SUBJ-001 \(model\) as of 2026-06-01$"),
    re.compile("^" + re.escape(DISCLAIMER) + "$"),
    re.compile("^" + re.escape(NO_AGGREGATION) + "$"),
    re.compile(r"^## Regime [A-Z][A-Z0-9-]+$"),
)
NOT_IN_EFFECT_HEADING = "## Not in effect on 2026-06-01"
PROPOSED_HEADING = "## Proposed law not assessed"


def check_rule_ids(memo: str, not_in_effect: list[str], excluded: list[str]) -> None:
    """Every non-blank line is boilerplate, a rule heading, or starts with its rule's id."""
    current: str | None = None
    listed: list[str] | None = None
    for line in memo.split("\n"):
        if not line or any(p.match(line) for p in BOILERPLATE):
            if line.startswith("## Regime "):
                current, listed = None, None
            continue
        heading = re.match(r"^### \[([A-Z][A-Z0-9-]+)\] \S", line)
        if heading:
            current, listed = heading.group(1), None
        elif line == NOT_IN_EFFECT_HEADING:
            current, listed = None, not_in_effect
        elif line == PROPOSED_HEADING:
            current, listed = None, excluded
        elif listed is not None:
            match = re.match(r"^- \[([A-Z][A-Z0-9-]+)\] ", line)
            assert match and match.group(1) in listed, line
        else:
            assert current is not None, line
            assert line.startswith(f"- [{current}] "), line


def test_every_statement_carries_rule_id_memo_full() -> None:
    """memo_full: every statement line starts with the id of its rule."""
    memo = (SNAPSHOTS / "memo_full.md").read_text(encoding="utf-8")
    check_rule_ids(memo, ["TEST-B-LATER-001"], ["TEST-B-PROP-001"])
    assert "## Not in effect on 2026-06-01" in memo
    assert "## Proposed law not assessed" in memo


def test_every_statement_carries_rule_id_memo_small() -> None:
    """memo_small: every statement line starts with the id of its rule."""
    memo = (SNAPSHOTS / "memo_small.md").read_text(encoding="utf-8")
    check_rule_ids(memo, [], [])


# ---- 4. Outcome templates -------------------------------------------------------------------

VALID_COMBINATIONS = [
    (
        (Outcome.APPLIES, None, None),
        "APPLIES",
        "On the facts supplied, the conditions of this rule are met.",
    ),
    (
        (Outcome.DOES_NOT_APPLY, Reason.TEST_NOT_MET, None),
        "DOES_NOT_APPLY (TEST_NOT_MET)",
        "On the facts supplied, the test in this rule is not met.",
    ),
    (
        (Outcome.DOES_NOT_APPLY, Reason.NOT_BOUND, None),
        "DOES_NOT_APPLY (NOT_BOUND)",
        "On the facts supplied, the binding condition in [{binding_id}] is not met,"
        " so this rule's test was not assessed.",
    ),
    (
        (Outcome.DOES_NOT_APPLY, Reason.EXEMPT, None),
        "DOES_NOT_APPLY (EXEMPT)",
        "On the facts supplied, an exemption applies ({exempted_by}), so this rule does not apply.",
    ),
    (
        (Outcome.CONDITIONAL, None, Direction.APPLIES_IF_CONFIRMED),
        "CONDITIONAL (APPLIES_IF_CONFIRMED)",
        "The result rests on facts graded only as suspected. If they are confirmed,"
        " the conditions of this rule are met.",
    ),
    (
        (Outcome.CONDITIONAL, None, Direction.DOES_NOT_APPLY_IF_CONFIRMED),
        "CONDITIONAL (DOES_NOT_APPLY_IF_CONFIRMED)",
        "The result rests on facts graded only as suspected. If they are confirmed,"
        " the conditions of this rule are not met.",
    ),
    (
        (Outcome.INSUFFICIENT_FACTS, None, None),
        "INSUFFICIENT_FACTS",
        "The facts supplied are not enough to assess this rule. The open points are listed below.",
    ),
    (
        (Outcome.UNSETTLED, None, None),
        "UNSETTLED",
        "The readings of this rule give different results on the facts supplied."
        " Which reading is right is for counsel; this tool takes no view.",
    ),
]


@pytest.mark.parametrize(("key", "label", "sentence"), VALID_COMBINATIONS)
def test_outcome_template_for_each_valid_combination(
    key: tuple[Outcome, Reason | None, Direction | None], label: str, sentence: str
) -> None:
    """Each of the eight valid final combinations has its label and sentence."""
    assert outcome_text(*key) == (label, sentence)


@pytest.mark.parametrize(
    "key",
    [
        (Outcome.APPLIES, Reason.TEST_NOT_MET, None),
        (Outcome.APPLIES, None, Direction.APPLIES_IF_CONFIRMED),
        (Outcome.DOES_NOT_APPLY, None, None),
        (Outcome.CONDITIONAL, None, None),
        (Outcome.CONDITIONAL, Reason.EXEMPT, Direction.APPLIES_IF_CONFIRMED),
        (Outcome.INSUFFICIENT_FACTS, Reason.NOT_BOUND, None),
        (Outcome.UNSETTLED, None, Direction.APPLIES_IF_CONFIRMED),
    ],
)
def test_outcome_template_invalid_combination_raises(
    key: tuple[Outcome, Reason | None, Direction | None],
) -> None:
    """Any other combination raises RenderError."""
    with pytest.raises(RenderError):
        outcome_text(*key)


# ---- 5. Banned words --------------------------------------------------------------------------

BANNED = (
    "comply",
    "compliant",
    "compliance",
    "safe",
    "covered",
    "should",
    "recommend",
    "advise",
    "clearly",
    "obviously",
    "certainly",
    "guarantee",
    "violat",
    "illegal",
    "lawful",
)


def test_no_banned_words_in_templates() -> None:
    """No template constant contains a banned word, case-insensitively."""
    found = [
        (name, word)
        for name, value in template_constants().items()
        for word in BANNED
        if word in value.lower()
    ]
    assert found == []


# ---- Section-level behaviour (T2, T6, (d)2, (d)4) --------------------------------------------


def test_helper_warning_in_relying_rule_section(tmp_path: Path) -> None:
    """A helper's warning appears in the section of the rule that relies on it, and only there."""
    memo = render_memo(*full_case(tmp_path))
    by_rule = sections(memo)
    line = (
        "- [TEST-EXEMPT-001] Warning NOT_VERIFIED on [TEST-EXB-001], which this rule relies on:"
        " verification status is secondary"
    )
    assert line in by_rule["TEST-EXEMPT-001"]
    others = [r for r, lines in by_rule.items() if r != "TEST-EXEMPT-001"]
    assert all("[TEST-EXB-001], which" not in "\n".join(by_rule[r]) for r in others)


def test_own_warnings_printed(tmp_path: Path) -> None:
    """A rule's own NOT_VERIFIED and STALE warnings head its section (D23)."""
    by_rule = sections(render_memo(*full_case(tmp_path)))
    assert by_rule["TEST-INSUF-001"][0] == (
        "- [TEST-INSUF-001] Warning NOT_VERIFIED: verification status is secondary"
    )
    assert by_rule["TEST-UNRES-001"][0] == (
        "- [TEST-UNRES-001] Warning STALE: last verified 2026-07-01, 146 days before"
        " 2026-11-24 (more than 90)"
    )


def test_helper_warnings_follow_binding_and_unless_chains(tmp_path: Path) -> None:
    """Binding chain at any depth; unless rules at any depth with their bindings; sorted."""
    rules = [
        rule_dict("TEST-TOP-001", f_("test.t1"), binding="TEST-HB-001", unless=["TEST-HU-001"]),
        rule_dict("TEST-HB-001", f_("test.hb1"), binding="TEST-HB-002"),
        rule_dict(
            "TEST-HB-002",
            f_("test.hb2"),
            verification_status="secondary",
            last_verified=STALE_VERIFIED,
        ),
        rule_dict("TEST-HU-001", f_("test.hu1"), unless=["TEST-HU-002"]),
        rule_dict(
            "TEST-HU-002",
            f_("test.hu2"),
            binding="TEST-HB-003",
            verification_status="unverified",
        ),
        rule_dict("TEST-HB-003", f_("test.hb3"), verification_status="secondary"),
        rule_dict("TEST-OTHER-001", f_("test.t2"), unless=["TEST-HO-001"]),
        rule_dict("TEST-HO-001", f_("test.ho1"), verification_status="secondary"),
    ]
    facts = {
        "test.hb1": fact_of(T),
        "test.hb2": fact_of(T),
        "test.hu1": fact_of(F),
        "test.t1": fact_of(T),
        "test.t2": fact_of(T),
        "test.ho1": fact_of(F),
    }
    pack = write_pack(tmp_path, rules)
    result = assess_subject(SUBJECT, KIND, pack, facts, as_of=AS_OF)
    by_rule = sections(render_memo(result, pack, facts))
    helper_lines = [line for line in by_rule["TEST-TOP-001"] if "which this rule relies on" in line]
    assert helper_lines == [
        "- [TEST-TOP-001] Warning NOT_VERIFIED on [TEST-HB-002], which this rule relies on:"
        " verification status is secondary",
        "- [TEST-TOP-001] Warning STALE on [TEST-HB-002], which this rule relies on:"
        " last verified 2026-07-01, 146 days before 2026-11-24 (more than 90)",
        "- [TEST-TOP-001] Warning NOT_VERIFIED on [TEST-HB-003], which this rule relies on:"
        " verification status is secondary",
        "- [TEST-TOP-001] Warning NOT_VERIFIED on [TEST-HU-002], which this rule relies on:"
        " verification status is unverified",
    ]
    other_lines = [
        line for line in by_rule["TEST-OTHER-001"] if "which this rule relies on" in line
    ]
    assert other_lines == [
        "- [TEST-OTHER-001] Warning NOT_VERIFIED on [TEST-HO-001], which this rule relies on:"
        " verification status is secondary",
    ]


def test_no_decisive_never_for_rule_with_readings(tmp_path: Path) -> None:
    """NO_DECISIVE is for single-trigger rules; agreeing readings get the reading line (T2)."""
    by_rule = sections(render_memo(*full_case(tmp_path)))
    for rule_id in ("TEST-B-AGREE-001", "TEST-B-SPLIT-001"):
        assert all(NO_DECISIVE_TEXT not in line for line in by_rule[rule_id])
    assert (
        "- [TEST-B-AGREE-001] No single fact is decisive under every reading."
        in (by_rule["TEST-B-AGREE-001"])
    )
    assert "- [TEST-ANY-001] " + NO_DECISIVE_TEXT in by_rule["TEST-ANY-001"]


def test_exempt_result_has_no_decisive_line(tmp_path: Path) -> None:
    """Under EXEMPT neither decisive line is printed ((d)2); base questions are."""
    lines = sections(render_memo(*full_case(tmp_path)))["TEST-EXEMPT-001"]
    assert all("Decisive facts" not in line for line in lines)
    assert all("No single fact is decisive" not in line for line in lines)
    assert "- [TEST-EXEMPT-001] Missing fact: test.x1 (not supplied)." in lines


def test_unresolved_exemption_labels(tmp_path: Path) -> None:
    """D6a label, CONDITIONAL label (T5) and INSUFFICIENT_FACTS label on unresolved lines."""
    by_rule = sections(render_memo(*full_case(tmp_path)))
    assert (
        "- [TEST-APPLY-001] Exemption [TEST-EXA-001] is not resolved on the facts supplied"
        " (APPLIES, but an exemption to it is open), so it is not treated as applying."
    ) in by_rule["TEST-APPLY-001"]
    assert (
        "- [TEST-COND-001] Exemption [TEST-EXE-001] is not resolved on the facts supplied"
        " (CONDITIONAL), so it is not treated as applying."
    ) in by_rule["TEST-COND-001"]
    assert (
        "- [TEST-INSUF-001] Exemption [TEST-EXD-001] is not resolved on the facts supplied"
        " (INSUFFICIENT_FACTS), so it is not treated as applying."
    ) in by_rule["TEST-INSUF-001"]


# ---- 6. Inputs match (D20) ---------------------------------------------------------------------


def test_mismatched_facts_raise(tmp_path: Path) -> None:
    """Facts that differ from those behind the result raise RenderError."""
    result, pack, facts = full_case(tmp_path)
    changed = {**facts, "test.a1": fact_of(F)}
    with pytest.raises(RenderError):
        render_memo(result, pack, changed)
    with pytest.raises(RenderError):
        render_result_json(result, pack, changed)


def test_other_pack_raises(tmp_path: Path) -> None:
    """A result rendered against a different pack raises RenderError."""
    result, _, facts = full_case(tmp_path)
    other = write_pack(tmp_path, SMALL_RULES)
    with pytest.raises(RenderError):
        render_memo(result, other, facts)


def test_include_proposed_result_renders(tmp_path: Path) -> None:
    """A result built with include_proposed=True renders without error."""
    memo = render_memo(*small_proposed_case(tmp_path))
    assert (
        "- [TEST-PROP-002] Proposed law, not in force; assessed because proposed rules"
        " were included."
    ) in memo


def test_proposed_dependency_result_renders(tmp_path: Path) -> None:
    """(d)1: the include_proposed=False re-run raises ResultError; the True re-run matches."""
    rules = [
        rule_dict("TEST-DEP-001", f_("test.d1"), unless=["TEST-DEPP-001"]),
        rule_dict("TEST-DEPP-001", f_("test.dp1"), law_status="proposed", effective={}),
    ]
    facts = {"test.d1": fact_of(T), "test.dp1": fact_of(F)}
    pack = write_pack(tmp_path, rules)
    result = assess_subject(SUBJECT, KIND, pack, facts, as_of=AS_OF, include_proposed=True)
    assert "- [TEST-DEP-001] Result: APPLIES." in render_memo(result, pack, facts)
    json.loads(render_result_json(result, pack, facts))


def test_proposed_rule_with_to_but_no_from_raises(tmp_path: Path) -> None:
    """(d)8: a proposed rule with effective.to and no effective.from raises RenderError."""
    rules = [
        rule_dict(
            "TEST-PROP-003",
            f_("test.p3"),
            law_status="proposed",
            effective={"to": date(2027, 1, 1)},
        ),
    ]
    facts = {"test.p3": fact_of(T)}
    pack = write_pack(tmp_path, rules)
    result = assess_subject(SUBJECT, KIND, pack, facts, as_of=AS_OF, include_proposed=True)
    with pytest.raises(RenderError):
        render_memo(result, pack, facts)


# ---- 7. JSON ------------------------------------------------------------------------------------


def test_result_json_envelope(tmp_path: Path) -> None:
    """Envelope keys and order are fixed; "result" validates back into an equal model."""
    result, _, _ = small_case(tmp_path)
    data = json.loads(build_result_small(tmp_path))
    assert list(data) == [
        "format_version",
        "kind",
        "disclaimer",
        "facts",
        "rules_in_pack",
        "result",
    ]
    assert data["format_version"] == "0.1"
    assert data["kind"] == "subject_result"
    assert data["disclaimer"] == DISCLAIMER
    assert data["facts"] == [{"fact": "test.s1", "value": "true", "grade": "verified"}]
    assert data["rules_in_pack"] == [
        {
            "id": "TEST-PROP-002",
            "version": "1.0.0",
            "regime": "TEST",
            "law_status": "proposed",
            "verification_status": "verified",
            "last_verified": "2026-11-01",
            "source_id": "test-source-1",
        },
        {
            "id": "TEST-SMALL-001",
            "version": "1.0.0",
            "regime": "TEST",
            "law_status": "in_force",
            "verification_status": "verified",
            "last_verified": "2026-11-01",
            "source_id": "test-source-1",
        },
    ]
    assert SubjectResult.model_validate_json(json.dumps(data["result"])) == result


def test_result_json_facts_unknown_has_null_grade(tmp_path: Path) -> None:
    """A fact supplied as UNKNOWN is listed with value "unknown" and grade null."""
    result, pack, facts = full_case(tmp_path)
    data = json.loads(render_result_json(result, pack, facts))
    assert {"fact": "test.i1", "value": "unknown", "grade": None} in data["facts"]
    assert [item["fact"] for item in data["facts"]] == sorted(FULL_FACTS)


def test_render_json_diff_envelope(tmp_path: Path) -> None:
    """SubjectDiff envelope: fixed keys; "data" validates back into an equal model."""
    diff = small_diff(tmp_path)
    data = json.loads(render_json(diff))
    assert list(data) == ["format_version", "kind", "disclaimer", "data"]
    assert data["format_version"] == "0.1"
    assert data["kind"] == "subject_diff"
    assert data["disclaimer"] == DISCLAIMER
    assert SubjectDiff.model_validate_json(json.dumps(data["data"])) == diff


def test_render_json_divergence_envelope(tmp_path: Path) -> None:
    """DivergenceTable envelope: fixed keys; "data" validates back into an equal model."""
    table = small_divergence(tmp_path)
    data = json.loads(render_json(table))
    assert list(data) == ["format_version", "kind", "disclaimer", "data"]
    assert data["kind"] == "divergence_table"
    assert DivergenceTable.model_validate_json(json.dumps(data["data"])) == table


def test_render_json_rejects_other_types(tmp_path: Path) -> None:
    """render_json on anything but SubjectDiff or DivergenceTable raises RenderError."""
    result, _, _ = small_case(tmp_path)
    with pytest.raises(RenderError):
        render_json(result)  # type: ignore[arg-type]
    with pytest.raises(RenderError):
        render_json("not a model")  # type: ignore[arg-type]


# ---- 8. Determinism -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(OUTPUTS))
def test_determinism(name: str, tmp_path: Path) -> None:
    """Two renders are equal; one trailing newline; no carriage return."""
    first = OUTPUTS[name](tmp_path)
    second = OUTPUTS[name](tmp_path)
    assert first == second
    assert first.endswith("\n") and not first.endswith("\n\n")
    assert "\r" not in first
