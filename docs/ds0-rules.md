Working document, not legal advice. Rule content comes only from notes/b1-extracts.md; anything not yet read from primary text is marked pending.

Quote convention: each quote block is the entry's Text field copied character for character from notes/b1-extracts.md, without the outer quotation marks. An excerpt is a continuous run of characters from that Text field, labelled as such. Each quote gives the entry heading and the page as that file gives them. Outside quotes, the excluded source is called "the named source" (the entity the order names; matched later against the DS2 excluded-source record).

### US-DHS-2026-01-APPLIES

- Regime: US-DHS
- Role: binding
- applies_to: software
- Title: Order #2026-01 reaches Federal Civilian Executive Branch Agency IT and procurement (Applies To)
- Test in words: the product is in, or offered for, the information technology systems or procurements of a Federal Civilian Executive Branch Agency, other than its national security systems and secure compartmented information systems. The order's Applies To line names agencies, not products; tying a product to it through its use in agency IT or procurement is a modelling choice (D31), not the order's words.
- Readings: none (one test)
- Binding: none
- Exemptions: none
- Effect: WITHIN_APPLIES_TO
- Citation: fr-2026-21447; "Order, Applies To". Quoted for open points: "Footnote 8", "Footnote 11".
- Quotes (copied):
  - "Order, Applies To" (Page: PDF p.2 / 91 FR 66347)

    ```text
    Applies To: Federal Civilian Executive Branch Agencies except for their national security systems and secure compartmented information systems
    ```

  - "Footnote 8" (Location: PDF p. 3 / 91 FR 66348)

    ```text
    The Secretary of Homeland Security's authority to issue exclusion and removal orders is applicable to civilian agencies, to the extent not covered by the authority of the Secretary of Defense and Director of National Intelligence, as defined by 41 U.S.C. § 1323(5)(A)(ii) or (iii).
    (ii)The Secretary of Defense, for exclusion and removal orders applicable to the Department of Defense and national security systems other than sensitive compartmented information systems.
    (iii)The Director of National Intelligence, for exclusion and removal orders applicable to the intelligence community and sensitive compartmented information systems, to the extent not covered by clause (ii).
    ```

  - "Footnote 11" (Location: PDF p. 3 / 91 FR 66348)

    ```text
    Pursuant to 41 U.S.C. § 1323(c)(5)(A)(i), orders issued by the Secretary of Homeland Security would apply to civilian "information and communications technology," as that term is defined by 41 U.S.C. § 1321(5).
    ```

- Facts read: context.civilian_agency_it_or_procurement, context.nss_or_sci_system
- Verification: verified
- Effective:
  - from: 2026-07-24
  - to: null
  - published: 2026-10-20
  - basis: Order prints 'Original Release Date: July 24, 2026' (PDF p. 2, 91 FR 66347) and no issuance or signature date. Required Actions 1 and 2 take effect 'immediately after' issuance (PDF p. 4, 91 FR 66349). from is the Original Release Date, read as the issuance date: a reading, not stated in the order. published is the Federal Register date (91 FR 66346, 20 Oct 2026).
- Open points:
  - Footnote 8 carves out the authority of the Secretary of Defense and the Director of National Intelligence. It prints the statute as "41 U.S.C. § 1323(5)(A)(ii) or (iii)", with no "(c)"; footnotes 11 and 14 print "41 U.S.C. § 1323(c)(5)(A)(i)". The statute check is task A.
  - Footnotes 11 and 14 tie the order to "information and communications technology" as defined by 41 U.S.C. § 1321(5). The statute check is task A. Whether the § 1321(5) definition narrows what counts as a product here: open (DS3).
  - "Applies To" says "secure compartmented information systems"; footnote 8's (ii) and (iii) lines say "sensitive compartmented information systems". Open (DS3); the statute's own wording at 41 U.S.C. § 1323 is copied in task A.

### US-DHS-2026-01-EXCLUDE

