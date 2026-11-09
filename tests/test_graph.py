"""Tests for src/core/graph.py: the fact graph, its loader and its JSON Schema."""

import json
import typing
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from export_schema import SCHEMA_PATH, build_schema

from core.graph import EDGE_ENDPOINTS, Edge, GraphError, OwnsEdge, load_graph

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "graph"
VALID = sorted((FIXTURES / "valid").glob("*.yaml"))
INVALID = sorted((FIXTURES / "invalid").glob("*.yaml"))

# Each invalid file must fail for its own reason. Fragments come from the fixture
# (a bad value, an id, a field name) or from our own messages, never pydantic's wording.
INVALID_EXPECTED: dict[str, str] = {
    "01-unknown-top-level-field.yaml": "notes",
    "02-node-extra-field.yaml": "nationality",
    "03-unknown-node-kind.yaml": "checkpoint",
    "04-duplicate-id.yaml": "duplicate id: base-1",
    "05-edge-to-missing-node.yaml": "edge e-1: 'to' node base-9 does not exist",
    "06-derived-from-entity.yaml": "edge e-1 (derived_from): from-node dev-co-1 has kind entity",
    "07-derived-from-bad-method.yaml": "'distill'",
    "08-grade-missing.yaml": "a stated fact cannot be graded missing; leave it out instead",
    "09-owns-over-100.yaml": "120",
    "10-derived-from-cycle.yaml": "lineage cycle: model-1 -> model-2 -> model-1",
}

FORBIDDEN_PROPERTIES = {
    "name",
    "label",
    "nationality",
    "ethnicity",
    "citizenship",
    "language",
    "country",
}

OWNS_TEMPLATE = """\
schema_version: 1
graph_id: inline-owns
nodes:
  - id: parent-co-1
    kind: entity
    entity_type: organisation
    evidence: {{grade: declared, source_ref: s-1, recorded_by: user, recorded_on: 2026-11-01}}
  - id: dev-co-1
    kind: entity
    entity_type: organisation
    evidence: {{grade: declared, source_ref: s-1, recorded_by: user, recorded_on: 2026-11-01}}
edges:
  - id: e-1
    kind: owns
    from: parent-co-1
    to: dev-co-1
    percent: {percent}
    basis: equity
    evidence: {{grade: declared, source_ref: s-1, recorded_by: user, recorded_on: 2026-11-01}}
"""


def write(tmp_path: Path, text: str, name: str = "graph.yaml") -> Path:
    """Write text to a YAML file in tmp_path and return its path."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def property_names(schema: Any) -> set[str]:
    """Collect every key of every "properties" object anywhere in a JSON Schema."""
    found: set[str] = set()
    if isinstance(schema, dict):
        props = schema.get("properties")
        if isinstance(props, dict):
            found.update(props)
        for value in schema.values():
            found |= property_names(value)
    elif isinstance(schema, list):
        for item in schema:
            found |= property_names(item)
    return found


def test_fixture_counts() -> None:
    """There are exactly 10 valid and 10 invalid fixtures, and every invalid one is mapped."""
    assert len(VALID) == 10
    assert {p.name for p in INVALID} == set(INVALID_EXPECTED)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixture_loads(path: Path) -> None:
    """Each valid fixture loads into a Graph."""
    graph = load_graph(path)
    assert graph.nodes


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_fixture_fails_for_its_reason(path: Path) -> None:
    """Each invalid fixture raises GraphError carrying its expected fragment."""
    with pytest.raises(GraphError) as excinfo:
        load_graph(path)
    assert INVALID_EXPECTED[path.name] in str(excinfo.value)


def test_graph_error_keeps_original_cause() -> None:
    """GraphError is raised 'from' the underlying error, so the cause stays attached."""
    with pytest.raises(GraphError) as excinfo:
        load_graph(FIXTURES / "invalid" / "08-grade-missing.yaml")
    assert excinfo.value.__cause__ is not None


def test_missing_file_raises_graph_error(tmp_path: Path) -> None:
    """A file that does not exist raises GraphError, not OSError."""
    with pytest.raises(GraphError):
        load_graph(tmp_path / "absent.yaml")


def test_duplicate_yaml_key_rejected(tmp_path: Path) -> None:
    """A repeated mapping key fails instead of silently keeping the last value."""
    text = "schema_version: 1\ngraph_id: dup-key\ngraph_id: dup-key-again\nnodes: []\nedges: []\n"
    with pytest.raises(GraphError) as excinfo:
        load_graph(write(tmp_path, text))
    assert "graph_id" in str(excinfo.value)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_round_trip(path: Path, tmp_path: Path) -> None:
    """Load, dump by alias to YAML, load again: the two graphs are equal."""
    first = load_graph(path)
    dumped = yaml.safe_dump(first.model_dump(by_alias=True, mode="json"), sort_keys=False)
    second = load_graph(write(tmp_path, dumped))
    assert second == first


def test_percent_read_exactly_as_written(tmp_path: Path) -> None:
    """A YAML float percent becomes the exact Decimal written, never a rounded float."""
    graph = load_graph(write(tmp_path, OWNS_TEMPLATE.format(percent="50.0000000000000001")))
    edge = graph.edges[0]
    assert isinstance(edge, OwnsEdge)
    assert edge.percent == Decimal("50.0000000000000001")
    assert edge.percent > Decimal("50")


@pytest.mark.parametrize("percent", [".nan", ".inf"])
def test_percent_nan_and_inf_rejected(tmp_path: Path, percent: str) -> None:
    """Not-a-number and infinity are not valid ownership percents."""
    with pytest.raises(GraphError) as excinfo:
        load_graph(write(tmp_path, OWNS_TEMPLATE.format(percent=percent)))
    assert "percent" in str(excinfo.value)


def test_committed_schema_matches_model() -> None:
    """schemas/graph.schema.json is exactly what export_schema produces now."""
    assert SCHEMA_PATH.read_text(encoding="utf-8") == build_schema()


def test_schema_uses_from_and_to() -> None:
    """Edges appear in the JSON Schema with the YAML names "from" and "to"."""
    names = property_names(json.loads(build_schema()))
    assert {"from", "to"} <= names
    assert "from_" not in names


def test_schema_has_no_identity_properties() -> None:
    """No property in the schema is a name, label or identity-group field."""
    names = property_names(json.loads(build_schema()))
    assert names.isdisjoint(FORBIDDEN_PROPERTIES)


def test_edge_endpoints_cover_exactly_the_edge_kinds() -> None:
    """EDGE_ENDPOINTS has one row per edge kind in the Edge union, no more, no fewer."""
    union = typing.get_args(Edge)[0]
    kinds = {
        typing.get_args(member.model_fields["kind"].annotation)[0]
        for member in typing.get_args(union)
    }
    assert set(EDGE_ENDPOINTS) == kinds
