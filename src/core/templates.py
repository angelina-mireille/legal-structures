"""Every fixed sentence of the renderers (C6, D22), as constants.

The memo is built only from these constants plus rule and fact data. Placeholders in
braces are filled by core.render with str.format. Wording was approved in C6; change it
only with a decision, and tests/test_render.py checks it word for word.
"""

from __future__ import annotations

from typing import Final

# ---- Boilerplate (no rule id) ----------------------------------------------------------

TITLE: Final[str] = "# Assessment of {subject_id} ({subject_kind}) as of {as_of}"
DISCLAIMER: Final[str] = (
    "Prototype analysis, not legal advice. Each line follows from the rules and facts"
    " supplied; where readings differ, no reading is preferred."
)
NO_AGGREGATION: Final[str] = (
    "Regimes are shown side by side. This memo draws no conclusion across regimes."
)
REGIME_HEADING: Final[str] = "## Regime {regime}"
RULE_HEADING: Final[str] = "### [{id}] {title}"
NOT_IN_EFFECT_HEADING: Final[str] = "## Not in effect on {as_of}"
PROPOSED_HEADING: Final[str] = "## Proposed law not assessed"

# ---- Result line and the eight outcome labels and sentences -----------------------------

RESULT: Final[str] = "- [{id}] Result: {label}. {sentence}"

LABEL_APPLIES: Final[str] = "APPLIES"
SENTENCE_APPLIES: Final[str] = "On the facts supplied, the conditions of this rule are met."

LABEL_TEST_NOT_MET: Final[str] = "DOES_NOT_APPLY (TEST_NOT_MET)"
SENTENCE_TEST_NOT_MET: Final[str] = "On the facts supplied, the test in this rule is not met."

LABEL_NOT_BOUND: Final[str] = "DOES_NOT_APPLY (NOT_BOUND)"
SENTENCE_NOT_BOUND: Final[str] = (
    "On the facts supplied, the binding condition in [{binding_id}] is not met,"
    " so this rule's test was not assessed."
)

LABEL_EXEMPT: Final[str] = "DOES_NOT_APPLY (EXEMPT)"
SENTENCE_EXEMPT: Final[str] = (
    "On the facts supplied, an exemption applies ({exempted_by}), so this rule does not apply."
)

LABEL_APPLIES_IF_CONFIRMED: Final[str] = "CONDITIONAL (APPLIES_IF_CONFIRMED)"
SENTENCE_APPLIES_IF_CONFIRMED: Final[str] = (
    "The result rests on facts graded only as suspected. If they are confirmed,"
    " the conditions of this rule are met."
)

LABEL_DOES_NOT_APPLY_IF_CONFIRMED: Final[str] = "CONDITIONAL (DOES_NOT_APPLY_IF_CONFIRMED)"
SENTENCE_DOES_NOT_APPLY_IF_CONFIRMED: Final[str] = (
    "The result rests on facts graded only as suspected. If they are confirmed,"
    " the conditions of this rule are not met."
)

LABEL_INSUFFICIENT_FACTS: Final[str] = "INSUFFICIENT_FACTS"
SENTENCE_INSUFFICIENT_FACTS: Final[str] = (
    "The facts supplied are not enough to assess this rule. The open points are listed below."
)

LABEL_UNSETTLED: Final[str] = "UNSETTLED"
SENTENCE_UNSETTLED: Final[str] = (
    "The readings of this rule give different results on the facts supplied."
    " Which reading is right is for counsel; this tool takes no view."
)

# ---- Detail lines --------------------------------------------------------------------------

BASE_UNDER_EXEMPTION: Final[str] = (
    "- [{id}] Without the exemption, the result would be {base_label}: {base_sentence}"
)
BINDING_UNRESOLVED: Final[str] = (
    "- [{id}] Whether [{binding_id}] binds the subject is not settled on the facts"
    " supplied; the test is not met either way."
)
READING: Final[str] = "- [{id}] Reading {reading_id}: {label}."
READINGS_AGREE: Final[str] = "- [{id}] All {count} readings of this rule give this result."
DECISIVE: Final[str] = (
    "- [{id}] Decisive facts (removing any one would change the result): {facts}."
)
NO_DECISIVE: Final[str] = (
    "- [{id}] No single fact is decisive: removing any one fact alone would not change the result."
)
DECISIVE_NONE_ALL_READINGS: Final[str] = "- [{id}] No single fact is decisive under every reading."
FACTS_TO_CONFIRM: Final[str] = "- [{id}] Facts to confirm: {facts}."
QUESTION_MISSING: Final[str] = "- [{id}] Missing fact: {fact}."
QUESTION_STRONGER: Final[str] = (
    "- [{id}] Stronger evidence needed for {fact}: this rule requires at least {required}."
)

