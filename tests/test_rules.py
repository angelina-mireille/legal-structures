"""Tests for src/core/rules.py: rule schema, fail-closed pack loading, warnings.

Every rule here is synthetic (regime TEST, example.org URLs, invented citations).
"""

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from check_sources import check as check_sources
from export_schema import RULE_SCHEMA_PATH, build_rule_schema

from core.graph import EDGE_ENDPOINTS
from core.rules import NODE_KINDS, RuleError, load_rule_pack

TODAY = date(2026, 11, 8)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "rules"
FIXTURE_PACK = FIXTURES / "pack"
FIXTURE_SOURCES = FIXTURES / "sources"
SOURCE_URL = "https://example.org/test-source-1"
ZERO_HASH = "sha256:" + "0" * 64


def make_rule(**overrides: Any) -> dict[str, Any]:
    """Return a complete, valid synthetic rule as a dict, with top-level overrides."""
    rule: dict[str, Any] = {
        "id": "TEST-MADE-001",
        "version": "1.0.0",
        "regime": "TEST",
        "title": "Made-up test rule",
        "law_status": "in_force",
        "applies_to": "model",
        "binding": None,
        "trigger": {"fact": "test.fact_a"},
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
            "last_verified": TODAY,
            "verified_by": "user",
        },
        "clock": None,
    }
    rule.update(overrides)
    return rule


