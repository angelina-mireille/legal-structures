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
