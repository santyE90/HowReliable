# Phase 8A Owner-report NLP Annotation Guide

Guide version: `howreliable-owner-report-annotation-1.0`.
Applies to `howreliable-owner-report-nlp-1.0` and
`howreliable-owner-report-taxonomy-1.0` in the [specification](owner-report-nlp.md).
Status: Milestone A defined this guide. G2A supplies empty annotation worksheets and a
[local preparation/review workflow](owner-report-nlp-review-workflow.md); human annotation
is separate human work. G2B.1 provides [preliminary development scoring](owner-report-nlp-development-evaluation.md)
only for explicitly completed, validated entries; saved drafts are excluded.

## Annotation task

Annotate explicit component referents, observable reported symptoms, assertion status and
clearly supported component-symptom relations. Describe what the narrative says. Do not
infer a diagnosis, severity, reliability, risk, incident truth or expected future outcome.
Use only the narrative and minimal source identifiers/dates needed for traceability.
Hide structured component/severity labels, canonical model predictions, future targets,
and machine-extracted labels from annotators to avoid anchoring.

Use the component and symptom tables in the specification as the authoritative v1 label
inventory. Mark an explicit unrepresented concept as unmapped, and a genuinely ambiguous
concept as ambiguous. A blank narrative or no recognized mention is a valid empty-label
case. Do not manufacture evidence spans for absence.

## Evidence spans

Annotate the shortest complete phrase identifying the referent or symptom. Exclude articles,
surrounding punctuation and assertion cues unless they are necessary to the concept.
For "the brake pedal was very hard", annotate `brake pedal` as `brakes` and `very hard`
as `braking_difficulty` in that explicit context. Record the supporting relation clause.

Record zero-based original-string Unicode code-point offsets `[start, end)`, exact evidence
text, label and assertion. Verify `narrative[start:end] == evidence_text`. Work against the
unaltered narrative, not the normalized matching view. Never hand-count UTF-8 bytes or
browser UTF-16 units as canonical offsets. Any annotation tool must demonstrate conversion
and round-trip tests before use.

Annotate repeated occurrences separately, including contradictory statements. Shared spans
across component and symptom kinds are allowed when both interpretations are explicit;
within one kind prefer the longest specific referent over overlapping generic aliases.
Record distinct symptoms separately when both are stated. Generic `operation_loss` is a
fallback rather than an extra label on every more-specific malfunction phrase.

## Assertions and context

| Status | Meaning | Example |
| --- | --- | --- |
| `affirmed` | Narrative asserts the concept/event occurred or existed | "The engine stalled" |
| `negated` | Narrative explicitly denies it in the relevant scope | "The engine did not stall" |
| `uncertain` | Possible, suspected or hypothetical statement | "The dealer suspects a fuel pump problem" |
| `unresolved` | Scope or meaning cannot be determined conservatively | Conflicting/fragmentary wording whose scope is unclear |

Apply assertions to each span, not the document as a whole. The component can be affirmed
as a referent while its symptom is negated: in "the engine did not stall", `engine` is an
affirmed component mention and `stall` is a negated symptom. In "no engine problem", the
engine referent is still explicit; denial concerns the problem, not the existence of an
engine. Do not turn named-component mention frequencies into malfunction frequencies.
For "possibly the fuel pump", the component attribution is uncertain.

Record negation/uncertainty cue spans separately. Restrict scope to the relevant clause;
punctuation, contrast and coordination require interpretation rather than a fixed number
of words alone. "Brakes failed, but no crash occurred" does not negate braking difficulty.
"Not only" is not a denial. "No longer stalls" denies current stalling and implies a
historical episode, but do not invent a historical evidence span absent explicit wording.

Repair history remains narrative evidence: "battery replaced" mentions a battery but does
not establish a battery symptom. An explicit historical symptom may be affirmed; affirmed
does not mean current or unresolved. Do not infer dates, successful repair, or causes.
"If this happens again" does not by itself assert a new observed episode. Flag unresolved
context when temporal or hypothetical scope is unclear.

## Ambiguity and association examples

| Narrative | Annotation policy |
| --- | --- |
| "Check engine light came on" | Affirmed `warning_indicator`; no engine-damage claim; a lamp name alone does not justify a specific affected-component relation |
| "Engine stalled twice" | `engine` + `stall_shutdown`, both affirmed, with explicit relation |
| "Brake pedal became hard" | `brakes` + `braking_difficulty`, explicit relation |
| "Battery was replaced; vehicle still stalled" | Battery mention and stalling symptom; no battery-stall association inferred |
| "Steering wheel shook" | `steering` + `vibration`, explicit relation |
| "Wheel problem" | Ambiguous component unless surrounding text resolves steering versus road wheel; no specific symptom inferred |
| "No vibration, but a grinding noise" | Negated `vibration`; affirmed `noise`; no component guessed |
| "It failed" | Unresolved referent; do not guess a component or specific symptom |

