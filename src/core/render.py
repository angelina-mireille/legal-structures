"""Renderers: the counsel memo in Markdown and JSON envelopes (C6, D19-D25).

- render_memo: the memo for one SubjectResult, built only from core.templates plus rule
  and fact data (D21, D22). Every statement line starts with "- [<rule id>] ".
- render_result_json: the SubjectResult with the facts and the pack's rules (D25).
- render_json: a SubjectDiff or DivergenceTable in the same envelope (D25).

Before rendering a SubjectResult, the result is re-run from the pack and facts given
(D20): a memo never shows facts that did not produce its result.

Pure: no I/O, no logging, no clock, and inputs are never changed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, Final

from core import templates as tpl
from core.diff import SubjectDiff
from core.divergence import DivergenceTable
from core.evaluator import Fact, TriValue
from core.outcomes import Direction, Outcome, Question, QuestionKind, Reason
from core.results import (
    ClockNote,
    ClockStatus,
    ExemptionResult,
    ResultError,
    RuleResult,
    SubjectResult,
    assess_subject,
)
from core.rules import Rule, RulePack

FORMAT_VERSION: Final[str] = "0.1"

_OUTCOME_TEXT: Final[dict[tuple[Outcome, Reason | None, Direction | None], tuple[str, str]]] = {
    (Outcome.APPLIES, None, None): (tpl.LABEL_APPLIES, tpl.SENTENCE_APPLIES),
    (Outcome.DOES_NOT_APPLY, Reason.TEST_NOT_MET, None): (
        tpl.LABEL_TEST_NOT_MET,
        tpl.SENTENCE_TEST_NOT_MET,
    ),
    (Outcome.DOES_NOT_APPLY, Reason.NOT_BOUND, None): (tpl.LABEL_NOT_BOUND, tpl.SENTENCE_NOT_BOUND),
    (Outcome.DOES_NOT_APPLY, Reason.EXEMPT, None): (tpl.LABEL_EXEMPT, tpl.SENTENCE_EXEMPT),
    (Outcome.CONDITIONAL, None, Direction.APPLIES_IF_CONFIRMED): (
        tpl.LABEL_APPLIES_IF_CONFIRMED,
        tpl.SENTENCE_APPLIES_IF_CONFIRMED,
    ),
    (Outcome.CONDITIONAL, None, Direction.DOES_NOT_APPLY_IF_CONFIRMED): (
        tpl.LABEL_DOES_NOT_APPLY_IF_CONFIRMED,
        tpl.SENTENCE_DOES_NOT_APPLY_IF_CONFIRMED,
    ),
    (Outcome.INSUFFICIENT_FACTS, None, None): (
        tpl.LABEL_INSUFFICIENT_FACTS,
        tpl.SENTENCE_INSUFFICIENT_FACTS,
    ),
    (Outcome.UNSETTLED, None, None): (tpl.LABEL_UNSETTLED, tpl.SENTENCE_UNSETTLED),
}

_UNRESOLVED_LABEL: Final[dict[Outcome, str]] = {
    Outcome.APPLIES: tpl.EXEMPTION_D6A_LABEL,
    Outcome.CONDITIONAL: tpl.EXEMPTION_LABEL_CONDITIONAL,
    Outcome.INSUFFICIENT_FACTS: tpl.LABEL_INSUFFICIENT_FACTS,
    Outcome.UNSETTLED: tpl.LABEL_UNSETTLED,
}

_DEFINITE: Final[frozenset[Outcome]] = frozenset(
    {Outcome.APPLIES, Outcome.DOES_NOT_APPLY, Outcome.CONDITIONAL}
)


class RenderError(Exception):
    """Raised when a result cannot be rendered faithfully (mismatch or unknown combination)."""


# ---- Small formatting helpers ------------------------------------------------------------


def outcome_text(
    outcome: Outcome, reason: Reason | None, direction: Direction | None
) -> tuple[str, str]:
    """(label, sentence template) for one of the eight valid final combinations (D22)."""
    try:
        return _OUTCOME_TEXT[(outcome, reason, direction)]
    except KeyError:
        raise RenderError(
            f"no template for outcome {outcome}, reason {reason}, direction {direction}"
        ) from None


def _ids(ids: Iterable[str]) -> str:
    """Rule ids in square brackets, sorted, comma-separated."""
    return tpl.LIST_SEPARATOR.join(tpl.ID_REF.format(id=i) for i in sorted(ids))


def _fact_text(name: str, facts: Mapping[str, Fact]) -> str:
    """One fact as "<name> (<VALUE>, <grade>)", "(UNKNOWN)" or "(not supplied)" (D21)."""
    item = facts.get(name)
    if item is None:
        return tpl.FACT_NOT_SUPPLIED.format(name=name)
    if item.value is TriValue.UNKNOWN or item.grade is None:
        return tpl.FACT_UNKNOWN.format(name=name)
    return tpl.FACT_STATED.format(name=name, value=item.value.name, grade=item.grade.value)


def _facts_text(names: Iterable[str], facts: Mapping[str, Fact]) -> str:
    """Several facts, sorted by name, comma-separated."""
    return tpl.LIST_SEPARATOR.join(_fact_text(n, facts) for n in sorted(names))


def _sentence(template: str, rule: Rule, exempted_by: tuple[str, ...]) -> str:
    """Fill an outcome sentence's binding id and exemption ids."""
    return template.format(binding_id=rule.binding or "", exempted_by=_ids(exempted_by))


