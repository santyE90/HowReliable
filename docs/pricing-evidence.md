# P5B–P5C: manual Canadian asking-price evidence contract

Status: **P5C backend implemented; no frontend integration**. Design version
`howreliable-pricing-design-1.0`; input schema
`howreliable-pricing-input-1.0`, output schema `howreliable-pricing-comparison-1.0`,
comparison policy `howreliable-manual-comparables-policy-1.0`.

## Implemented P5C boundary

`POST /api/demo/v1/price-comparisons` accepts a complete subject snapshot, comparison date
and up to ten manual entries. Typed input: `howreliable.demo.pricing_schemas.PricingRequest`;
pure engine: `howreliable.demo.pricing.compare_prices`. No listing facts are persisted, fetched
or logged. Responses including validation errors use `Cache-Control: no-store`. The existing
demo factory still needs its historical index to start, but pricing never queries it or the
model, and can compare vehicles outside historical coverage. The frozen API-only factory
and all P4 contracts/policies are unchanged. The dashboard does not yet expose pricing.

P5C supersedes P5B's same-city guard, sparse minimum/maximum suppression and required
comparable identity. Same province is required; city differences are disclosed warnings.
Minimum/maximum are returned for any nonempty primary set, but median/subject positioning
still require three primary representatives. Missing comparable identity is an excluded row;
subject identity remains mandatory. This precedence was reported before implementation.

### Synthetic request and response example

```json
{
  "comparison_date": "2026-11-03",
  "subject": {
    "make": "BMW", "model": "335i", "year": 2011,
    "trim": "base", "powertrain": "3.0 petrol", "transmission": "automatic",
    "drivetrain": "rwd", "body_style": "sedan", "province": "ON", "city": "Toronto",
    "seller_type": "dealer", "condition_status": "no_known_issues_reported",
    "accident_history": "no", "title_status": "normal_reported",
    "odometer_km": 200000, "asking_price_cad": "12000.00",
    "tax_fee_basis": "taxes_and_fees_excluded"
  },
  "comparables": [{
    "entry_id": "demo_a", "source_name": "Synthetic dealer", "source_listing_id": "demo_a",
    "vehicle": {
      "make": "BMW", "model": "335i", "year": 2011,
      "trim": "base", "powertrain": "3.0 petrol", "transmission": "automatic",
      "drivetrain": "rwd", "body_style": "sedan", "province": "ON", "city": "Ottawa",
      "seller_type": "dealer", "condition_status": "no_known_issues_reported",
      "accident_history": "no", "title_status": "normal_reported"
    },
    "odometer": 210000, "odometer_unit": "km", "asking_price": "11000.00",
    "currency": "CAD", "price_basis": "cash_asking", "tax_fee_basis": "taxes_and_fees_excluded",
    "observed_on": "2026-11-03", "listing_status": "active_reported",
    "permission_basis": "synthetic", "permission_attested": true, "is_subject_vehicle": "no"
  }]
}
```

Selected response fields (the full response also preserves normalized observations/provenance):

```json
{
  "schema_version": "howreliable-pricing-comparison-1.0",
  "policy_version": "howreliable-manual-comparables-policy-1.0",
  "evidence_kind": "advertised_asking_prices",
  "counts": {
    "submitted": 1, "eligible": 1, "primary": 1, "contextual": 0, "excluded": 0,
    "confirmed_duplicate_groups": 0, "unresolved_duplicate_groups": 0
  },
  "display_mode": "INDIVIDUAL_ONLY",
  "price_summary": {
    "primary_count": 1, "minimum_cad": "11000.00", "median_cad": null,
    "maximum_cad": "11000.00", "median_display_cad": null,
    "median_display_rounded": false, "subject_difference_from_median_cad": null
  }
}
```

This entry is primary with a city warning, price difference `-1000.00` (comparable minus
subject), and mileage difference `10000` km. Three otherwise eligible distinct entries at
11,000 / 12,000 / 13,000 yield median 12,000 and subject median difference zero. These are
invented examples, not researched prices or market valuations.

The actual output uses `entries[].observation.entry_id`, `possible_duplicate_group_id`,
`price_summary.subject_difference_from_median_cad`, and `coverage` for mileage/date ranges,
city/province/seller coverage, permission/verification statuses, subject-price availability
and gaps/mismatches. `method` discloses guards/sign conventions. `input_sha256` hashes
canonical normalized JSON including input order; exact reruns are deterministic. Reordering
entries changes output order/hash, but not group IDs, representative choice or aggregates.

