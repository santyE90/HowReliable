# Local browser demo (Milestones H2–H3)

**Current direction:** P1/P2 provide the [purchase-assessment workflow](purchase-assessment.md),
using historical evidence and deterministic inspection prompts. H4 screenshots/recordings
and the M1B–M3 count-forecast redesign are deferred. **Assess this vehicle** is the primary
browser action; historical charts and separate ML/NLP panels remain available. The model is
optional for purchase/history browsing; frozen prediction values and rules are unchanged. The checkpoint
below preserves the earlier H3/H4 handoff history.

P4C adds optional expandable maintenance, condition, accident-history and inspection fields.
Results show the supplied unverified details, missing information and deterministic follow-up
questions. Unknown is the default; no problems reported is not verified problem-free condition.
Inspection findings require a reported performed inspection; contradictory entries are rejected.
Inputs are not persisted and do not alter historical evidence or the frozen ML experiment.
P4B.2 manual NLP validation is deferred, its local worksheets are retained, and its findings
are not exposed here. P4D adds a versioned `recommendation` response field using
structured purchase context, with caution / insufficient information / conditional worth
considering outcomes. P4E displays this unchanged recommendation near the top of results,
with reasons, evidence origins, essential gaps, and expandable reconsideration conditions,
limitations and technical rules. The negative outcome remains reserved/inactive. Guidance is
conditional on verification, not a reliability score, mechanical inspection or market appraisal.
Historical evidence, the frozen ML experiment and global NLP stay separate. Edits/reset clear
the recommendation; late/mismatched responses cannot restore stale results. A missing/malformed
recommendation shows an unavailable message while history remains usable. See the
purchase-assessment decision table and P4E workflow.
Startup and artifacts are unchanged.

P5D adds an optional **Compare Asking Prices** panel. Expand it, reuse the selected vehicle,
price and odometer, enter known subject configuration/location, and manually add up to ten
permitted comparable advertisements. Complete source/observation/permission information and
expand configuration/evidence fields as available. Unknowns remain explicit. Select
**Compare asking prices** to call the existing local pricing endpoint. See the
[pricing workflow and contract](pricing-evidence.md) for fields and comparison rules.

Results distinguish primary/contextual/excluded entries, display primary extrema and
individual differences, and show a selected-sample median only at three primary entries.
This is advertised-price positioning, not an appraisal or good-deal verdict. No URLs or
external listings are retrieved; source facts and permissions remain unverified. Pricing
stays separate from P4 readiness, history, ML and NLP. Edits invalidate pending results;
vehicle changes clear subject-specific pricing details. Clear pricing entries/global Reset
clear the relevant state, and reload loses comparables. No persistent listing storage, new
dependencies or additional data artifacts are required.

P5E completes the local manual-pricing validation pass. It adds strict response binding to
the submitted subject price/odometer and comparable facts, with exact decimal-string checks.
Synthetic scenarios exercise sparse/mixed samples, thresholds, permissions, duplicates,
arithmetic and asynchronous failures. Advertised-price positioning remains separate from
P4 readiness and is not an appraisal. User permissions, listing truth and market coverage
are not independently verified; broader device/screen-reader certification is not claimed.

## Where We Left Off — H3.1 checkpoint (2026-11-02)

This preserves the H3.1 handoff; development has resumed for H4 portfolio readiness.
H4A audited the repository and H4B updates presentation/reproducibility documentation;
H4C will capture actual screenshots and a walkthrough. See [reproducibility](reproducibility.md)
for the clean-clone, historical-index, and full-demo setup levels, and
[licensing status](licensing.md) for the pending owner decision.
H1 audited readiness, H2 built the historical
index/API, and H3/H3.1 added and refined the browser dashboard. The primary view is historical
owner-reported complaints: unique reports, report-date timeline, structured components, and
coverage. Source-row counts remain secondary. Readable component labels are presentation-only;
categories overlap and counts are not vehicle failure rates. API contracts, counts, model
outputs, and original data remain unchanged.

