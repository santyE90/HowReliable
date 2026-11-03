# Purchase assessment P1–P4E: historical evidence and purchase readiness

P1 adds a deterministic backend assessment, not a new predictive model or buying verdict.
Portfolio screenshots/polish and the M1B–M3 count-forecast redesign are deferred. P2 integrates
the existing assessment contract into the local browser without changing the advice rules.

P4C adds optional structured individual-vehicle context, described below. P4B.2 manual NLP
validation is deferred; the bounded P4B findings are not published in the dashboard. P4D
adds conditional purchase readiness, displayed in the existing dashboard by P4E.
Historical counts, inspection priorities, and frozen ML outputs remain unchanged.

## P4D conditional purchase-readiness policy

The existing `POST /api/demo/v1/purchase-assessments` response adds `recommendation`, schema
`howreliable-purchase-recommendation-1.0`, policy
`howreliable-purchase-readiness-policy-1.0`. Requests are unchanged, including legacy requests.
This additive contract leaves original history, advice and model fields unchanged. Existing
schema/methodology markers continue to identify their historical evidence rules; recommendation
logic has its own version. Strict downstream clients must accept the additional response field.

The pure `recommend(RecommendationInput)` function consumes only purchase-specific statements
and maintenance-documentation status. It cannot accept cohort history, odometer, asking price,
model predictions, or NLP outputs. No file access, persistence, external calls or randomness
occur in the function. Major repairs and free-text descriptions are not interpreted as
diagnoses, severity, repair costs, danger, or evidence that issues were resolved. An inspection
summary must be nonblank, but its content is not verified or interpreted by the policy.

### Decision table and precedence

| Priority | Outcome | Requirements / interpretation |
| --- | --- | --- |
| 1 | `PROCEED_WITH_CAUTION` | Any explicitly reported concern or specified documentation limitation; investigate before proceeding, without inferring danger |
| 2 | `INSUFFICIENT_INFORMATION` | No above concern, but one or more essential condition/inspection evidence gaps |
| 3 | `WORTH_CONSIDERING` | All minimum requirements below met and no above concerns; conditional permission to continue consideration, not advice to buy |
| Inactive | `NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS` | Reserved; there is no active blocker rule supported by the present inputs |

Concern precedence is fixed in this order: mechanical problems, dashboard warnings,
drivability problems, outstanding maintenance, reported accidents, seller-reported accident
evidence, inspection issues found, inconclusive inspection, unresolved inspection issues,
partial maintenance records, and undocumented maintenance. Each reported concern is retained;
missing-information reasons follow in the essential-field order below. There are no weights,
numeric risk scores or complaint-count thresholds. Caution can coexist with missing information:
it identifies a known need for investigation, not an independently verified stronger diagnosis.

Any reported accident remains caution under version 1 even with documented history and a
favorable inspection: current fields cannot establish applicability, damage severity or repair
quality. Likewise, `issues_found` with unresolved issues `no` remains caution because claimed
resolution is not verified. Partial/undocumented maintenance triggers documentation caution,
not an assertion that maintenance was omitted. Seller-reported accident evidence is a caution
even with accident history `no`: it describes an evidence limitation, not an accident finding.

### Minimum requirements for conditional readiness

All of the following are necessary:

1. Mechanical problems, warning lights, drivability problems and outstanding maintenance are
   explicitly `no` (user reports, not independently established negatives).
2. Maintenance documentation is `documented`.
3. Accident history is `no` and supporting history documentation is `documented`.
4. Inspection status is `performed`, result is `no_issues_reported`, unresolved issues are
   `no`, and an inspection summary is present. A dropdown alone cannot establish readiness.

The corresponding eleven fields define essential missing information in that order (four
condition flags, maintenance status, accident status/documentation, then four inspection
fields). Unknown, unavailable or inconclusive results and absent/whitespace-only summaries
remain gaps. Not-performed inspection is an unmet requirement. Optional repair/accident/problem
notes are not required and their absence is not a blocker. P4C's broader context gap list can
therefore differ from the recommendation's essential gap list.