Malformed money, enums, canonical dates, unsafe reference URLs and structural duplicate
references return 422; confirmed/possible duplicate contradictions also return 422 without
partial results. Commercially unusable prices, identity and provenance produce excluded
entries. URL validation is lexical only; no hostname resolution or retrieval occurs. No
independent authenticity, permission or advertisement-condition verification is claimed.

This defines descriptive comparisons of user-selected advertisements, not fair market
value, completed transaction prices, repair costs, mechanical reliability or buying advice.
It follows the P5A feasibility audit and preserves the [P4 contract](purchase-assessment.md),
historical index, frozen model and [local dashboard](local-demo.md).

## Source permissions and session boundary

Only manually entered facts that the user is permitted to supply are in scope. No scraping,
URL fetching, website previews, provider APIs, uploads, listing descriptions or photographs.
A URL is an inert provenance reference, never an instruction to retrieve it. Manually copying
a listing does not establish rights to redistribute it. Unknown permission is not approval.

P5A found official commercial valuation/listing products but no universally open licence for
Canadian marketplace reuse. Relevant official terms include [AutoTrader Canada](https://www.autotrader.ca/company/terms-of-use/),
[CarGurus Canada](https://www.cargurus.ca/about/terms-of-use/),
[Canadian Black Book](https://www.canadianblackbook.com/terms/) and
[MarketCheck](https://www.marketcheck.com/terms-of-service). These are P5A references, not a
new legal determination or a standing authorization. Recheck applicable terms before real
integration or public demonstrations. A source URL or attribution does not grant permission.

Proposed permission bases: `user_owned`, `explicit_permission`, `licensed`,
`synthetic`, `unknown`. Require a bounded reference describing the asserted basis for the
first three (a permission/contract reference, not the document itself). A user attestation
records their claim; the application cannot authenticate ownership, consent or licence scope.
Permission `unknown`, missing supporting reference, or `permission_attested=false` excludes
the row from numerical comparisons. Do not accept a blanket "publicly visible" basis.
Demonstration fixtures use synthetic facts explicitly labelled as such. Mixing synthetic
and real observations in a numerical sample is prohibited.

Comparables and derived results live only in page memory and transient request/response
memory. No database, files, localStorage, sessionStorage, cookies, exports, analytics or
body logging. Future HTTP responses should use `Cache-Control: no-store`; browser fetches
should also request no-store. Reload/closing the page loses the comparison. Requests must
not persist notes in validation logs or error telemetry. Do not collect contact details,
names, exact street addresses, full VINs, signed/private URLs or permission documents.

## Input envelope and validation layers

Proposed shape:

```text
PricingComparisonRequest
  schema_version: howreliable-pricing-input-1.0
  comparison_date: YYYY-MM-DD
  subject: PricingSubject
  comparables: ManualComparable[0..10]
```

The caller supplies `comparison_date` so identical inputs and policy yield identical results;
no hidden current-time dependency. It is the declared comparison date, not a certification
that listings remain active. This bounded ten-row cap is a UX rule, not sampling validity.

Reuse strict, frozen Pydantic models with forbidden extra fields in later implementation.
Malformed types, oversized strings, invalid enums/dates, repeated local entry IDs, and
structurally invalid decimal strings produce field-addressed request validation errors.
Do not silently drop them or return partial calculations for an invalid envelope.
Structurally accepted but commercially unusable rows (unknown price, negative/zero asking
amount, non-CAD currency, wrong identity, missing provenance) receive `EXCLUDED` decisions.
Thus a missing price is a reviewable exclusion; an amount of `"twelve thousand"` is a type
validation error. The UI should explain this distinction and retain entries for correction.

### Shared identity, configuration and context

| Field | Proposed validation and missing behavior |
| --- | --- |
| `make`, `model` | Subject required; comparable missing/blank is excluded; max 100 characters; existing NFKC/whitespace/case normalization; no fuzzy aliases |
| `year` | Strict integer, existing 1886..2100 range; no adjacent-year inference |
| `trim`, `powertrain`, `body_style` | Optional strings, max 100 characters each; blank becomes null; normalized exact comparison only |
| `transmission` | Existing transmission taxonomy (`automatic`, `manual`, `cvt`, `dct`, `other`, `unknown`); default `unknown` |
| `drivetrain` | Existing drivetrain taxonomy (`fwd`, `rwd`, `awd`, `four_wd`, `other`, `unknown`); default `unknown` |
| `province` | `AB`, `BC`, `MB`, `NB`, `NL`, `NS`, `NT`, `NU`, `ON`, `PE`, `QC`, `SK`, `YT`, or null |
| `city` | Optional string, max 100 characters; normalized exact matching, no inferred geography |
| `seller_type` | `dealer`, `private`, `unknown`; default `unknown` |
| `condition_status` | `no_known_issues_reported`, `issues_reported`, `unknown`; default `unknown`; never verified condition |
| `accident_history` | Existing `yes`, `no`, `unknown`; default `unknown` |
| `title_status` | `normal_reported`, `salvage`, `rebuilt`, `other`, `unknown`; default `unknown`; no document verification |

String bounds apply to submitted strings before normalization. Reject control characters in
identity/reference text; do not normalize distinct trim/engine names into guessed equivalence.
`other` is not sufficient to establish a configuration match. Unknown/null means unavailable,
never "standard trim", no accidents, or no mechanical issues. Users are not required to find
optional advertisement details to submit an entry: missing facts affect eligibility instead.

### Subject vehicle

Reuse make/model/year, `odometer_km` and `asking_price_cad` from the purchase form with
their current semantics: missing values are null, whole nonnegative kilometres, finite
nonnegative Decimal CAD asking price with at most two decimal places. Do not change P4
bounds or validation. An absent or zero subject asking price suppresses positioning
differences, but does not prevent a comparable-only evidence summary.

Add optional shared pricing configuration/location/seller fields above, plus
`tax_fee_basis` below and `subject_reference` (optional source/reference pair) for self-listing
detection. Copy the user's known condition/accident statements into pricing context explicitly;
do not reinterpret P4 notes or infer title/trim from complaint data. Pricing-specific details
must not change the P4 identity digest, recommendation input or policy.

### Manual comparable

| Field | Proposed validation / default |
| --- | --- |
| `entry_id` | Required unique local identifier, 1..40 ASCII letters/digits/underscore/hyphen; stable within the request |
| `source_name` | Optional string max 100; absence/blank is an exclusion |
| `source_listing_id` | Optional string max 120; opaque source identity, no seller personal identifiers |
| `listing_url` | Optional absolute public HTTP(S) URL max 2048; reject credentials, fragment, query string, localhost/private IP literals; never fetched |
| `vehicle` | Shared identity/configuration/context above |
| `odometer` | Null or strict nonnegative integer; maximum browser-safe integer for input interchange |
| `odometer_unit` | `km`, `mi`, `unknown`; default `unknown`; missing reading/unit prevents primary eligibility |
| `asking_price` | Null or strict decimal string, finite, at most two decimals and max 12 integer digits; no symbols/separators/exponents; null or nonpositive values excluded |
| `currency` | `CAD`, `USD`, `other`, `unknown`; default `unknown`; only CAD enters comparisons; no exchange conversion |
| `price_basis` | `cash_asking`, `monthly_payment`, `valuation`, `transaction`, `unknown`; default `unknown`; only `cash_asking` is eligible |
| `tax_fee_basis` | `taxes_and_fees_excluded`, `taxes_excluded_fees_included`, `taxes_and_fees_included`, `unknown`; default `unknown` |
| `observed_on` | Optional canonical date; missing is an exclusion; future relative to comparison date is excluded |
| `listed_on` | Optional canonical date; unknown allowed; later than observation is excluded as inconsistent |
| `listing_status` | `active_reported`, `inactive_reported`, `unknown`; default `unknown`; inactive excluded, unknown contextual |
| `permission_basis` | As defined above; default `unknown` |
| `permission_reference` | Optional string max 200; required for owned/permissioned/licensed bases; do not include confidential contract text |
| `permission_attested` | Strict boolean, default false; required true for all numerical inclusion, including labelled synthetic fixtures |
| `verification_status` | `user_entered_unverified`, `user_rechecked`; default `user_entered_unverified`; never means independently verified by HowReliable |
| `is_subject_vehicle` | `yes`, `no`, `unknown`; default `unknown`; yes excluded, unknown contextual |
| `duplicate_of_entry_id` | Optional existing entry ID, not self; user assertion of same physical vehicle, even across sources |
| `possible_duplicate_of_entry_id` | Optional existing entry ID, not self; uncertain duplicate needing review |

Do not require a URL, VIN, photograph, original listing date, trim or history report. Source
name plus observation and permission information may establish usable provenance without
a listing reference; inability to check identity/deduplication is still an explicit gap.
The subject uses the same tax/fee enum, default unknown. Financing-only prices, valuations
and completed transactions remain visible as excluded entries, never added to asking prices.

For odometer-only conversion use exactly `1 mi = 1.609344 km` with Decimal arithmetic;
retain the original reading/unit and the unrounded converted value. Display rounding must
not change eligibility. This is unit conversion, not a price adjustment.

## Eligibility decision table

Every accepted row has exactly one category. Evaluate all applicable reason codes in fixed
policy order; an exclusion overrides contextual reasons, which override primary eligibility.
An empty primary set must stay empty. Rejected envelope errors are not counted as a run.

| Order | Condition | Category / example reason code |
| --- | --- | --- |
| 1 | No usable provenance/permission, wrong currency/price basis, absent/nonpositive cash price, impossible dates or inactive listing | `EXCLUDED`: `permission_unusable`, `provenance_missing`, `currency_not_cad`, `not_cash_asking`, `price_unusable`, `date_inconsistent`, `listing_inactive` |
| 2 | Subject itself, confirmed duplicate, or normalized make/model/year differs | `EXCLUDED`: `subject_listing`, `duplicate_listing`, `identity_mismatch` |
| 3 | Suspected duplicate unresolved, explicit self-listing status unknown | `CONTEXTUAL_COMPARABLE`: `possible_duplicate`, `subject_identity_unconfirmed` |
| 4 | Configuration, local region, seller type, tax/fee basis, mileage, condition or history unknown or not comparable | `CONTEXTUAL_COMPARABLE`: field-specific `*_unknown`, `*_mismatch` or `mileage_outside_window` |
| 5 | Observation older than freshness window or active status unknown | `CONTEXTUAL_COMPARABLE`: `observation_stale`, `listing_status_unknown` |
| 6 | All checks satisfied and exact make/model/year | `PRIMARY_COMPARABLE`: `exact_identity_and_policy_match` |

Implemented conservative v1 guards, using the P5C approval:

- Configuration: trim, powertrain, transmission, drivetrain and body style must be known
  and match exactly for primary eligibility. Missing values on either side are contextual,
  including two unknowns. Known different configurations are contextual, not corrected.
- Region: same known province for primary. Different/missing cities remain visible warnings,
  not automatic contextual classification. Do not infer distances or local-market equivalence.
- Mileage: both readings known; absolute converted difference at most 25,000 km, inclusive.
  Larger gaps are contextual. No percentage weighting or dollar adjustment. The window is
  an inspectable selection heuristic, not a validated equivalent-value band.
- Freshness: observation within 30 calendar days inclusive of comparison date. Older rows
  remain contextual, never silently refreshed. Known listing date is useful but not required.
- Same known seller type and identical known tax/fee basis for primary; otherwise contextual.
  Do not estimate taxes, fees, certification costs or private/dealer premiums.
- Same known condition/accident/title categories for primary. Salvage, rebuilt or `other`
  title listings are contextual even when subject and listing share that category: broad
  labels cannot establish comparable damage, legal status or repair quality.

These restrictions may produce no primary comparables from ordinary incomplete ads. That
is an honest outcome, not a reason to guess optional attributes or loosen rules invisibly.
No quality probability, mechanical risk level or numerical confidence score is assigned.

## Duplicate and self-listing policy

Treat distinct advertisements as observations, not necessarily distinct physical vehicles.
Keep every submitted entry and its decision; count each confirmed vehicle once in summaries.

1. A user-declared `is_subject_vehicle=yes` or exact subject source/listing reference excludes
   the entry. The frontend should default to unknown rather than silently asserting no.
2. Same normalized source name plus nonempty source listing ID, or identical normalized URL,
   establishes a duplicate advertisement. URL normalization lowercases scheme/host and removes
   a default port; preserves case-sensitive path and trailing slash; no heuristic path rewriting.
3. An explicit `duplicate_of_entry_id` links the same vehicle across sources. Group links
   transitively with exact duplicate evidence. Invalid/cyclic references are envelope errors.
   A component containing the subject is entirely excluded.
4. Choose one representative per confirmed group by latest `observed_on`, then `entry_id`
   lexical order. Do not choose by lowest price or best eligibility. Apply eligibility to that
   representative; other observations are excluded duplicates. An unusable newest observation
   does not silently fall back to an older favorable one. Price changes are retained as gaps,
   not treated as separate vehicles.
5. Different sources with no shared reference cannot be proven independent. Exact normalized
   make/model/year/configuration, odometer reading/unit, city and asking price can flag a
   possible duplicate only when those fields are known. Do not merge on a partial fingerprint.
   All entries in an unresolved possible-duplicate group are contextual and excluded from the
   primary aggregate until the user resolves the ambiguity. User-declared possible links
   receive the same treatment. A group cannot be both confirmed and unresolved; reject
   contradictory declarations. No narrative matching, image matching or VIN lookup.

Entries without a reference can still be considered, but report that cross-source duplicates
may be undetected. Distinct listing IDs do not prove distinct vehicles. Do not claim a global
unique-vehicle count; report confirmed duplicate groups, unresolved duplicate groups and
primary representative count separately.

## Output contract and accounting

```text
PricingComparisonResult
  schema_version, policy_version, comparison_date
  evidence_kind: advertised_asking_prices
  subject: normalized pricing subject
  entries[]: entry_id, normalized observation, eligibility, reason_codes[],
             duplicate_group_id|null, representative_entry_id|null,
             missing_fields[], mismatched_fields[], warnings[],
             price_difference_cad|null, odometer_difference_km|null
  counts: submitted, eligible, primary, contextual, excluded,
          confirmed_duplicate_groups, unresolved_duplicate_groups
  display_mode: NO_PRIMARY_EVIDENCE | INDIVIDUAL_ONLY | SELECTED_SAMPLE_SUMMARY
  price_summary: primary_count, minimum_cad|null, median_cad|null, maximum_cad|null
  subject_position: subject_asking_price_cad|null, difference_from_sample_median_cad|null
  mileage_coverage: primary minimum_km|null, maximum_km|null, subject_km|null
  evidence_coverage: observation date range, regions, seller types, provenance statuses,
                     permissions (asserted/unverified), missingness and mismatch counts
  limitations[], method: eligibility guards, rounding policy, duplicate policy
```

`eligible = primary + contextual` means eligible for evidence display, **not inclusion in the
primary summary**. `submitted = primary + contextual + excluded`. Confirmed duplicate entries
remain submitted/excluded even though one representative can be primary/contextual. Every
entry retains its original input order in output; decisions never disappear. Order reason
codes by the decision-table order, then field declaration order. Derive stable group IDs
from sorted member entry IDs, not hash-randomization or input order.

All money inputs/outputs are decimal strings, never binary floats. Proposed rules:

- Individual price difference = comparable asking price minus subject asking price. Positive
  means that comparable advertises a higher price. Return null when either price is unusable.
  Contextual rows may show their raw difference with a contextual label; excluded rows do not.
- Odometer difference = comparable kilometres minus subject kilometres; preserve sign.
  Never multiply it by a price coefficient. Null if either reading is unavailable.
- Zero primary comparables: `NO_PRIMARY_EVIDENCE`; no price summary or median positioning.
- One/two primary comparables: `INDIVIDUAL_ONLY`; show those prices and differences only.
  Return the individual primary minimum/maximum; keep median and median positioning null.
  These extrema describe only those entered prices, not a market distribution.
- Three or more: `SELECTED_SAMPLE_SUMMARY`; compute unweighted primary-only minimum,
  median and maximum. Sort money numerically; an even-sample median is the exact Decimal
  average of the middle prices. Quartiles and percentage deal grades are outside v1.
- Subject median difference = subject asking price minus selected-sample median. Positive
  means above that selected sample, **not overpriced**. Do not reverse this sign relative to
  its documented label. No subject positioning if subject price is null/zero.
- Preserve exact median/difference in output (half-cent values can result). Render CAD to
  two decimals using explicit `ROUND_HALF_UP`, mark rounded values, and never calculate
  subsequent values from rounded displays. No tax conversion or currency conversion.
- Mileage ranges and date coverage use only primary representatives; separately describe
  contextual coverage so users can see what was left out. All null outputs have an explanatory
  status/reason, not zero or an invented best estimate.

The three-row minimum is a product display rule, not statistical validation. A median of
three selected advertisements is not fair market value. No extrapolation to all Canadian
vehicles, inferred sold prices, bargain ratings, depreciation/repair adjustments or buy/avoid
conclusions. Selection bias, stale/relisted ads, unverified attributes, unequal tax/fee bases,
regional availability, hidden duplicates and missing configuration remain explicit limitations.

## Synthetic scenarios (not real listings or market evidence)

Assume permission-attested synthetic inputs, exact configuration/local market matches,
known matching tax/fee basis, active status, self-listing `no`, and dates within 30 days unless
otherwise stated. Subject: CAD 12,000.00; 200,000 km.

| Case | Expected decision / output |
| --- | --- |
| Three distinct primary entries at 11,000 / 12,000 / 13,000 CAD | Median 12,000; subject difference 0; no fair-value assertion |
| Only entries at 11,000 and 13,000 | Individual differences -1,000 / +1,000; aggregate summary null |
| Four primary entries at 10,000 / 11,000 / 12,000 / 14,000 | Median 11,500; subject difference +500 |
| Four primary entries at 10,000 / 11,000.00 / 11,000.01 / 14,000 | Exact median 11,000.005; render 11,000.01 with rounding indication |
| Correct identity but trim unknown or odometer missing | Contextual with field gaps, never imputed |
| Entry at 225,000 km vs subject 200,000; then at 225,001 | First passes mileage guard; second contextual |
| Same province but different city | Can remain primary with a city warning; no adjustment |
| Different seller type, tax basis or accident status | Contextual; no adjustment |
| Observed exactly 30 days before comparison; then 31 days | First passes freshness guard; second contextual |
| Monthly payment, USD, zero/missing price, provider estimate or sold price | Excluded with specific reasons |
| Different model year or subject itself | Excluded; no broadening to reach three entries |
| Cross-source confirmed duplicate with different prices | Latest observation represents one vehicle; other excluded; discrepancy disclosed |
| Ambiguous cross-source duplicate | All suspected group members contextual pending resolution |
| Missing observation date or unknown permission basis | Excluded provenance; public visibility does not repair permission |
| Three low-price ads plus P4 mechanical concerns | Separate price positioning; P4 caution remains unchanged |
| Synthetic mixed with real entries | Envelope rejected; never present fabricated observations as market evidence |

## Backend boundary and remaining integration gates

P5C introduces strict pricing models and a pure comparison function in separate demo
modules. Reuse identity normalization, Decimal conventions and safe typed responses. The
pricing request must carry a complete subject snapshot plus comparables; never rely on a
hidden earlier assessment or reinterpret text notes. The separate explicit POST
`/api/demo/v1/price-comparisons` keeps P4's API and recommendation input unchanged. This route
is implemented in the demo API. It can operate without an index match/model because
it compares submitted advertisements; display unmatched historical identity explicitly.

P5D can add a compact optional comparable-entry section to the existing dashboard, returning
price positioning alongside, not inside, P4 readiness. Use text nodes, labelled inputs,
explicit manual submission, safe inert source references, no-store requests, version guards
and reset behavior. Changing subject price/configuration or any comparable must invalidate
price results. It must never automatically alter or override the P4 recommendation. A change
to shared P4 inputs must also invalidate P4 results, preserving the existing behavior.

P5E should test Decimal/rounding, boundary dates/mileage, incomplete advertisements,
duplicate order/permutation invariance, count conservation, exclusion precedence, no-network
URL handling, no persistence, XSS-safe text, stale responses, sparse samples and unchanged P4
outputs. Human review must confirm that labels cannot be mistaken for appraisal or verified
condition. P5C synthetic tests cover the implemented engine; browser pricing integration remains P5D.

## P5C decisions and remaining P5D review

1. P5C approves full known configuration and same province for primary eligibility; seller/tax
   basis and known matching condition/history guards remain. Many ads may remain contextual.
2. P5C approves the 25,000 km and 30-day guards and ten-entry cap. These are product heuristics,
   not empirically validated comparison tolerances.
3. Permission attestation/reference rules and the requirement to use synthetic records for
   public demonstrations unless real-data display rights are established.
4. Confirmed/possible duplicate handling, especially newest-only representation and no
   automatic fallback when the newest record is unusable.
5. Separate request endpoint and independence from historical-index coverage, with no
   persistent comparison storage or provider integration.
6. Exact half-cent output plus rounded display is implemented. Median is suppressed below
   three primary observations, while primary minimum/maximum remain available.

P4's recommendation policy remains unchanged. Permission checking is not legal certification;
advertised condition is not inspected condition; selected asking prices are not transaction
prices. P5C implements only the backend; P5D frontend work requires separate authorization.
