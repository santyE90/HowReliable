# P6B: vehicle problem profile contract and evidence policy

Status: **P6C backend implemented; dashboard integration deferred to P6D**.
Request/response contract: `vehicle-problem-profile-1.0`.
Evidence/question policy: `howreliable-problem-evidence-policy-1.0`.

P6A found that a useful initial profile can use the existing validated historical index.
It also found that processed recall, manufacturer-communication and EWR serving artifacts
are absent locally, while vehicle-specific NLP remains experimentally extracted and not
independently validated. These are availability/validation limits, not evidence of no issues.
The profile describes historical complaint evidence, not verified mechanical failures,
diagnoses, individual failure probabilities, representative defect rates or buying advice.

See [local demo/index contracts](local-demo.md), [purchase assessment](purchase-assessment.md),
[pricing separation](pricing-evidence.md), [component mapping](reliability-events.md),
[recall contracts](recalls.md), [manufacturer communications](manufacturer-communications.md),
and the [P4B experiment limitations](purchase-symptom-experiment.md).

## Initial scope and exclusions

Use only `HistoricalIndex.discover()` and `summary()` against the existing immutable index.
Preserve its identity, counting, report grouping, timeline and provenance semantics. No index
rebuild, new database, narrative scan, artifact acquisition, model inference or NLP extraction.

Initial public evidence consists of normalized cohort identity, source/report counts,
structured mapped components, report-date timeline/coverage, provenance and conservative
inspection questions. User-supplied configuration is context, never a filter claiming the
indexed complaints concern that exact configuration. No VIN is requested or resolved.
Current condition, reported symptoms, crash severity and individual safety are not established.

Raw complaint narratives, private source identifiers, detailed row lineage, symptom spans,
experimental NLP counts/quality metrics and EWR exposure ratios are outside this response.
The optional existing global G1 sample remains a separate view; it is not profile evidence.
The deferred P4B.2 worksheet does not need to be completed to implement this profile.

## Implemented request

Use `POST /api/demo/v1/vehicle-problem-profiles` on the local demo factory.

| Field | Type, default and validation |
| --- | --- |
| `schema_version` | Literal `vehicle-problem-profile-1.0`, default same |
| `make`, `model` | Required nonblank text; max 100 submitted characters each; existing `VehicleAssociation` NFKC, whitespace collapse and case folding |
| `year` | Required strict integer, existing 1886..2100 domain; no adjacent-year matching |
| `configuration` | Optional object, default null; retained as supplied context only |

Configuration fields: optional `trim`, `powertrain`, `body_style`, and `generation` text
(max 100 characters each, blank to null); `transmission` and `drivetrain` use the existing
domain taxonomies with `unknown` defaults. Optional `market_country` is `CA`, `US`, `other`,
or `unknown` (default). Normalize descriptive text consistently but preserve unknown values;
reject control characters and extra fields. Do not infer aliases, engine identity, trim,
generation or drivetrain from broad cohort names. Known configuration still does not verify
complaint applicability. An entirely unknown supplied object is not stronger evidence than null.

Use strict, frozen Pydantic conventions. Reject malformed/incomplete required identity with
422, without guessing. Do not include price, maintenance, condition flags, recommendation,
model/NLP results, date-cutoff filtering or free-form narratives in this request. Report the
existing full historical snapshot; an as-of or date-filtered profile would need separate scope.

Example synthetic request (configuration is hypothetical, not a verified source restriction):

```json
{
  "schema_version": "vehicle-problem-profile-1.0",
  "make": "Example Motors", "model": "Example Sedan", "year": 2011,
  "configuration": {
    "trim": "example trim", "transmission": "automatic", "market_country": "CA"
  }
}
```

## Implemented response composition

```text
VehicleProblemProfile
  schema_version: vehicle-problem-profile-1.0
  policy_version: howreliable-problem-evidence-policy-1.0
  profile_status: AVAILABLE | NO_MATCHING_REPORTS | AMBIGUOUS_IDENTITY | SOURCE_UNAVAILABLE
  requested_identity: normalized make/model/year
  supplied_configuration: normalized configuration|null
  identity_resolution: status, candidates: HistoricalVehicle[]
  applicability: cohort_match, configuration, individual_vehicle, market, limitations[]
  historical_evidence: HistoricalSummary|null
  component_evidence: ComponentEvidenceAnnotation[]
  inspection_questions: InspectionQuestion[]
  source_coverage: complaints, recalls, manufacturer_communications, validated_symptoms
  missing_information: [{code, explanation}]
  limitations: string[]
```

