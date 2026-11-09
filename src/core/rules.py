"""Rule files: schema, fail-closed pack loading, and staleness warnings.

One rule per YAML file, named "<id>.yaml". This module checks the shape of rules and
the references between them; it does not evaluate triggers (that is C3a). It holds no
legal content: real rules arrive later as YAML files written from primary text.

load_rule_pack returns a whole, valid pack or raises one RuleError listing every
problem. It never returns a partial pack.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Final, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StringConstraints,
    Tag,
    ValidationError,
    field_validator,
    model_validator,
)

from core.graph import EvidenceGrade, Node, NonEmptyText, StatedGrade
from core.yaml_strict import StrictYAMLError, load_yaml

MAX_TRIGGER_DEPTH: Final[int] = 8
STALE_AFTER_DAYS: Final[int] = 90
IGNORED_NAMES: Final[frozenset[str]] = frozenset({".DS_Store", ".gitkeep"})

RuleId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9-]{2,63}$")]
Version = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
Regime = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9-]{1,31}$")]
Effect = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")]
FactName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]{0,127}$")]
InterpretationId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")]
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://\S+$")]
QuoteHash = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
ClockAmount = Annotated[int, Field(ge=1, strict=True)]  # strict: no bool, Decimal or str


def _node_kinds() -> tuple[str, ...]:
    """Read the node kinds from graph.py's Node union, so they are never retyped here."""
    union = get_args(Node)[0]  # Node is Annotated[Union[...], Field(...)]
    return tuple(get_args(cls.model_fields["kind"].annotation)[0] for cls in get_args(union))


NODE_KINDS: Final[tuple[str, ...]] = _node_kinds()
NodeKind = Literal[NODE_KINDS]  # type: ignore[valid-type]


class RuleError(Exception):
    """Raised when a rule pack cannot be loaded. problems lists every reason found."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems: tuple[str, ...] = tuple(problems)
        super().__init__("\n".join(self.problems))


class _Frozen(BaseModel):
    """Base for every rule model: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- Trigger expressions (shape only; C3a evaluates them) --------------------


class AllExpr(_Frozen):
    """True when every child is true."""

    all: Annotated[tuple[Expr, ...], Field(min_length=1)]


class AnyExpr(_Frozen):
    """True when at least one child is true."""

    any: Annotated[tuple[Expr, ...], Field(min_length=1)]


class NotExpr(_Frozen):
    """Negates its child. "not" is a Python keyword, so the field is not_."""

    not_: Expr = Field(alias="not")


class FactExpr(_Frozen):
    """A leaf naming a fact, optionally with the weakest evidence grade that counts."""

    fact: FactName
    min_grade: StatedGrade | None = None

    @field_validator("min_grade", mode="before")
    @classmethod
    def _reject_missing(cls, value: Any) -> Any:
        """Refuse "missing": it is what the evaluator reports, not a threshold."""
        if value == EvidenceGrade.MISSING:
            raise ValueError("min_grade cannot be 'missing'")
        return value


_EXPR_TAGS: Final[dict[type, str]] = {
    AllExpr: "all",
    AnyExpr: "any",
    NotExpr: "not",
    FactExpr: "fact",
}


def _expr_tag(value: Any) -> str | None:
    """Pick the expression model from the first operator key present."""
    if isinstance(value, dict):
        for key in ("all", "any", "not", "fact"):
            if key in value:
                return key
        return None
    return _EXPR_TAGS.get(type(value))


Expr = Annotated[
    Annotated[AllExpr, Tag("all")]
    | Annotated[AnyExpr, Tag("any")]
    | Annotated[NotExpr, Tag("not")]
    | Annotated[FactExpr, Tag("fact")],
    Discriminator(
        _expr_tag,
        custom_error_type="invalid_expression",
        custom_error_message="an expression is exactly one of all, any, not or fact",
    ),
]

for _model in (AllExpr, AnyExpr, NotExpr):
    _model.model_rebuild()


