# Purchase assessment P1–P2: historical evidence and inspection prompts

P1 adds a deterministic backend assessment, not a new predictive model or buying verdict.
Portfolio screenshots/polish and the M1B–M3 count-forecast redesign are deferred. P2 integrates
the existing assessment contract into the local browser without changing the advice rules.

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
