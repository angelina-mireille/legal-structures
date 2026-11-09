# Plan

## Revised order (2026-11-08)
Phase A (done), then Phase C (about 25.5 hours), then Downstream v0 (about 33 hours), then Phases D and E. Phase B is parked. Phase 2 (Perimeter brief) is replaced by cited rule files written during Phase D.

## Phase A: setup (week 1, about 5 hours)

| ID | Milestone (one sitting) | Hours | Done when | Status |
|---|---|---|---|---|
| A1 | Environment and repo: uv, Python 3.12 pinned, pytest, ruff (lint and format), pre-commit, GitHub Actions CI. Public repo with MIT licence, DISCLAIMER.md and a README banner. CLAUDE.md carrying the guardrails. .env with the API key, .gitignore, and a monthly spend limit set in the Anthropic Console. | 3 | A fresh clone runs uv sync && uv run pytest green with one smoke test; ruff is clean; CI is green; git ls-files shows no .env. | Done (.env with the API key and the monthly spend limit deferred to C7a) |
| A2 | Source library: one record per primary source (URL, retrieval date, SHA-256 of the retrieved text, and the text itself where it is public domain). A script flags records older than 90 days. | 2 | Every Verified row in section 8 has a record; the staleness script runs in CI. | Done |

## Phase B: Downstream brief (parked 2026-11-08)

| ID | Milestone | Hours | Done when | Status |
|---|---|---|---|---|
| B1 | Close the open sources: official text of the Commission guidelines (paragraph numbers), FAR 2.101, the Defense and Intelligence orders on SAM.gov. | 3 | Rows D4, D6, D7 and D8 in section 8 are Verified or the text is rewritten without them. | Done except section 8 row D4 (DoW and DNI orders), moved to DS4 |
| B2 | Draft (about 1,000 words plus closing paragraph) and finalise the lineage-tree visual. | 5 | Fits two pages; every factual sentence has a source; no conclusion on which reading is right. | Parked: draft saved as docs/downstream-analysis.md |
| B3 | Second-reader review and revisions. | 2, plus waiting | The reader marks both readings as fairly put. | Parked: second reader moves to the v1 eval |
| B4 | Publish as a doc and PDF, with a short post linking it. | 1.5 | Public, dated, and linked from the repo README. Just before publishing, re-check FAR Case 2026-001 (proposed rule, 91 FR 37550, 23 June 2026) and the agency deviations in section 8 rows D11-D12 of the plan doc. | Parked: publication waits for the tool's launch |

## Phase C: shared core (about 25.5 hours; C7a and C7b moved)

| ID | Milestone | Hours | Done when | Status |
|---|---|---|---|---|
| C1 | Graph model in pydantic, JSON Schema export, fixtures. Downstream first: entity, model, dataset and software nodes; lineage edges; evidence on every node and edge; ownership stakes. Perimeter node and edge kinds are added in D1. | 4-5 | 10 valid and 10 invalid fixtures behave as expected; unknown fields are rejected; the committed JSON Schema matches the model. | Done (commit c181448) |
| C2 | Rule schema, loader, staleness warning. Each rule has a status: in_force or proposed. | 3 | A rule missing a citation, source URL or verification date fails to load; a 91-day-old rule loads with a warning. | Done (commit 5ddc721) |
| C3a | Evaluator: three-valued logic, binding rules first. | 4 | Truth-table tests for all, any and not over true, false and unknown pass. | |
| C3b | Five outcomes, exemptions, interpretations, clocks; the result model holds several regimes per entity and a CONFLICT field for v2. | 4 | Each outcome has at least 3 tests; removing any decisive fact yields INSUFFICIENT_FACTS. | |
| C4 | Diff engine. Also renders the divergence table across regimes. | 3 | On 10 hand-made pairs, the diff names exactly the changed facts in each flipped rule's trigger. | |
| C5 | Hash-chained audit log and verify command. | 2.5 | Editing, deleting or reordering any line is detected. | |
| C6 | Renderers: JSON and the counsel memo in Markdown, with templated explanations. | 3 | Snapshot tests pass; every memo statement carries a rule ID. | |
| C7a | LLM extraction with a confirm-each-fact loop in the CLI. | 4 | Proposals show source spans; nothing enters the graph without an explicit accept; with no API key the tool still runs on templates. | Moved after Downstream v0 |
| C7b | Citation validator and prompt-injection suite. | 4 | 20 of 20 invented-citation outputs rejected; 15 injection documents leave extracted facts unchanged and are logged. | Moved after Downstream v0 |
| C8 | Determinism check and the metamorphic test helper. | 2 | 100 runs are byte-identical; one sample relation uses the helper. | |

## Downstream v0 (about 33 hours, after Phase C)