def write_rule(rules_dir: Path, rule: dict[str, Any], name: str | None = None) -> Path:
    """Write a rule dict as YAML; the filename defaults to '<id>.yaml'."""
    path = rules_dir / (name or f"{rule['id']}.yaml")
    path.write_text(yaml.safe_dump(rule, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def pack(tmp_path: Path) -> tuple[Path, Path]:
    """An empty rules dir and a sources dir holding the synthetic test source."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    sources_dir = tmp_path / "sources"
    shutil.copytree(FIXTURE_SOURCES, sources_dir)
    return rules_dir, sources_dir


def load(dirs: tuple[Path, Path], today: date = TODAY):
    """Load the pack in dirs."""
    return load_rule_pack(dirs[0], dirs[1], today)


def load_error(dirs: tuple[Path, Path], today: date = TODAY) -> str:
    """Load the pack, expect RuleError, and return its message."""
    with pytest.raises(RuleError) as excinfo:
        load(dirs, today)
    return str(excinfo.value)


def nested_not(levels: int) -> dict[str, Any]:
    """A fact leaf wrapped in `levels` not-nodes (depth = levels + 1)."""
    node: dict[str, Any] = {"fact": "test.fact_a"}
    for _ in range(levels):
        node = {"not": node}
    return node


def warning_pairs(rule_pack) -> list[tuple[str, str]]:
    """The pack's warnings as (rule_id, code) pairs."""
    return [(w.rule_id, w.code) for w in rule_pack.warnings]


# ---- Done-when: missing citation, source URL, verification date ------------


def test_valid_made_rule_loads(pack: tuple[Path, Path]) -> None:
    """The make_rule baseline is valid, so every failure below is caused by its override."""
    write_rule(pack[0], make_rule())
    assert [r.id for r in load(pack).rules] == ["TEST-MADE-001"]


def test_missing_citation_fails(pack: tuple[Path, Path]) -> None:
    """A rule without a citation does not load."""
    rule = make_rule()
    del rule["citation"]
    write_rule(pack[0], rule)
    message = load_error(pack)
    assert "TEST-MADE-001.yaml" in message and "citation" in message


def test_missing_source_url_fails(pack: tuple[Path, Path]) -> None:
    """A citation without source_url does not load."""
    rule = make_rule()
    del rule["citation"]["source_url"]
    write_rule(pack[0], rule)
    assert "citation.source_url" in load_error(pack)


def test_missing_last_verified_fails(pack: tuple[Path, Path]) -> None:
    """A verification block without last_verified does not load."""
    rule = make_rule()
    del rule["verification"]["last_verified"]
    write_rule(pack[0], rule)
    assert "verification.last_verified" in load_error(pack)


# ---- Staleness ---------------------------------------------------------------


def with_last_verified(day: date) -> dict[str, Any]:
    """A made rule last verified on day."""
    rule = make_rule()
    rule["verification"]["last_verified"] = day
    return rule


def test_90_days_old_has_no_warning(pack: tuple[Path, Path]) -> None:
    """Exactly 90 days old is not stale."""
    write_rule(pack[0], with_last_verified(TODAY - timedelta(days=90)))
    assert load(pack).warnings == ()


def test_91_days_old_is_stale(pack: tuple[Path, Path]) -> None:
    """91 days old loads, with one STALE warning."""
    write_rule(pack[0], with_last_verified(TODAY - timedelta(days=91)))
    rule_pack = load(pack)
    assert [r.id for r in rule_pack.rules] == ["TEST-MADE-001"]
    assert warning_pairs(rule_pack) == [("TEST-MADE-001", "STALE")]


def test_last_verified_after_today_fails(pack: tuple[Path, Path]) -> None:
    """A verification date in the future is an error, not a warning."""
    write_rule(pack[0], with_last_verified(TODAY + timedelta(days=1)))
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "after today" in message


# ---- Shape errors ------------------------------------------------------------


def test_unknown_field_fails(pack: tuple[Path, Path]) -> None:
    """A field the schema does not know is rejected."""
    write_rule(pack[0], make_rule(notes="extra"))
    assert "notes" in load_error(pack)


def test_trigger_and_interpretations_together_fail(pack: tuple[Path, Path]) -> None:
    """A rule cannot have both a trigger and interpretations."""
    interpretations = [
        {"id": "reading_a", "summary": "A", "trigger": {"fact": "test.fact_a"}},
        {"id": "reading_b", "summary": "B", "trigger": {"fact": "test.fact_b"}},
    ]
    write_rule(pack[0], make_rule(interpretations=interpretations))
    assert "exactly one of trigger or interpretations" in load_error(pack)


def test_neither_trigger_nor_interpretations_fails(pack: tuple[Path, Path]) -> None:
    """A rule must have a trigger or interpretations."""
    rule = make_rule()
    del rule["trigger"]
    write_rule(pack[0], rule)
    assert "exactly one of trigger or interpretations" in load_error(pack)


def test_single_interpretation_fails(pack: tuple[Path, Path]) -> None:
    """Interpretations need at least two items."""
    rule = make_rule(
        interpretations=[{"id": "reading_a", "summary": "A", "trigger": {"fact": "test.x"}}]
    )
    del rule["trigger"]
    write_rule(pack[0], rule)
    assert "interpretations" in load_error(pack)


def test_duplicate_interpretation_id_fails(pack: tuple[Path, Path]) -> None:
    """Interpretation ids are unique within a rule."""
    item = {"id": "reading_a", "summary": "A", "trigger": {"fact": "test.x"}}
    rule = make_rule(interpretations=[item, dict(item)])
    del rule["trigger"]
    write_rule(pack[0], rule)
    assert "duplicate interpretation id" in load_error(pack)


def test_min_grade_missing_fails(pack: tuple[Path, Path]) -> None:
    """'missing' is not a valid min_grade."""
    write_rule(pack[0], make_rule(trigger={"fact": "test.fact_a", "min_grade": "missing"}))
    assert "min_grade" in load_error(pack)


def test_applies_to_widget_fails(pack: tuple[Path, Path]) -> None:
    """applies_to must be a graph node kind."""
    write_rule(pack[0], make_rule(applies_to="widget"))
    assert "applies_to" in load_error(pack)


def test_depth_8_loads(pack: tuple[Path, Path]) -> None:
    """A leaf inside 7 not-nodes is depth 8, the maximum."""
    write_rule(pack[0], make_rule(trigger=nested_not(7)))
    assert len(load(pack).rules) == 1


def test_depth_9_fails(pack: tuple[Path, Path]) -> None:
    """A leaf inside 8 not-nodes is depth 9 and fails."""
    write_rule(pack[0], make_rule(trigger=nested_not(8)))
    assert "depth" in load_error(pack)


def test_depth_9_inside_interpretation_fails(pack: tuple[Path, Path]) -> None:
    """The depth limit also applies to interpretation triggers."""
    rule = make_rule(
        interpretations=[
            {"id": "reading_a", "summary": "A", "trigger": {"fact": "test.x"}},
            {"id": "reading_b", "summary": "B", "trigger": nested_not(8)},
        ]
    )
    del rule["trigger"]
    write_rule(pack[0], rule)
    assert "depth" in load_error(pack)


def test_expression_with_two_operators_fails(pack: tuple[Path, Path]) -> None:
    """An expression node is exactly one of all, any, not or fact."""
    trigger = {"all": [{"fact": "test.a"}], "any": [{"fact": "test.b"}]}
    write_rule(pack[0], make_rule(trigger=trigger))
    assert "TEST-MADE-001.yaml" in load_error(pack)


def test_empty_all_fails(pack: tuple[Path, Path]) -> None:
    """all needs at least one item."""
    write_rule(pack[0], make_rule(trigger={"all": []}))
    assert "TEST-MADE-001.yaml" in load_error(pack)


# ---- Clock amount -------------------------------------------------------------


def write_with_amount(rules_dir: Path, amount_text: str) -> None:
    """Write a made rule whose clock amount is the given raw YAML text."""
    rule = make_rule(clock={"amount": "AMOUNT", "unit": "hours", "trigger": "test event"})
    text = yaml.safe_dump(rule, sort_keys=False).replace("amount: AMOUNT", f"amount: {amount_text}")
    (rules_dir / "TEST-MADE-001.yaml").write_text(text, encoding="utf-8")


def test_clock_integer_amount_loads(pack: tuple[Path, Path]) -> None:
    """An unquoted whole number loads."""
    write_with_amount(pack[0], "72")
    clock = load(pack).rules[0].clock
    assert clock is not None and clock.amount == 72


@pytest.mark.parametrize("amount_text", ["72.5", "72.0", "7.2e+1", "true", '"72"', "0"])
def test_clock_bad_amount_fails(pack: tuple[Path, Path], amount_text: str) -> None:
    """Decimals (even whole-valued), booleans, strings and zero are rejected."""
    write_with_amount(pack[0], amount_text)
    assert "clock.amount" in load_error(pack)


def test_clock_bad_unit_fails(pack: tuple[Path, Path]) -> None:
    """unit is hours, calendar_days or business_days."""
    write_rule(pack[0], make_rule(clock={"amount": 3, "unit": "weeks", "trigger": "test event"}))
    assert "clock.unit" in load_error(pack)


# ---- Source records ------------------------------------------------------------


def write_source(sources_dir: Path, name: str, text: str) -> None:
    """Write a raw source record file."""
    (sources_dir / name).write_text(text, encoding="utf-8")


def cite(source_id: str, url: str = SOURCE_URL) -> dict[str, Any]:
    """A made rule citing source_id at url."""
    rule = make_rule()
    rule["citation"]["source_id"] = source_id
    rule["citation"]["source_url"] = url
    return rule


def test_source_not_found_fails(pack: tuple[Path, Path]) -> None:
    """A source_id with no record file fails, naming the rule."""
    write_rule(pack[0], cite("test-source-9"))
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "source not found" in message


def test_source_url_mismatch_fails(pack: tuple[Path, Path]) -> None:
    """source_url must equal the record's url exactly."""
    write_rule(pack[0], cite("test-source-1", "https://example.org/other"))
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "source_url mismatch" in message


def test_source_record_missing_url_fails(pack: tuple[Path, Path]) -> None:
    """A record with no url is reported as malformed, naming the rule."""
    write_source(pack[1], "test-source-2.yaml", "id: test-source-2\ntitle: x\n")
    write_rule(pack[0], cite("test-source-2"))
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "malformed" in message


@pytest.mark.parametrize(
    "text",
    ["id: [unclosed\n", "id: a\nid: b\n", "- a\n- b\n", "url: https://example.org/x\n"],
    ids=["not-yaml", "duplicate-key", "not-mapping", "missing-id"],
)
def test_malformed_source_record_is_a_rule_error(pack: tuple[Path, Path], text: str) -> None:
    """Any broken record gives a RuleError naming the rule, never a raw exception."""
    write_source(pack[1], "test-source-2.yaml", text)
    write_rule(pack[0], cite("test-source-2"))
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "malformed" in message


def test_source_record_id_mismatch_fails(pack: tuple[Path, Path]) -> None:
    """A record file whose id differs from its name is an id mismatch, not 'not found'."""
    write_source(pack[1], "test-source-2.yaml", f"id: test-source-3\nurl: {SOURCE_URL}\n")
    write_rule(pack[0], cite("test-source-2"))
    message = load_error(pack)
    assert "source record id mismatch" in message and "source not found" not in message


@pytest.mark.parametrize("source_id", ["../test-source-1", "a/b", "a..b"])
def test_source_id_pattern_blocks_paths(pack: tuple[Path, Path], source_id: str) -> None:
    """source_id cannot contain '/' or '..'."""
    write_rule(pack[0], cite(source_id))
    assert "citation.source_id" in load_error(pack)


# ---- References between rules --------------------------------------------------


def test_unless_unknown_rule_fails(pack: tuple[Path, Path]) -> None:
    """unless must name a rule in the pack."""
    write_rule(pack[0], make_rule(unless=["TEST-NOPE-001"]))
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "unknown rule TEST-NOPE-001" in message


def test_binding_unknown_rule_fails(pack: tuple[Path, Path]) -> None:
    """binding must name a rule in the pack."""
    write_rule(pack[0], make_rule(binding="TEST-NOPE-001"))
    assert "unknown rule TEST-NOPE-001" in load_error(pack)


def test_cross_regime_reference_fails(pack: tuple[Path, Path]) -> None:
    """binding and unless may only name rules of the same regime."""
    write_rule(pack[0], make_rule(unless=["TEST-OTHER-001"]))
    write_rule(pack[0], make_rule(id="TEST-OTHER-001", regime="TEST-OTHER"))
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "different regime" in message


def test_self_reference_fails(pack: tuple[Path, Path]) -> None:
    """A rule cannot name itself."""
    write_rule(pack[0], make_rule(unless=["TEST-MADE-001"]))
    assert "names itself" in load_error(pack)


def test_unless_cycle_fails(pack: tuple[Path, Path]) -> None:
    """Two rules naming each other in unless form a cycle."""
    write_rule(pack[0], make_rule(id="TEST-A-001", unless=["TEST-B-001"]))
    write_rule(pack[0], make_rule(id="TEST-B-001", unless=["TEST-A-001"]))
    message = load_error(pack)
    assert "cycle" in message and "TEST-A-001" in message and "TEST-B-001" in message


def test_binding_unless_cycle_fails(pack: tuple[Path, Path]) -> None:
    """A cycle that mixes binding and unless is also caught."""
    write_rule(pack[0], make_rule(id="TEST-A-001", binding="TEST-B-001"))
    write_rule(pack[0], make_rule(id="TEST-B-001", unless=["TEST-A-001"]))
    assert "cycle" in load_error(pack)


def test_filename_not_matching_id_fails(pack: tuple[Path, Path]) -> None:
    """A rule's file must be named '<id>.yaml'."""
    write_rule(pack[0], make_rule(), name="TEST-WRONG-001.yaml")
    message = load_error(pack)
    assert "TEST-MADE-001" in message and "filename" in message


def test_duplicate_rule_id_fails(pack: tuple[Path, Path]) -> None:
    """Two files carrying the same id fail."""
    write_rule(pack[0], make_rule())
    write_rule(pack[0], make_rule(), name="TEST-COPY-001.yaml")
    assert "duplicate id" in load_error(pack)


# ---- Fail-closed loading ---------------------------------------------------------


def test_two_bad_files_raise_one_error_naming_both(pack: tuple[Path, Path]) -> None:
    """All per-file problems come back together in one RuleError."""
    write_rule(pack[0], make_rule(id="TEST-A-001", applies_to="widget"))
    write_rule(pack[0], make_rule(id="TEST-B-001", surprise=True))
    write_rule(pack[0], make_rule(id="TEST-C-001"))
    with pytest.raises(RuleError) as excinfo:
        load(pack)
    message = str(excinfo.value)
    assert "TEST-A-001.yaml" in message and "TEST-B-001.yaml" in message
    assert "TEST-C-001" not in message
    assert len(excinfo.value.problems) == 2


def test_duplicate_yaml_key_fails(pack: tuple[Path, Path]) -> None:
    """A repeated key is rejected, not silently overwritten."""
    text = yaml.safe_dump(make_rule(), sort_keys=False) + "effect: TEST_OTHER\n"
    (pack[0] / "TEST-MADE-001.yaml").write_text(text, encoding="utf-8")
    message = load_error(pack)
    assert "TEST-MADE-001.yaml" in message and "duplicate key" in message


def test_pack_checks_wait_until_every_file_parses(pack: tuple[Path, Path]) -> None:
    """While any file fails to parse, pack checks (such as unknown references) are not run."""
    write_rule(pack[0], make_rule(id="TEST-A-001", unless=["TEST-NOPE-001"]))
    write_rule(pack[0], make_rule(id="TEST-B-001", applies_to="widget"))
    message = load_error(pack)
    assert "TEST-B-001.yaml" in message and "unknown rule" not in message


def test_error_keeps_original_cause(pack: tuple[Path, Path]) -> None:
    """A per-file RuleError is raised 'from' the underlying error."""
    write_rule(pack[0], make_rule(applies_to="widget"))
    with pytest.raises(RuleError) as excinfo:
        load(pack)
    assert excinfo.value.__cause__ is not None


# ---- Directory contents --------------------------------------------------------------


def test_yml_file_fails(pack: tuple[Path, Path]) -> None:
    """A .yml file is not skipped; it is an error."""
    write_rule(pack[0], make_rule())
    write_rule(pack[0], make_rule(id="TEST-YML-001"), name="TEST-YML-001.yml")
    assert "TEST-YML-001.yml" in load_error(pack)


def test_subfolder_fails(pack: tuple[Path, Path]) -> None:
    """A subfolder in the rules dir is an error."""
    write_rule(pack[0], make_rule())
    (pack[0] / "nested").mkdir()
    assert "nested" in load_error(pack)


def test_empty_pack_dir_fails(pack: tuple[Path, Path]) -> None:
    """An empty rules dir is an error, not an empty pack."""
    assert "no rule files" in load_error(pack)


def test_only_ignored_files_is_empty(pack: tuple[Path, Path]) -> None:
    """A dir holding only .DS_Store and .gitkeep is still an empty pack."""
    (pack[0] / ".DS_Store").write_bytes(b"\x00")
    (pack[0] / ".gitkeep").write_text("", encoding="utf-8")
    assert "no rule files" in load_error(pack)


def test_ds_store_is_ignored(pack: tuple[Path, Path]) -> None:
    """.DS_Store next to valid rules does not stop the pack loading."""
    write_rule(pack[0], make_rule())
    (pack[0] / ".DS_Store").write_bytes(b"\x00\x01")
    assert len(load(pack).rules) == 1


def test_other_hidden_file_fails(pack: tuple[Path, Path]) -> None:
    """Any other hidden file, such as .notes, is an error."""
    write_rule(pack[0], make_rule())
    (pack[0] / ".notes").write_text("todo\n", encoding="utf-8")
    assert ".notes" in load_error(pack)


def test_missing_rules_dir_fails(tmp_path: Path) -> None:
    """A rules dir that does not exist raises RuleError."""
    with pytest.raises(RuleError):
        load_rule_pack(tmp_path / "absent", FIXTURE_SOURCES, TODAY)


def test_today_must_be_a_date_not_datetime() -> None:
    """Passing a datetime as today is a calling mistake."""
    with pytest.raises(TypeError):
        load_rule_pack(FIXTURE_PACK, FIXTURE_SOURCES, datetime(2026, 11, 8, 12, 0))


# ---- The fixture pack -----------------------------------------------------------------


def test_fixture_pack_loads_with_expected_warnings() -> None:
    """The four fixture rules load, ordered by id, with exactly one NOT_VERIFIED warning."""
    rule_pack = load_rule_pack(FIXTURE_PACK, FIXTURE_SOURCES, TODAY)
    assert [r.id for r in rule_pack.rules] == [
        "TEST-BIND-001",
        "TEST-EXEMPT-001",
        "TEST-RULE-001",
        "TEST-SPLIT-001",
    ]
    assert warning_pairs(rule_pack) == [("TEST-SPLIT-001", "NOT_VERIFIED")]


def test_fixture_clock_is_72_hours() -> None:
    """TEST-RULE-001's clock loads as 72 hours."""
    rules = {r.id: r for r in load_rule_pack(FIXTURE_PACK, FIXTURE_SOURCES, TODAY).rules}
    clock = rules["TEST-RULE-001"].clock
    assert clock is not None and (clock.amount, clock.unit) == (72, "hours")


def test_fixture_split_has_two_interpretations_and_is_proposed() -> None:
    """TEST-SPLIT-001 is proposed, unverified, with two interpretations."""
    rules = {r.id: r for r in load_rule_pack(FIXTURE_PACK, FIXTURE_SOURCES, TODAY).rules}
    split = rules["TEST-SPLIT-001"]
    assert split.law_status == "proposed"
    assert split.trigger is None
    assert split.interpretations is not None
    assert [i.id for i in split.interpretations] == ["reading_a", "reading_b"]


def test_rules_ordered_by_id_not_file_order(pack: tuple[Path, Path]) -> None:
    """RulePack.rules is sorted by id, whatever order the files were written in."""
    for rule_id in ["TEST-C-001", "TEST-A-001", "TEST-B-001"]:
        write_rule(pack[0], make_rule(id=rule_id))
    assert [r.id for r in load(pack).rules] == ["TEST-A-001", "TEST-B-001", "TEST-C-001"]


def test_guard_fixture_rules_are_synthetic() -> None:
    """Every fixture rule is regime TEST with an example.org source URL."""
    paths = sorted(FIXTURE_PACK.glob("*.yaml"))
    assert len(paths) == 4
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["regime"] == "TEST", path.name
        assert data["citation"]["source_url"].startswith("https://example.org/"), path.name


def test_fixture_source_passes_check_sources() -> None:
    """The synthetic source record passes the repo's own source-record checks."""
    record = yaml.safe_load((FIXTURE_SOURCES / "test-source-1.yaml").read_text(encoding="utf-8"))
    assert check_sources(FIXTURE_SOURCES, record["retrieved"]) == []


# ---- Node kinds and schema ---------------------------------------------------------------


def test_node_kinds_match_graph() -> None:
    """NODE_KINDS equals the set of node kinds graph.py's edges connect."""
    kinds_in_edges: set[str] = set()
    for allowed_from, allowed_to in EDGE_ENDPOINTS.values():
        kinds_in_edges |= allowed_from | allowed_to
    assert set(NODE_KINDS) == kinds_in_edges == {"entity", "model", "dataset", "software"}


def test_committed_rule_schema_matches_model() -> None:
    """schemas/rule.schema.json is exactly what export_schema produces now."""
    assert RULE_SCHEMA_PATH.read_text(encoding="utf-8") == build_rule_schema()