Reuse `HistoricalVehicle`, `HistoricalSummary`, `ComponentCount` and `TimelineBin` semantics.
Embed the existing historical summary once rather than creating another count/timeline store.
Its components are the authoritative per-component `source_row_count` and
`unique_report_count`; its `unique_report_count` is the report denominator. Do not duplicate
provenance or invent a second generated snapshot timestamp.

`ComponentEvidenceAnnotation` decorates a summary entry by `category`, which must match
exactly one `historical_evidence.components[].category`. It contains:

- `category`, readable `label`, `count_reference` (the category key), and
  `denominator_reference="historical_evidence.unique_report_count"`.
- `evidence_basis="documented_structured_component_mapping"`, stable mapping/policy rule ID,
  and `question_ids[]`.
- `interpretation` and `limitations[]`: source component labels were mapped into broad
  categories, not extracted from text or verified as malfunctions.

Thus a component's report and row counts are obtained from the referenced existing
`ComponentCount`, not copied into an independently mutable field. The UI can compose a row
showing label, report count, denominator and secondary row count. No percentage is required.
If a reference cannot be resolved or counts violate invariants, fail validation rather than
displaying an unsupported observation. Inspection questions repeat supporting counts only
because their explanation contract requires them; validate them against the same summary.

### Source coverage sections

Each source section has `availability`, `reason_code`, `explanation`,
`applicability_status`, `snapshot_date|null`, `provenance_reference|null`,
`unique_record_count|null`, and `records|null` where relevant.

| Source | Initial representation |
| --- | --- |
| Complaints | `AVAILABLE`; count/provenance reference the embedded summary; metadata identifies NHTSA ODI and US reporting origin |
| Recalls | `SOURCE_UNAVAILABLE`, reason `processed_serving_artifact_unavailable`; count and records null |
| Manufacturer communications | Same unavailable representation; count and records null |
| Validated symptoms | `VALIDATED_EVIDENCE_UNAVAILABLE`, reason `nlp_human_validation_deferred`; count and records null |

No recall/communication count is fabricated from frozen model features or historical documentation.
For a no-match/ambiguous response, the complaint index can be available while its cohort
applicability is unmatched/ambiguous. In that case complaint count/provenance references
requiring a matched summary are null; retain only available source-level metadata, never
dereference null history or manufacture a zero count. Record the distinction in `reason_code`.
Future recall records may carry campaign ID, source dates, components, source descriptions/remedy
and applicability references; communication records may carry NHTSA document ID, structured type,
dates, components, source summary and applicability references. These are reserved design slots,
not permission to load or publish them in P6C. A future populated contract needs explicit
record schemas, source-validation and applicability review; consumers cannot interpret arbitrary
objects in these slots as approved evidence.

For unavailable sources, null means not evaluated/available, not an empty verified result.
An empty record list and zero count are permissible only after a separately approved source
has been loaded and checked with documented matching semantics. EWR is omitted entirely from
the shopper-facing profile; production is not an active-fleet or distance exposure denominator.

## Resolution, applicability and missing evidence

Keep identity resolution separate from applicability and availability. Do not compress them
into a numeric confidence level or a single "verified" flag.

| Dimension/state | Meaning and response behavior |
| --- | --- |
| `EXACT_COHORT_MATCH` | Exactly one historical canonical make/model/year candidate; does not establish trim/VIN applicability |
| `NO_MATCHING_REPORTS` | No indexed cohort matched this normalized identity; 200 envelope with null history and empty component annotations, never manufactured zero-report history |
| `AMBIGUOUS_IDENTITY` | Multiple candidates; 409 envelope with deterministic candidate list and null history; require explicit resolution, no aggregate across candidates |
| `CONFIGURATION_APPLICABILITY_UNRESOLVED` | Initial state even with supplied configuration; the index has no validated configuration-specific complaint partition |
| `INDIVIDUAL_VEHICLE_NOT_VERIFIED` | No VIN applicability, condition assessment or inspection performed |
| `US_SOURCE_MARKET_APPLICABILITY_UNRESOLVED` | NHTSA US reporting origin; Canadian-market/individual-vehicle relevance is not verified |
| `SOURCE_UNAVAILABLE` | Necessary source cannot be validated/read; 503 where a profile handler can respond, otherwise preserve current startup failure for an invalid/missing mandatory index |
| `INCOMPLETE_EVIDENCE` | Additive quality flag for missing/conflicting dates, unknown/broad categories or unavailable sources; not a failed identity match |

