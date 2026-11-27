# Assessment of TEST-SUBJ-001 (model) as of 2026-06-01

Prototype analysis, not legal advice. Each line follows from the rules and facts supplied; where readings differ, no reading is preferred.

Regimes are shown side by side. This memo draws no conclusion across regimes.

## Regime TEST

### [TEST-ANY-001] Synthetic rule met in two ways

- [TEST-ANY-001] Result: APPLIES. On the facts supplied, the conditions of this rule are met.
- [TEST-ANY-001] No single fact is decisive: removing any one fact alone would not change the result.
- [TEST-ANY-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-ANY-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

### [TEST-APPLY-001] Synthetic rule that applies

- [TEST-APPLY-001] Result: APPLIES. On the facts supplied, the conditions of this rule are met.
- [TEST-APPLY-001] Decisive facts (removing any one would change the result): test.a1 (TRUE, verified), test.a2 (TRUE, documented).
- [TEST-APPLY-001] Exemption [TEST-EXA-001] is not resolved on the facts supplied (APPLIES, but an exemption to it is open), so it is not treated as applying.
- [TEST-APPLY-001] Open point for exemption [TEST-EXA-001]: confirm test.cb1 (TRUE, suspected).
- [TEST-APPLY-001] Clock: 30 calendar_days after the test event occurs. Start date not computed; when the clock starts is for counsel.
- [TEST-APPLY-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-APPLY-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

### [TEST-COND-001] Synthetic conditional rule (applies if confirmed)

- [TEST-COND-001] Result: CONDITIONAL (APPLIES_IF_CONFIRMED). The result rests on facts graded only as suspected. If they are confirmed, the conditions of this rule are met.
- [TEST-COND-001] Decisive facts (removing any one would change the result): test.c1 (TRUE, suspected).
- [TEST-COND-001] Facts to confirm: test.c1 (TRUE, suspected).
- [TEST-COND-001] Exemption [TEST-EXE-001] is not resolved on the facts supplied (CONDITIONAL), so it is not treated as applying.
- [TEST-COND-001] Open point for exemption [TEST-EXE-001]: confirm test.ee1 (TRUE, suspected).
- [TEST-COND-001] Clock: 72 hours after the test notice is received. Start date not computed; when the clock starts is for counsel. Shown because the conditions of this rule are met if the facts to confirm are confirmed.
- [TEST-COND-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-COND-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

### [TEST-COND-002] Synthetic conditional rule (does not apply if confirmed)

- [TEST-COND-002] Result: CONDITIONAL (DOES_NOT_APPLY_IF_CONFIRMED). The result rests on facts graded only as suspected. If they are confirmed, the conditions of this rule are not met.
- [TEST-COND-002] Decisive facts (removing any one would change the result): test.c2 (FALSE, suspected).
- [TEST-COND-002] Facts to confirm: test.c2 (FALSE, suspected).
- [TEST-COND-002] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-COND-002] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

### [TEST-EXEMPT-001] Synthetic rule under an applying exemption

- [TEST-EXEMPT-001] Warning NOT_VERIFIED on [TEST-EXB-001], which this rule relies on: verification status is secondary
- [TEST-EXEMPT-001] Result: DOES_NOT_APPLY (EXEMPT). On the facts supplied, an exemption applies ([TEST-EXB-001]), so this rule does not apply.
- [TEST-EXEMPT-001] Without the exemption, the result would be INSUFFICIENT_FACTS: The facts supplied are not enough to assess this rule. The open points are listed below.
- [TEST-EXEMPT-001] Missing fact: test.x1 (not supplied).
- [TEST-EXEMPT-001] Exemption [TEST-EXB-001] applies on the facts supplied.
- [TEST-EXEMPT-001] Exemption [TEST-EXN-001] does not apply on the facts supplied.
- [TEST-EXEMPT-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-EXEMPT-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

### [TEST-INSUF-001] Synthetic rule with open questions

- [TEST-INSUF-001] Warning NOT_VERIFIED: verification status is secondary
- [TEST-INSUF-001] Result: INSUFFICIENT_FACTS. The facts supplied are not enough to assess this rule. The open points are listed below.
- [TEST-INSUF-001] Missing fact: test.i1 (UNKNOWN).
- [TEST-INSUF-001] Stronger evidence needed for test.i2 (TRUE, declared): this rule requires at least documented.
- [TEST-INSUF-001] Exemption [TEST-EXD-001] is not resolved on the facts supplied (INSUFFICIENT_FACTS), so it is not treated as applying.
- [TEST-INSUF-001] Open point for exemption [TEST-EXD-001]: missing fact test.ed1 (not supplied).
- [TEST-INSUF-001] Open point for exemption [TEST-EXD-001]: stronger evidence needed for test.ed2 (TRUE, documented); at least verified is required.
- [TEST-INSUF-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: secondary, last checked 2026-11-01.
- [TEST-INSUF-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

### [TEST-NOTBOUND-001] Synthetic rule whose binding condition fails

- [TEST-NOTBOUND-001] Result: DOES_NOT_APPLY (NOT_BOUND). On the facts supplied, the binding condition in [TEST-BIND-001] is not met, so this rule's test was not assessed.
- [TEST-NOTBOUND-001] Decisive facts (removing any one would change the result): test.b1 (FALSE, verified).
- [TEST-NOTBOUND-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-NOTBOUND-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

### [TEST-UNRES-001] Synthetic rule with an unsettled binding condition

- [TEST-UNRES-001] Warning STALE: last verified 2026-07-01, 146 days before 2026-11-24 (more than 90)
- [TEST-UNRES-001] Result: DOES_NOT_APPLY (TEST_NOT_MET). On the facts supplied, the test in this rule is not met.
- [TEST-UNRES-001] Whether [TEST-BIND-002] binds the subject is not settled on the facts supplied; the test is not met either way.
- [TEST-UNRES-001] Decisive facts (removing any one would change the result): test.u1 (FALSE, verified).
- [TEST-UNRES-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-07-01.
- [TEST-UNRES-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

## Regime TEST-B

### [TEST-B-AGREE-001] Synthetic rule whose readings agree

- [TEST-B-AGREE-001] Result: APPLIES. On the facts supplied, the conditions of this rule are met.
- [TEST-B-AGREE-001] All 2 readings of this rule give this result.
- [TEST-B-AGREE-001] No single fact is decisive under every reading.
- [TEST-B-AGREE-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-B-AGREE-001] In effect from 2026-01-01 until, but not including, 2027-01-01. Basis for the dates: synthetic test fixture.

### [TEST-B-SPLIT-001] Synthetic rule whose readings differ

- [TEST-B-SPLIT-001] Result: UNSETTLED. The readings of this rule give different results on the facts supplied. Which reading is right is for counsel; this tool takes no view.
- [TEST-B-SPLIT-001] Reading reading_a: APPLIES.
- [TEST-B-SPLIT-001] Reading reading_b: DOES_NOT_APPLY (TEST_NOT_MET).
- [TEST-B-SPLIT-001] Clock: 30 calendar_days after the test event occurs. Start date not computed; when the clock starts is for counsel. Shown because this rule's conditions are met, or would be met if confirmed, under these readings: reading_a.
- [TEST-B-SPLIT-001] In force on 2026-06-01 but not published until 2026-07-01.
- [TEST-B-SPLIT-001] Source: Test Source s. 1, https://example.org/test-source-1 (source record test-source-1). Verification: verified, last checked 2026-11-01.
- [TEST-B-SPLIT-001] In effect from 2026-01-01. Basis for the dates: synthetic test fixture.

## Not in effect on 2026-06-01

- [TEST-B-LATER-001] Not in effect on 2026-06-01; not assessed.

## Proposed law not assessed

- [TEST-B-PROP-001] Proposed law; not assessed (proposed rules were not included).