This is a conservative process policy, not an empirically validated purchasing threshold.
Documented and performed remain user-selected descriptions: the application does not verify
records, inspection quality, inspector independence, authenticity, dates or current relevance.
A nonblank summary is only a completeness requirement, not a semantic quality check. If notes
contradict structured selections, the user must correct the selections; there is no automated
interpretation of free text. Always verify the evidence before relying on conditional readiness.

### Explanation contract and examples

Every recommendation contains `outcome`, `explanation`, `supporting_reasons`, essential
`missing_information`, `conditions_that_would_change_recommendation`, `limitations`, and
`reserved_outcomes`. Each reason has a stable rule ID, evidence-field references, evidence
origin, explanation and next step. Origins are `user_supplied_condition`,
`user_entered_inspection`, or `generic_purchase_guidance`. Historical NHTSA evidence stays in
`historical_evidence` and never masquerades as evidence about this car. Inspection statements
are specifically user-entered inspection evidence, not verified inspector findings.

| Example | Outcome |
| --- | --- |
| Legacy make/model/year-only request | Insufficient information |
| No inspection, otherwise favorable answers | Insufficient information |
| Warning light reported, other evidence unknown | Proceed with caution, with explicit gaps |
| Inspection issues found, resolution claimed | Proceed with caution pending verification |
| Documented history and complete favorable reported inspection | Worth considering, conditional on verification |
| Same favorable inputs at high mileage or for a high-complaint cohort | Same readiness outcome; existing separate inspection guidance/history still applies |
| One historical report but mechanical concerns reported | Proceed with caution; sparse history does not cancel concerns |

Asking price is excluded because no comparable-market evidence or repair-cost appraisal is
available. Worth considering does not establish good value, affordability, mechanical reliability
or a guaranteed outcome. Mileage is not an independent validated blocker. Frozen 2023 complaint
activity and unvalidated NLP are not individual failure evidence and have no decision role.

### Reserved negative outcome and future integration

Generic issue flags and notes do not establish a defensible exclusion. Activating a negative
outcome would require a separately approved versioned blocker rule, structured independently
verifiable evidence and its applicability to the offered vehicle, verification status/date,
unresolved/remedy status, and clear reconsideration conditions. None of those verification
capabilities is supplied by this policy. Do not infer them from accident status, warnings or
inspection-summary prose. Negative-outcome rules remain inactive even if every concern is yes.

P4E displays the unchanged P4D response near the beginning of the purchase assessment.
No consumer-facing NLP claims are introduced and the policy remains unchanged.

## P4E dashboard recommendation

Select a vehicle, supply any known purchase context, and choose **Assess this vehicle**.
The purchase-readiness section names the selected vehicle and shows the human-readable
outcome, backend explanation, supporting reasons with evidence-origin labels, and essential
missing information. Outcome labels are **Insufficient information**, **Proceed with caution**,
**Worth considering**, and **Not recommended under current conditions**. The last remains
reserved and cannot be reached by the current decision rules. If it unexpectedly appears
in a response, the browser labels it reserved/inactive and asks you to verify the response.

The section uses neutral styling rather than a reliability grade or numerical score. It states
that inputs are not independently verified, historical NHTSA evidence is separate, asking
price is not compared with market values, and independent inspection remains important.
Conditional worth considering is not a mechanical assessment or instruction to buy.

Expand **Conditions that could change this recommendation** for the backend's next steps,
**Recommendation limitations** for full qualifications, and **Technical rules and evidence
provenance** for policy versions, rule IDs, field references and origins. Expand the separate
individual-vehicle details for all submitted notes and optional context gaps. Existing
historical limitations are also expandable to avoid repeating full explanations by default.
Component evidence, charts, inspection prompts, the frozen historical model and the global
NLP sample remain distinct views. The bounded P4B evidence is not exposed.

Editing any purchase input immediately removes the displayed result. Pending or late responses
cannot restore it after an edit or reset. Reset returns all context fields to blank/unknown
defaults. The response vehicle must match the requested make/model/year before any result is
displayed. Missing/malformed recommendation data or unsupported schema/policy versions produce
a **Recommendation unavailable** message, without inventing an outcome or preventing historical
evidence from rendering. HTTP failures keep previous results cleared and show a retryable error.

