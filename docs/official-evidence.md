# P7: optional official NHTSA evidence

P7 completes planned feature development. Verified recall and manufacturer-communication
evidence is available independently of the complaint index, frozen model, P4 readiness and
P5 pricing. NLP and EWR are not published. See [the profile contract](vehicle-problem-profile.md)
and [local demo](local-demo.md).

## Sources, scope and permission

The [official distribution page](https://www.nhtsa.gov/nhtsa-datasets-and-apis) listed all
six files on 2026-11-04. Their URLs responded without credentials or payment. HEAD did not
provide Content-Length; the following are actual downloaded byte counts. These are newly
acquired snapshots, not restored September artifacts.

| Official file | Bytes | Scope |
| --- | ---: | --- |
| [FLAT_RCL_PRE_2010.zip](https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_PRE_2010.zip) | 7,440,320 | Recall PRE partition |
| [FLAT_RCL_POST_2010.zip](https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip) | 14,979,352 | Recall POST partition |
| [RCL.txt](https://static.nhtsa.gov/odi/ffdd/rcl/RCL.txt) | 3,053 | Recall dictionary |
| [TSBS_RECEIVED_2020-2024.zip](https://static.nhtsa.gov/odi/ffdd/tsbs/TSBS_RECEIVED_2020-2024.zip) | 31,775,534 | Canonical rich communication TSV |
| [MFR_COMMS_RECEIVED_2020-2024.zip](https://static.nhtsa.gov/odi/ffdd/tsbs/MFR_COMMS_RECEIVED_2020-2024.zip) | 11,663,382 | Compact CSV overlap audit only |
| [TSBS.txt](https://static.nhtsa.gov/odi/ffdd/tsbs/TSBS.txt) | 6,018 | Communication dictionary |

[NHTSA terms](https://www.nhtsa.gov/about-nhtsa/terms-use) permit copying/distribution of
public information, disclaim accuracy/completeness and do not guarantee third-party rights.
Keep source attribution and provenance; no commercial-site scraping or manufacturer PDF
collection is involved. Downloaded/generated files remain Git-ignored.

The current communication dictionary includes September 2026 field-length updates. Its
14-field order remains compatible with the existing parser, which does not truncate these
fields. Ingestion retains the adapter's older layout label; the actual dictionary checksum
identifies the checked dictionary independently. Compact CSV and rich TSV are never unioned.
Communication coverage is a received-date selection, not all documents for a model year.

## Verified local artifacts

| Source | Source rows | Canonical identities | Applicability rows | Eligible known-year vehicle applications |
| --- | ---: | ---: | ---: | ---: |
| Recalls | 328,817 | 30,435 campaigns | 287,680 vehicle rows | 287,099 |
| Communications | 2,404,711 rich rows | 73,930 documents | 1,688,707 relationships | 1,665,754 |

Unknown-year exclusions are counted: 581 recall applications and 22,953 communication
applications. Nonvehicle recalls do not match vehicle cohorts. Campaign/document identity
is separate from applicability; manufacturer bulletin/campaign numbers are not assumed unique.

```text
data/raw/nhtsa/recalls/p7-20261104-v1/
data/raw/nhtsa/manufacturer_communications/p7-20261104-v1/
data/processed/recalls/p7-20261104-v1/
data/processed/manufacturer_communications/p7-20261104-v1/
data/processed/official/p7-20261104-v1/evidence.sqlite
data/processed/official/p7-20261104-v1/manifest.json
artifacts/official/p7-20261104-v1/   # local execution receipts, not application inputs
```

Raw acquisition manifests record actual URLs, retrieval UTC and SHA-256. Processed directories
contain canonical records, applicability and completed `ingestion.provenance.json` with
counts and output hashes. The standalone serving database is 1,943,490,560 bytes, SHA-256:

```text
221b27fd825c5e1c47c5c4746c1744feb3402ec55e7bbd64f84ad0cf9fac35a1
```

Serving schema: `howreliable-official-evidence-1.0`.
Matching policy: `official-exact-nfkc-whitespace-casefold-1.0`.
Manifest and embedded metadata bind database, source-record/applicability, acquisition,
ingestion-provenance and dictionary hashes, builder/adapter identities, scope and retrieval
timestamps. Injected `generation_utc=2026-11-04T18:00:00Z` is a reproducibility timestamp,
not the actual acquisition time; source snapshot dates come from the acquisition receipts.

The owner approved 5 GiB disk, 2 GiB worker RAM and 30 minutes processing. Windows Job Objects
enforced worker memory limits. Recall ingestion took 56.662 seconds, communication ingestion
170.494 seconds and serving construction 331.975 seconds. Maximum observed worker memory
was 1,576,083,456 bytes; final task disk use was approximately 2.87 GiB. These measurements
do not guarantee resource use for different future source files.

## Explicit offline construction

With the verified raw and canonical snapshots present:

```powershell
.\.venv\Scripts\python.exe -m howreliable.demo.official_evidence --recalls data/processed/recalls/p7-20261104-v1 --communications data/processed/manufacturer_communications/p7-20261104-v1 --output-dir data/processed/official/p7-20261104-v1 --generation-utc 2026-11-04T18:00:00Z
```

The existing output is intentionally refused; a deliberate rebuild needs a new reviewed path.
The builder verifies raw receipts, hashes, ingestion completion, schemas, count conservation,
record/application keys and foreign keys. It uses disk-backed SQLite, validates integrity,
writes completion metadata last in staging and atomically publishes a new directory.
Interruption does not publish completion. No EWR/cross-source diagnostics are prerequisites.

Startup validates the optional database checksum and embedded metadata. Missing/corrupt
official artifacts preserve complaint-only, model-free operation. HTTP requests use indexed
exact identity lookup, count distinct identities and return at most ten records per source
in stable ID order. No JSONL scans, acquisition or rebuilding occur in HTTP/startup paths.
Source files are never modified. The full canonical/applicability files remain local for
traceability; matching retains NFKC/whitespace/case normalization without guessed aliases.

## API and browser

POST `/api/demo/v1/vehicle-problem-profiles` keeps the 1.0 request. Responses remain
`vehicle-problem-profile-1.0` if no verified source can be joined; resolved profiles with
official evidence return `vehicle-problem-profile-1.1`. Complaint fields, applicability
limitations and inspection-question policy are unchanged. Ambiguous cohorts are not guessed.

Official source sections include snapshot scope/date, checksum provenance, unique/returned
record counts, a truncation flag and typed records. Records preserve NHTSA identity,
manufacturer references, source descriptions/consequences/remedies or communication
type/summary, distinct date meanings, components, source filenames and quality flags.

Zero means **no exact records in this verified snapshot**, never no recalls/problems.
Unavailable evidence stays null. The browser separates recalls and communications in native
expandable sections, uses safe text nodes, validates both versions and preserves loading,
Reset, cancellation and stale-response protection. Previews are explicitly incomplete when
the total exceeds ten; no new frequency, severity or reliability percentage is calculated.

| Cohort | Complaint reports / rows | Recall campaigns | Communication documents | Preview |
| --- | --- | ---: | ---: | --- |
| 2011 BMW 335i | 22 / 35 | 7 | 8 | All matching records |
| 2011 Toyota Corolla | 23 / 32 | 9 | 101 | First 10 communications, explicitly limited |

These are U.S. NHTSA regulatory/documentary records, not failure-frequency measurements or
purchase verdicts. Broad matching does not verify VIN, trim, engine, Canadian-market or
Transport Canada applicability, individual condition, current open recalls or repair
completion. Campaign/document-wide components/text must not imply a specific configuration
has a diagnosed defect. No official evidence changes P4, P5 or the historical frozen model.

## Validation and final cleanup

Synthetic tests cover source checksums/completeness, exact matching, deduplication, bounded
previews, deterministic publication, interruption, corruption fallback and unchanged P4/P5
API responses. Desktop/mobile Edge checks cover real/synthetic official records, hostile
text, malformed responses, applicability wording and wrapping. Existing P6 native keyboard
and stale-response checks remain applicable; spoken screen-reader certification is not claimed.
The historical index checksum remains
`e9e1fb211a6c7b7ac929c7e9deca6a48bc32ce7a818a7372ab028f32f2517948`.

The P7 checkpoint reported 944 passed, 5 failed, 7 setup errors and 1 skipped. Final v1.0
cleanup resolves the missing fixtures through verified deterministic recovery and changes
only the cross-batch Brier assertion to a justified absolute tolerance. The current full suite
passes 956 tests with one optional research-artifact skip; no source data, evidence policy
or frozen model was changed. See [the release record and backup procedure](release-v1.md).
Preserve ignored verified artifacts and review the Git diff before any requested commit.
No further feature-development milestones are proposed.
