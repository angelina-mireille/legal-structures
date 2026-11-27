"""Tests for C2b: the loader refuses helper-rule features the engine ignores (D26-D28).

Every rule here is synthetic (TEST- ids, regime TEST, "test." fact names, example.org
URLs). Expected problem messages are written out literally, never built by the code
under test.
"""

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.rules import RuleError, RulePack, load_rule_pack

TODAY = date(2026, 11, 27)
LAST_VERIFIED = date(2026, 11, 1)
FIXTURE_SOURCES = Path(__file__).resolve().parent / "fixtures" / "rules" / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64
EFFECTIVE_FROM = date(2026, 1, 1)

A, B = "test.alpha", "test.beta"
CLOCK_30 = {"amount": 30, "unit": "calendar_days", "trigger": "Test event occurs."}


# ---- Helpers (local copies of tests/test_results.py's, not imported) ------------------


def rule_dict(
    rule_id: str,
    trigger: dict[str, Any] | None = None,
    binding: str | None = None,
    interpretations: list[dict[str, Any]] | None = None,
    unless: list[str] | None = None,
    clock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A minimal synthetic TEST- rule as a dict; trigger defaults to one fact leaf."""
    rule: dict[str, Any] = {
        "id": rule_id,
        "version": "1.0.0",
        "regime": "TEST",
        "title": "Synthetic helper-rule test rule",
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
        "clock": clock,
        "effective": {"from": EFFECTIVE_FROM, "basis": "synthetic test fixture"},
    }
    if interpretations is not None:
        rule["interpretations"] = interpretations
    else:
        rule["trigger"] = trigger or {"fact": A}
    return rule


def readings() -> list[dict[str, Any]]:
    """Two interpretations, reading_a and reading_b."""
    return [
        {"id": "reading_a", "summary": "Test reading A.", "trigger": {"fact": A}},
        {"id": "reading_b", "summary": "Test reading B.", "trigger": {"fact": B}},
    ]


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


def load_problems(tmp_path: Path, rules: list[dict[str, Any]]) -> tuple[str, ...]:
    """Load the pack, expect RuleError, and return its problems."""
    with pytest.raises(RuleError) as caught:
        write_pack(tmp_path, rules)
    return caught.value.problems


# ---- 1-2: (a) unless on a binding rule ---------------------------------------------------


def test_binding_rule_with_unless_refused(tmp_path: Path) -> None:
    """(a) A binding rule with an unless is refused, naming the helper and its user."""
    problems = load_problems(
        tmp_path,
        [
            rule_dict("TEST-TOP", binding="TEST-HELP"),
            rule_dict("TEST-HELP", unless=["TEST-EX"]),
            rule_dict("TEST-EX"),
        ],
    )
    assert problems == (
        "TEST-HELP: used as binding by TEST-TOP, but has unless;"
        " unless on a binding rule is never applied",
    )


def test_binding_rule_with_unless_at_depth_refused(tmp_path: Path) -> None:
    """(a) at depth: A -> B -> C by binding, C has unless; the problem names C and B."""
    problems = load_problems(
        tmp_path,
        [
            rule_dict("TEST-A", binding="TEST-B"),
            rule_dict("TEST-B", binding="TEST-C"),
            rule_dict("TEST-C", unless=["TEST-EX"]),
            rule_dict("TEST-EX"),
        ],
    )
    assert problems == (
        "TEST-C: used as binding by TEST-B, but has unless;"
        " unless on a binding rule is never applied",
    )


# ---- 3: (b) interpretations on a binding rule --------------------------------------------


def test_binding_rule_with_interpretations_refused(tmp_path: Path) -> None:
    """(b) A binding rule with interpretations is refused at load time."""
    problems = load_problems(
        tmp_path,
        [
            rule_dict("TEST-TOP", binding="TEST-SPLIT"),
            rule_dict("TEST-SPLIT", interpretations=readings()),
        ],
    )
    assert problems == (
        "TEST-SPLIT: used as binding by TEST-TOP, but has interpretations;"
        " a binding rule is evaluated by its trigger only",
    )


# ---- 4: (c) a clock on a helper rule ------------------------------------------------------

CLOCK_CASES = {
    "binding": (
        [
            rule_dict("TEST-TOP", binding="TEST-HELP"),
            rule_dict("TEST-HELP", clock=CLOCK_30),
        ],
        "TEST-HELP: used as binding by TEST-TOP, but has a clock;"
        " a helper rule's clock is never shown",
    ),
    "exemption": (
        [
            rule_dict("TEST-TOP", unless=["TEST-HELP"]),
            rule_dict("TEST-HELP", clock=CLOCK_30),
        ],
        "TEST-HELP: used as unless by TEST-TOP, but has a clock;"
        " a helper rule's clock is never shown",
    ),
    "exemption-of-exemption": (
        [
            rule_dict("TEST-TOP", unless=["TEST-EX"]),
            rule_dict("TEST-EX", unless=["TEST-HELP"]),
            rule_dict("TEST-HELP", clock=CLOCK_30),
        ],
        "TEST-HELP: used as unless by TEST-EX, but has a clock;"
        " a helper rule's clock is never shown",
    ),
}


@pytest.mark.parametrize("case", list(CLOCK_CASES))
def test_helper_rule_with_clock_refused(tmp_path: Path, case: str) -> None:
    """(c) A clock on a binding rule, an exemption, or an exemption's exemption is refused."""
    rules, message = CLOCK_CASES[case]
    assert load_problems(tmp_path, rules) == (message,)


# ---- 5: one helper, two users -------------------------------------------------------------


def test_one_helper_two_users_gives_two_problems(tmp_path: Path) -> None:
    """A helper named by two rules gives one problem per user."""
    problems = load_problems(
        tmp_path,
        [
            rule_dict("TEST-TOP1", binding="TEST-HELP"),
            rule_dict("TEST-TOP2", binding="TEST-HELP"),
            rule_dict("TEST-HELP", unless=["TEST-EX"]),
            rule_dict("TEST-EX"),
        ],
    )
    assert problems == (
        "TEST-HELP: used as binding by TEST-TOP1, but has unless;"
        " unless on a binding rule is never applied",
        "TEST-HELP: used as binding by TEST-TOP2, but has unless;"
        " unless on a binding rule is never applied",
    )


# ---- 6: everything in one RuleError -------------------------------------------------------


def test_all_problems_in_one_sorted_error(tmp_path: Path) -> None:
    """(a), (b), (c) and an unrelated problem are all listed in one sorted RuleError."""
    problems = load_problems(
        tmp_path,
        [
            rule_dict("TEST-TOP-A", binding="TEST-HA"),
            rule_dict("TEST-HA", unless=["TEST-HX"]),
            rule_dict("TEST-HX"),
            rule_dict("TEST-TOP-B", binding="TEST-HB"),
            rule_dict("TEST-HB", interpretations=readings()),
            rule_dict("TEST-TOP-C", unless=["TEST-HC"]),
            rule_dict("TEST-HC", clock=CLOCK_30),
            rule_dict("TEST-TOP-D", unless=["TEST-NOPE"]),
        ],
    )
    assert problems == (
        "TEST-HA: used as binding by TEST-TOP-A, but has unless;"
        " unless on a binding rule is never applied",
        "TEST-HB: used as binding by TEST-TOP-B, but has interpretations;"
        " a binding rule is evaluated by its trigger only",
        "TEST-HC: used as unless by TEST-TOP-C, but has a clock;"
        " a helper rule's clock is never shown",
        "TEST-TOP-D: unless names unknown rule TEST-NOPE",
    )


# ---- 7: still allowed ---------------------------------------------------------------------

ALLOWED_CASES = {
    "unless-on-exemption": [
        rule_dict("TEST-TOP", unless=["TEST-EX"]),
        rule_dict("TEST-EX", unless=["TEST-EX2"]),
        rule_dict("TEST-EX2"),
    ],
    "interpretations-on-exemption": [
        rule_dict("TEST-TOP", unless=["TEST-EX"]),
        rule_dict("TEST-EX", interpretations=readings()),
    ],
    "clock-on-top-level": [
        rule_dict("TEST-TOP", clock=CLOCK_30),
    ],
    "binding-with-binding": [
        rule_dict("TEST-TOP", binding="TEST-B"),
        rule_dict("TEST-B", binding="TEST-C"),
        rule_dict("TEST-C"),
    ],
}


@pytest.mark.parametrize("case", list(ALLOWED_CASES))
def test_still_allowed(tmp_path: Path, case: str) -> None:
    """These helper shapes are applied by the engine, so the loader accepts them."""
    rules = ALLOWED_CASES[case]
    pack = write_pack(tmp_path, rules)
    assert [rule.id for rule in pack.rules] == sorted(rule["id"] for rule in rules)