# ---- Exemptions ------------------------------------------------------------------------------

EXEMPTION_APPLIED: Final[str] = "- [{id}] Exemption [{ex_id}] applies on the facts supplied."
EXEMPTION_NOT_APPLYING: Final[str] = (
    "- [{id}] Exemption [{ex_id}] does not apply on the facts supplied."
)
EXEMPTION_UNRESOLVED: Final[str] = (
    "- [{id}] Exemption [{ex_id}] is not resolved on the facts supplied ({ex_label}),"
    " so it is not treated as applying."
)
EXEMPTION_D6A_LABEL: Final[str] = "APPLIES, but an exemption to it is open"
EXEMPTION_LABEL_CONDITIONAL: Final[str] = "CONDITIONAL"
EXEMPTION_OPEN_MISSING: Final[str] = (
    "- [{id}] Open point for exemption [{ex_id}]: missing fact {fact}."
)
EXEMPTION_OPEN_STRONGER: Final[str] = (
    "- [{id}] Open point for exemption [{ex_id}]: stronger evidence needed for {fact};"
    " at least {required} is required."
)
EXEMPTION_OPEN_CONFIRM: Final[str] = "- [{id}] Open point for exemption [{ex_id}]: confirm {fact}."

# ---- Clock (the note itself is results.CLOCK_NOTE) -----------------------------------------

CLOCK: Final[str] = "- [{id}] Clock: {amount} {unit} after {trigger}. {note}"
CLOCK_IF_CONFIRMED: Final[str] = (
    " Shown because the conditions of this rule are met if the facts to confirm are confirmed."
)
CLOCK_UNDER_READINGS: Final[str] = (
    " Shown because this rule's conditions are met, or would be met if confirmed,"
    " under these readings: {readings}."
)

# ---- Status, source and dates ---------------------------------------------------------------

IN_FORCE_UNPUBLISHED: Final[str] = (
    "- [{id}] In force on {as_of} but not published until {published}."
)
PROPOSED_ASSESSED: Final[str] = (
    "- [{id}] Proposed law, not in force; assessed because proposed rules were included."
)
SOURCE: Final[str] = (
    "- [{id}] Source: {primary}, {source_url} (source record {source_id})."
    " Verification: {status}, last checked {last_verified}."
)
EFFECTIVE: Final[str] = "- [{id}] In effect from {from}. Basis for the dates: {basis}."
EFFECTIVE_UNTIL: Final[str] = (
    "- [{id}] In effect from {from} until, but not including, {to}. Basis for the dates: {basis}."
)
EFFECTIVE_NONE: Final[str] = "- [{id}] No effective date recorded (proposed law)."

# ---- Warnings ----------------------------------------------------------------------------------

WARNING: Final[str] = "- [{id}] Warning {code}: {message}"
HELPER_WARNING: Final[str] = (
    "- [{id}] Warning {code} on [{helper_id}], which this rule relies on: {message}"
)

# ---- List sections -----------------------------------------------------------------------------

NOT_IN_EFFECT: Final[str] = "- [{id}] Not in effect on {as_of}; not assessed."
EXCLUDED_PROPOSED: Final[str] = (
    "- [{id}] Proposed law; not assessed (proposed rules were not included)."
)

# ---- Fact and list formats (D21) -----------------------------------------------------------------

FACT_STATED: Final[str] = "{name} ({value}, {grade})"
FACT_UNKNOWN: Final[str] = "{name} (UNKNOWN)"
FACT_NOT_SUPPLIED: Final[str] = "{name} (not supplied)"
ID_REF: Final[str] = "[{id}]"
LIST_SEPARATOR: Final[str] = ", "
