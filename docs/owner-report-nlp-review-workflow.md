# Phase 8A G2A annotation preparation and review

Preparation version: `howreliable-owner-report-annotation-preparation-1.0`.
Applies to [taxonomy/specification v1](owner-report-nlp.md) and the
[annotation guide v1](owner-report-nlp-annotation-guide.md). G2A prepares materials only:
no annotation, automatic gold labels, precision/recall/F1 scoring or extraction-rule tuning.

## Reproducible selection

```console
python -m howreliable.nlp.annotations --corpus data/processed/nhtsa/complaints/complaints-clean.jsonl --predictions data/processed/nlp/owner-reports/g1-smoke-20261027-seed-8a01/extraction.jsonl --output-dir artifacts/nlp/owner-reports/g2a-annotation-20261027-v2 --seed howreliable-phase8a-g2a-20261027-v1 --generation-utc 2026-10-27T12:00:00Z
```

Output directories must be new. Within the repository they must be under the ignored NLP
artifact directories. A completed candidate extraction/provenance and checksum-verified
membership index are required. The candidate extraction must be in full-corpus descriptive
mode, but may contain only a bounded subset: the default real-data candidate pool is G1's
691 complete reports from 1,000 original clean rows. This avoids full-corpus NLP.

The sampler streams the validated original clean corpus to build a disk-backed, private
membership-only index with existing report grouping and transitive exact-text logic. No
lexicon, assertion or association extractor is invoked on that corpus. Candidate narratives,
dates, source-row membership and original-corpus hash are checked against the source.
Selection preserves all component rows and distinct narrative variants of each report.

V1 requires non-fallback ODI identities and at least one inspectable narrative. It excludes
incomplete candidate groups and globally multi-report evaluation components; this conservative
policy avoids splitting duplicate chains or solving exact-size allocations using partial
components. Singleton evaluation groups still contain every original row of their report.
Candidate exclusions and counts are explicit. This policy may omit duplicated-report cases;
future designs can select whole multi-report evaluation components under separate review.
No distinct ODI reports are silently merged into one annotation unit.

Fixed seed: `howreliable-phase8a-g2a-20261027-v1`. Ranking uses SHA-256 of canonical JSON
`[seed, partition, stratum, report_group_id]`, with report ID as deterministic tie-break.
This hash ranking is the reproducible pseudorandom selection mechanism; it does not depend
on Python's process-randomized hash or filesystem order. The seed, quotas and policy are
fixed before human labels are produced. Partitions alternate per stratum in this order:

| Primary sampling bucket | Target per partition |
| --- | ---: |
| Rare predicted category: <=15 eligible candidate reports | 15 |
| Any negated predicted mention | 10 |
| Any uncertain predicted mention | 5 |
| At least two distinct predicted components | 10 |
| No recognized mentions | 10 |
| Unresolved assertion or ambiguous predicted component/symptom | 10 |
| Encoding control, short-narrative or oversized-narrative flag | 10 |
| Common predicted category: >=50 eligible candidate reports | 10 |
| Background, any remaining eligible report | 20 |

Buckets overlap, but each report is selected only once. Earlier buckets consume candidates
first. Unmet quotas are recorded and remaining slots filled by seeded background ranking,
never by duplicating reports. Separate overlapping coverage totals show all applicable tags.
Rare/common thresholds describe observed candidate predictions, not actual category truth.
No confidence score or easy-case filter is used. Missing/ambiguous context is proxied by
unresolved/ambiguous extraction and narrative-quality flags, not inferred human labels.
Reports with entirely absent/blank narratives cannot support the primary inspectable-report
sample; any such exclusions remain explicit. Missing narrative variants in an otherwise
inspectable report are preserved as reviewable empty cases.

This is a two-stage, prediction-assisted convenience/stratified sample from G1, not a uniform
200-report draw from the full corpus. Exact final inclusion probabilities are not derived;
population-weighted quality claims are unsupported. Dates, narrative length, source-row
multiplicity and quality remain inspectable through the private mapping; no extra quotas
for those dimensions are promised. Categories absent from G1 cannot be covered by prediction
strata. Broader sampling or corpus NLP requires separate authorization. G1 aggregate
diagnostics and machine predictions were previously observed; the custodian must confirm
that no narrative-based rule tuning contaminated prospective held-out reports.

## Artifacts and privacy

- `development/worksheet.jsonl` and `held_out/worksheet.jsonl`: exactly 100 unique reports
  each, with stable seeded pseudonymous annotation IDs, original narrative variants, exact
  text hashes, row multiplicity and report/occurrence date sets. Gold component, symptom and
  association arrays are empty; annotator/reviewer/adjudicator IDs and notes are null;
  status is `pending`. No structured component, severity, make/model, direct source IDs,
  sampling bucket or machine prediction is included in the worksheet.
- `worksheet-schema.json`: formal schema for the worksheet and annotation fields. Existing
  NLP code enums and span/reference field contracts are reused, without changing extraction
  schemas. Mention evidence uses original Unicode code-point `[start,end)` offsets. Arrays
  of component/symptom annotations carry code, assertion, rule/evidence and cue-span fields;
  use a human-guide identifier for manual rule provenance, never a machine prediction ID.
- `private/mapping.jsonl`: annotation ID to report identity and all complete original source
  records, including raw quality flags. This is private lineage, not an annotator handout.
- `private/predictions.jsonl`: existing machine predictions and sampling tags, separately
  retained for audit; never show these to annotators before gold freeze.