- Regime: US-DHS
- Role: top-level
- applies_to: software
- Title: Order #2026-01, Required Action 1: exclusion from civilian agency procurements (product limb)
- Test in words: the product is a product of the named source or of an affiliate of it. Affiliate means the footnote 9/12 control test: an individual or business is an affiliate if, directly or indirectly, either one controls or can control the other, or a third party controls or can control both.
- Readings: none in v0 (whether footnote 13 adds a limb or a reading is open, below)
- Binding: US-DHS-2026-01-APPLIES
- Exemptions: pending task G
- Effect: EXCLUDE_FROM_CIVILIAN_PROCUREMENT
- Citation: fr-2026-21447; "Order, Scope paragraph" (limb 1), "Order, Required Actions 1-2" (item 1), "Order, footnote 9", "Order, footnote 12", "Order, footnote 10", "Order, footnote 13". Quoted for open points: "Order, company name (Summary of Risks from Source)", "Notice, company name".
- Quotes (copied):
  - "Order, Scope paragraph" (Page: PDF p.3 / 91 FR 66348), excerpt: limb 1 only

    ```text
    (1) exclude DeepSeek, DeepSeek-affiliated entities[fn 9], and their products from civilian agency procurements,[fn 10]
    ```

  - "Order, Required Actions 1-2" (Page: PDF p.4 / 91 FR 66349), excerpt: item 1 only

    ```text
    1. Exclude DeepSeek, DeepSeek-affiliated entities,[fn 12] and their products from civilian agency procurements,[fn 13] effective immediately after issuance of this Order, to include agency-approved products lists, service provider equipment lists, e-commerce markets, and other similar functions that facilitate the procurement of information technology hardware, software, and services.
    ```

  - "Order, footnote 9" (Page: PDF p.3 / 91 FR 66348)

    ```text
    For purposes of this Order, an individual or business is an "affiliated entity" or "affiliate" of DeepSeek AG if, directly or indirectly, either one controls or can control the other; or a third party controls or can control both. See 48 C.F.R. § 2.101 (definition of "affiliates").
    ```

  - "Order, footnote 12" (Page: PDF p.4 / 91 FR 66349)

    ```text
    For purposes of this Order, an individual or business is an "affiliated entity" or "affiliate" of DeepSeek AG if, directly or indirectly, either one controls or can control the other; or a third party controls or can control both. See 48 C.F.R. § 2.101 (definition of "affiliates").
    ```

  - "Order, footnote 10" (Page: PDF p.3 / 91 FR 66348). The extract notes that "to" before "civilian agencies" is missing in the source (a typo, checked by AM); footnote 13 has it.

    ```text
    To include third party implementations of DeepSeek used to provide products and services civilian agencies.
    ```

  - "Order, footnote 13" (Page: PDF p.4 / 91 FR 66349)

    ```text
    To include third party implementations of DeepSeek used to provide products and services to civilian agencies.
    ```

  - "Order, company name (Summary of Risks from Source)" (Page: PDF p.2 / 91 FR 66347)

    ```text
    Hangzhou DeepSeek Artificial Intelligence Basic Technology Research Co., Ltd. (hereinafter DeepSeek)
    ```

  - "Notice, company name" (Page: PDF p.1 / 91 FR 66346)

    ```text
    Hangzhou DeepSeek Artificial Intelligence Co., Ltd (DeepSeek)
    ```

- Facts read: software.provided_by_named_source, software.provided_by_affiliate_of_named_source. For the footnote 13 question (open point ii): software.is_third_party_implementation_of_named_source_model, context.used_to_provide_to_civilian_agencies. Mapping input, not a rule leaf (D33): software.provider_and_control_record_declared_complete.
- Verification: verified
- Effective:
  - from: 2026-07-24
  - to: null
  - published: 2026-10-20
  - basis: Order prints 'Original Release Date: July 24, 2026' (PDF p. 2, 91 FR 66347) and no issuance or signature date. Required Actions 1 and 2 take effect 'immediately after' issuance (PDF p. 4, 91 FR 66349). from is the Original Release Date, read as the issuance date: a reading, not stated in the order. published is the Federal Register date (91 FR 66346, 20 Oct 2026).
- Open points:
  - (i) Which name anchors the affiliate test. Three names appear and differ: the order body's (quote "Order, company name (Summary of Risks from Source)"), the notice's (quote "Notice, company name") and the one footnotes 9 and 12 name (quotes "Order, footnote 9", "Order, footnote 12"). No conclusion. Open (DS2).
  - (ii) Whether footnote 13 extends the exclusion to third-party implementations, and if so whether that is a second limb or a reading. Open (DS3).
  - (iii) Footnotes 9 and 12 say "controls or can control". How the graph records the capacity to control, apart from controls edges: open (DS1).
  - (iv) The graph has developed_by but no "provides" edge. How "provided by" is recorded: open (DS1).
  - (v) Required Action 1 reaches "their products"; Required Action 2 reaches "products provided by". Whether these are the same set: open (DS3). Rules 2 and 3 share the software.provided_by_* facts as a proposal only.
  - The entity limb (excluding the named source and its affiliated entities themselves, not only their products) is not built in v0. The rule applies to software only.

### US-DHS-2026-01-REMOVE