def expr_depth(expr: AllExpr | AnyExpr | NotExpr | FactExpr) -> int:
    """Nesting depth: a lone fact is 1, and each all, any or not adds 1."""
    if isinstance(expr, FactExpr):
        return 1
    if isinstance(expr, NotExpr):
        return 1 + expr_depth(expr.not_)
    children = expr.all if isinstance(expr, AllExpr) else expr.any
    return 1 + max(expr_depth(child) for child in children)


# ---- Rule parts ---------------------------------------------------------------


class Interpretation(_Frozen):
    """One reading of an unsettled provision, with its own trigger."""

    id: InterpretationId
    summary: NonEmptyText
    trigger: Expr


class Citation(_Frozen):
    """Where the rule comes from: a source record in sources/ and a pinpoint quote hash."""

    primary: NonEmptyText
    source_id: SourceId
    source_url: HttpsUrl
    pinpoint_quote_hash: QuoteHash  # format only; matching it to an extract comes later


class Verification(_Frozen):
    """Who last checked the rule against its source, and when."""

    status: Literal["verified", "secondary", "unverified"]
    last_verified: date
    verified_by: NonEmptyText  # a role or handle such as "user", never a person's name


class Clock(_Frozen):
    """A deadline: amount units after the trigger event (plain text)."""

    amount: ClockAmount
    unit: Literal["hours", "calendar_days", "business_days"]
    trigger: NonEmptyText


class Rule(_Frozen):
    """One rule file."""

    id: RuleId
    version: Version
    regime: Regime
    title: NonEmptyText
    law_status: Literal["in_force", "proposed"]
    applies_to: NodeKind
    binding: RuleId | None
    trigger: Expr | None = None
    interpretations: Annotated[tuple[Interpretation, ...], Field(min_length=2)] | None = None
    effect: Effect
    unless: tuple[RuleId, ...] = ()
    citation: Citation
    verification: Verification
    clock: Clock | None

    @model_validator(mode="after")
    def _check_rule(self) -> Rule:
        """Exactly one of trigger or interpretations; unique interpretation ids; depth limit."""
        if (self.trigger is None) == (self.interpretations is None):
            raise ValueError("rule needs exactly one of trigger or interpretations")
        problems: list[str] = []
        if self.trigger is not None:
            problems += _depth_problem("trigger", self.trigger)
        seen: set[str] = set()
        for item in self.interpretations or ():
            if item.id in seen:
                problems.append(f"duplicate interpretation id: {item.id}")
            seen.add(item.id)
            problems += _depth_problem(f"interpretation {item.id} trigger", item.trigger)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _depth_problem(label: str, expr: AllExpr | AnyExpr | NotExpr | FactExpr) -> list[str]:
    """Report a trigger nested deeper than MAX_TRIGGER_DEPTH."""
    depth = expr_depth(expr)
    if depth > MAX_TRIGGER_DEPTH:
        return [f"{label} depth {depth} exceeds the maximum of {MAX_TRIGGER_DEPTH}"]
    return []


class RuleWarning(_Frozen):
    """A non-fatal note about a loaded rule."""

    rule_id: RuleId
    code: Literal["STALE", "NOT_VERIFIED"]
    message: str


class RulePack(_Frozen):
    """A whole, valid set of rules (ordered by id) and their warnings."""

    rules: tuple[Rule, ...]
    warnings: tuple[RuleWarning, ...]


# ---- Loading ------------------------------------------------------------------


def _format_validation_error(err: ValidationError) -> str:
    """One line per pydantic error, as 'field.path: message'."""
    parts = []
    for item in err.errors():
        loc = ".".join(str(p) for p in item["loc"])
        parts.append(f"{loc}: {item['msg']}" if loc else item["msg"])
    return "; ".join(parts)