Emit a relation only when the clause explicitly connects a component and symptom, or an
unambiguous local grammatical construction does so. Do not connect all mentions in the same
sentence. For multiple plausible components or unresolved pronouns, leave the relation
absent and annotate the ambiguity. A relation expresses `reported_with`, never causation.
Endpoint assertions remain explicit; a relation is not automatically an affirmed fault.

## Sampling 200 unique reports

1. Validate the selected input snapshot and provenance. Freeze the sampling mode/date scope,
   algorithm version and deterministic seed in an annotation manifest before labels exist.
2. Build report groups using source namespace plus ODINO, with CMPLID fallback, and connect
   exact identical nonempty narratives transitively across reports. Preserve conflicting
   narrative variants and exclude no rows silently.
3. Select 200 distinct report groups with inspectable narratives; every evaluation connected
   component must belong entirely to one partition. A selected report is one annotation
   unit with all distinct narrative variants and their row mappings. Do not treat each
   component row as another unique report.
4. Assign 100 reports to development and 100 to held-out deterministically at group level.
   If group sizes prevent an exact allocation, resample whole groups and document attempts;
   never break grouping to reach the counts. Unselected duplicate relatives remain barred
   from the opposite partition and from rule-development examples.
5. Use an auditable stratified sample covering dates, text lengths, encoding flags, report
   multiplicity, and a random background stratum. Structured component may guide sampling
   coverage but stays hidden during annotation and is not gold truth. Freeze stratum quotas
   before label review; report inclusion probabilities and deviations.
6. Include hard negation/uncertainty and rare-category cases where available. Any deliberately
   selected challenge supplement must be reported separately; it cannot silently replace
   the held-out sample or support a population-wide performance claim.

Two annotators independently label both partitions where feasible, followed by adjudication.
At minimum independently review all 200 reports and record who annotated/reviewed each,
disagreements and adjudication decisions. If staffing cannot provide independent review,
record that limitation and obtain protocol approval before claiming completion. Assign the
reviewer/custodian before sampling; no reviewer availability is assumed by this document.

The custodian seals held-out IDs, text, gold labels and hashes from rule developers. Only
development annotations may guide aliases, negation rules or taxonomy revisions. Freeze
the extractor version/configuration before held-out scoring. A held-out run is not a tuning
loop: changes based on its errors require a new evaluation version and a fresh held-out
set before another generalization claim. Prior inadvertent exposure must be disclosed.

## Review and evaluation

Milestone E supplies persistent memberships and transitive evaluation-group keys as
documented in the [specification](owner-report-nlp.md). Future samplers must use the verified
completed index, keep whole evaluation groups together, and call
`validate_partition_assignments()` with the entire proposed event-to-partition mapping.
Checking development and held-out mappings independently cannot detect leakage between them.
Date-excluded rows cannot be assigned through this helper. Report identity remains separate
from duplicate-text evaluation isolation. No annotations or sample assignments are created
by the E implementation.

For each unit verify source lineage, exact span slicing, correct code, per-span assertion,
cue evidence and relation support. Document unknowns rather than forcing agreement.
Record inter-annotator span/label/assertion agreement before adjudication; adjudicated
annotations are the gold reference, not a majority vote from structured labels.

Primary metrics collapse repeated affirmed named labels within a report. Compute component
and symptom precision separately; provisional target is 90% for each. Also report recall,
F1, TP/FP/FN, category support, assertion errors, span accuracy, association quality and
abstention/coverage. Include the specification's uncertainty/support rules and explicitly
mark undefined metrics. A zero-prediction extractor cannot meet the precision target.

A stratified 100-report held-out sample is small. State whether results are sample-weighted
or descriptive; do not claim corpus-representative or category-level validation without
adequate support and an appropriate sampling analysis. Duplicate groups and multiple labels
introduce dependence. High precision on a few labels does not validate all categories or
mechanical interpretation. No minimum recall or per-category pass threshold is approved.

## Storage and change control

Keep annotations, group memberships and evidence excerpts in the new ignored NLP artifact
area. Store original-text hashes, schema/taxonomy/guide versions, partition, source row IDs,
annotator/reviewer references and review status. Restrict access to raw narratives; do not
publish incidental identifiers or raw excerpts in Git, routine logs or API responses.

Never edit source narratives to make offsets convenient. Corrections affect annotation
versions only. Changes in taxonomy meanings, span policy, grouping, or assertion scope
require a versioned decision and affected-label review. Do not modify the existing Component
enum, canonical model, historical fixture, frozen checksum, or API schema.