- Regime: US-DHS
- Role: top-level
- applies_to: software
- Title: Order #2026-01, Required Action 2: removal from civilian agency information technology systems
- Test in words: the product is provided by the named source or an affiliate of it, or it is a third-party product or service "developed using" implementations of the named source. Products provided by the named source or an affiliate are reached under both readings. The readings differ on "developed using".
- Readings:
  - reading_a: Reading A, narrow: runs on, or is built from, the named source's weights. Proposed graph pattern (proposed; settled in DS3): provided by the named source or an affiliate; or incorporates a named-source model, or a model derived from one (derived_from methods fine_tune, continued_pretraining, quantize, prune, merge).
  - reading_b: Reading B, broad: any development use. Proposed graph pattern (proposed; settled in DS3): reading_a's patterns, plus distilled_from, trained_on_output_of and developed_with_tool.
- Binding: US-DHS-2026-01-APPLIES
- Exemptions: pending task G
- Effect: REMOVE_FROM_CIVILIAN_IT
- Citation: fr-2026-21447; "Order, Scope paragraph" (limb 2), "Order, Required Actions 1-2" (item 2), "Footnote 14".
- Quotes (copied):
  - "Order, Scope paragraph" (Page: PDF p.3 / 91 FR 66348), excerpt: limb 2 only

    ```text
    (2) remove products provided by DeepSeek and DeepSeek entities, and third-party products and services developed using DeepSeek implementations, from civilian agency information technology systems.[fn 11]
    ```

  - "Order, Required Actions 1-2" (Page: PDF p.4 / 91 FR 66349), excerpt: item 2 only

    ```text
    2. Remove products provided by DeepSeek, DeepSeek-affiliated entities, and third-party products and services developed using DeepSeek implementations, from civilian agency information technology systems[fn 14] immediately after the issuance of the Order, or seek an Exception, as described below.
    ```

  - "Footnote 14" (Location: PDF p. 4 / 91 FR 66349)

    ```text
    Pursuant to 41 U.S.C. § 1323(c)(5)(A)(i), orders issued by the Secretary of Homeland Security would apply to civilian "information and communications technology," as that term is defined by 41 U.S.C. § 1321(5).
    ```

- Facts read:
  - both readings: software.provided_by_named_source, software.provided_by_affiliate_of_named_source, software.incorporates_named_source_model, software.incorporates_model_derived_from_named_source_model
  - reading_b only: software.lineage_has_distillation_from_named_source_model, software.lineage_has_training_on_named_source_outputs, software.developed_with_named_source_tool
  - mapping inputs, not rule leaves (D33): software.lineage_declared_complete, software.provider_and_control_record_declared_complete
- Verification: verified
- Effective:
  - from: 2026-07-24
  - to: null
  - published: 2026-10-20
  - basis: Order prints 'Original Release Date: July 24, 2026' (PDF p. 2, 91 FR 66347) and no issuance or signature date. Required Actions 1 and 2 take effect 'immediately after' issuance (PDF p. 4, 91 FR 66349). from is the Original Release Date, read as the issuance date: a reading, not stated in the order. published is the Federal Register date (91 FR 66346, 20 Oct 2026).
- Open points:
  - Scope limb 2 says "DeepSeek and DeepSeek entities"; Required Action 2 says "DeepSeek, DeepSeek-affiliated entities". Both are recorded; no conclusion. Open (DS3).
  - Path depth: whether a lineage path counts at any depth is decided from the text (D30). Open (DS3).
  - Which reading, if any, covers uses_code_from and trained_on edges. Open (DS3).

### US-DHS-2026-01-EXCEPTION

- Regime: US-DHS
- Role: exemption
- applies_to: software
- Title: pending task G
- Test in words: pending task G
- Readings: pending task G
- Binding: pending task G
- Exemptions: pending task G
- Effect: pending task G
- Citation: fr-2026-21447; "Order, Exceptions, 60-day sentence"
- Quotes (copied):
  - "Order, Exceptions, 60-day sentence" (Page: PDF p.4 / 91 FR 66349). The extract notes that the numbered list after this sentence is not extracted.

    ```text
    Executive agency requests for exceptions must be submitted in writing within 60 days of the issuance of this order and include all necessary information for the issuing official to review and evaluate it, including:
    ```

- Facts read: pending task G
- Verification: pending task G
- Effective: pending task G
- Open points:
  - The 60-day sentence sets a deadline for agencies' exception requests. It says "days" with no calendar or business qualifier. It is recorded here only, not as a clock (D36).
  - Whether exceptions cover Required Action 1, Required Action 2 or both: pending task G.

### US-NDAA (NDAA s. 1532 rule)

