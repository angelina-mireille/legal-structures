"""Tests for scripts/check_sources.py: staleness and missing-field checks."""

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from check_sources import FIELDS, check, is_stale, main

TODAY = date(2026, 10, 25)
REPO_SOURCES = Path(__file__).resolve().parent.parent / "sources"


def make_record(**overrides: object) -> dict[str, object]:
    """Return a complete, fresh, unstored source record with optional overrides."""
    record: dict[str, object] = {
        "id": "example-source",
        "title": "Example source",
        "publisher": "Example publisher",
        "url": "https://example.org/source",
        "retrieved": TODAY,
        "sha256": "0" * 64,
        "stored": False,
        "text_file": None,
    }
    record.update(overrides)
    return record


def write_record(sources: Path, record: dict[str, object], name: str = "example.yaml") -> Path:
    """Write a record as YAML into the sources directory and return its path."""
    sources.mkdir(parents=True, exist_ok=True)
    path = sources / name
    path.write_text(yaml.safe_dump(record), encoding="utf-8")
    return path


@pytest.fixture
def sources(tmp_path: Path) -> Path:
    """An empty sources/ directory inside a temporary repo root."""
    path = tmp_path / "sources"
    path.mkdir()
    return path


def test_complete_fresh_record_has_no_problems(sources: Path) -> None:
    """A complete record retrieved today is clean."""
    write_record(sources, make_record())
    assert check(sources, TODAY) == []


def test_stored_record_with_existing_file_has_no_problems(sources: Path) -> None:
    """A stored record whose text file exists is clean."""
    (sources / "text").mkdir()
    (sources / "text" / "example.pdf").write_bytes(b"%PDF")
    write_record(sources, make_record(stored=True, text_file="sources/text/example.pdf"))
    assert check(sources, TODAY) == []


def test_is_stale_boundary() -> None:
    """91 days old is stale; 90 days old is not."""
    assert is_stale(TODAY - timedelta(days=91), TODAY)
    assert not is_stale(TODAY - timedelta(days=90), TODAY)


def test_stale_record_is_flagged(sources: Path) -> None:
    """A record retrieved 91 days ago is reported as stale."""
    write_record(sources, make_record(retrieved=TODAY - timedelta(days=91)))
    problems = check(sources, TODAY)
    assert len(problems) == 1
    assert "older than 90 days" in problems[0]


@pytest.mark.parametrize("field", FIELDS)
def test_missing_field_is_flagged(sources: Path, field: str) -> None:
    """Removing any one field is reported, naming that field."""
    record = make_record()
    del record[field]
    write_record(sources, record)
    problems = check(sources, TODAY)
    assert any(field in p and "missing" in p for p in problems)


@pytest.mark.parametrize("field", ["id", "title", "publisher", "url", "sha256"])
def test_empty_field_is_flagged(sources: Path, field: str) -> None:
    """An empty string counts as missing."""
    write_record(sources, make_record(**{field: ""}))
    problems = check(sources, TODAY)
    assert any(field in p and "missing" in p for p in problems)


def test_stored_without_text_file_is_flagged(sources: Path) -> None:
    """stored: true with text_file: null is reported."""
    write_record(sources, make_record(stored=True, text_file=None))
    problems = check(sources, TODAY)
    assert any("text_file" in p for p in problems)


def test_stored_with_nonexistent_text_file_is_flagged(sources: Path) -> None:
    """stored: true whose text_file path does not exist is reported."""
    write_record(sources, make_record(stored=True, text_file="sources/text/nowhere.pdf"))
    problems = check(sources, TODAY)
    assert any("does not exist" in p for p in problems)


def test_bad_date_is_flagged_not_crash(sources: Path) -> None:
    """A retrieved value that is not a date is reported, not raised."""
    write_record(sources, make_record(retrieved="last spring"))
    problems = check(sources, TODAY)
    assert any("retrieved" in p for p in problems)


def test_broken_yaml_is_flagged_not_crash(sources: Path) -> None:
    """A file that is not valid YAML is reported, not raised."""
    (sources / "broken.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    problems = check(sources, TODAY)
    assert any("broken.yaml" in p for p in problems)


def test_non_mapping_yaml_is_flagged(sources: Path) -> None:
    """A YAML file that is a list, not a record, is reported."""
    (sources / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    problems = check(sources, TODAY)
    assert any("list.yaml" in p for p in problems)


def test_main_exit_codes(sources: Path) -> None:
    """main returns 0 when clean and 1 when anything is flagged."""
    write_record(sources, make_record())
    assert main(["--sources", str(sources), "--today", TODAY.isoformat()]) == 0
    write_record(sources, make_record(retrieved=TODAY - timedelta(days=91)), name="old.yaml")
    assert main(["--sources", str(sources), "--today", TODAY.isoformat()]) == 1


def test_repo_records_have_every_field() -> None:
    """The real records in sources/ are complete (staleness ignored by pinning today)."""
    records = sorted(REPO_SOURCES.glob("*.yaml"))
    assert len(records) == 8
    for path in records:
        retrieved = yaml.safe_load(path.read_text(encoding="utf-8"))["retrieved"]
        assert check(REPO_SOURCES, retrieved) == [], path.name