The secondary **Historical ML Experiment — 2023 Complaint Activity** estimates whether at
least one NHTSA complaint would be reported for the selected vehicle cohort during 2023 using
information available through December 2022. It is not a reliability score, an individual
failure probability, a current forecast, or a mechanical failure/repair prediction. The
separate global G1 NLP sample covers 1,000 source rows / 691 reports, predates the latest
rules, and represents neither the selected vehicle nor the full corpus.

### Resume locally

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn howreliable.demo.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**; stop with **Ctrl+C**. Required: the installed `.venv` plus
`data/processed/demo/history-v1-20261102-v2.sqlite` and its `.provenance.json` sidecar.
The canonical bundle is optional for the ML experiment, and the G1 summary/sidecar are optional
for the separate NLP panel. Earlier H2/H3 handoff requirements below are superseded where noted.
No rebuild, corpus processing, annotation, or cloud access is needed to resume the demo.

The index contains 412,866 accepted source rows, 290,634 unique reports, and 10,670 vehicle
identities; 8,416 have frozen model predictions. Its valid report dates span 2020–2024.
Useful walkthrough vehicles: **2011 BMW 335i** and **2011 Toyota Corolla**. Use selectors rather
than guessing canonical IDs. Unsupported historical vehicles retain history without a model
estimate. Artifact provisioning is still required on another computer; Git alone is insufficient.

### Deferred work and infrastructure boundary

- G2C.2's 20-report NLP challenge annotation is deferred indefinitely. Preserve its artifacts,
  frozen membership, blank worksheets, private mappings, and hidden predictions. Do not resume
  annotation, tune rules, or inspect held-out NLP materials as part of demo work.
- Last user-reported AWS state: the application ALB and its managed public IPv4/ENI were retired
  on October 26, 2026; ECS was stopped at desired/running/pending 0/0/0. Model S3 artifacts and
  ECR images were retained. This is a historical checkpoint, **not a live status verification**;
  no AWS access was performed for H3.1 and no running deployment is assumed.
- Terraform state was recovered, but reconciliation remains deliberately deferred. Configuration
  still declares desired count 1; historical deployment templates and older guardrail notes may
  describe the former ALB. Do not deploy or run Terraform to resume the local demo. Do not touch
  shared Identity Center/KMS resources.
- H3.1 changes were subsequently committed and pushed, as reported by the owner. H4 documentation
  work does not authorize further commits or staging/publishing datasets, model bundles,
  annotation materials, or recovery/state files. Preserve unrelated working-tree changes.

### H4 — Portfolio Readiness

Review GitHub presentation and repository hygiene without discarding local work: inspect the
working tree, confirm ignored/private artifacts stay excluded, review obsolete deployment claims,
and prepare only intentional code/docs changes for later authorized commits. Capture screenshots
of history, model-supported/unsupported states, and the clearly separate NLP sample. Record a
short walkthrough emphasizing provenance and limitations. Broader browser, real keyboard and
screen-reader usability review, and reproducible artifact-provisioning instructions remain useful.
Vehicle-specific NLP or broader quality evaluation requires separate scope approval; it is not
needed for H4. Deployment remains out of scope unless explicitly requested.

Known limitations: selective complaint reporting without exposure denominators; a historical
2023 forecast only; limited exploratory NLP evidence; no live data updates; no packaged artifact
distribution; no comprehensive accessibility certification. No new analytics are implied by polish.

H2 adds a narrative-free historical SQLite index and an optional local demo API. H3 adds
a responsive, same-origin HTML/CSS/JavaScript dashboard at `/`. The original API factory
and frozen prediction contracts are unchanged. No AWS credentials, cloud access, Docker,
frontend build system, external fonts/CDNs, tracking, or training are required.

## Build explicitly

From the repository root in PowerShell, using the existing environment and restored corpus:

```powershell
.\.venv\Scripts\python.exe -m howreliable.demo.index --input data/processed/nhtsa/complaints/complaints-clean.jsonl --output data/processed/demo/history-v1-20261102-v2.sqlite --generation-utc 2026-11-02T18:00:00Z
```

The timestamp is injected and must be UTC. The builder never runs during API startup. Both
the database and `.sqlite.provenance.json` completion marker must be absent. Reruns require
a new output path; there is deliberately no overwrite flag. `data/processed/` is Git-ignored.