| ID | Milestone (one sitting) | Hours | Done when | Status |
|---|---|---|---|---|
| DS0 | Turn the brief draft into a rule list and facts register (no code) | 2 | Every rule has an ID, regime, test, citation and status; the draft is saved as docs/downstream-analysis.md | In progress (draft saved 2026-11-08) |
| DS1 | Lineage schema and the Product X example | 3 | The schema validates Product X; it has no nationality fields | |
| DS2 | Excluded-source records for the three US regimes, plus a test that rule code names no source | 3 | Records exist with verification data; the test passes | |
| DS3 | DHS rules: exclusion (affiliate control) and removal (two readings). Extract order footnotes 8, 11 and 14 first | 3 | Each reading is tested; UNSETTLED appears where they differ | |
| DS4 | DoW order and NDAA s. 1532 rules, including one ownership threshold. Open the SAM.gov text and the statute first | 3.5 | Both rules are Verified; boundary tests on the threshold pass | |
| DS5 | EU rule: "indicative criterion met (para 60)", read with para 59, fallbacks in para 61, from the guidelines in sources/ | 2.5 | The rule cites paragraph numbers; fallback thresholds are tested | |
| DS6 | Divergence report renderer | 3 | Product X's report shows every disagreement with its driving facts | |
| DS7 | Questionnaire pack (templated) | 3 | Each regime lists the facts needed, their current evidence grade, and conditional attestation text marked for counsel | |
| DS8 | Pending-law toggle | 2 | A proposed rule can be switched on, and the diff shows what flips | |
| DS9 | 12 gold cases and the metamorphic tests | 4 | Labels locked before the first run; all relations pass or failures are logged | |
| DS10 | Demo, README written as a legal memo (including the analysis), 2-minute recording | 4 | Runs from one command; the recording is under 2:00 | |

## Phase D: Perimeter v1a (after Downstream v0, about 38.5 hours)

| ID | Milestone | Hours | Done when | Status |
|---|---|---|---|---|
| D1 | Architecture schema and the four demo architectures (A, A plus veto co-signer, A plus fraud-only veto, 2-of-3 majority). | 3 | All four validate; none has a nationality field. | |
| D2a | FinCEN rules, part 1: binding, definition, wallet factors, multisig, hosted. Transcribed from the memo's F-propositions, each re-checked against the opened text, with pinpoint and quote hash. | 2.5 | Rules load as Verified; one unit test per rule passes. | |
| D2b | FinCEN rules, part 2: six exemptions, payment-processor conditions, exchanger, what attaches, from the memo's remaining F-propositions. Open 31 CFR 1022.380, 1022.210, 1022.320 and 1010.410(f) first. | 2.5 | Same test; P5 in section 8 becomes fully Verified. | |
| D3 | California rules from the memo's C-propositions (s. 3103 and s. 3201 already read in M1): control (with the fraud-only proviso), exchange, transfer, store, exemptions. | 2.5 | P8 is Verified, or the exemption rules are marked unverified and excluded from outputs. | |
| D4 | Sanctions-consequence flag and the s. 1960 display note; resolve the 10-year rule's effective date or leave it out of outputs. | 3 | The flag appears only for US persons with possession or a stop or redirect right, worded as in section 2. | |
| D5 | First 14 gold cases: write the architectures and your own labels before any run. | 4 | Labels are locked in a file whose hash is committed before the first run. | |
| D6 | Seven metamorphic relations, over-warning checks, refuse-and-ask tests. | 3 | All pass, or each failure is logged as an issue with a cause. | |
| D7 | Demo flow and diff table polish. | 3 | The 2-minute script runs end to end from one command. | |
| D8 | Expand to about 25 gold cases, adding session keys, facilitators and fraud-only pauses. | 4 | About 25 cases labelled and locked. | |
| D9a, D9b | Held-out set: FinCEN rulings, enforcement and criminal cases (BTC-e, Helix, Samourai, Storm), DFPI consent orders. Facts encoded from the primary documents; contaminated cases marked. | 6 (2 sittings) | Each case cites its source document and carries a contamination flag. | |
| D10 | Second reader: send the packet, receive labels, compute kappa and Wilson intervals. | 2, plus 2-3 weeks waiting | A script produces the agreement table from the two label files. | |
| D11 | Eval report. | 3 | Published with counts, intervals, the contaminated split, false positives, limits, and the second reader's type (practitioner or student). | |

## Phase E: packaging (after Phase D, about 8.5 hours)

| ID | Milestone | Hours | Done when | Status |
|---|---|---|---|---|
| E1 | README written as a legal memo: question presented, short answer, analysis (how "control" diverges), method, limits, disclaimer, then how to run it. | 4 | A law classmate can follow it without running code; every legal statement cites a rule ID. | |
| E2 | 2-minute demo recording, captioned. | 2.5 | Under 2:00, captioned, linked from the README. | |
| E3 | Outreach assets: tailor the section 6 pitches, a one-page summary PDF, one post. | 2 | One ready message per employer type. | |

## Phase 2: Perimeter brief

| ID | Sitting | Hours | Done when | Status |
|---|---|---|---|---|
| M1 | Read and extract: 1010.100(ff)(5); FIN-2019-G001 ss. 1-2, 4.2, 4.6; Cal. Fin. Code ss. 3102, 3103 and 3201; 31 CFR 501.601, 501.603 and 501.604 | 3 | Each planned proposition has its pinpoint quote saved in the source library | Replaced 2026-11-08: rule files in Phase D |
| M2 | Draft the propositions and the facts register | 3 | Every proposition has an ID, text, pinpoint, facts list and status | Replaced 2026-11-08: rule files in Phase D |
| M3 | Worked examples, the comparison table, the "unsettled" section | 2 | The table gives an answer or "unsettled" for every cell, each traced to a proposition | Replaced 2026-11-08: rule files in Phase D |
| M4 | Review: a classmate for clarity, the second reader later for substance | 1, plus waiting | Reviewer marks each proposition as fairly stated | Replaced 2026-11-08: rule files in Phase D |