Results receive keyboard focus at the assessment heading, and the polite status region announces
the outcome or unavailability. Native expandable sections remain keyboard accessible; text and
notes use safe DOM text nodes. The demo remains local and model-optional. No new API contract,
policy, data artifact, persistence or dependency is introduced by P4E. UI tests establish behavior,
not mechanical accuracy, verified inspection quality or comprehensive accessibility certification.

## P4C individual-vehicle context

Expand **Maintenance details**, **Current vehicle condition**, **Accident history**, or
**Independent inspection** in the existing form. The sections are optional and collapsed
initially. Old requests containing only the original fields remain accepted at the same
endpoint. New fields are top-level request properties; unknown keys still fail validation.

| Request field | Values / default |
| --- | --- |
| `outstanding_maintenance` | `yes`, `no`, `unknown` (default) |
| `major_repairs`, `maintenance_notes` | Optional text; default null |
| `mechanical_problems`, `warning_lights`, `drivability_problems` | `yes`, `no`, `unknown` (default) |
| `problem_description` | Optional text; default null |
| `accident_history` | `yes`, `no`, `unknown` (default) |
| `accident_documentation` | `documented`, `seller_reported`, `unknown` (default) |
| `accident_description` | Optional text; default null |
| `inspection_status` | `not_performed`, `performed`, `unknown` (default) |
| `inspection_result` | `no_issues_reported`, `issues_found`, `inconclusive`, `unavailable` (default) |
| `unresolved_inspection_issues` | `yes`, `no`, `unknown` (default) |
| `inspection_summary` | Optional text; default null |

Each text field accepts at most 500 Unicode characters; null or whitespace-only text means
not supplied. Nonblank text is preserved. Enum fields may be omitted, but explicit null,
booleans and unsupported enum values are rejected. Existing `maintenance_history` remains
the documentation-status input; undocumented does not mean maintenance never happened.

Inspection results other than `unavailable`, a known unresolved-issues answer, or nonblank
inspection findings require `inspection_status=performed`. `no_issues_reported` cannot be
combined with unresolved issues `yes`. `issues_found` plus unresolved issues `no` is valid:
previously identified issues may have been addressed, but the application does not verify
that claim. A performed inspection with unavailable findings is valid but incomplete.
Contradictions return HTTP 422; the browser explains inspection conflicts and focuses the
inspection status. Changing its status never silently deletes the supplied findings.

The response adds `individual_vehicle_context`, schema
`howreliable-individual-vehicle-context-1.0`, with:

- `supplied_information`: the normalized new fields, also echoed in `purchase_context`.
- `missing_information`: stable field names for null, unknown or unavailable values,
  including optional notes. A blank optional note is not itself a purchase blocker.
- `follow_up_questions`: deterministic requests to clarify unknowns, reported problems,
  accident details and incomplete inspection findings. No verdict or scoring is calculated.
- `evidence_limitations`: all details are unverified user statements, even if described as
  documented or independently inspected. No problems reported does not mean independently
  verified problem-free; accident status does not establish damage severity.

This is an additive extension of `howreliable-purchase-assessment-1.0`; the existing
methodology and historical evidence rules are unchanged. Consumers must allow the new
response fields. The submitted answers and gap list appear before existing component advice
and historical charts. All fields invalidate pending responses when edited and reset to
unknown/unavailable or blank. Text renders safely through DOM text nodes. There is no new
persistence, document upload, or request-body logging. Do not enter personal information.

Example **hypothetical** context, not a real listing or verified inspection:

```json
{
  "make": "bmw", "model": "335i", "year": 2011,
  "odometer_km": 210000, "asking_price_cad": "12000.00",
  "maintenance_history": "partial", "outstanding_maintenance": "yes",
  "maintenance_notes": "Service documentation has gaps.",
  "major_repairs": "Seller reports battery replacement; receipt unavailable.",
  "mechanical_problems": "unknown", "warning_lights": "no",
  "drivability_problems": "unknown", "accident_history": "unknown",
  "inspection_status": "performed", "inspection_result": "issues_found",
  "unresolved_inspection_issues": "yes",
  "inspection_summary": "Inspector reportedly identified brake wear; written findings pending."
}
```