Required identity omissions remain 422; do not reinterpret an incomplete request as no reports.
An exact match with zero rows in a synthetic/future valid source can return AVAILABLE history
with zero counts, but it must say zero recorded evidence is not proof of no problems. Current
discovery cannot find an absent cohort and should not manufacture one. No-match responses
offer only generic inspection questions with null supporting counts; ambiguous responses do
not offer category-specific questions. Invalid source reads must never look like a valid zero.

Candidates sort by normalized make/model/year/ID. Generation is supplied context only and
cannot resolve an index identity conflict without verified source support. Existing broad
identity digests remain unchanged. Configuration, missing metadata and data-source limitations
stay visible even when exact matching succeeds.

Buyer-facing wording must say these are US NHTSA complaint reports. An exact cohort match
does not mean every trim, powertrain, Canadian-market vehicle or individual VIN is affected.
There is no Transport Canada recall verification, current open-recall check, remedy-completion
check or assertion that a particular car has a safety defect.

## Counting, dates and deterministic ordering

1. Preserve every indexed source row. Group unique reports by the existing source namespace
   plus ODINO policy, using CMPLID fallback where needed. Identical narratives never merge
   distinct reports. Do not open narratives to calculate this profile.
2. Each report counts at most once per structured category. A report may support multiple
   categories. Their sum is not a total report count, and component presence is not a count
   of confirmed failures. Retain `other` and `unknown` without inventing specific parts.
3. Sort component entries by unique-report count descending, then canonical category code
   ascending. This is descriptive frequency order, never severity, likelihood or repair urgency.
   Component annotations use the same ordering. No top-N truncation hides remaining categories.
4. Reuse the existing monthly report-date timeline, not occurrence dates. A report enters a
   month only when its selected-cohort rows agree on a valid nonmissing report date. Otherwise
   it enters `month=null`, including its source rows. Retain current ordering (null bucket
   first, then ascending YYYY-MM) and conservation of report and row totals.
5. Earliest/latest valid row dates describe observed extrema, not continuous/lifetime coverage.
   Missing-date row count is not the same as unknown/conflicting-date report count. Preserve
   both meanings; do not impute dates or assign conflicted reports to multiple months.
6. Multiple cohorts may share a report in a different valid index. Never sum cohort counts into
   a global unique-report total. Global provenance conflict counters are global diagnostics,
   not proof of selected-cohort conflicts; selected conflicts require actual scoped evidence.
7. Same normalized request, immutable index and policy produce identical serialized output.
   No random choice, request-time generated timestamp or hidden date-dependent filtering.

Invariants: source rows >= unique reports; each category's unique reports <= cohort reports;
category source rows >= category reports; timeline report/row sums equal cohort totals;
annotations resolve to existing component categories; category-question support matches its
category count. Do not require the sum of category report counts to equal the report total.

## Evidence terminology and interpretation

| Evidence kind | Buyer-facing terminology | Boundary |
| --- | --- | --- |
| Direct structured field | "Complaint reports", "Historical reporting period" | Values recorded by source, not confirmed incident truth |
| Documented component mapping | "Reported component evidence", "Reports associated with this structured component category" | Coarse mapped labels, not textual symptom extraction or diagnosis |
| Generic inspection guidance | "General inspection question" | A practical prompt, not a finding supported by a complaint count |
| Unavailable source | "Source unavailable locally" | Unknown, never zero/clear/healthy |
| Unvalidated NLP | "Validated symptom evidence unavailable" | No symptom category/count or quality result published |

"Reports mentioning this component" may be used only with an immediate explanation that
the count comes from structured labels, not validated narrative mentions. Prefer the more
precise mapped-category wording above. Avoid "known failures", "most likely failures",
"defect probability", "reliability percentage", "guaranteed problems" and "most dangerous".
Do not turn a high category count into a particular failure mechanism, causal relationship,
severity, cost or required repair. A zero category is not proof the component is problem-free.

Disclose self-selected reporting, no exposure denominator, limited historical snapshot,
possible later revisions, broad configuration mixing and imperfect component mappings.
For example, powertrain labels can map to `other`; do not silently treat that as transmission
evidence or infer absence of transmission complaints. Unknown/broad coverage is an evidence
gap, not an allocation to more specific categories.

## Inspection-question policy

Review of existing P4 wording found reusable boundaries: ask an independent inspector to
assess current condition and relevant records, explicitly without an inferred defect/repair.
P6 uses a separate versioned question template; it does not run P4 recommendations or change
their questions, thresholds, policy or outputs.

`InspectionQuestion` fields:

| Field | Meaning |
| --- | --- |
| `question_id` | Stable policy identifier, e.g. `profile.v1.component.engine` |
| `question_text` | Deterministic question, not diagnosis or repair instruction |
| `supporting_component` | Existing category or null for generic questions |
| `supporting_unique_report_count` | Exact mapped-category report count; null for generic |
| `evidence_basis` | `structured_component_reports` or `generic_inspection_guidance` |
| `rule_id` | `profile-question.v1.structured_component` or specific generic rule ID |
| `limitations` | Count is allegations with mapped categories; no individual condition or specific defect established |

For each supported specific category with a positive report count, use this conservative
template with the readable label below:

> What did the independent pre-purchase inspection find about the current condition of the
> {component label}, and what relevant service records can be verified for this vehicle?

Support identifies why the area is worth asking about, not why a part must be defective.
Do not ask unsupported mechanism-specific questions (such as a presumed failed sensor,
overheating cause or replacement interval) from a broad category alone.

| Category | Component label used in the template |
| --- | --- |
| `engine` | engine |
| `transmission` | transmission |
| `electrical` | electrical system |
| `cooling` | cooling system |
| `suspension` | suspension |
| `brakes` | brakes |
| `steering` | steering |
| `fuel_system` | fuel system |
| `hvac` | heating and air conditioning |
| `exhaust` | exhaust system |
| `body` | body and doors |
| `airbags_restraints` | airbags and restraints |
| `tires_wheels` | tires and wheels |

Reuse existing canonical category and presentation-label conventions; do not change the
domain Component enum. `other`/`unknown` retain component entries but generate no invented
part-specific question. Append separately labelled generic questions in fixed order:

1. `profile.v1.generic.independent_inspection`: "Has an independent inspector assessed the
   whole vehicle, including areas with no recorded complaints?"
2. `profile.v1.generic.service_records`: "Which service records can be verified against this
   vehicle's dates and odometer history?"

Specific questions follow component order, then generic questions. Even one report can
motivate a question, but explicitly state that one report cannot establish a recurring
pattern. No minimum-frequency gate or numerical confidence score is approved. An empty or
unknown-only profile still gets generic advice, not reassurance or a purchase verdict.

## Synthetic examples

These are invented fixtures, not BMW/Corolla observations or validated failure descriptions.

| Case | Expected profile behavior |
| --- | --- |
| Four rows, two reports: report A has engine twice plus electrical; B has other | Engine 1 report/2 rows, electrical 1/1, other 1/1; total remains 2 reports/4 rows; sum of category reports is 3, not the denominator |
| Engine and electrical tie at one report | Electrical precedes engine by canonical code; specific questions follow that order |
| Report A rows disagree on dates; B has a valid month | A and all its rows occur once in the null-month bucket; B once in its month; timeline totals reconcile |
| Two reports carry only unknown/other | Both categories remain visible; no specific part diagnosis/question; generic questions only |
| Exact cohort plus supplied trim and CA market | Exact cohort status, unresolved configuration/VIN/Canadian applicability; counts do not narrow to the supplied trim |
| No historical identity match | Null history with explicit no-match status; never a fabricated healthy zero |
| Multiple candidates | 409 ambiguity envelope and deterministic candidates; no guessed history or merged question support |
| Missing recall/TSB artifacts | Unavailable sections with null counts/records, not zero campaigns/documents |
| Local P4B symptom artifacts present | Validated symptoms remain unavailable; no experimental symptoms or quality metrics enter the profile |
| Same profile alongside cheap P5 advertisements or P4 caution | Identical complaint profile; no combined score or override of purchase concerns |

## Smallest P6C architecture

Add a separate typed profile endpoint rather than extending `HistoricalSummary`. The existing
history, P4 and P5 contracts remain unchanged, while profile-specific questions, configuration
and unavailable-source states have an explicit version. POST avoids overloading existing
discovery/history query parameters and carries optional context without a VIN or private notes.

A thin service resolves exactly one identity with the existing index reader and constructs
`HistoricalSummary` once. A pure `build_problem_profile(request, resolution, history)` decorates
the validated summary with deterministic labels, states, source coverage and questions. It
never invokes the purchase recommendation, pricing engine, model registry or NLP package.
Existing labels/prompt concepts may be reused without refactoring unrelated P4 behavior.

Use existing read-only indexed queries. Do not add SQL tables, rebuild the index, scan JSONL
or persist supplied configuration. Startup remains model-optional with the historical index
mandatory; existing checksum validation remains fail-closed. Extra sources being unavailable
must not prevent complaint profiles. If a later official-source artifact is approved, load a
separate versioned/checksummed optional artifact, not a rewritten historical index. None is
needed for the initial structured MVP.