# ---- D20 inputs match --------------------------------------------------------------------


def _check_inputs(result: SubjectResult, pack: RulePack, facts: Mapping[str, Fact]) -> None:
    """Re-run the result with include_proposed False, then True; raise unless one matches.

    A ResultError on either attempt counts as "not equal". Other errors propagate.
    """
    last_error: ResultError | None = None
    for include_proposed in (False, True):
        try:
            again = assess_subject(
                result.subject_id,
                result.subject_kind,
                pack,
                facts,
                as_of=result.as_of,
                include_proposed=include_proposed,
            )
        except ResultError as err:
            last_error = err
            continue
        if again == result:
            return
    raise RenderError(
        "the result does not follow from the pack and facts given; nothing was rendered"
    ) from last_error


# ---- Rule sections ----------------------------------------------------------------------


def _relied_on(root: Rule, by_id: Mapping[str, Rule]) -> set[str]:
    """Ids of rules root relies on: its binding chain, and each unless rule at any depth
    with its binding chain (binding links only, as in diff._fact_reads)."""
    found: set[str] = set()

    def chain(rule: Rule) -> None:
        seen: set[str] = set()
        ref = rule.binding
        while ref is not None and ref in by_id and ref not in seen:
            seen.add(ref)
            found.add(ref)
            ref = by_id[ref].binding

    exempt_seen: set[str] = {root.id}

    def exemption(ref: str) -> None:
        if ref in exempt_seen or ref not in by_id:
            return
        exempt_seen.add(ref)
        found.add(ref)
        chain(by_id[ref])
        for inner in sorted(by_id[ref].unless):
            exemption(inner)

    chain(root)
    for ref in sorted(root.unless):
        exemption(ref)
    found.discard(root.id)
    return found


def _warning_lines(rule: Rule, pack: RulePack) -> list[str]:
    """The rule's own warnings (by code), then its helpers' (by helper id, code) (D23)."""
    by_id = {r.id: r for r in pack.rules}
    helpers = _relied_on(rule, by_id)
    own = sorted((w for w in pack.warnings if w.rule_id == rule.id), key=lambda w: w.code)
    relied = sorted(
        (w for w in pack.warnings if w.rule_id in helpers), key=lambda w: (w.rule_id, w.code)
    )
    lines = [tpl.WARNING.format(id=rule.id, code=w.code, message=w.message) for w in own]
    lines += [
        tpl.HELPER_WARNING.format(id=rule.id, code=w.code, helper_id=w.rule_id, message=w.message)
        for w in relied
    ]
    return lines


def _readings_lines(item: RuleResult) -> list[str]:
    """One line per reading when they disagree; the agree line when they agree."""
    base = item.base
    if base.readings_agree is True:
        return [tpl.READINGS_AGREE.format(id=item.rule_id, count=len(base.interpretations))]
    lines = []
    for reading in base.interpretations:
        label, _ = outcome_text(reading.outcome, reading.reason, reading.direction)
        lines.append(
            tpl.READING.format(id=item.rule_id, reading_id=reading.interpretation_id, label=label)
        )
    return lines


def _decisive_lines(item: RuleResult, facts: Mapping[str, Fact]) -> list[str]:
    """Decisive facts, or the right no-decisive line; none under EXEMPT ((d)2) or open results."""
    if item.outcome not in _DEFINITE or item.reason == Reason.EXEMPT:
        return []
    base = item.base
    if base.decisive_facts:
        return [tpl.DECISIVE.format(id=item.rule_id, facts=_facts_text(base.decisive_facts, facts))]
    if base.interpretations:
        return [tpl.DECISIVE_NONE_ALL_READINGS.format(id=item.rule_id)]
    return [tpl.NO_DECISIVE.format(id=item.rule_id)]