The result requests clarification and documentation without changing complaint counts or
issuing a buy/avoid judgment. Asking price remains context only. No current individual-car
condition, market value, repair cost, or mechanical-failure probability is established.
The P4D policy above adds conditional process guidance displayed by P4E.

## Browser workflow

Open the [local demo](local-demo.md) and select make, model, and year. Optionally enter whole
kilometres and an asking price in CAD (no currency symbols or thousands separators), then choose
maintenance-documentation status; the default is unknown. Select **Assess this vehicle**.
Blank mileage/price values are sent as null, not zero. Price is sent as a decimal string to
avoid browser floating-point rounding; odometer input must fit the browser's exact integer range.

The primary assessment shows the backend's ranked concerns and support counts, union-based
unknown/other coverage, complaint-supported versus generic inspection prompts, purchase
considerations, evidence limitations, and rule identifiers. Historical timeline/component charts
follow below. The frozen experiment remains a separate secondary panel; the global NLP sample
remains separate from the selected vehicle. No frontend risk score or buy/avoid recommendation
is derived.

Changing any vehicle or purchase-context field clears the previous result and invalidates
in-flight responses. Reassess to refresh. Reset clears the selection and optional values and
restores unknown maintenance status. Invalid fields are highlighted; HTTP 404/409/422/server
errors have explicit messages without retaining stale results. Results receive keyboard focus
at their heading after success; controls retain native keyboard navigation and labels.

P3 stabilization keeps the action disabled while dependent vehicle options load. Once the
purchase assessment is ready, optional ML loading no longer blocks the action. The odometer
control has a native maximum of 9,007,199,254,740,991 to match JavaScript's exact integer
range, so out-of-range values receive normal field validation and focus. This is a browser
numeric-precision limit, not a mileage/condition threshold; assessment rules and API bounds
are unchanged. Late responses remain invalidated after either vehicle or context changes.

## Endpoint and inputs

Run the existing local demo factory as described in [local setup](local-demo.md), then use:

```http
POST /api/demo/v1/purchase-assessments
Content-Type: application/json

{
  "make": "bmw",
  "model": "335i",
  "year": 2011,
  "odometer_km": 210000,
  "asking_price_cad": "12000.00",
  "maintenance_history": "partial"
}
```

The example odometer, asking price and maintenance status are hypothetical user inputs,
not facts from NHTSA or a real vehicle listing. Interactive input/output schemas appear
under this endpoint in `/docs` and `/openapi.json`.

- `make`, `model`, `year` are required. Existing canonical Unicode/case/whitespace
  normalization applies; there are no fuzzy aliases or inferred trim/powertrain matches.
  Year must be an integer in the existing 1886–2100 domain range.
- `odometer_km` is optional/null or a nonnegative integer in kilometres. Strings, booleans,
  fractional readings and negative values are rejected. Omission does not imply zero.
- `asking_price_cad` is optional/null or a finite, nonnegative CAD amount with at most two
  decimal places. JSON numbers and decimal strings are accepted; booleans and NaN/infinity
  are rejected. It is serialized as a decimal string in the response to preserve the value.
  No price comparison, currency conversion, market value or repair-cost estimate is performed.
- `maintenance_history` defaults to `unknown`; allowed values are `documented`, `partial`,
  `unknown`, and `undocumented`. These are unverified user descriptions, not inspected records.
- Unknown request fields are rejected. No VIN, narrative, seller identity or ML probability
  is requested.

An exact historical match returns 200 even when no frozen-model prediction exists for the
vehicle. No historical match returns 404; multiple candidates return 409 without guessing.
Invalid inputs return 422. The assessment does not call frozen prediction inference; however,
the demo factory now permits a missing or validation-failed model bundle. Historical browsing
and purchase assessments still require a valid historical index. Frozen-model endpoints and
the demo prediction link return HTTP 503 with `detail.code=MODEL_UNAVAILABLE` when the model
cannot be loaded. No alternate model or weakened checksum check is used. The original API-only
factory remains fail-closed by default. `/health` is process liveness, not model readiness.