Reuse existing historical provenance once: source/index checksums, schema, cleaning/mapping
versions, injected index-build timestamp, grouping/date policy and source filename. Add only
profile contract/policy identity. Avoid raw source IDs, local machine paths, credentials,
narratives, private review mappings and experimental outputs in public evidence references.
Inspect provenance serialization for safe metadata without changing existing API contracts.
Any frontend integration belongs to a later approved milestone and must preserve P4/P5
separation, safe rendering, keyboard behavior and stale-response guards.

## P6C acceptance tests

Use synthetic fixtures first; no acquisition or full-corpus processing is needed.

- Legacy history, P4/P5, frozen API and model-free startup regressions remain unchanged.
- Canonical Unicode/case/whitespace matching; invalid/missing identity; exact/unmatched/
  ambiguous resolution without fuzzy guesses or changed identity digests.
- Duplicate component rows, overlapping categories, identical text on distinct reports,
  source-record fallback and conservation of reports/rows.
- Date absence/conflicts, null-month ordering and timeline conservation; no occurrence-date
  substitution, accidental as-of claims or global-to-cohort conflict misattribution.
- Stable component order and question IDs/support; null generic counts; unknown-only,
  sparse and zero-evidence synthetic cases without reassurance.
- Supplied configuration never filters broad counts or establishes VIN/Canadian applicability.
- Recall/TSB unavailable counts/records remain null; local experimental artifacts cannot
  become validated symptoms; EWR is absent from the shopper profile.
- Identical requests produce identical serialized profiles; no P4/P5, market-price or frozen
  probability input controls profile counts or questions.
- No corpus/narrative/NLP/model calls, network requests, writes or new persistence; source
  corruption fails closed and existing historical index checksum stays unchanged.
- Read-only representative query timing on bounded fixtures/selected existing cohorts, plus
  relevant pytest, Ruff, mypy and documentation validation before completion.

## Approved P6B decisions implemented in P6C

1. New POST endpoint and reuse of one embedded historical summary with category references,
   rather than duplicated count/timeline/provenance representations.
2. Explicit 200 no-match envelope, 409 ambiguity envelope, 422 invalid request, and preservation
   of current fail-closed startup/503 source-failure boundaries.
3. Configuration as unverified context only, with unresolved configuration/VIN/Canadian-market
   applicability even when the cohort match is exact.
4. The conservative template and 13-category mapping, no specific questions for unknown/other,
   and separately labelled generic questions with null support counts.
5. Unavailable recall/TSB sections and validated-symptom marker with null evidence, no EWR,
   no narrative publication and no requirement to resume P4B.2 annotation.

P6C implements these approved decisions without changing P4/P5 policy, frozen artifacts,
datasets or existing API contracts. Source acquisition and deployment remain outside scope.

## P6C implementation and local verification

The response models live in `src/howreliable/demo/profile_schemas.py`. The thin indexed
service and pure builder live in `src/howreliable/demo/problem_profile.py`; the demo app
registers the endpoint. No profile evidence is displayed in the browser yet.

```powershell
$body = @{ make = 'BMW'; model = '335i'; year = 2011 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/demo/v1/vehicle-problem-profiles' `
  -ContentType 'application/json' -Body $body
```

The returned `historical_evidence` preserves the existing history schema and counts.
Profile provenance exposes only documented index metadata keys, strips any directory from
`source_filename`, and omits unrecognized metadata. Existing history responses are unchanged.
`source_coverage.complaints.snapshot_date` references the injected index-build timestamp,
not a claim of current source freshness or the most recent complaint date.

Model-free read-only verification against the existing index found:

| Cohort | Unique reports | Source rows | Mapped categories | Questions (including 2 generic) |
| --- | ---: | ---: | ---: | ---: |
| 2011 BMW 335i | 22 | 35 | 5 | 6 |
| 2011 Toyota Corolla | 23 | 32 | 7 | 8 |

Repeated identical requests produced byte-identical responses. The historical index SHA-256
remained `e9e1fb211a6c7b7ac929c7e9deca6a48bc32ce7a818a7372ab028f32f2517948`.
These counts describe this restored snapshot, not lifetime incidence or Canadian applicability.
Synthetic tests cover all 13 question categories, overlaps, report fallback, missing/conflicting
dates, zero versus unavailable evidence, invalid requests, safe provenance and error envelopes.
Malformed dates are rejected by the existing clean-record validator before index publication;
the profile neither reparses source records nor substitutes occurrence dates.

P6D may add a separate dashboard section using this endpoint, preserving historical,
purchase-readiness, pricing, frozen ML and exploratory NLP distinctions. It must render
unavailable/ambiguous states, use safe text rendering and stale-response guards, and avoid
presenting questions as diagnoses or structured counts as validated symptom evidence.