The H2 development run `history-v1.sqlite` is retained as an intermediate build; its report
hash encoding was superseded by the existing-policy-compatible v2 path above. Only the v2
path is selected by the demo factory. No earlier output was overwritten.

Validated clean records are streamed using `iter_clean_records()`. Each accepted row is
stored once in source order, including repeated rows. Vehicle identities are reconstructed
with the existing `VehicleAssociation` normalization and digest and checked against the
clean record ID; disagreement aborts the build. No fuzzy identities are inferred. This
corpus has no generation field; a nonmatching generation-sensitive ID also aborts rather
than being silently reassigned.

Reports follow the existing source-type + ODINO grouping policy, falling back to CMPLID
when ODINO is missing/blank. IDs are hashed with the same deterministic JSON encoding.
Identical narratives never merge distinct reports. No narratives, raw report IDs, VINs,
review annotations, or prediction payloads are copied into the index.

## Schema and completion provenance

Index schema `howreliable-history-index-1.0` contains:

| Table | Contents |
|---|---|
| `vehicles` | Canonical broad ID, normalized make/model, model year |
| `rows` | Source-line sequence, hashed report group, vehicle ID, report date, structured component, fallback flag |
| `reports` | Global source-row count and date/vehicle conflict accounting per report |
| `metadata` | Deterministically serialized provenance |

Indexes cover vehicle identity, vehicle/report date, vehicle/component, and report grouping.
Source-line sequence plus the source-file checksum provides row lineage without retaining
unnecessary original identifiers. Processing uses a bounded SQLite cache and file-backed
temporary SQL storage rather than retaining the corpus in memory.

Provenance records source SHA-256 and field schema, cleaning/mapping versions, cleaning
provenance checksum, builder/validator/identity-code hashes, SQLite version, injected UTC
timestamp, grouping/date policies, and global counts. The external completion marker adds
the database SHA-256. Reproducibility means the same source, code, timestamp, and SQLite
environment; database bytes are not promised identical across SQLite releases.

Construction occurs in a temporary sibling directory. Count checks, input re-hashing,
SQLite integrity and foreign-key checks run before publication. Same-filesystem hard links
publish complete files atomically without replacing an existing path; the completion marker
is published last. This requires a filesystem supporting hard links (such as local NTFS).
Catchable failures clean up only files owned by that build. A force-killed process can leave
a temporary directory or unmarked database: startup refuses an incomplete pair. Inspect and
approve cleanup or choose a new output path; do not treat an unmarked database as complete.

The service checks the database checksum and embedded/sidecar metadata once at startup and
uses read-only SQLite connections thereafter. Published index files must remain immutable
while serving. No source corpus scan occurs during requests.

## Local startup

```powershell
.\.venv\Scripts\python.exe -m uvicorn howreliable.demo.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` for the dashboard, or `/docs` for API documentation.
Stop the server with **Ctrl+C** in the terminal that launched it.
The demo factory explicitly uses local model artifacts,
even if the shell selects S3 for other tools. A completed historical index is required.
The canonical model is optional: absent/invalid bundles make prediction endpoints return
503 `MODEL_UNAVAILABLE` while purchase/history remain usable. Validation is not bypassed.
The original `howreliable.api.app:create_app` command remains fail-closed by default and
continues to expose only the original frozen API, without the demo homepage.

### Required artifacts and troubleshooting

- Existing `.venv` with the installed project and pinned dependencies (Python 3.12+).
- Optional for ML only: complete `howreliable-rf-2022-cutoff-v1` bundle and its manifest-referenced
  model, feature, target, handoff, evaluation, and explanation artifacts at their original paths.
- `data/processed/demo/history-v1-20261102-v2.sqlite` and its checksum completion marker.
- Optional G1 summary and provenance at
  `artifacts/nlp/owner-reports/g1-smoke-20261027-seed-8a01/summary.json` and
  `summary.json.provenance.json`. Missing G1 artifacts do not prevent history or predictions.