- Regime: US-NDAA
- Role: pending task C
- applies_to: pending task C
- Title: pending task C
- Test in words: pending task C
- Readings: pending task C
- Binding: pending task C
- Exemptions: pending task C
- Effect: pending task C
- Citation: pending task C
- Quotes (copied): pending task C
- Facts read: pending task C
- Verification: pending task C
- Effective: pending task C
- Open points:
  - P.L. 119-60 s. 6604 is checked while the statute is open.
  - The threshold and any aggregation come from the text (D29, D30).

### US-DOW (DoW order rule)

- Regime: US-DOW
- Role: pending task B
- applies_to: pending task B
- Title: pending task B
- Test in words: pending task B
- Readings: pending task B
- Binding: pending task B
- Exemptions: pending task B
- Effect: pending task B
- Citation: pending task B
- Quotes (copied): pending task B
- Facts read: pending task B
- Verification: pending task B
- Effective: pending task B
- Open points:
  - If the SAM.gov record does not carry the operative text, this rule moves to v0.1.

### EU-AIA-GPAI-PARA60

- Regime: EU-AIA
- Role: top-level
- applies_to: model
- Title: Commission GPAI guidelines, indicative criterion for a downstream modifier becoming provider (para 60, with para 61)
- Test in words: Indicative criterion (para 60): the training compute used for the modification is greater than a third of the training compute of the original model. Para 59 makes a significant change in the model's generality, capabilities or systemic risk the test; para 60 is an indicative criterion for it, not the test itself. Where the modifier cannot be expected to know that value and cannot estimate it, the para 61 replacement applies: a third of 10^25 FLOP if the original model is a general-purpose AI model with systemic risk, and otherwise a third of 10^23 FLOP.
- Readings: none (one test)
- Binding: none
- Exemptions: none
- Effect: INDICATIVE_CRITERION_MET_PARA_60
- Citation: ec-gpai-guidelines-en; "Guidelines para 59", "Guidelines para 60", "Guidelines para 61, condition", "Guidelines para 61, first replacement", "Guidelines para 61, second replacement". Quoted for open points: "Guidelines para 9, first sentence".
- Quotes (copied):
  - "Guidelines para 59" (no page given in the extract)

    ```text
    Instead, the Commission considers a downstream modifier to become the provider of the modified general-purpose AI model only if the modification leads to a significant change in the model’s generality, capabilities, or systemic risk.
    ```

  - "Guidelines para 60" (no page given in the extract)

    ```text
    Based on the considerations above, an indicative criterion for when a downstream modifier is considered to be the provider of a general-purpose AI model is that the training compute used for the modification is greater than a third of the training compute of the original model (see paragraph 115 for how ‘training compute’ should be understood in these guidelines).
    ```

  - "Guidelines para 61, condition" (no page given in the extract)

    ```text
    However, if the downstream modifier cannot be expected to know this value (for example because it has not been communicated by the provider of the original model) and cannot estimate it (see Sections A.1 and A.2 of the Annex to these guidelines for how to estimate training compute) then the threshold should be replaced as follows.
    ```

  - "Guidelines para 61, first replacement" (no page given in the extract)

    ```text
    If the original model is a general-purpose AI model with systemic risk, the threshold should be replaced with a third of the threshold for a model being presumed to have high-impact capabilities (i.e. currently 10^25 FLOP, see Article 51(2) AI Act).
    ```

  - "Guidelines para 61, second replacement" (no page given in the extract)

    ```text
    Otherwise, it should be replaced with a third of the threshold that is part of the indicative criterion for a model to be considered a general-purpose AI model (i.e. currently 10^23 FLOP, see Section 2.1).
    ```

  - "Guidelines para 9, first sentence" (no page given in the extract)

    ```text
    These guidelines are not binding for providers of general-purpose AI models; an authoritative interpretation of the AI Act may only be given by the Court of Justice of the European Union (‘CJEU’).
    ```

- Facts read: model.modification_compute_over_one_third_original, model.original_compute_knowable, model.original_has_systemic_risk, model.modification_compute_over_fallback_threshold
- Verification: pending task D
- Effective: pending task D
- Open points:
  - The guidelines are not binding (quote "Guidelines para 9, first sentence"). How law_status fits them: open (DS5).
  - The para 61 figures are stated as "currently" and borrowed from Art. 51(2) AI Act and Section 2.1, which are not in sources/. Open (DS5).

## Known regimes without public text

Listed under D39. These are not rule files: a rule needs a source record and a quote hash.

| Regime | Status | Reported by (secondary source) | Next step |
|---|---|---|---|
| DNI order | text not public | not yet identified (reportedly listed on SAM.gov without text) | pending task E |
| Further DHS order | text not public | CRS IF13336, 27 Oct 2026 | pending task E |