def _question_line(rule_id: str, question: Question, facts: Mapping[str, Fact]) -> str:
    """A rule's question: a missing fact or stronger evidence needed."""
    fact = _fact_text(question.fact, facts)
    if question.kind == QuestionKind.MISSING:
        return tpl.QUESTION_MISSING.format(id=rule_id, fact=fact)
    required = question.required_grade.value if question.required_grade else ""
    return tpl.QUESTION_STRONGER.format(id=rule_id, fact=fact, required=required)


def _exemption_lines(rule_id: str, ex: ExemptionResult, facts: Mapping[str, Fact]) -> list[str]:
    """One exemption's line, followed by its open points (questions, then facts to confirm)."""
    if ex.applied:
        return [tpl.EXEMPTION_APPLIED.format(id=rule_id, ex_id=ex.rule_id)]
    if not ex.unresolved:
        return [tpl.EXEMPTION_NOT_APPLYING.format(id=rule_id, ex_id=ex.rule_id)]
    label = _UNRESOLVED_LABEL.get(ex.outcome)
    if label is None:
        raise RenderError(f"{rule_id}: no label for unresolved exemption outcome {ex.outcome}")
    lines = [tpl.EXEMPTION_UNRESOLVED.format(id=rule_id, ex_id=ex.rule_id, ex_label=label)]
    for question in ex.questions:
        fact = _fact_text(question.fact, facts)
        if question.kind == QuestionKind.MISSING:
            lines.append(tpl.EXEMPTION_OPEN_MISSING.format(id=rule_id, ex_id=ex.rule_id, fact=fact))
        else:
            required = question.required_grade.value if question.required_grade else ""
            lines.append(
                tpl.EXEMPTION_OPEN_STRONGER.format(
                    id=rule_id, ex_id=ex.rule_id, fact=fact, required=required
                )
            )
    for name in ex.facts_to_confirm:
        lines.append(
            tpl.EXEMPTION_OPEN_CONFIRM.format(
                id=rule_id, ex_id=ex.rule_id, fact=_fact_text(name, facts)
            )
        )
    return lines


def _clock_line(rule_id: str, clock: ClockNote) -> str:
    """The clock line, with the reason it is shown for IF_CONFIRMED and UNDER_READINGS."""
    line = tpl.CLOCK.format(
        id=rule_id, amount=clock.amount, unit=clock.unit, trigger=clock.trigger, note=clock.note
    )
    if clock.status == ClockStatus.IF_CONFIRMED:
        line += tpl.CLOCK_IF_CONFIRMED
    elif clock.status == ClockStatus.UNDER_READINGS:
        line += tpl.CLOCK_UNDER_READINGS.format(readings=tpl.LIST_SEPARATOR.join(clock.readings))
    return line


def _effective_line(rule: Rule) -> str:
    """The effective-dates line; a rule with a to date but no from date raises ((d)8)."""
    eff = rule.effective
    if eff.from_ is None:
        if eff.to is not None:
            raise RenderError(f"{rule.id}: effective.to is set without effective.from")
        return tpl.EFFECTIVE_NONE.format(id=rule.id)
    values: dict[str, Any] = {"id": rule.id, "from": eff.from_.isoformat(), "basis": eff.basis}
    if eff.to is None:
        return tpl.EFFECTIVE.format(**values)
    return tpl.EFFECTIVE_UNTIL.format(**values, to=eff.to.isoformat())


def _rule_lines(
    item: RuleResult, rule: Rule, pack: RulePack, facts: Mapping[str, Fact], as_of: str
) -> list[str]:
    """Every statement line of one rule section, in the D21 order."""
    rid = item.rule_id
    base = item.base
    lines = _warning_lines(rule, pack)
    label, sentence = outcome_text(item.outcome, item.reason, item.direction)
    lines.append(
        tpl.RESULT.format(id=rid, label=label, sentence=_sentence(sentence, rule, item.exempted_by))
    )
    if item.reason == Reason.EXEMPT:
        base_label, base_sentence = outcome_text(base.outcome, base.reason, base.direction)
        lines.append(
            tpl.BASE_UNDER_EXEMPTION.format(
                id=rid, base_label=base_label, base_sentence=_sentence(base_sentence, rule, ())
            )
        )
    if base.binding_unresolved:
        lines.append(tpl.BINDING_UNRESOLVED.format(id=rid, binding_id=rule.binding))
    if base.interpretations:
        lines += _readings_lines(item)
    lines += _decisive_lines(item, facts)
    if base.facts_to_confirm:
        lines.append(
            tpl.FACTS_TO_CONFIRM.format(id=rid, facts=_facts_text(base.facts_to_confirm, facts))
        )
    lines += [_question_line(rid, q, facts) for q in base.questions]
    for ex in item.exemptions:
        lines += _exemption_lines(rid, ex, facts)
    if item.clock is not None:
        lines.append(_clock_line(rid, item.clock))
    if item.in_force_unpublished and rule.effective.published is not None:
        lines.append(
            tpl.IN_FORCE_UNPUBLISHED.format(
                id=rid, as_of=as_of, published=rule.effective.published.isoformat()
            )
        )
    if item.law_status == "proposed":
        lines.append(tpl.PROPOSED_ASSESSED.format(id=rid))
    lines.append(
        tpl.SOURCE.format(
            id=rid,
            primary=rule.citation.primary,
            source_url=rule.citation.source_url,
            source_id=rule.citation.source_id,
            status=rule.verification.status,
            last_verified=rule.verification.last_verified.isoformat(),
        )
    )
    lines.append(_effective_line(rule))
    return lines