- `private/global-membership.sqlite`: original-corpus source identifiers and transitive
  evaluation groups, with no raw narratives. All selected event assignments are checked
  together by `validate_partition_assignments()`.
- `partition-manifest.json`: immutable membership, evaluation keys, seed, quotas, actual
  allocations, exclusions, overlapping coverage and prior-exposure limitations.
- `provenance.json`: completion marker, input/output SHA-256 and sizes, source prediction
  rule/configuration provenance, code hash/revision and dirty status, injected UTC timestamp.

All materials stay local and Git-ignored. Annotation IDs are pseudonymous, not a guarantee
that narrative text is anonymous: incidental identifiers remain in original narratives.
Never paste narratives into routine logs, Git, external tools or summary reports. CLI failures
report only exception class because validation exception payloads can contain text.

Generation stages into a private temporary sibling directory, checks unchanged source hashes,
writes completion provenance last, then renames the complete directory into place. Existing
destinations are refused. Failures remove staging; hard-kill orphan staging folders require
inspection and must not be treated as completed runs. Freeze the original template and its
checksums; work on new local copies without overwriting it. Timing and SQLite storage bytes
can depend on runtime, but selected membership and worksheet ordering are deterministic.

## Practical review and held-out custody

1. Assign named annotators, independent reviewer/adjudicator and held-out custodian. These
   people are not assigned automatically. Independent review is a human prerequisite for
   completion, not something G2A claims to have achieved.
2. Custodian verifies completion checksums and the 100/100 manifest, records custody and
   confirms prior exposure. Keep the held-out worksheet, private mappings, predictions and
   full manifest outside rule developers' routine access. Directory separation and hashes
   freeze membership but are not encryption or filesystem access controls; configure local
   access with the custodian. Do not call the held-out material operationally sealed until
   this has happened.
3. Share only development worksheets, schema and guides for rule development. Give two
   independent annotators separate new worksheet copies where feasible. For held-out work,
   the custodian supplies blinded worksheets directly to the assigned reviewers. Never
   display sampling tags, source structured component/severity or machine labels.
4. Human reviewers annotate original text, preserving variant IDs and exact text hashes.
   Keep repeated spans and contradictory statements. Fill explicit four-way assertions,
   cue spans and supported relations according to the guide. Empty gold arrays remain valid
   for a reviewed no-mention case; status distinguishes that from an untouched `pending` row.
5. Record annotator identities and status `annotated`. An independent reviewer checks text
   slicing, codes, scope and references, recording `reviewed` or `disputed`. Preserve each
   independent version and all disagreements; do not overwrite dissenting annotations.
6. A named adjudicator resolves disputes using only source evidence and the frozen guide,
   records rationale, and sets `adjudicated`. Genuine ambiguous cases retain ambiguous or
   unresolved labels. If the guide needs revision, version it and explicitly reannotate
   affected units rather than resolving ambiguity by inspecting machine predictions.
7. Freeze reviewed/adjudicated gold and hashes before any later scoring. Develop changes
   using development annotations only. Run no held-out scoring or rule tuning in G2A.
   Future candidate selection must preserve barred held-out evaluation-group memberships,
   including any unselected exact-text relatives; never check splits independently.

G2A.1 adds a [development-only local editor and semantic validator](owner-report-nlp-local-editor.md).
It stores separate working copies; it does not change frozen worksheets or enable holdout review.
Use the exported schema plus the Pydantic `AnnotationUnit` model for structural validation.
Before gold freeze, reviewers must additionally verify exact original-text slicing and
association endpoints. G2A preparation itself does not supply an editor or scorer; the
separately implemented G2A.1 tool supports local development review only. Browser UTF-16 offsets
must be converted and round-trip
checked before use; plain Python string offsets follow the approved Unicode convention.

## Frozen evaluation conventions

G2B.1 implements [preliminary development evaluation](owner-report-nlp-development-evaluation.md)
for explicitly completed human development working-copy entries. It never evaluates holdout.
The following conventions remain the protocol; G2A preparation itself performs no scoring.

Report-level component and symptom primary labels are `(report, kind, code, affirmed)`,
deduplicated within report. Report component and symptom results separately. Exclude
ambiguous/unmapped labels from named-label primary metrics and report them diagnostically.
Exact spans require identical offsets, kind, code and assertion. Overlap spans require a
nonempty original-character intersection with matching kind, code and assertion. Match
one-to-one by maximum cardinality, then greatest total intersection-over-union, then lexical
gold/prediction `(variant_id,start,end,kind,code,assertion,mention_id)` ordering. Never award
several predictions credit for one gold span. No overlap threshold beyond nonempty overlap
is claimed as an existing approved accuracy threshold; it is the documented v1 reporting
convention, with exact-span metrics retained alongside it.

For assertion diagnostics, align by kind/code/exact span without assertion and report a
four-by-four confusion table; unmatched labels are separate omissions/extras. Report
association metrics only for `reported_with` links whose mapped component and symptom
endpoints and endpoint assertions agree; a co-occurrence is not a relation. Keep span-exact
and overlap-based association variants distinct. No metric is computed in G2A.

Later reports must include per-category unique-report support, TP/FP/FN, micro/per-category
metrics, abstention, undefined zero denominators and 95% Wilson precision intervals with
report dependence limitations. The provisional 90% affirmed-label precision target and
<20-positive-predictions insufficient-support flag remain unchanged. Do not claim statistical
validation for this small, stratified sample. Changes based on held-out errors require a
new evaluation version and fresh held-out set; never tune and rescore the same holdout.
