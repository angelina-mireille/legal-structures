# Decisions

## 2026-10-25 (A2): full text stored only for US federal government works
Records keep the full text only for US federal government works (CFR, Federal Register, FinCEN guidance, FAR), which are public domain. Every other source (e.g. Cal. Fin. Code s. 3102) gets the URL and hash only; the downloaded copy is deleted after hashing.

## 2026-10-25 (A2): sha256 covers the raw bytes as retrieved or saved
The hash is of the file's exact bytes (HTML, PDF), not of extracted text, so anyone can re-check it with `shasum -a 256` and no extraction tool is involved.

## 2026-10-25 (A2): five sources saved by hand from a browser
Automated download was blocked for eCFR (31 CFR 1010.100, 501.601, 501.603, 501.604: redirected to a "Request Access" page) and for leginfo (Cal. Fin. Code s. 3102: HTTP 403 challenge page). The user saved these five pages from a browser on 2026-10-25. Their sha256 covers the file as saved, which may differ from the bytes a script would receive, so a later re-fetch can give a different hash without the law having changed. No unofficial copies were used.

## 2026-10-25 (A2): one record for FR 2026-21447, notice and appendix
The record `fr-2026-21447` covers both the notice and its appendix (the signed order), which are in the same govinfo PDF; the user checked that pages 2-5 contain the signed order. The govinfo PDF is used rather than the Federal Register XML, which has only image references for the appendix.

## 2026-10-25 (A2): FinCEN URL recorded after redirect
FIN-2019-G001 is recorded at the final `/system/files/` URL that served the hashed bytes (the `/sites/default/files/` link redirects there).

## 2026-10-27 (B1): EU output label renamed to "indicative criterion met (para 60)"
The EU output label is renamed from 'presumptively provider' to 'indicative criterion met (para 60)'. Reason: para 60 of the Commission GPAI guidelines calls the one-third test an indicative criterion; para 59 makes significant change the test; 'presumed' appears only in para 67, about high-impact capabilities.

## 2026-10-29 (B2): OCR for scanned pages of fr-2026-21447
Quotes from scanned pages of fr-2026-21447 are OCR transcriptions, each checked against the page image by me and marked as such.

## 2026-11-08 (plan): Downstream v0 built before Perimeter v1a
Build order is now thin core, then Downstream v0, then Perimeter v1a. Reasons: public commentary on the DHS order filled quickly; vendors face provenance questionnaires now; three overlapping US regimes apply different tests, which is Downstream's thesis. LLM milestones C7a and C7b move after Downstream v0. The Perimeter brief is written as cited rule files during Phase D.

## 2026-11-08 (DS0): brief draft kept as an internal analysis
docs/downstream-brief.md is renamed docs/downstream-analysis.md with history kept. It is not polished or published; it is the source for the DS0 rule list and facts register.

## 2026-11-08 (C1): the graph records facts; readings stay in rules
Lineage edges record what happened (distilled from, trained on outputs of, developed with a tool). Which edges count under Reading A or Reading B of "developed using" is decided by the DHS rules (DS3), not tagged in the input, so a lineage file never encodes a legal conclusion. Added beyond the plan doc: trained_on (model to dataset), incorporates (software to a component), and the derived_from method continued_pretraining. Ownership percent is a Decimal so threshold boundaries compare exactly. Domain fields (compute, location) wait for DS1, after the law they serve is read.

## 2026-11-08 (C2): rule files and fail-closed loading
Rules carry law_status (in_force or proposed), named apart from verification.status. A rule has either one trigger or two or more interpretations, never both. Clocks carry an amount and a unit (hours, calendar_days or business_days), because some reporting deadlines are set in hours. Every rule's citation names a source record by id, and the loader checks that the record exists and that its URL matches the rule's source_url. A pack with any invalid file fails to load as a whole; staleness (more than 90 days) and non-verified status are warnings returned with the pack, not errors.

