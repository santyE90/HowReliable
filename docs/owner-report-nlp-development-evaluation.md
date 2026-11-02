# Preliminary development evaluation (G2B.1)

Evaluation version: `howreliable-development-evaluation-1.0`.
This is a read-only evaluation of human development annotations and separately frozen
predictions. It writes new result artifacts only. It does not annotate, complete drafts,
modify predictions, tune rules, score holdout, run corpus NLP or integrate the canonical model.

## Run

```powershell
$source = 'artifacts/nlp/owner-reports/g2a-annotation-20261027-v2/development/worksheet.jsonl'
$working = 'artifacts/nlp/owner-reports/annotation-work/development-review.json'
$predictions = 'artifacts/nlp/owner-reports/g2a-annotation-20261027-v2/private/predictions.jsonl'
$output = 'artifacts/nlp/owner-reports/g2b1-development-evaluation-20261027-v1'
python -m howreliable.nlp.development_evaluation --source $source --working $working --predictions $predictions --output-dir $output --generation-utc 2026-10-27T18:00:00Z
```

Use a new output directory for every later run. `--prediction-provenance` optionally
specifies the frozen prediction completion provenance; the default is the preparation
run's `provenance.json`. Both development source and prediction bytes must match that
provenance. Outputs inside the repository must remain in the ignored NLP artifact area,
outside the frozen preparation run and protected input directories.

The original G2A file mixes development and held-out prediction packets. The reader checks
the canonical outer `annotation_id`/`partition` header **before decoding predictions**.
Held-out payloads remain opaque bytes and are skipped, never decoded, exposed or scored.
The mixed file is hashed as an integrity check. No held-out worksheet, private source
mapping or partition manifest is opened. All development packets must match the supplied
development source IDs. Explicit held-out input paths are rejected before reading them.

## Eligibility and validation

An eligible unit must be `annotated` or `reviewed`, with every original variant marked
complete, a nonempty annotator ID and explicit empty-label confirmation for reviewed
no-mention variants. `reviewed` additionally requires a nonempty independent reviewer ID.
Pending, in-progress and needs-adjudication reports are excluded. Incomplete completion
claims are also excluded and listed as validation problems, not silently completed.

The shared validator checks immutable source identities/text/metadata, offsets, cue spans,
codes, explicit assertions, unique IDs, association references and status consistency.
For an incomplete completion claim, an evaluation-only copy with draft status and cleared
completion flags permits evidence validation without scoring it. No submitted gold object
or file is modified; malformed identities, marker IDs, labels, spans or references fail
the run instead of being repaired. Otherwise semantically invalid drafts also fail the run.

Saving annotations alone does not make a report eligible. In the
[local editor](owner-report-nlp-local-editor.md), finish and confirm every variant, fill
the annotator ID, choose **annotated after the last edits**, and Save. Edits intentionally
return completed entries to in-progress. A run with zero eligible reports is valid and
produces undefined metrics, not invented scores. Annotation files and backups are never
written by this command.

## Identity, duplicate rows and missing coverage

Frozen packet annotation IDs identify reports. Original narrative fingerprints and
processing status identify variants within each report. The mapping must be unique;
ambiguous blank-text variants fail instead of guessing. Each variant requires predictions
for exactly its original source-row count, with unique source event IDs and consistent
report identity. Duplicate component rows must yield identical normalized mentions/links.
Conflicting duplicate predictions fail. Equivalent source-row predictions collapse into
one variant's evidence; repeated spans within that variant collapse by semantic identity.

If a report or any of its variants lacks complete prediction coverage, the entire report
is excluded from paired metrics and recorded separately as `missing_prediction`. This is
not an ordinary false negative. A complete prediction row with empty extraction arrays
is a valid empty prediction and **does** incur false negatives for gold labels. A completed
human empty-label report is a valid negative example and incurs false positives for extra
predicted labels. Distinct ODI reports are never merged because their text matches.

## Metrics

- Primary component and symptom precision/recall/F1 use affirmed named taxonomy labels
  at report level. A report contributes each code once, across all its variants and rows.
  Ambiguous/unmapped labels and other assertions are excluded from this primary measure.
  Per-category results report gold/predicted unique-report support and TP/FP/FN.
- Exact-span and overlap-span metrics include all taxonomy codes/assertions. Matching
  requires equal kind, code and assertion; exact additionally requires equal offsets,
  whereas overlap requires a nonempty original-character intersection. Matching is
  one-to-one, maximum cardinality first, then maximum exact rational total IoU, then
  deterministic lexical pair preference. Sorted semantic spans supply the lexical order.
  Greedy matching and floating-point tie decisions are not used.
- Assertion classification aligns equal kind/code/exact spans while ignoring assertion,
  then reports four-way confusion and accuracy on aligned pairs. Unmatched gold and
  predicted spans are reported separately, so alignment-conditioned accuracy must not be
  interpreted as end-to-end extraction accuracy.
- Explicit association metrics require both matched endpoints and their assertions to
  agree with a gold `reported_with` link in the same variant. Exact and overlap endpoint
  matching are reported separately. Supporting evidence is validated, but clause-boundary
  equality is not an additional relation-scoring criterion. Co-occurrence creates no link.

Precision is null when there are no predicted positives; recall is null when there are
no gold positives. F1 is null when `2*TP+FP+FN` is zero, otherwise the count-based F1 is
reported. Null is never converted to 100%. Precision tables include descriptive 95% Wilson
intervals and an insufficient-support flag below 20 predictions. These intervals do not
correct report/label dependence or stratified/convenience sampling bias.

All results are **preliminary, tiny, non-representative development diagnostics**. Five
reports cannot establish the 90% held-out precision target. Human annotations may still
need independent review/adjudication. No target-attainment claim is produced, even when
synthetic tests or small subsets happen to have perfect scores.

## Artifacts and reproducibility

- `aggregate.json`: eligible/evaluated counts, exclusions, validation problems, missing
  prediction coverage, valid empty cases, metric tables, support, assertion confusion and
  disagreement-type totals. No narrative, evidence text or source identifiers.
- `development-disagreements.jsonl`: development annotation/variant IDs, error type,
  category/assertion and offsets where applicable. No narrative or evidence text. These
  references can guide later human inspection; no gold or rule edits happen automatically.
  Report-label, span, assertion and association diagnostics overlap and are not additive
  counts of distinct mistakes. Missing prediction coverage has its own error type.
- `provenance.json`: completion marker, exact source/working/prediction/provenance input
  hashes, working revision, frozen schema/rule identities, evaluator code identity, injected
  UTC timestamp, output sizes/hashes and matching policy.

The parser binds the working-file hash to the exact bytes evaluated. Input hashes are
rechecked before publication, so concurrent editor saves stop publication rather than
misattribute results to a newer revision. Output bytes are deterministic for fixed inputs,
code, runtime and timestamp. Existing outputs are refused; artifacts stage privately,
completion provenance is written last, and the completed directory is renamed into place.
Caught failures clean staging. Hard-kill orphans require inspection and are not complete
runs without valid completion provenance. CLI errors are fixed codes, never raw validation
payloads containing narratives. No browser/editor predictions panel is added.

The first local G2B.1 invocation found five saved `in_progress` reports and 95 `pending`,
so it correctly evaluated **zero reports**, with all precision/recall/F1 and assertion
accuracy undefined. The working copy passed semantic validation. Complete/save those
reports explicitly before rerunning into a new output directory; do not promote their
states programmatically just to obtain scores.
