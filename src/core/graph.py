"""Fact graph: nodes, edges and evidence, loaded from YAML.

The graph records facts only (what was built from what, who owns or controls whom,
and how well each fact is evidenced). It holds no legal tests, thresholds, readings
or source names; those belong to rules.

Edge direction runs from the dependent thing to its source: "B distilled_from T"
is written from: B, to: T.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Final, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    WithJsonSchema,
    field_validator,
    model_validator,
)
from yaml.constructor import ConstructorError

# Edge kind -> (allowed from-node kinds, allowed to-node kinds).
# Perimeter kinds (D1) are added here as new rows.
EDGE_ENDPOINTS: Final[dict[str, tuple[frozenset[str], frozenset[str]]]] = {
    "derived_from": (frozenset({"model"}), frozenset({"model"})),
    "distilled_from": (frozenset({"model"}), frozenset({"model"})),
    "trained_on_output_of": (frozenset({"model", "dataset"}), frozenset({"model"})),
    "trained_on": (frozenset({"model"}), frozenset({"dataset"})),
    "uses_code_from": (frozenset({"model", "software"}), frozenset({"software"})),
    "developed_with_tool": (
        frozenset({"model", "dataset", "software"}),
        frozenset({"model", "software"}),
    ),
    "incorporates": (frozenset({"software"}), frozenset({"model", "dataset", "software"})),
    "developed_by": (frozenset({"model", "dataset", "software"}), frozenset({"entity"})),
    "owns": (frozenset({"entity"}), frozenset({"entity"})),
    "controls": (frozenset({"entity"}), frozenset({"entity"})),
}

# Edge kinds that must not form a cycle (owns and controls may be circular).
LINEAGE_KINDS: Final[frozenset[str]] = frozenset(
    {"derived_from", "distilled_from", "trained_on_output_of", "trained_on"}
)

MISSING_GRADE_MESSAGE: Final[str] = "a stated fact cannot be graded missing; leave it out instead"

Id = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
NonEmptyText = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class GraphError(Exception):
    """Raised for any failure to load or validate a graph file."""


class EvidenceGrade(StrEnum):
    """How well a fact is evidenced. Shared with the evaluator (C3).

    "missing" exists for the evaluator, which reports facts that were never stated.
    A stated node or edge can never carry it.
    """

    DECLARED = "declared"
    DOCUMENTED = "documented"
    VERIFIED = "verified"
    SUSPECTED = "suspected"
    MISSING = "missing"


StatedGrade = Annotated[
    EvidenceGrade,
    WithJsonSchema({"type": "string", "enum": ["declared", "documented", "verified", "suspected"]}),
]


class _Frozen(BaseModel):
    """Base for every graph model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(_Frozen):
    """Where a fact comes from and how strong it is."""

    grade: StatedGrade
    source_ref: NonEmptyText
    recorded_by: NonEmptyText  # a role or handle such as "user", never a person's name
    recorded_on: date

    @field_validator("grade", mode="before")
    @classmethod
    def _reject_missing(cls, value: Any) -> Any:
        """Refuse the "missing" grade on a stated fact."""
        if value == EvidenceGrade.MISSING:
            raise ValueError(MISSING_GRADE_MESSAGE)
        return value


# ---- Nodes ---------------------------------------------------------------


class EntityNode(_Frozen):
    """An organisation or an individual (no name or identity fields)."""

    id: Id
    kind: Literal["entity"]
    entity_type: Literal["organisation", "individual"]
    evidence: Evidence


class ModelNode(_Frozen):
    """An AI model."""

    id: Id
    kind: Literal["model"]
    evidence: Evidence


class DatasetNode(_Frozen):
    """A dataset."""

    id: Id
    kind: Literal["dataset"]
    evidence: Evidence


class SoftwareNode(_Frozen):
    """A software artefact."""

    id: Id
    kind: Literal["software"]
    form: Literal["application", "service", "library", "source_code"]
    evidence: Evidence


Node = Annotated[
    EntityNode | ModelNode | DatasetNode | SoftwareNode,
    Field(discriminator="kind"),
]


# ---- Edges ---------------------------------------------------------------


class _EdgeBase(_Frozen):
    """Fields every edge has. "from" is a Python keyword, so the field is from_."""

    id: Id
    from_: Id = Field(alias="from")
    to: Id
    evidence: Evidence


class DerivedFromEdge(_EdgeBase):
    """A model built from another model by the stated method."""

    kind: Literal["derived_from"]
    method: Literal["fine_tune", "continued_pretraining", "quantize", "prune", "merge"]


class DistilledFromEdge(_EdgeBase):
    """A model distilled from a teacher model."""

    kind: Literal["distilled_from"]


class TrainedOnOutputOfEdge(_EdgeBase):
    """A model or dataset built from another model's outputs."""

    kind: Literal["trained_on_output_of"]


class TrainedOnEdge(_EdgeBase):
    """A model trained on a dataset."""

    kind: Literal["trained_on"]


class UsesCodeFromEdge(_EdgeBase):
    """A model or software that uses code from a software artefact."""

    kind: Literal["uses_code_from"]


class DevelopedWithToolEdge(_EdgeBase):
    """Something developed with the help of a model or software tool."""

    kind: Literal["developed_with_tool"]


class IncorporatesEdge(_EdgeBase):
    """Software that contains a model, dataset or other software."""

    kind: Literal["incorporates"]


class DevelopedByEdge(_EdgeBase):
    """A model, dataset or software developed by an entity."""

    kind: Literal["developed_by"]


class OwnsEdge(_EdgeBase):
    """A direct stake of one entity in another. No aggregation or indirect calculation."""

    kind: Literal["owns"]
    percent: Annotated[Decimal, Field(gt=0, le=100, allow_inf_nan=False)]
    basis: Literal["equity", "voting", "unknown"]