def _finish(blocks: list[list[str]]) -> str:
    """Join blocks with one blank line between them and exactly one trailing newline."""
    text = "\n\n".join("\n".join(block) for block in blocks) + "\n"
    if "\r" in text:
        raise RenderError("output would contain a carriage return")
    return text


# ---- Public entry points ------------------------------------------------------------------


def render_memo(result: SubjectResult, pack: RulePack, facts: Mapping[str, Fact]) -> str:
    """The counsel memo in Markdown for one SubjectResult (D19-D24)."""
    _check_inputs(result, pack, facts)
    by_id = {rule.id: rule for rule in pack.rules}
    as_of = result.as_of.isoformat()
    blocks: list[list[str]] = [
        [
            tpl.TITLE.format(
                subject_id=result.subject_id, subject_kind=result.subject_kind, as_of=as_of
            )
        ],
        [tpl.DISCLAIMER],
        [tpl.NO_AGGREGATION],
    ]
    for regime in result.regimes:
        blocks.append([tpl.REGIME_HEADING.format(regime=regime.regime)])
        for item in regime.rules:
            rule = by_id[item.rule_id]
            blocks.append([tpl.RULE_HEADING.format(id=rule.id, title=rule.title)])
            blocks.append(_rule_lines(item, rule, pack, facts, as_of))
    if result.not_in_effect:
        blocks.append([tpl.NOT_IN_EFFECT_HEADING.format(as_of=as_of)])
        blocks.append([tpl.NOT_IN_EFFECT.format(id=i, as_of=as_of) for i in result.not_in_effect])
    if result.excluded_proposed:
        blocks.append([tpl.PROPOSED_HEADING])
        blocks.append([tpl.EXCLUDED_PROPOSED.format(id=i) for i in result.excluded_proposed])
    return _finish(blocks)


def _dump(envelope: dict[str, Any]) -> str:
    """JSON text: indent 2, UTF-8 characters kept, one trailing newline."""
    return json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"


def render_result_json(result: SubjectResult, pack: RulePack, facts: Mapping[str, Fact]) -> str:
    """The SubjectResult with its facts and the pack's rules, as JSON (D25)."""
    _check_inputs(result, pack, facts)
    return _dump(
        {
            "format_version": FORMAT_VERSION,
            "kind": "subject_result",
            "disclaimer": tpl.DISCLAIMER,
            "facts": [
                {"fact": name, **facts[name].model_dump(mode="json")} for name in sorted(facts)
            ],
            "rules_in_pack": [
                {
                    "id": rule.id,
                    "version": rule.version,
                    "regime": rule.regime,
                    "law_status": rule.law_status,
                    "verification_status": rule.verification.status,
                    "last_verified": rule.verification.last_verified.isoformat(),
                    "source_id": rule.citation.source_id,
                }
                for rule in sorted(pack.rules, key=lambda r: r.id)
            ],
            "result": result.model_dump(mode="json"),
        }
    )


def render_json(model: SubjectDiff | DivergenceTable) -> str:
    """A SubjectDiff or DivergenceTable as JSON (D25); any other type raises RenderError."""
    if isinstance(model, SubjectDiff):
        kind = "subject_diff"
    elif isinstance(model, DivergenceTable):
        kind = "divergence_table"
    else:
        raise RenderError(f"cannot render {type(model).__name__} as JSON")
    return _dump(
        {
            "format_version": FORMAT_VERSION,
            "kind": kind,
            "disclaimer": tpl.DISCLAIMER,
            "data": model.model_dump(mode="json"),
        }
    )