def _list_rule_files(rules_dir: Path) -> tuple[list[Path], list[str]]:
    """Return the *.yaml files in rules_dir and a problem for every other entry."""
    if not rules_dir.is_dir():
        return [], [f"{rules_dir}: rules folder does not exist"]
    files: list[Path] = []
    problems: list[str] = []
    for entry in sorted(rules_dir.iterdir(), key=lambda p: p.name):
        if entry.name in IGNORED_NAMES:
            continue
        if entry.is_file() and entry.suffix == ".yaml":
            files.append(entry)
        elif entry.is_dir():
            problems.append(f"{entry.name}: folders are not allowed in the rules folder")
        else:
            problems.append(f"{entry.name}: not a .yaml rule file")
    if not files:
        problems.append(f"{rules_dir}: no rule files in the rules folder")
    return files, problems


def _parse_files(files: list[Path]) -> tuple[list[tuple[str, Rule]], list[str], Exception | None]:
    """Parse every file; return (filename, rule) pairs, problems, and the first cause."""
    parsed: list[tuple[str, Rule]] = []
    problems: list[str] = []
    first_cause: Exception | None = None
    for path in files:
        try:
            data = load_yaml(path.read_text(encoding="utf-8"))
            parsed.append((path.name, Rule.model_validate(data)))
        except ValidationError as err:
            problems.append(f"{path.name}: {_format_validation_error(err)}")
            first_cause = first_cause or err
        except (OSError, UnicodeDecodeError, StrictYAMLError) as err:
            problems.append(f"{path.name}: {err}")
            first_cause = first_cause or err
    return parsed, problems, first_cause


def _read_source(path: Path) -> dict[str, str] | str:
    """Read a source record; return {'id', 'url'} or the reason it is malformed."""
    try:
        data = load_yaml(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, StrictYAMLError) as err:
        return str(err).replace("\n", " ")
    if not isinstance(data, dict):
        return "not a mapping of fields"
    for field in ("id", "url"):
        if not isinstance(data.get(field), str) or not data[field]:
            return f"missing or non-text '{field}'"
    return {"id": data["id"], "url": data["url"]}


def _source_problems(
    rule: Rule, sources_dir: Path, cache: dict[str, dict[str, str] | str | None]
) -> list[str]:
    """Check that the cited source record exists, is well formed, and has the same URL."""
    source_id = rule.citation.source_id
    if source_id not in cache:
        path = sources_dir / f"{source_id}.yaml"
        cache[source_id] = _read_source(path) if path.is_file() else None
    record = cache[source_id]
    if record is None:
        return [f"{rule.id}: source not found: {source_id}"]
    if isinstance(record, str):
        return [f"{rule.id}: source record {source_id}.yaml is malformed: {record}"]
    if record["id"] != source_id:
        return [f"{rule.id}: source record id mismatch: {source_id}.yaml has id {record['id']!r}"]
    if record["url"] != rule.citation.source_url:
        return [
            f"{rule.id}: source_url mismatch: rule has {rule.citation.source_url},"
            f" record {source_id} has {record['url']}"
        ]
    return []


def _references(rule: Rule) -> list[tuple[str, str]]:
    """(field, rule id) for every rule this rule names in binding or unless."""
    refs = [("binding", rule.binding)] if rule.binding else []
    return refs + [("unless", ref) for ref in rule.unless]


def _reference_problems(by_id: dict[str, Rule]) -> list[str]:
    """binding and unless name existing rules of the same regime, and never the rule itself."""
    problems: list[str] = []
    for rule in by_id.values():
        for field, ref in _references(rule):
            if ref == rule.id:
                problems.append(f"{rule.id}: {field} names itself")
            elif ref not in by_id:
                problems.append(f"{rule.id}: {field} names unknown rule {ref}")
            elif by_id[ref].regime != rule.regime:
                problems.append(
                    f"{rule.id}: {field} names {ref}, which is in a different regime"
                    f" ({by_id[ref].regime}, not {rule.regime})"
                )
    return problems


