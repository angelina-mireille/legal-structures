# Plan

## Phase A: setup (week 1, about 5 hours)

| ID | Milestone (one sitting) | Hours | Done when | Status |
|---|---|---|---|---|
| A1 | Environment and repo: uv, Python 3.12 pinned, pytest, ruff (lint and format), pre-commit, GitHub Actions CI. Public repo with MIT licence, DISCLAIMER.md and a README banner. CLAUDE.md carrying the guardrails. .env with the API key, .gitignore, and a monthly spend limit set in the Anthropic Console. | 3 | A fresh clone runs uv sync && uv run pytest green with one smoke test; ruff is clean; CI is green; git ls-files shows no .env. | Done (.env with the API key and the monthly spend limit deferred to C7) |
| A2 | Source library: one record per primary source (URL, retrieval date, SHA-256 of the retrieved text, and the text itself where it is public domain). A script flags records older than 90 days. | 2 | Every Verified row in section 8 has a record; the staleness script runs in CI. | |

## Phase B: Downstream brief (weeks 1-2, about 11.5 hours; wins if time is tight)

| ID | Milestone | Hours | Done when | Status |
|---|---|---|---|---|
| B1 | Close the open sources: official text of the Commission guidelines (paragraph numbers), FAR 2.101, the Defense and Intelligence orders on SAM.gov. | 3 | Rows D4, D6, D7 and D8 in section 8 are Verified or the text is rewritten without them. | |
| B2 | Draft (about 1,000 words plus closing paragraph) and finalise the lineage-tree visual. | 5 | Fits two pages; every factual sentence has a source; no conclusion on which reading is right. | |
| B3 | Second-reader review and revisions. | 2, plus waiting | The reader marks both readings as fairly put. | |
| B4 | Publish as a doc and PDF, with a short post linking it. | 1.5 | Public, dated, and linked from the repo README. | |

## Phase C: shared core (weeks 3-7, about 33.5 hours)

| ID | Milestone | Hours | Done when | Status |
|---|---|---|---|---|
| C1 | Graph model in pydantic, JSON Schema export, fixtures. | 4 | 10 valid and 10 invalid fixtures behave as expected; unknown fields are rejected. | |
| C2 | Rule schema, loader, staleness warning. | 3 | A rule missing a citation, source URL or verification date fails to load; a 91-day-old rule loads with a warning. | |
| C3a | Evaluator: three-valued logic, binding rules first. | 4 | Truth-table tests for all, any and not over true, false and unknown pass. | |
| C3b | Five outcomes, exemptions, interpretations, clocks; the result model holds several regimes per entity and a CONFLICT field for v2. | 4 | Each outcome has at least 3 tests; removing any decisive fact yields INSUFFICIENT_FACTS. | |
| C4 | Diff engine. | 3 | On 10 hand-made pairs, the diff names exactly the changed facts in each flipped rule's trigger. | |
| C5 | Hash-chained audit log and verify command. | 2.5 | Editing, deleting or reordering any line is detected. | |
| C6 | Renderers: JSON and the counsel memo in Markdown, with templated explanations. | 3 | Snapshot tests pass; every memo statement carries a rule ID. | |
| C7a | LLM extraction with a confirm-each-fact loop in the CLI. | 4 | Proposals show source spans; nothing enters the graph without an explicit accept; with no API key the tool still runs on templates. | |
| C7b | Citation validator and prompt-injection suite. | 4 | 20 of 20 invented-citation outputs rejected; 15 injection documents leave extracted facts unchanged and are logged. | |
| C8 | Determinism check and the metamorphic test helper. | 2 | 100 runs are byte-identical; one sample relation uses the helper. | |

## Phase D: Perimeter v1a (weeks 8-11, about 38.5 hours)

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

## Phase E: packaging (week 12, about 8.5 hours)

| ID | Milestone | Hours | Done when | Status |
|---|---|---|---|---|
| E1 | README written as a legal memo: question presented, short answer, analysis (how "control" diverges), method, limits, disclaimer, then how to run it. | 4 | A law classmate can follow it without running code; every legal statement cites a rule ID. | |
| E2 | 2-minute demo recording, captioned. | 2.5 | Under 2:00, captioned, linked from the README. | |
| E3 | Outreach assets: tailor the section 6 pitches, a one-page summary PDF, one post. | 2 | One ready message per employer type. | |

## Phase 2: Perimeter brief

| ID | Sitting | Hours | Done when | Status |
|---|---|---|---|---|
| M1 | Read and extract: 1010.100(ff)(5); FIN-2019-G001 ss. 1-2, 4.2, 4.6; Cal. Fin. Code ss. 3102, 3103 and 3201; 31 CFR 501.601, 501.603 and 501.604 | 3 | Each planned proposition has its pinpoint quote saved in the source library | |
| M2 | Draft the propositions and the facts register | 3 | Every proposition has an ID, text, pinpoint, facts list and status | |
| M3 | Worked examples, the comparison table, the "unsettled" section | 2 | The table gives an answer or "unsettled" for every cell, each traced to a proposition | |
| M4 | Review: a classmate for clarity, the second reader later for substance | 1, plus waiting | Reviewer marks each proposition as fairly stated | |