## 2026-11-09 (C3a): evaluator semantics
- D1 Input: the evaluator takes facts as a mapping from fact name to Fact (value TRUE, FALSE or UNKNOWN; grade required for TRUE and FALSE, absent for UNKNOWN; "missing" rejected). A name absent from the mapping is UNKNOWN. No graph access.
- D2 Grades: suspected < declared < documented < verified. A TRUE or FALSE fact graded below a leaf's min_grade is UNKNOWN for that leaf; the trace keeps the supplied value and grade.
- D3 Binding: the binding rule is evaluated first, recursively. Binding FALSE: the trigger is not evaluated and the value is FALSE. Binding TRUE: the value is the trigger value. Binding UNKNOWN: the trigger is evaluated and the value is the Kleene AND of binding and trigger. No binding counts as bound TRUE.
- D4 Output: raw values with a leaf trace; no outcome labels in the evaluator.
- Strong Kleene: a result is definite whenever the known facts settle it (FALSE AND UNKNOWN is FALSE), so no fact is asked for that cannot change the result.

Rejected alternatives:
- Deciding the graph mapping now: it depends on the DS0 facts register and the DS1 schema, and many facts are not graph-derived.
- Weak Kleene: it asks for facts that cannot change the result.
- Below-grade as FALSE: under not, weak evidence becomes a definite TRUE.
- Accepted-grade sets: they need a C2 schema change.
- Binding UNKNOWN stops with UNKNOWN: it asks the binding question even when the trigger is definitely false.
- Binding UNKNOWN treated as bound: a hidden legal assumption.
- Bare values without a trace: C3b would have to re-walk the tree.

Open items:
- Graph-to-facts mapping (DS1/DS3).
- Numeric thresholds need a comparison leaf or a precomputed fact, and the threshold must stay in the cited rule (decide before DS4).
- Grades ignore the direction of a fact: an exculpatory self-declaration counts the same as an admission.
- Whether CONDITIONAL covers results resting on a suspected FALSE (C3b).
- "Decisive fact" means a fact whose removal changes the result (C3b).
- Interpretations and unless (C3b).
- A binding rule may be about a different subject than the rule it binds (e.g. entity vs model); the facts mapping then carries facts about both subjects. Decide namespacing with the graph-to-facts mapping.

## 2026-11-24 (C3b): outcomes
- D1 Relevance: a fact is relevant to a rule's result if some TRUE/FALSE assignment of the other unknown facts makes setting it TRUE rather than FALSE change the rule value. It is computed by re-running the C3a evaluator with hypothetical facts at grade verified. More than 12 distinct unknown facts raises OutcomeError (fail closed).
- D2 Decisive facts: for a TRUE or FALSE rule value, a fact is decisive if removing it from the facts mapping changes the value (by C3a monotonicity, to UNKNOWN).
- D3 Outcome order for a rule with one trigger, from the rule-level value (binding included):
  1. Bound FALSE: see S1 (revised).
  2. Value TRUE or FALSE, and removing every suspected fact makes it UNKNOWN: CONDITIONAL, direction APPLIES_IF_CONFIRMED (TRUE) or DOES_NOT_APPLY_IF_CONFIRMED (FALSE); facts_to_confirm are the removed suspected facts relevant (D1) to the reduced result. A result resting on a suspected FALSE is CONDITIONAL too.
  3. Value TRUE: APPLIES. Value FALSE: DOES_NOT_APPLY, reason TEST_NOT_MET, binding_unresolved when bound is UNKNOWN.
  4. Value UNKNOWN: INSUFFICIENT_FACTS, one question per relevant unknown fact, sorted by fact: MISSING (absent or supplied as UNKNOWN) or NEEDS_STRONGER_EVIDENCE (with the current grade and the highest min_grade among the leaves that downgraded it).