def _reference_cycles(by_id: dict[str, Rule]) -> list[str]:
    """Find cycles through binding and unless with a depth-first search.

    Self-references and unknown ids are reported elsewhere, so they are skipped here.
    """
    successors = {
        rule_id: sorted({ref for _, ref in _references(rule) if ref != rule_id and ref in by_id})
        for rule_id, rule in sorted(by_id.items())
    }
    on_path: list[str] = []
    finished: set[str] = set()
    problems: list[str] = []

    def visit(rule_id: str) -> None:
        on_path.append(rule_id)
        for nxt in successors[rule_id]:
            if nxt in on_path:
                cycle = [*on_path[on_path.index(nxt) :], nxt]
                problems.append(f"{cycle[0]}: reference cycle: " + " -> ".join(cycle))
            elif nxt not in finished:
                visit(nxt)
        on_path.pop()
        finished.add(rule_id)

    for rule_id in successors:
        if rule_id not in finished:
            visit(rule_id)
    return problems


def _pack_problems(parsed: list[tuple[str, Rule]], sources_dir: Path, today: date) -> list[str]:
    """Every whole-pack check; each problem starts with the rule id."""
    problems: list[str] = []
    by_id: dict[str, Rule] = {}
    file_of: dict[str, str] = {}
    cache: dict[str, dict[str, str] | str | None] = {}
    for filename, rule in parsed:
        if rule.id in by_id:
            problems.append(f"{rule.id}: duplicate id in {file_of[rule.id]} and {filename}")
        else:
            by_id[rule.id] = rule
            file_of[rule.id] = filename
        if filename != f"{rule.id}.yaml":
            problems.append(f"{rule.id}: filename {filename} does not match id ({rule.id}.yaml)")
        problems += _source_problems(rule, sources_dir, cache)
        if rule.verification.last_verified > today:
            problems.append(
                f"{rule.id}: last_verified {rule.verification.last_verified}"
                f" is after today ({today})"
            )
    return problems + _reference_problems(by_id) + _reference_cycles(by_id)


def _warnings(rules: tuple[Rule, ...], today: date) -> tuple[RuleWarning, ...]:
    """STALE and NOT_VERIFIED warnings, sorted by rule id then code."""
    found: list[RuleWarning] = []
    for rule in rules:
        checked = rule.verification.last_verified
        age = (today - checked).days
        if today - checked > timedelta(days=STALE_AFTER_DAYS):
            found.append(
                RuleWarning(
                    rule_id=rule.id,
                    code="STALE",
                    message=f"last verified {checked}, {age} days before {today}"
                    f" (more than {STALE_AFTER_DAYS})",
                )
            )
        if rule.verification.status != "verified":
            found.append(
                RuleWarning(
                    rule_id=rule.id,
                    code="NOT_VERIFIED",
                    message=f"verification status is {rule.verification.status}",
                )
            )
    return tuple(sorted(found, key=lambda w: (w.rule_id, w.code)))


def load_rule_pack(rules_dir: str | Path, sources_dir: str | Path, today: date) -> RulePack:
    """Load every rule in rules_dir, checked against sources_dir, as of today.

    today is passed in (never read from the clock) so results are deterministic.
    Any problem raises one RuleError listing all problems; nothing partial is returned.
    """
    if isinstance(today, datetime) or not isinstance(today, date):
        raise TypeError(f"today must be a date, not {type(today).__name__}")
    files, problems = _list_rule_files(Path(rules_dir))
    parsed, parse_problems, first_cause = _parse_files(files)
    problems += parse_problems
    if problems:
        raise RuleError(sorted(problems)) from first_cause
    pack_problems = _pack_problems(parsed, Path(sources_dir), today)
    if pack_problems:
        raise RuleError(sorted(pack_problems))
    rules = tuple(sorted((rule for _, rule in parsed), key=lambda r: r.id))
    return RulePack(rules=rules, warnings=_warnings(rules, today))