Run from the repository root: artifact paths are relative to it. If startup fails, inspect
the terminal for missing/checksum-invalid index artifacts; do not bypass validation
or regenerate frozen files. For a missing historical index, use the explicit build command
above only with absent destinations. An existing conflicting index is never overwritten.
If port 8000 is busy, use `--port 8001` and the corresponding browser URL. Do not use the old
API-only factory when expecting a homepage. If discovery fails, use **Retry catalog** after
restoring server availability. A model-unavailable message is independent of purchase/history
availability; restore and validate the original bundle, then restart to enable predictions.
`/health` reports process liveness, not model readiness. Refresh after updating local assets; no service worker caches
old assets. No API keys or `.env` file are needed for this local factory.

### Demo walkthrough

1. Open the homepage; choose a make, then model, then year. Only facets and at most one
   vehicle item per discovery call are transferred; the entire catalog is not downloaded.
2. Optionally enter kilometres and asking price in CAD, and choose maintenance-documentation
   status (unknown by default). Select **Assess this vehicle**. Review complaint-supported versus
   generic inspection advice, purchase considerations, and evidence limitations; no verdict is made.
   Historical timeline/component charts follow, preserving report/row counts and coverage.
3. Read the separate **Historical ML Experiment — 2023 Complaint Activity** panel. Supported cohorts show the frozen
   probability, classification/threshold, model contributors, evidence, limitations, and
   provenance. Unsupported/ambiguous matches show an unavailable explanation without estimates.
4. Expand **Explore global NLP sample** independently of vehicle selection. This displays only
   the existing G1 summary, explicitly labelled as 1,000 rows / 691 reports with older rules.
   It never filters by the selected vehicle or triggers extraction.
5. Changing a vehicle, mileage, price, or maintenance field clears the assessment and invalidates
   in-flight responses. Reassess to refresh. **Reset** also clears optional fields and resets
   maintenance to unknown. The global sample remains a separate view.

The dashboard uses native labelled controls, keyboard focus indicators, a skip link, live
status messages, reduced-motion support, and responsive layouts. Charts have visible textual
labels/counts; component source-row counts and monthly accounting are also available as text.
API strings are inserted with DOM `textContent`, not HTML. There are no raw narratives,
external services, browser telemetry, or automatic annotations.

## Demo contract: `howreliable-demo-1.0`

| Method and route | Purpose |
|---|---|
| `POST /api/demo/v1/purchase-assessments` | Deterministic purchase-context assessment; see the [typed contract](purchase-assessment.md) |
| `/api/demo/v1/vehicles` | Historical vehicle discovery; optional make, model, year, limit, offset |
| `/api/demo/v1/vehicles/resolve` | Exact normalized make/model/year resolution: matched, unmatched, ambiguous |
| `/api/demo/v1/vehicles/{vehicle_id}/history` | Counts, monthly report-date timeline, structured components, provenance |
| `/api/demo/v1/vehicles/{vehicle_id}/prediction` | Explicit supported/unsupported/ambiguous link to unchanged frozen result |
| `/api/demo/v1/nlp/sample-summary` | Existing global bounded G1 summary only; never vehicle-specific |

Examples:

```text
/api/demo/v1/vehicles
/api/demo/v1/vehicles?make=ford
/api/demo/v1/vehicles?make=ford&model=escape
/api/demo/v1/vehicles/resolve?make=ford&model=escape&year=2020
/api/demo/v1/vehicles/{id-from-discovery}/history
/api/demo/v1/vehicles/{id-from-discovery}/prediction
```

Discovery returns a paginated `items` list, total matches, and deterministic facet lists.
Initially use `makes`; after choosing a make use `models`; after choosing a model use
`years`. Model filtering without a make is rejected (422). Make/model input uses existing
canonical Unicode normalization, not fuzzy matching. An unmatched exact identity is explicit;
unsupported historical IDs return 404. Predictions require both matching identity fields
and the canonical ID. A field match with a different ID is ambiguous and returns no link.

## Counting, dates, and interpretation

Vehicle summaries count every source row, but count each report once. Component frequencies
count a report once per structured component even when it has repeated source rows. A report
can mention multiple components, so component report counts must not be summed as a report
total. Distinct vehicle summaries may share reports if the source associates an ODI with
different vehicles; global conflict counts expose this condition. Global unique reports are
not the sum of per-vehicle unique reports.