- D4 Interpretations: each reading's trigger is evaluated with the rule's binding and given a D3 outcome; every per-reading outcome is kept. Readings identical in (outcome, reason, direction) collapse to that outcome with readings_agree True; otherwise the outcome is UNSETTLED.
- D5 Unless: not applied in C3b; the outcome carries the unless ids as exemptions_pending.
- S1 (revised) Bound FALSE: evaluate again with every suspected fact removed. Reduced bound still FALSE: DOES_NOT_APPLY, NOT_BOUND. Reduced value UNKNOWN: CONDITIONAL, DOES_NOT_APPLY_IF_CONFIRMED, with the relevant removed suspected facts to confirm. Reduced value FALSE (the trigger fails on its own): DOES_NOT_APPLY, TEST_NOT_MET, binding_unresolved. A suspected fact never yields a definite DOES_NOT_APPLY through the binding.
- S2 binding_unresolved is True only with DOES_NOT_APPLY / TEST_NOT_MET; a CONDITIONAL never carries it.
- S3 When readings collapse, the rule's decisive_facts are those decisive in every reading (so removing one still gives INSUFFICIENT_FACTS); facts_to_confirm and questions are the union across readings, and a fact needing stronger evidence takes the highest required grade.
- S4 A fact counts as unknown for D1 if any leaf reads it as UNKNOWN (including a fact readable in one leaf but below another leaf's min_grade); each hypothetical replaces the fact in every leaf.
- Overdetermined results have no decisive facts: when two facts each support the result on their own (any(TRUE, TRUE), or a suspected FALSE binding with a verified FALSE trigger), no single removal changes it, so decisive_facts is empty.

Rejected alternatives:
- Listing every unknown leaf as a question: over-asks facts that cannot change the result.
- A sixth outcome for weak evidence: breaks the five outcomes.
- A NOT_BOUND outcome, or omitting unbound rules: a reader cannot see why a regime is silent.
- CONDITIONAL only on a suspected TRUE: a suspected exculpatory fact would read as a conclusion.
- Always UNSETTLED when interpretations exist: contradicts the demo and DS3's done-when.

Open items for C3c:
- Exemptions (strict, flagged).
- Clocks (display only).
- Result model by subject and regime.
- applies_to and law_status filtering.
- Whether the cap of 12 fits real rules.

## 2026-11-24 (C3c): exemptions, clocks and the result model
- D6 Exemptions are strict. Start from the C3b RuleOutcome (the base outcome).
  - Base DOES_NOT_APPLY (NOT_BOUND or TEST_NOT_MET): kept; exemptions are not evaluated.
  - Otherwise each rule in unless is assessed with the same C3c logic, recursively, so an exemption's own exemptions apply.
  - An exemption applies only if its final outcome is APPLIES (and D6a holds). If any applies: final outcome DOES_NOT_APPLY, reason EXEMPT, exempted_by = the applying ids (sorted), no direction, no clock.
  - If none applies: the base outcome, reason and direction stand. An exemption whose final outcome is CONDITIONAL, INSUFFICIENT_FACTS or UNSETTLED is listed as unresolved, carrying its questions and facts_to_confirm. An exemption that is DOES_NOT_APPLY is listed as not applying, with no flag.
  - An exemption written with interpretations follows the same rule: UNSETTLED means it is not applied, and it is flagged.
  - A repeated id in the exemption chain raises ResultError (guard for hand-built packs).
- D6a Pessimistic nesting: an exemption counts as applying only if its final outcome is APPLIES and none of its own exemptions is unresolved. Otherwise it is listed as APPLIES, not applied, unresolved, carrying the open sub-exemptions' questions and facts_to_confirm. Whoever relies on an exemption bears the uncertainty at every level: an open carve-back (a sub-exemption) stops the exemption applying, just as an open exemption does not displace the rule. This also keeps T12 monotone: under D6 alone, removing a carve-back fact could turn INSUFFICIENT_FACTS into DOES_NOT_APPLY / EXEMPT.
- D6b An UNSETTLED exemption carries the union of its readings' questions and facts_to_confirm, merged as in C3b S3.
- EXEMPT exists only at the C3c layer: a C3b RuleOutcome rejects it, and assess_rule never produces it.
- D7 Clocks are display only; no date arithmetic. When the rule has a clock, a ClockNote copies amount, unit and trigger exactly:
  - status APPLIES when the final outcome is APPLIES;
  - status IF_CONFIRMED when it is CONDITIONAL with direction APPLIES_IF_CONFIRMED;
  - status UNDER_READINGS when it is UNSETTLED and at least one reading is APPLIES or CONDITIONAL with APPLIES_IF_CONFIRMED, listing those reading ids;
  - no clock otherwise.
  - Every ClockNote carries the fixed text: "Start date not computed; when the clock starts is for counsel."
- D8 Result model: assess_subject(subject_id, subject_kind, pack, facts, include_proposed=False) -> SubjectResult.
  - Top-level rules: applies_to equals subject_kind (applies_to is a single node kind), excluding any rule named in any rule's binding or unless (helper rules are evaluated inside the rules that use them).
  - law_status proposed rules are excluded unless include_proposed is True; the excluded top-level ids are listed in excluded_proposed.
  - If an included rule relies on a proposed rule through binding or unless, at any depth, while include_proposed is False: ResultError naming both rules. Pending-law dependencies are DS8's job.
  - Results are grouped by regime: RegimeResult(regime, rules sorted by id, conflict). conflict is reserved for v1 and must be None.
  - An unknown subject_kind raises ResultError.

Rejected alternatives:
- Kleene exemptions (rule AND NOT exemption): "applies" would never show while any exemption is open.
- A per-rule field choosing who bears the uncertainty: right long term, but a schema change, so later.
- Clocks only on APPLIES: a reporting clock matters most while a fact is being confirmed.
- Reporting helper rules as their own results: noisy, and the binding question already shows through NOT_BOUND and binding_unresolved.

Open items:
- A per-rule burden choice for exemptions.
- Pending-law dependencies (DS8).
- Fact namespacing when a binding or exemption rule applies to a different node kind than the rule it serves.

## 2026-11-26 (C3d): effective dates and as-of evaluation
- D9 Schema: a rule gains effective {from, to, published, basis}. The dates are dates or null, and basis is text or null. In the Python model the field is from_ (alias "from"), because from is a Python keyword. An omitted block counts as all null. from is inclusive and to is exclusive. basis says where in the primary text the dates come from. The loader fails closed:
  - law_status in_force with no from;
  - from on or after to;
  - from set without a basis.
  Proposed rules may leave from empty.
- D10 as_of is a required, keyword-only argument to assess_subject and assess_rule_final. It has no default, and the code never reads the clock. A datetime raises TypeError, matching load_rule_pack's handling of today. evaluator.py and outcomes.py are unchanged.
- D11 Filtering happens in results.py:
  - A top-level rule outside its dates is left out, and its id is listed (sorted) in not_in_effect, beside excluded_proposed. The proposed filter runs first, so a proposed rule outside its dates is listed only in excluded_proposed when include_proposed is False.
  - A helper rule (binding or unless, at any depth) outside its dates raises ResultError naming both rules. The check is static: it walks every reference, whether or not evaluation reaches it.
  - assess_rule_final on a rule that is itself outside its dates raises ResultError naming the rule and as_of.
  - A proposed rule with no from is included when include_proposed is True.
- D12 Published: a rule in effect at as_of whose published date is after as_of is included, and its RuleResult carries in_force_unpublished = True. Otherwise the flag is False, including when published is null. The outcome is unchanged; the flag is display only.
  - RuleResult gains law_status, copied from the rule. A validator refuses in_force_unpublished = True unless law_status is in_force, so a proposed rule is never flagged. Reason: renderers and the pending-law toggle need each result to say whether it comes from law in force or proposed law.
- D13 as_of is recorded on SubjectResult and survives the JSON round trip.

Rejected alternatives:
- as_of defaulting to today: breaks the fixed-date rule in CLAUDE.md.
- The date check in the evaluator: C3a D4 keeps outcome labels out of the evaluator.
- Treating an out-of-date helper as false: a hidden legal assumption.
- Storing published without using it: loses the "in force but unpublished" signal.

Open items:
- What an out-of-date binding or exemption should mean, once a real time-limited helper appears.
- The static helper date check may be stricter than needed once real time-limited helpers exist.
- Warnings for rules taking effect in the future.
- How to record a date the primary text leaves unclear (basis says so, and the rule stays unverified).

## 2026-11-26 (C4): diff engine and divergence table
- D14 What is compared: diff_subjects(subject_id, subject_kind, pack, facts_before, facts_after, *, as_of_before, as_of_after, include_proposed=False) -> SubjectDiff in src/core/diff.py.
  - It calls assess_subject once per side, with the same pack, subject and include_proposed, so a result can never be paired with the wrong facts.
  - as_of_before and as_of_after are both required and keyword-only, with no default; the code never reads the clock. A datetime raises TypeError, as in assess_subject.
  - SubjectDiff carries both SubjectResults and the fields below.
  - Comparing two packs is out of scope (DS8).
- D15 Flips and detail changes, for a rule assessed on both sides:
  - flip: the final (outcome, reason, direction) on RuleResult differs (the key C3b uses to collapse readings);
  - detail change: no flip, but at least one of these differs: base (the base outcome, reason and direction), base.binding_unresolved, base.decisive_facts, base.facts_to_confirm, base.questions, readings (each interpretation's id, outcome, reason, direction), exemptions (each exemption's rule_id, outcome, applied, unresolved, questions, facts_to_confirm), exempted_by, clock (status, readings), in_force_unpublished;
  - otherwise unchanged.
  - "base" was added when the plan was approved. Reason: under an exemption that applies on both sides, the underlying rule can change while every other listed field stays the same, and that change matters if the exemption later falls away.
  - An exemption's questions and facts_to_confirm were added to "exemptions" before commit. Reason: otherwise a fact that changes only an open exemption's questions puts the rule in unchanged_despite_changes, which reads as "this change did not matter".
  - Every changed rule, flip or detail, lists the names of the detail fields that differ (sorted), not their values; the values are in the two results the diff carries.
  - A rule assessed on one side only goes in entered_effect (not in effect before, assessed after) or left_effect (the reverse), sorted. Nothing else is said about it.
- D16 Changed facts:
  - A fact has changed when its (value, grade) differs between facts_before and facts_after. An absent fact counts as UNKNOWN with no grade, so absent versus UNKNOWN is not a change. A change of grade alone is a change.
  - The facts a rule refers to are read statically from the pack, not from the trace: every leaf in its trigger or in each interpretation, in its binding rule at any depth, and in each rule in its unless list at any depth (including their bindings and their own unless rules). Reason: ExemptionResult has no trace, and the trace skips the trigger when the binding is FALSE.
  - Each changed rule lists every changed fact it refers to, with the before and after Fact (None when absent) and every place the fact appears: FactRead(rule_id = the rule whose expression holds the leaf, via = "self" | "binding" | "unless" (the first step from the changed rule), interpretation_id = the reading id or None).
  - These are changed facts the rule refers to. The diff makes no claim that any of them caused the change.
  - unchanged_despite_changes: sorted ids of rules assessed on both sides, unchanged, that refer to at least one changed fact.
  - Guard: a flip that refers to no changed fact raises DiffError (with one pack this cannot happen, so reaching it means a bug). A detail change that refers to no changed fact raises DiffError unless its only changed field is in_force_unpublished, which can come from the dates alone.
- D17 Divergence table: divergence_table(result: SubjectResult, pack) -> DivergenceTable in src/core/divergence.py.
  - One row per assessed rule, sorted by (regime, rule_id): regime, rule_id, effect (looked up in the pack), law_status, outcome, reason, direction, decisive_facts (from base), exempted_by, in_force_unpublished, and for an UNSETTLED rule its readings (id, outcome, reason, direction).
  - The table also copies subject_id, subject_kind, as_of, not_in_effect and excluded_proposed.
  - No aggregation across regimes: no "regimes disagree" flag, no grouping by effect, no winner. RegimeResult.conflict stays reserved.
  - A rule id missing from the pack, or whose regime differs from the pack's, raises DivergenceError.
  - No rendering of any kind; that is C6 and DS6.
- D18 Models: every new model is a frozen pydantic model with extra="forbid". Every tuple is sorted, and validators refuse unsorted input, as in results.py. SubjectDiff and DivergenceTable survive a JSON round trip. No I/O, no logging, no clock; inputs are never changed.
  - Added when the plan was approved: a SubjectDiff validator refuses before and after results whose subject_id or subject_kind differ.

Rejected alternatives:
- Diffing two SubjectResults supplied by the caller: nothing checks they came from the facts given.
- Facts read from the trace: exemptions carry no trace; unbound triggers are skipped.
- Flip by outcome alone: hides EXEMPT versus TEST_NOT_MET.
- Calling changed facts causes: a counterfactual claim the diff does not test.
- Grouping rules across regimes by effect: effect labels are free text per rule, so a match would be coincidence.

Open items:
- A way to mark rules in different regimes as answering the same question (a rule field, decided at DS0 with real text).
- Diffing two packs (DS8), where the no-changed-fact guard will not hold.
- Which changed facts were decisive on each side, if C6 needs it.
- Effect on RuleResult instead of a pack lookup, if C6 needs results that describe themselves.
- unless on a rule used as a binding rule is never applied (the evaluator follows binding; results.py applies unless only to the assessed rule and its exemptions), and the loader does not refuse it. _fact_reads mirrors this by following binding links only. A loader check is a C2 change; to do before DS3.
