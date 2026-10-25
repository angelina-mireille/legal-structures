"""Check the source library: flag records that are stale or missing a field.

Usage: uv run python scripts/check_sources.py [--sources DIR] [--today YYYY-MM-DD]

Exits 0 when every record is clean and 1 when anything is flagged. In GitHub
Actions each problem is also printed as a ::warning:: annotation.
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

MAX_AGE_DAYS = 90
DEFAULT_SOURCES = Path(__file__).resolve().parent.parent / "sources"


class SourceRecord(BaseModel):
    """One primary source: where it came from, when, and the hash of the bytes retrieved."""

    id: str
    title: str
    publisher: str
    url: str
    retrieved: date
    sha256: str
    stored: bool
    text_file: str | None


FIELDS: tuple[str, ...] = tuple(SourceRecord.model_fields)


def load_records(sources: Path) -> tuple[dict[str, dict], list[str]]:
    """Read every *.yaml in sources; return {filename: data} and problems for unreadable files."""
    records: dict[str, dict] = {}
    problems: list[str] = []
    for path in sorted(sources.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: not valid YAML ({exc.__class__.__name__})")
            continue
        if not isinstance(data, dict):
            problems.append(f"{path.name}: not a record (expected a mapping of fields)")
            continue
        records[path.name] = data
    return records, problems


def missing_fields(data: dict) -> list[str]:
    """Return the fields that are absent or empty; text_file may be null only if not stored."""
    missing = []
    for field in FIELDS:
        value = data.get(field)
        if field == "text_file":
            if field not in data or (value in (None, "") and data.get("stored") is True):
                missing.append(field)
        elif value is None or value == "":
            missing.append(field)
    return missing


def is_stale(retrieved: date, today: date, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """True if retrieved is more than max_age_days before today."""
    return today - retrieved > timedelta(days=max_age_days)


def check_record(name: str, data: dict, root: Path, today: date) -> list[str]:
    """Return the problems with one record; text_file is resolved relative to root."""
    missing = missing_fields(data)
    if missing:
        return [f"{name}: missing field '{field}'" for field in missing]
    try:
        record = SourceRecord.model_validate(data)
    except ValidationError as exc:
        return [
            f"{name}: invalid '{'.'.join(map(str, err['loc']))}' ({err['msg']})"
            for err in exc.errors()
        ]
    problems = []
    if record.stored and record.text_file and not (root / record.text_file).is_file():
        problems.append(f"{name}: text_file '{record.text_file}' does not exist")
    if is_stale(record.retrieved, today):
        problems.append(f"{name}: retrieved {record.retrieved} is older than {MAX_AGE_DAYS} days")
    return problems


def check(sources: Path, today: date) -> list[str]:
    """Return every problem in sources; text_file paths are relative to its parent."""
    records, problems = load_records(sources)
    for name, data in records.items():
        problems.extend(check_record(name, data, sources.parent, today))
    return problems


def main(argv: list[str] | None = None) -> int:
    """Run the check, print the results, and return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)

    problems = check(args.sources, args.today)
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    for problem in problems:
        print(f"::warning::{problem}" if in_ci else problem)
    count = len(list(args.sources.glob("*.yaml")))
    if problems:
        print(f"{len(problems)} problem(s) in {count} source record(s).")
        return 1
    print(f"All {count} source records OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
