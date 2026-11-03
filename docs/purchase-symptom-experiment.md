# P4B: bounded vehicle-specific symptom evidence experiment

Status: experimental, offline review only. P4A recommended keeping narrative extraction
separate from purchase recommendations until evidence quality is reviewed. This experiment
does not change the dashboard, API, index, frozen model, NLP rules, or human annotations.

## Reproduce explicitly

From the repository root with the existing environment, use a new, absent destination:

```powershell
.\.venv\Scripts\python.exe -m howreliable.nlp.vehicle_review --input data/processed/nhtsa/complaints/complaints-clean.jsonl --output-dir artifacts/nlp/p4b-vehicle-review-20261103-v1 --generation-utc 2026-11-03T18:00:00Z
```

The historical index defaults to `data/processed/demo/history-v1-20261102-v2.sqlite`.
It and its provenance must match the clean source and cleaning provenance. Both approved
identities must resolve exactly. Cross-vehicle report identities abort rather than silently
merge. A 10,000-row safety cap bounds the experiment; it is not a sampling policy.

The source is streamed once to validate/select rows using index source-line positions.
Only the selected rows enter the existing NLP pipeline. This is not full-corpus NLP.
Source and index hashes are checked again before completion. Source narratives and field
ordering are preserved in the subset; subset provenance identifies the parent checksum,
selection, and derived row count rather than presenting it as a fresh cleaning run.

## Local artifacts and review

All outputs live under Git-ignored `artifacts/nlp/`. The run contains:

- `lineage.json`: original source-line positions and source event identities.
- Per-cohort `selected-clean.jsonl` and derived provenance.
- Existing extraction JSONL, extraction provenance, and SQLite membership index.
- Existing descriptive summary and summary provenance.
- Per-cohort `review.json`: report identity, source rows, structured categories, every
  distinct narrative variant, component/symptom spans, assertions, cue spans and associations.
- `completion.json`: schema, scope, injected UTC timestamp, code/source/index checksums,
  and hashes for every completed artifact.

The complete directory is staged privately and renamed into an absent destination only
after validation. Overwrites are refused. A catchable interruption removes staging files;
an abrupt process termination can leave an unpublished temporary directory. A run without
a verified completion marker must not be consumed. Publication targets local Windows/NTFS.

Review artifacts contain original text and private lineage: keep them local, do not commit
or serve them. Open `review.json` locally, inspect each span against its narrative, and
record review decisions separately. All review statuses are initially pending. The existing
human annotation worksheets, held-out data and challenge artifacts are not opened or changed.

`artifacts/nlp/p4b-human-review-20261103-v1.json` contains a small tentative spot-review
checklist with short local evidence spans, a source completion checksum, and SHA-256 sidecar.
It is not gold annotation or a comprehensive correctness audit.

## Observed scope and coverage

| Cohort | Source rows | Unique reports | Reports with components | Reports with symptoms | No symptoms extracted |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2011 BMW 335i | 35 | 22 | 18 | 8 | 14 |
| 2011 Toyota Corolla | 32 | 23 | 14 | 6 | 17 |

All 45 reports had processable narratives. There were 45 distinct within-report narrative
variants and no within-report narrative conflicts. Repeated rows remain in extraction;
review variants consolidate identical text only within the same report. Distinct reports
are never merged merely because their text matches. Structured `other` remains visible;
neither cohort contained structured `unknown` in this selection.

Affirmed unique-report symptom counts (categories overlap):

| Symptom | BMW | Corolla |
| --- | ---: | ---: |
| Hesitation / power loss | 2 | 1 |
| Smoke | 2 | 0 |
| Warning indicator | 2 | 3 |
| Noise | 1 | 0 |
| Operation loss | 0 | 1 |
| No start | 0 | 1 |

BMW additionally has unresolved warning-indicator, power-loss, leak, smoke and shutdown
mentions (one supporting report per category). Corolla has one report with a negated
warning indicator. There are no uncertain symptom mentions, although uncertain component
mentions exist. No explicit component-symptom associations were emitted by the current
narrow association rules. This is not evidence that no such relationships were described.

Across distinct review variants, BMW has 8 affirmed and 5 unresolved symptom mentions;
Corolla has 8 affirmed and 1 negated symptom mention. These are mention counts, not report
counts. Existing summaries also provide source-row counts, which can repeat the same text.
For report-category totals across assertions, use `category_totals_all_assertions`, not a
sum of assertion-specific counts: a report can contain contradictory statements.

## Validation and interpretation

Checks validate selected row identity/component/date against the immutable index, full
source row accounting, per-cohort report conservation, original Unicode evidence/cue spans,
association endpoints, and artifact checksums. A second run with the same timestamp produced
18 byte-identical files, including memberships and completion provenance.

Spot review found useful explicit smoke/no-start extraction and correctly separated denied
warning indications. It also found suspected omissions involving transmission operation,
sensor failure, unintended acceleration and steering difficulty. A power-loss phrase in
steering/brake context merits taxonomy review rather than assuming propulsion loss. These
are tentative observations; rules and gold labels remain unchanged.

The five earlier development reports used to design G2C.1 do not establish generalization.
This bounded run has no independent reference set and supplies no precision/recall estimate.
Component presence does not establish malfunction; reports do not verify mechanical failures,
causes, current individual-vehicle condition, or risk. Sparse extraction is not reassuring.

Recommendation: suitable for local human evidence review, not yet for published recurring
problem claims or purchase recommendation logic. Review these bounded reports independently
before approving any consumer-facing symptom descriptions. Do not expand processing or tune
rules as an implicit consequence of this experiment.