class ControlsEdge(_EdgeBase):
    """One entity controls another; means describes the fact."""

    kind: Literal["controls"]
    means: NonEmptyText


Edge = Annotated[
    DerivedFromEdge
    | DistilledFromEdge
    | TrainedOnOutputOfEdge
    | TrainedOnEdge
    | UsesCodeFromEdge
    | DevelopedWithToolEdge
    | IncorporatesEdge
    | DevelopedByEdge
    | OwnsEdge
    | ControlsEdge,
    Field(discriminator="kind"),
]


# ---- Graph and whole-graph checks ------------------------------------------


class Graph(_Frozen):
    """A whole graph file. Whole-graph checks run on every construction."""

    schema_version: Literal[1]
    graph_id: Id
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]

    @model_validator(mode="after")
    def _check_graph(self) -> Graph:
        """Run the whole-graph checks and fail with every problem found."""
        problems = (
            _duplicate_ids(self.nodes, self.edges)
            + _endpoint_problems(self.nodes, self.edges)
            + _duplicate_edges(self.edges)
            + _lineage_cycles(self.nodes, self.edges)
        )
        if problems:
            raise ValueError("\n".join(problems))
        return self


def _duplicate_ids(nodes: tuple[Node, ...], edges: tuple[Edge, ...]) -> list[str]:
    """Ids must be unique across nodes and edges together."""
    seen: set[str] = set()
    problems: list[str] = []
    for item in (*nodes, *edges):
        if item.id in seen:
            problems.append(f"duplicate id: {item.id}")
        seen.add(item.id)
    return problems


def _endpoint_problems(nodes: tuple[Node, ...], edges: tuple[Edge, ...]) -> list[str]:
    """Each edge's endpoints exist, have allowed kinds, and are not the same node."""
    kind_of = {node.id: node.kind for node in nodes}
    problems: list[str] = []
    for edge in edges:
        allowed_from, allowed_to = EDGE_ENDPOINTS[edge.kind]
        for end, ref, allowed in (("from", edge.from_, allowed_from), ("to", edge.to, allowed_to)):
            if ref not in kind_of:
                problems.append(f"edge {edge.id}: '{end}' node {ref} does not exist")
            elif kind_of[ref] not in allowed:
                problems.append(
                    f"edge {edge.id} ({edge.kind}): {end}-node {ref} has kind {kind_of[ref]};"
                    f" allowed: {', '.join(sorted(allowed))}"
                )
        if edge.from_ == edge.to:
            problems.append(f"edge {edge.id} ({edge.kind}): self-loop on {edge.from_}")
    return problems


def _duplicate_edges(edges: tuple[Edge, ...]) -> list[str]:
    """No two edges share kind, from and to; owns edges may differ by basis."""
    first_by_key: dict[tuple[str, str, str, str | None], str] = {}
    problems: list[str] = []
    for edge in edges:
        basis = edge.basis if isinstance(edge, OwnsEdge) else None
        key = (edge.kind, edge.from_, edge.to, basis)
        if key in first_by_key:
            problems.append(
                f"duplicate edge: {edge.id} repeats {first_by_key[key]}"
                f" ({edge.kind} {edge.from_} -> {edge.to})"
            )
        else:
            first_by_key[key] = edge.id
    return problems


def _lineage_cycles(nodes: tuple[Node, ...], edges: tuple[Edge, ...]) -> list[str]:
    """Find cycles among lineage edges with a depth-first search.

    Self-loops and edges to missing nodes are reported by other checks, so they are
    skipped here. Each cycle is reported as the path of node ids that closes it.
    """
    successors: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        if (
            edge.kind in LINEAGE_KINDS
            and edge.from_ != edge.to
            and edge.from_ in successors
            and edge.to in successors
        ):
            successors[edge.from_].append(edge.to)

    on_path: list[str] = []
    finished: set[str] = set()
    problems: list[str] = []

    def visit(node_id: str) -> None:
        on_path.append(node_id)
        for nxt in successors[node_id]:
            if nxt in on_path:
                cycle = [*on_path[on_path.index(nxt) :], nxt]
                problems.append("lineage cycle: " + " -> ".join(cycle))
            elif nxt not in finished:
                visit(nxt)
        on_path.pop()
        finished.add(node_id)

    for node_id in successors:
        if node_id not in finished:
            visit(node_id)
    return problems


# ---- Loader ----------------------------------------------------------------

_YAML_SPECIAL_FLOATS: Final[dict[str, str]] = {
    ".inf": "Infinity",
    "+.inf": "Infinity",
    "-.inf": "-Infinity",
    ".nan": "NaN",
}


class _StrictLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys and reads floats as Decimal."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        """Build a mapping, failing on any key that appears twice."""
        self.flatten_mapping(node)
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError:
                continue  # unhashable key: the base constructor reports it
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _construct_decimal(loader: _StrictLoader, node: yaml.ScalarNode) -> Decimal:
    """Read a YAML float from its written text, so 33.3 is exactly Decimal("33.3")."""
    text = str(loader.construct_scalar(node)).replace("_", "").lower()
    try:
        return Decimal(_YAML_SPECIAL_FLOATS.get(text, text))
    except InvalidOperation as err:
        raise ConstructorError(
            None, None, f"cannot read {text!r} as a number", node.start_mark
        ) from err


_StrictLoader.add_constructor("tag:yaml.org,2002:float", _construct_decimal)


def load_graph(path: str | Path) -> Graph:
    """Load and validate a graph file. Any failure raises GraphError; nothing partial."""
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = yaml.load(text, Loader=_StrictLoader)  # safe: a SafeLoader subclass
        return Graph.model_validate(data)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as err:
        raise GraphError(f"{path}: {err}") from err