The timeline uses report dates, never occurrence dates. Within the selected vehicle, a report
enters one month only when all its rows agree on a valid nonmissing date. Missing/conflicting
dates use a `null` month bucket, including that report's source rows. Thus both timeline count
columns reconcile with their vehicle totals. Coverage exposes earliest/latest observed valid
row dates and missing-date row count; those extrema do not imply uninterrupted coverage.
Malformed or noncanonical report dates fail closed before publication under the validated
clean-data contract; they are never silently parsed, dropped, or replaced with occurrence dates.

Historical observations and the frozen forecast are separate. The prediction link explicitly
labels the December 2022 cutoff and January–December 2023 forecast window. Follow its URL to
retrieve the original result unchanged. An unsupported vehicle has history but no fabricated
prediction. Neither output measures current failure probability, defect rate, severity, or
mechanical reliability. NHTSA reporting is selective and lacks an exposure denominator.

The optional NLP endpoint verifies completion and the G1 summary checksum, returns its
provenance/rule identities, and labels it a global 1,000-row / 691-report sample predating
current extraction rules. It accepts no vehicle filter. Missing/unverified artifacts return
503. It does not open annotation partitions or predictions or run extraction.

## Remaining portfolio work

The local dashboard is implemented; publication, broader browser/screen-reader usability
review, and a recorded demo/screenshots remain separate portfolio tasks. Existing ignored
artifacts must be restored on another laptop; the repository alone is not a packaged demo.
The 2023 forecast is historical and the NLP quality evidence is exploratory, not generalization
evidence. Vehicle-specific NLP needs separately approved bounded processing and a versioned
vehicle-scoped aggregation design. Full-corpus NLP and annotation work remain deferred.
## Vehicle Problem Profile (P6C backend / P6D dashboard)

Choose a make, model and year, then use **Load / refresh vehicle profile** in the
**Vehicle Problem Profile** panel below the vehicle results and above price comparisons.
It works independently of **Assess this vehicle**, including when the model is unavailable.
The selected identity appears in both the result heading and status announcement. No trim,
powertrain or pricing configuration is inferred or sent to the profile endpoint.

The overview distinguishes unique reports from duplicate-preserving source rows and shows
the observed report-date period. Expand **View component counts and complaint-linked
inspection questions** for the backend's frequency-ordered categories and unchanged prompts.
Unknown/other labels remain visible without specific part-level questions. Generic inspection
questions have their own heading. Existing historical charts remain the timeline visualization;
the profile adds expandable date accounting, provenance, applicability and full limitations.

Vehicle selection changes and Reset clear the profile and invalidate pending requests.
Refresh clears previous evidence while loading. Malformed, mismatched and failed responses
show no partial evidence. Profile loading does not modify P4 readiness or P5 comparisons;
changing purchase-only inputs does not alter the identity-only profile.

The backend still supports `POST /api/demo/v1/vehicle-problem-profiles` directly. Use the
existing local launch command above, then in another PowerShell terminal:

```powershell
$body = @{ make = 'Toyota'; model = 'Corolla'; year = 2011 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/demo/v1/vehicle-problem-profiles' `
  -ContentType 'application/json' -Body $body
```

Schema `vehicle-problem-profile-1.0` embeds the historical summary once and adds component
evidence references, conservative inspection questions, provenance and source availability.
The immutable historical index is required; the frozen model bundle is optional.
Exact matches return 200; no-match returns 200 with null history, ambiguity returns a typed
409 profile, invalid requests return 422, and read/validation failure returns a typed 503
profile. Missing/corrupt mandatory indexes still prevent startup.

These US NHTSA reports are allegations, not verified failures or failure rates. Component
categories overlap. Exact cohort matching does not establish trim, VIN or Canadian-market
applicability. Recall/TSB evidence is unavailable locally, and validated NLP symptom evidence
remains unavailable; null is not zero. Questions are inspection prompts, not diagnoses.
This endpoint does not change purchase-readiness or asking-price comparison policy.
See [the profile contract and evidence policy](vehicle-problem-profile.md) for details.