## Response contract

Schema: `howreliable-purchase-assessment-1.0`.
Methodology: `howreliable-purchase-rules-1.0`.

| Field | Meaning |
|---|---|
| `vehicle` | Resolved canonical historical identity |
| `purchase_context` | Validated, normalized user inputs; omitted evidence remains null/unknown |
| `historical_evidence` | Existing `HistoricalSummary`, including source/report counts, dates, timeline, component counts, provenance and limitations |
| `component_coverage` | Total reports, report-set unions for specific labels and unknown/other labels, and unknown/other source rows |
| `reported_component_concerns` | Specific categories with positive observed unique-report counts, labels, supporting source-row counts and the report denominator |
| `inspection_priorities` | Explicit `complaint_supported` versus `generic` advice with rule IDs and support references |
| `purchase_considerations` | Separate odometer, maintenance and price explanations with rule IDs |
| `evidence_limitations` | Reporting, coverage, mapping and individual-vehicle limitations |
| `policy` | Versioned ordering and mileage-prompt policy, without a risk score |

There is no generated timestamp or random selection, so the same validated inputs and
immutable index produce identical serialized responses. Historical index provenance is
preserved. The new endpoint does not modify existing API responses or contracts.

## Evidence rules

The service reuses `HistoricalIndex.discover()` and `summary()`. One additional indexed,
read-only query derives unknown/other coverage by distinct report-ID unions. It changes no
tables, files, or source data and never reads raw complaint narratives.

The historical index's report grouping is source type + ODINO, with source-record fallback
when ODINO is unavailable. Every source row remains accounted for; repeated component rows
do not increase that component's unique-report frequency. A report can support multiple
categories. Specific-component coverage and unknown/other coverage can overlap; neither
their sum nor the sum of component counts is a unique-report total.

Specific concerns are ordered by unique-report count descending, then canonical category
code ascending. This is frequency ordering, **not severity, risk or repair urgency**. `other`
and `unknown` remain visible in the historical distribution/coverage but do not generate
invented component-specific advice. Sparse/empty evidence does not imply a safe vehicle.
The pure builder supports zero-report summaries; an identity absent from the actual index
still returns 404 rather than manufacturing a zero-evidence match.

Component prompts ask an independent inspector to assess current condition and review
relevant service records. Generic whole-vehicle inspection and service-record verification
are labelled separately. No known defect, part diagnosis or repair procedure is inferred.
The existing mapping is deliberately coarse: for example, some powertrain descriptions map
to `other`, so a zero transmission count must not be interpreted as no transmission concerns.

## Purchase context rules

- At **200,000 km or above**, request more condition/service evidence and emphasize an
  independent inspection. This is an explicit advice heuristic, not a validated failure
  threshold. Below it, the result does not assert lower risk or good condition. Missing
  mileage produces a request for the reading. This threshold can be reviewed in a future
  version; it is recorded in every response.
- `documented` maintenance prompts verification of dates, odometer entries and applicability.
  `partial` prompts identification of gaps. `unknown` asks whether records exist.
  `undocumented` states that work cannot be verified here without claiming it never occurred.
  Documentation affects how informed the assessment can be, not inferred mechanical reliability.
- Asking price is displayed only as supplied CAD context. It never changes historical
  evidence, concern ordering, or inspection prompts, and is never called fair or overpriced.

## Limitations and P3 validation scope

NHTSA reports are not verified failures. Counts lack active-population and distance-driven
denominators, concern a limited historical snapshot, and combine differing configurations.
The result is not an inspection, appraisal, purchase verdict, current forecast, reliability
ranking, mechanical-failure probability or validated individual-vehicle risk score.

P3 should validate the purchase workflow across additional vehicles, sparse/unknown evidence,
real keyboard/screen-reader use, browsers, and network-failure scenarios. Review inspection-prompt
wording and the explicit mileage heuristic with the owner; no statistical validation is implied
by UI tests. Preserve the distinction between historical evidence and generic advice, avoid
displaying the frozen forecast as purchase risk, and retain unsupported/unknown states.
