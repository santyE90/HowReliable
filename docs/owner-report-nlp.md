# Phase 8A Owner-report NLP Specification

Specification version: `howreliable-owner-report-nlp-1.0`.
Taxonomy version: `howreliable-owner-report-taxonomy-1.0`.
Status: Milestones A through F implemented with synthetic tests: streaming accounting,
component/symptom lexicons, bounded assertion rules, conservative local associations,
persistent duplicate memberships, temporal controls and descriptive summaries.
G1 completed bounded real-data smoke testing; G2A prepares blinded annotation materials
using the [review workflow](owner-report-nlp-review-workflow.md). Human annotation completion,
held-out evaluation and full-corpus performance remain outstanding
or unmeasured. Output schema is `howreliable-owner-report-extraction-1.3`; taxonomy v1 is
unchanged. Readers retain support for historical NLP schemas 1.0, 1.1 and 1.2.
G2A.1 provides a [localhost development editor and semantic validator](owner-report-nlp-local-editor.md)
without populating human annotations or changing frozen schemas.
G2B.1 adds [preliminary development evaluation](owner-report-nlp-development-evaluation.md)
of completed working-copy reports only; held-out evaluation remains deferred.
G2C.1 adds [targeted conservative rule improvements](owner-report-nlp-targeted-improvements.md)
and a separate development-only prediction path; five-report comparisons remain exploratory.

See the [annotation guide](owner-report-nlp-annotation-guide.md),
[roadmap](roadmap.md), [cleaning rules](cleaning-rules.md), and
[feature definitions](feature-engineering.md).

## Approved scope

Phase 8A is standalone, offline, deterministic extraction of explicit vehicle-component
mentions, reported symptoms, and their assertion status from NHTSA owner-report narratives.
It preserves source-row lineage, supports descriptive full-corpus and explicit as-of modes,
and may report basic frequencies. Extraction is evidence about statements in a report,
not verification that a component malfunctioned.

No failure diagnosis, causality, reliability estimate, severity estimate, vehicle risk,
sentiment score, recommendation, model promotion, external NLP API, pretrained-model
download, or canonical-model training is in scope. The existing structured component and
severity fields are source context, not text-extraction labels or gold truth.

Phase 8B owns advanced source normalization and theme analysis. Phase 8A includes only the
minimal derived normalization required for matching and basic component/symptom frequency
diagnostics; no topic modeling, clustering, embeddings, fuzzy entity resolution, or learned
theme labels. Phase 8C owns any approved integration with analytical features or inference.
Phase 9 owns component-level prediction. None is authorized by completion of Phase 8A.

## Inputs and isolation

The primary input is `data/processed/nhtsa/complaints/complaints-clean.jsonl`, accompanied by
its cleaning provenance. Consume it through the existing `iter_clean_records()` interface
in `howreliable.data.features.nhtsa_complaints`. Do not rerun ingestion or cleaning.
The restored snapshot has 412,866 accepted rows from 418,884 ingested rows and 6,018
exclusions. These are snapshot reference counts, not a hard-coded requirement for other
explicitly selected, separately versioned snapshots.

Required lineage includes `event_id`, `source_type`, `source_record_id` (CMPLID),
`source_reference_id` (ODINO when available), `broad_vehicle_id`, report and occurrence
dates, narrative, and quality flags. Retain structured component context separately.
Do not infer missing narrative text from model features or structured labels.

Future outputs belong only under new versioned directories such as
`data/processed/nlp/owner-reports/<run_id>/` and
`artifacts/nlp/owner-reports/<run_id>/`. These are proposed artifact locations, not existing
CLI commands. Data, annotations, and narrative excerpts remain Git-ignored.

The bundle `howreliable-rf-2022-cutoff-v1`, model bytes, registry manifest, features, targets,
split, presentation fixtures/checksums, handoffs, existing Component enum, and API schemas
must remain unchanged. No NLP output enters their directories or loader selection.

## Taxonomy v1

Labels are multi-label text annotations in a separate NLP namespace. Matching an example
phrase below requires the contextual decisions in the annotation guide; these examples
are not a complete executable lexicon. Existing domain enum values are never extended or
redefined. Optional mappings back to that enum are descriptive metadata only.

| Component code | Explicit referent examples | Boundary |
| --- | --- | --- |
| `engine` | engine, engine cylinder | Engine-warning lamps alone do not identify a damaged engine |
| `transmission` | transmission, gearbox, clutch | Generic loss of power does not identify transmission |
| `electrical` | battery, alternator, wiring, electrical system | A symptom alone does not establish electrical cause |
| `cooling` | radiator, coolant system, water pump | Heat alone does not identify cooling hardware |
| `suspension` | suspension, strut, shock absorber | Generic vibration does not identify suspension |
| `brakes` | brakes, brake pedal, brake booster | A warning mention does not establish brake malfunction |
| `steering` | steering, steering wheel, power steering | Distinguish steering wheel from road wheel |
| `fuel_system` | fuel pump, fuel line, fuel tank | Generic odor is not sufficient |
| `hvac` | air conditioning, cabin heater, defroster | Distinguish cabin heating from engine heat |
| `exhaust` | exhaust pipe, muffler, catalytic converter | Smoke alone is not an exhaust referent |
| `body` | door, window, latch, body panel | Vehicle-model names do not imply components |
| `airbags_restraints` | airbag, seat belt, restraint | Deployment mention is not a defect conclusion |
| `tires_wheels` | tire, road wheel, wheel rim | Bare ambiguous "wheel" requires context |

Use `component_unmapped` for an explicit vehicle part outside these groups. Use
`component_ambiguous` when an explicit referent cannot be assigned conservatively; record
candidate codes when supported. Neither is a positive named-component prediction. No
mention is represented by an empty list, never a fabricated `unknown` span.

| Symptom code | Observable statement examples | Boundary |
| --- | --- | --- |
| `stall_shutdown` | stalled, shut off while operating | Exclude deliberate switching off |
| `no_start` | would not start | Distinguish from uncertain future concern |
| `hesitation_power_loss` | hesitation, reduced/lost propulsion power | Do not infer a cause |
| `unintended_acceleration` | accelerated without driver intent | Ordinary acceleration is not a symptom |
| `noise` | grinding, knocking, squealing | Require vehicle-related reported noise |
| `vibration` | shaking, vibration | Exclude figurative or unrelated descriptions |
| `leak` | fluid leaking, dripping fluid | Fluid type may remain unspecified |
| `odor` | burning/fuel odor | Odor does not establish fire or leakage |
| `smoke` | visible smoke | Keep distinct from odor and overheating |
| `overheating` | overheated, temperature abnormally high | Exclude ordinary cabin-temperature preference |
| `warning_indicator` | warning lamp/message illuminated | Identify the indication, not a diagnosis |
| `braking_difficulty` | hard brake pedal, loss of braking/assistance | Normal braking is not a symptom |
| `steering_difficulty` | steering locked/heavy, assistance lost | Normal turning is not a symptom |
| `electrical_interruption` | lights cut out, electrical supply interrupted | Require explicit electrical context |
| `shift_engagement` | would not shift, harsh gear engagement | Normal shifting is not a symptom |
| `intermittent_operation` | cuts in and out, intermittently stops working | Retain another specific symptom when explicit |
| `operation_loss` | explicitly stopped working, failed to operate | Generic fallback, not a mechanical diagnosis |

Use `symptom_unmapped` for an explicit observable problem outside v1 and
`symptom_ambiguous` for a genuinely unresolved symptom description. Do not turn a generic
"problem" or bare "failure" into a specific symptom. Reserve taxonomy extensions for a
reviewed version change; never tune categories using held-out errors.

## Processing contract

Preserve original text. A derived matching view may use Unicode NFKC, casefolding, and
whitespace normalization, with explicit alignment back to the original narrative. Do not
silently repair uncertain Latin-1/C1 characters, remove negators, discard punctuation
boundaries, stem broadly, fuzzy-match, or truncate long text. Preserve input quality flags.
Missing, empty, unsupported, or unalignable text receives an explicit status.

Evidence offsets are zero-based Unicode code-point positions in the original Python
string, with an exclusive end. `narrative[start:end]` must equal the stored evidence text.
They are neither UTF-8 byte offsets nor UTF-16 code-unit offsets. Output mentions are
sorted by start, end, kind, and code; duplicate identical annotations are collapsed.

Assertion values are `affirmed`, `negated`, `uncertain`, and `unresolved`. They describe the
statement, not real-world verification. Repair/history and conditional wording are handled
as specified in the guide. Contradictory spans remain separate; no document-wide status
overwrites them. No numerical confidence score is emitted.

Associations link component and symptom mention IDs only when text explicitly supports
the relation in a shared clause or unambiguous local construction. Proximity alone,
structured component labels, and unresolved pronouns cannot create associations.

## Report groups, duplicate text, and time

Preserve one output row per input clean row, including excluded-by-date or unprocessable
rows. `event_id` must be unique; repeated IDs fail rather than disappear. Define report
groups by source namespace plus nonempty ODINO; otherwise use source namespace plus
CMPLID and mark the fallback. Missing identifiers fail input validation. Record all row
memberships and divergent narratives; do not pick an arbitrary representative version.

Fingerprint exact original nonempty narrative text as SHA-256 of UTF-8 bytes. Empty/missing
texts do not create one giant duplicate group. Exact-text reuse may share computation but
never removes lineage. No approximate merging is part of v1.

Evaluation grouping is the transitive closure of shared report IDs and identical nonempty
narratives, so indirect duplicate chains cannot cross partitions. Grouping is for evaluation
isolation, not a claim that different ODI reports are the same incident. Frequency reports
show source-row and unique-report denominators separately and flag conflicting variants.
Count a label at most once per report group and assertion category; category totals can
overlap and must not be summed as mutually exclusive incidents.

`full_corpus` is descriptive, not leakage-safe training evidence. `as_of` requires an
explicit ISO date and includes only rows with `report_date <= cutoff`; missing report dates
are excluded with an explicit status. Occurrence dates do not establish availability.
Filter before extraction and frequency aggregation; a future row cannot supply the text or
context for an eligible row in a mixed-date report group. Exact-text caching does not bypass
eligibility. Snapshot revisions may postdate the cutoff; disclose this historical limitation.

No future-complaint targets guide rule development. Any later learned transform must use
training-only inputs and a separately approved experiment; it is outside Phase 8A.

## Output schemas and provenance

The following are normative logical schemas for later implementation, not changes to
existing data or API schemas. Use explicit nulls for absent scalar values and empty lists
for absent mentions/relations. Unknown fields and invalid enum values fail validation.

| Artifact | Required fields |
| --- | --- |
| Extraction row | `schema_version`, `taxonomy_version`, `event_id`, source IDs, `broad_vehicle_id`, `report_group_id`, `narrative_sha256` (nullable), `report_date`, `occurrence_date`, `mode`, `cutoff` (nullable), `processing_status`, quality flags, structured component context, `mentions`, `associations` |
| Mention | Row-local stable `mention_id`, `kind` (`component` or `symptom`), `code`, `assertion`, `start`, `end`, `evidence_text`, `rule_id`, assertion-cue spans, candidate codes, ambiguity reason (nullable) |
| Association | Component and symptom mention IDs, relation `reported_with`, supporting original-text span, `rule_id`; linked mentions retain their own assertions |
| Duplicate membership | Report-group ID, event ID, text fingerprint, fallback/group-conflict indicators; evaluation component ID when sampled |
| Frequency diagnostic | Mode/cutoff, label/assertion or explicit pair, row count, unique-report count, eligible/processable report denominators, conflicting-group count |
| Annotation | Annotation schema/guide versions, report/evaluation group IDs, source text hashes and row references, partition, manual mentions/relations, annotation/review status and disagreement notes |

`processing_status` distinguishes `processed`, `missing_text`, `empty_text`,
`unsupported_text`, `unalignable_text`, `excluded_missing_report_date`, and
`excluded_after_cutoff`. `processed` with no mentions is valid. Any new status requires a
schema version review. Only affirmed named labels contribute to primary positive-frequency
counts; negated, uncertain, unresolved, and unmapped outcomes are separate diagnostics.

Run provenance must include input and provenance-file hashes, raw-source identity/hash,
snapshot counts, schema/taxonomy/guide versions, rule/configuration hashes, code revision
and dirty-worktree indicator, dependency/Python versions, normalization/offset/duplicate
policies, mode/cutoff, sample seed and manifest hash when applicable, injected UTC generation
time, all status/group counts, and output hashes/sizes. It must not contain credentials.

Specify UTF-8 without BOM, LF newlines, stable field/array ordering, finite JSON values,
and trailing newline. Identical inputs, rules, configuration and explicit clock must produce
identical deterministic bytes. Runtime/peak-memory observations belong in a separate
non-deterministic benchmark report. Outputs refuse overwrite; stage and verify before
publication, with no partial run presented as complete. Routine logs exclude narrative text.

## Evaluation and performance

Use the [annotation protocol](owner-report-nlp-annotation-guide.md): 200 manually annotated
unique reports, 100 development and 100 held-out, with report/exact-text group isolation.
Prioritize precision. Provisional primary target: at least 90% precision independently for
affirmed named-component labels and affirmed named-symptom labels on the held-out set.
This is a point-estimate target, not a statistical-validation claim or a recall target.

Report TP/FP/FN, micro precision/recall/F1, per-category support and metrics, report-level
label-set errors, extraction span exact/overlap scores, assertion confusion, association
precision/recall, abstention and processing coverage. A primary label prediction is
`(report_group_id, kind, code, affirmed)` with repeated spans collapsed. Wrong assertion or
wrong named label does not receive positive-label credit. Exact span metrics additionally
require matching offsets, kind, code and assertion; use deterministic one-to-one matching
for overlap metrics. Association scoring requires correct endpoints and the stated relation.

Give 95% Wilson intervals for positive-label precision and state their report/group
dependence limitation. Report per-category report counts; zero denominators are undefined,
never 100%. Fewer than 20 positive evaluated predictions in a category is explicitly
insufficient-support under this provisional reporting policy. Larger counts alone do not
establish validity. Do not claim a validated 90% target when samples are insufficient or
highly dependent. Report recall to expose trivial abstention; no numerical recall gate is
approved yet. Freeze sampling, gold labels, rules and thresholds before held-out scoring.

Stream the 412,866-row reference corpus with a target of at most 2 GB peak RAM. Avoid a
full-corpus dataframe or unbounded text cache. Duplicate indexing may use bounded disk-backed
storage; preserve deterministic IDs/output order. Benchmark first on a fixed sample, then
the complete corpus. Record wall time, throughput, peak process memory, hardware, library
versions and measurement method. Runtime acceptance remains unset until benchmark review.

## Milestones and acceptance

| Milestone | Deliverable | Acceptance gate |
| --- | --- | --- |
| A | This versioned specification and annotation guide | Scope, taxonomy, protocol, schemas, boundaries and open decisions documented; documentation-only changes |
| B | Input adapter, grouping, time controls and schemas | Input/status conservation, source preservation, path safety, duplicate/date isolation and synthetic tests |
| C | Explicit component matching only | Original-text spans, versioned lexicon, conservative unresolved assertions, accounting regressions; synthetic narratives only |
| D | Symptoms, assertion scope and associations | Versioned lexicon/context rules, synthetic assertion/association fixtures, legacy-schema and streaming regressions |
| E | Duplicate memberships and temporal controls | Persistent index, transitive evaluation keys, eligible accounting and synthetic partition-isolation tests |
| F | Deterministic descriptive summaries | Synthetic-tested report/row counts, eligible denominators, verified membership, completion provenance; no full-corpus run |
| G | Annotation manifests, development evaluation and benchmark | 100 development and 100 sealed held-out reports; duplicate isolation, annotation review and RAM target measured under separate approval |
| H | Frozen held-out evaluation and handoff | Precision targets/support/uncertainty honestly reported; failed or underpowered criteria remain explicit; frozen artifacts/API unchanged |

Later milestone work requires separate authorization. Tests should cover Unicode alignment,
negation scope, ambiguous terms, contradictory mentions, duplicate chains, missing dates,
mixed-date groups, stable serialization, overwrite refusal, interruption handling and memory
behavior. Preserve ingestion, cleaning, mapping, feature, registry, API and monitoring
regressions; verify canonical artifact hashes before/after full-artifact acceptance.

Documentation to update as implementation progresses: this specification/guide, roadmap,
architecture, data layout, evaluation limitations and local command reference. There is no
learned model at this stage; local extraction and descriptive-summary commands are below.

## Milestone B local adapter (historical schema 1.0)

This section records the empty-extraction B contract. Current C behavior supersedes its
empty-component and disabled-extraction statements as described in the next section.

`python -m howreliable.nlp` consumes the validated clean-record stream and its adjacent
`.provenance.json` sidecar. The sidecar must identify cleaning/mapping versions and the
expected accepted-row count. It emits schema `howreliable-owner-report-extraction-1.0`
with the specified `mentions` and `associations` arrays plus explicit `component_mentions`
and `symptom_mentions` arrays; all four collections are empty-only in Milestone B.
Nonempty collections will require a reviewed schema extension in Milestone C.

The following is usage only; the full corpus has not been processed for Milestone B:

```console
python -m howreliable.nlp --input data/processed/nhtsa/complaints/complaints-clean.jsonl --output data/processed/nlp/owner-reports/example/rows.jsonl --generation-utc 2026-10-27T12:00:00Z
```

For date filtering add `--mode as_of --cutoff 2022-12-31`. Full-corpus mode forbids a cutoff.
`--provenance` may select a separate completion-marker path; by default the marker is
`<output>.provenance.json`. Repository-local destinations must remain under
`data/processed/nlp/` or `artifacts/nlp/`. External scratch destinations support synthetic
tests. Outputs may not alias the input, its sidecar, or each other; existing targets fail.

One output row is emitted per valid input row, in input order, even when excluded by date
or lacking text. Missing narrative is `missing_text`; empty/whitespace-only is `empty_text`.
Date-excluded status takes precedence. No language classifier, normalization or alignment
is attempted; quality-flagged strings remain intact in the input and are fingerprinted.
`processed` means adapter processing succeeded, not that matching found no real-world issues.
Provenance explicitly records `extraction_implemented=false`.

Report identities use a hash of `[source_type, "ODINO", source_reference_id]`, with a typed
CMPLID fallback. Duplicate event IDs fail. SQLite indexes enforce uniqueness and count report
groups, exact nonempty texts and conflicting text variants on disk with an 8 MiB page-cache
budget. Whitespace-only text has no duplicate fingerprint. Group counts describe all input
rows, including excluded rows; they are not eligible-report frequency denominators.
Transitive evaluation grouping, membership exports, annotations and frequency reports are
deferred; the adapter makes no evaluation-partition or extraction-quality claim.

Files are staged outside final paths. Ordinary failures and interrupts remove files created
by this run. Provenance is published last; consumers must require its complete marker and
verify output checksum/count. A process kill or power loss can leave an incomplete/orphan
output; it must not be treated as completed or overwritten on retry. Recovery requires
inspection and explicit cleanup approval. No two-file atomic transaction is claimed.

Provenance includes input/sidecar/output hashes, counts, configuration hash, local code hash,
Git revision/dirty status when available, Python/Pydantic versions, policies and an injected
UTC time. Code identity hashes the adapter package and directly consumed validation/schema
sources. No source text is logged. Deterministic reruns require the same code/worktree
identity, input bytes, configuration, output filename and timestamp. Synthetic tests validate
these guarantees; the 2 GB full-corpus target remains unbenchmarked.

```console
python -m pytest tests/test_owner_report_nlp.py -q -p no:cacheprovider
```

## Milestone C component matching (historical schema 1.1)

The standalone component matcher remains unchanged as the C lexical baseline. The streaming
pipeline now additionally applies D context rules; its current output is schema 1.2.

The same CLI now uses lexicon `howreliable-owner-report-component-lexicon-1.0` and matcher
`howreliable-owner-report-component-matcher-1.0`. The authoritative executable aliases are
the immutable `LEXICON` in `src/howreliable/nlp/components.py`. It covers all thirteen named
component categories with explicit plurals and variants, including gearbox/clutch,
battery/alternator, water pump, shock absorber, brake pedal/booster, fuel pump, cabin heater,
muffler, door/latch, seatbelt/air bag and tire/tyre. Uppercase `ABS`, `SRS` and `HVAC` are
documented abbreviations; lowercase forms are deliberately not recognized. Bare wheel(s)
produces `component_ambiguous` with steering/road-wheel candidates. There is no generic
unmapped-part detector and no fuzzy alias expansion.

Matching uses per-original-code-point NFKC/casefold plus declared dash variants. Whole-word
boundaries prevent substrings inside longer words/identifiers. Declared multiword aliases
accept whitespace sequences or a hyphen between words. This deliberately limited view does
not compose across original combining-code-point sequences or guess encoding corrections.
An explicit original-index map handles compatibility/casefold expansions; partial-expansion
matches are rejected. Every evidence span slices the unchanged source narrative exactly.
Longest phrases win overlapping candidates, followed by start/code/alias tie-breaks;
retained mentions are sorted by original start/end/kind/code. Repeated nonoverlapping
mentions remain separate, with stable row-local IDs and alias-derived rule identifiers.

All C mentions have `assertion=unresolved`, empty cue spans, and an explicit reason.
This intentionally under-asserts even simple affirmative, negative, hypothetical and repair
statements. It does not evaluate negation or uncertainty scope. Indicator wording immediately
following a referent (for example engine light or ABS warning lamp) receives a warning-context
reason; it never establishes damage. Bare wheel ambiguity receives its own reason.
Recognition of a lexical referent alone is not an affirmed complaint or failed-component label.
Advanced scope and ambiguity resolution are deferred to D; no precision target is claimed.

Schema 1.1 replaces B's empty-only component collections with strict `ComponentMention`
objects carrying kind/code, original offsets/evidence, stable ID/rule ID, unresolved assertion,
cue spans, candidate codes and reason. `mentions` and `component_mentions` must agree;
duplicate identities, invalid spans/codes/order, and mentions in unprocessable/date-excluded
rows fail validation. `symptom_mentions` and `associations` remain empty-only. This is a
versioned NLP schema extension, not an API or frozen-artifact change.

The adapter filters dates before matching and never uses structured component context to
generate mentions. Original input bytes/hashes and record-accounting/publication guarantees
are preserved. Provenance records milestone C, component lexicon version/hash and matcher
version, `extraction_implemented=true`, `symptom_extraction_implemented=false`, normalization
and unresolved-assertion policy. No full historical NLP run or memory benchmark has occurred.

```console
python -m pytest tests/test_nlp_components.py tests/test_owner_report_nlp.py -q -p no:cacheprovider
```

## Milestone D symptoms, assertions and associations

The local CLI is unchanged in invocation but now emits populated component, symptom and
combined mention arrays and conservative associations. The executable symptom lexicon in
`src/howreliable/nlp/symptoms.py` is versioned
`howreliable-owner-report-symptom-lexicon-1.0`. It covers all seventeen named symptom families:
stall/shutdown, no-start, hesitation/power loss, unintended acceleration, noise, vibration,
shift engagement, leak, odor, smoke, overheating, warning indication, braking difficulty,
steering difficulty, electrical interruption, intermittent operation and generic operation
loss. Explicit aliases include "would not start", "harsh engagement", "burning odor",
"warning light", "loss of steering assistance", and "lights cut out". Morphology is a
finite alias list, not stemming; no generic unmapped-symptom classifier is claimed.

Symptoms reuse C's original-offset matching view, word boundaries and longest overlapping
phrase policy. Multiword symptoms can contain component mentions; within-kind overlaps are
resolved while cross-kind evidence can overlap. No original narrative is rewritten.

`howreliable-owner-report-assertion-1.0` classifies each mention independently. The scope is
the current punctuation/contrast-bounded clause and at most eight preceding tokens. Period,
question/exclamation mark, comma, semicolon, newline and explicit contrast words terminate
scope. Supported preceding cues include no/not/never/without/denied, possibility/suspicion,
and if/unless/would/should. "Not only" is not a denial. Simple postposed "is/was suspected"
or "is/was possible" and symptom "is/was not present/absent/denied" are recognized.
Cue spans always reference original text. Lexical absence phrases such as "would not start"
represent an affirmed no-start symptom; their internal negator is not an external denial.

Component referents may be affirmed while their symptoms are negated: "engine did not stall"
affirms an engine referent and negates stalling. This is not an affirmed engine fault.
Warning-context and ambiguous component referents remain unresolved. Mixed uncertainty and
negation, overlong context, and negation/uncertainty across conjunctions abstain as unresolved.
Repair/replacement/recall wording anywhere in a clause conservatively leaves its symptoms
unresolved; an explicit symptom in a separate clause is evaluated independently. Components
mentioned as repair history remain referents. Possible deliberate shutdown and generic
operation loss with no preceding subject also abstain.

`howreliable-owner-report-association-1.0` emits `reported_with`, never causality. A relation
requires exactly one component in the symptom's bounded clause, resolved endpoints, and
either a component contained in an explicit symptom phrase or a component immediately before
the symptom with an allowlisted grammatical connector of at most six words. Repair clauses,
warning indicators, multiple candidate components, unresolved pronouns/unsupported gaps and
cross-clause co-occurrence do not produce relations. Negated or uncertain explicit relations
may be retained; consumers must inspect endpoint assertions. Evidence covers both endpoints
and rule IDs record which construction supported the link.

Schema 1.2 expands assertion values to all four approved statuses, adds typed original-text
cue spans and symptoms, and typed associations with validated endpoint references. Combined
mentions must equal the sorted union of component and symptom arrays with unique IDs.
Legacy rows/provenance 1.0 (empty extraction) and 1.1 (component-only) remain readable without
rewriting their files; their capability constraints still apply. New provenance records D,
symptom lexicon version/hash, assertion and association rule versions, and explicit capability
flags. Input/output hashes, stable serialization, count conservation, date-before-extraction
filtering, duplicate accounting, overwrite refusal and cleanup behavior remain in force.

Limitations: this is a narrow rule system, not a dependency parser, language detector,
coreference resolver, diagnosis engine or complete negation grammar. Repair clauses can
under-count genuine historical symptoms; coordinated subjects/shared predicates and
postposed wording outside the listed forms may abstain or be missed. Clause boundaries can
split abbreviations. Lexical matches can be non-vehicle uses; accuracy is not validated by
synthetic tests. No held-out evaluation, precision claim, full-corpus run or memory benchmark
is made. Changes based on later annotation require the existing evaluation/version controls.

```console
python -m pytest tests/test_nlp_context.py tests/test_nlp_components.py tests/test_owner_report_nlp.py -q -p no:cacheprovider
```

## Milestone E duplicate memberships and temporal controls

B already supplies source-type/ODINO report hashes, typed CMPLID fallback, exact original
text hashes, SQLite uniqueness/accounting and report-date filtering. E extends those same
tables rather than introducing a competing report-identity policy. Component/symptom rules
are unchanged. There is no theme aggregation, annotation sampling, split assignment or
evaluation scoring in E.

Each completed CLI run now publishes `<output>.membership.sqlite` between the extraction
JSONL and its final provenance marker. Its schema is
`howreliable-owner-report-membership-1.0`, with grouping policy
`howreliable-owner-report-grouping-1.0`. The `events` table preserves every row's event ID,
source IDs/type, report ID, original nonempty narrative hash, source sequence, both dates,
fallback flag, availability eligibility and processability. Read with `ORDER BY sequence`;
SQLite physical row order is not a contract. `report_groups` provides narrative/date conflict
flags and evaluation-group IDs. The index contains identifiers/hashes, not copied narratives.

Report IDs remain distinct for distinct ODI identifiers, even when text is identical.
Evaluation groups instead form the transitive closure of shared reports and identical
nonempty narrative hashes. The representative is the lexicographically smallest report ID
in the connected component, yielding deterministic keys independent of input order. Keys
are snapshot-relative: adding/removing a bridging report can change a component. Missing
or whitespace-only narratives do not connect reports. No normalization, near-duplicate
matching or semantic incident deduplication is used. All group members are retained.

`report_group_conflict` means more than one distinct nonempty text hash within a report;
missing text alone is not a contradictory narrative. `report_date_conflict` means different
availability values, including known versus missing dates. Do not choose an arbitrary text
or earliest date. E preserves B's row-level rule: in as-of mode a row is eligible only when
its own report date is known and on/before the cutoff. A conflict is flagged, not repaired
or silently propagated to other rows. A report with mixed dates may have eligible and
excluded rows; its eligible report count is based solely on eligible rows. Occurrence dates
never grant eligibility. Invalid dates fail the validated clean-record stream and abort the
whole run before final publication. Full-corpus descriptive mode retains missing dates.

Schema 1.3 adds `evaluation_group_id`, `report_group_conflict`, `report_date_conflict` and
`eligible` to finalized extraction rows. Older schemas 1.0–1.2 remain readable with absent
membership fields; they are not sufficient inputs for duplicate-safe partitioning.
Rows are staged first, then augmented in input order after disk-backed grouping finishes.
No extraction uses another row's narrative, date or prediction.

Provenance records grouping/index versions, membership filename and SHA-256, SQLite runtime
version and `membership_counts`. Existing input/output row counts, unique-report counts and
conflicting-narrative report counts remain. Exact-text duplicate count is the number of
nonempty-text rows minus the number of distinct fingerprints; it includes repeated component
rows and repetitions across reports. It is not a count of duplicate incidents. Eligible
row/report/duplicate counts use eligible rows only; processable row/report counts additionally
require status `processed`. These are accounting diagnostics, not theme summaries.
Evaluation-group counts span all rows to conservatively prevent split leakage, even when
some connected rows are date-excluded. They are not eligible-summary denominators.

Before future partitioning, verify the run's complete provenance and BOTH output hashes.
The reusable check is:

```python
from pathlib import Path
from howreliable.nlp import validate_partition_assignments

validate_partition_assignments(
    Path("<completed-output>.membership.sqlite"),
    {"<event-id-1>": "development", "<event-id-2>": "held_out"},
)
```

Pass the entire proposed event-ID assignment together, never each split independently.
The helper opens the index read-only, rejects unknown events, blank partition names,
date-excluded assignments and cross-partition evaluation groups. It does not choose splits,
save assignments, enforce sample sizes or authenticate an index's hash itself. Future
sampling must use these group keys and recheck the complete assignment; report-only splitting
is unsafe for identical text across reports. SQLite TEMP tables used for this check are
connection-local, not mutations to the saved membership index.

The original overwrite/path protections cover the index too. Failure or interrupt removes
this run's published JSONL/index/marker. Hard kills may leave orphan files; absent matching
complete provenance they are uncommitted and require inspection, not automatic overwrite.
Index-byte reproducibility is tested on the same SQLite runtime; cross-version SQLite
storage-byte identity is not promised. Logical grouping keys have deterministic definitions.
Memory remains bounded by streaming plus disk indexes; no full-corpus benchmark has run.
The restored snapshot can contain historical revisions, so report-date eligibility still
does not establish that the exact text was published by that historical date.

```console
python -m pytest tests/test_nlp_grouping.py -q -p no:cacheprovider
```

## Milestone F descriptive summaries

The standalone `howreliable.nlp.summaries` command consumes a completed schema 1.3
extraction and its Milestone E membership index. It never reruns extraction or modifies
inputs. Existing extraction schemas/readers remain unchanged. Pre-E runs without a
verified membership index are rejected rather than inventing report memberships.

```console
python -m howreliable.nlp.summaries --extraction <completed-run>/rows.jsonl --output artifacts/nlp/owner-reports/example/summary.json --generation-utc 2026-10-27T12:00:00Z
```

Defaults for input provenance and index are `<extraction>.provenance.json` and
`<extraction>.membership.sqlite`. Optional `--extraction-provenance`, `--membership`
and `--provenance` accept explicit paths. Repository outputs must stay under
`artifacts/nlp` or `data/processed/nlp`; external scratch directories support synthetic tests.
This example is usage only: no historical corpus has been processed for F.

The UTF-8, LF, deterministically serialized JSON summary uses
`howreliable-owner-report-summary-1.0`. It includes:

- `denominators`: total, temporally eligible, and eligible-processable source rows and
  distinct reports. Processable means extraction status `processed`; date-excluded rows
  therefore cannot enter the processable denominators, even if their text was nonempty.
- `processing_statuses`: all input statuses, including excluded/missing/empty narratives.
- `components`, `symptoms`: category plus assertion status, occurrence count, source-row
  count and unique-report count. `primary_pattern` identifies affirmed named labels.
- `category_totals_all_assertions`: distinct row/report counts by category across statuses,
  with occurrence totals. These diagnostic totals are not positive-complaint counts.
- `associations`: only existing rule-supported links, grouped by component/symptom codes
  and both endpoint assertions. Both endpoints must be affirmed for a primary pattern.
- `assertions`: four-status diagnostics for emitted mentions (only observed statuses appear).
- `unresolved_mentions`: unresolved category/status counts. `eligible_processed_without_mentions`
  and `eligible_processed_without_associations` count rows/reports lacking emitted evidence.
  Absence of a link is not proof that an association was attempted and abstained; no new
  abstention reason or unsupported association is inferred.

Unique-report counts are the primary recurring-pattern measure. Each report counts once
per category/status or association/endpoint-status combination, regardless of repeated
mentions or duplicate component rows. Category totals deduplicate across statuses too.
Distinct ODI reports remain distinct even with identical narratives; evaluation-group IDs
are never report denominators. A report can occur in several statuses or in both eligible
and excluded row accounting. These overlapping counts must not be summed as incident totals.
All pattern counts use eligible processed rows only, before report-level deduplication.

Category/status and association tables sort by descending unique-report count, descending
source-row count, then lexical codes/statuses. Category totals use the same count priority
then category; assertion/processing tables sort lexically. Summaries contain aggregate labels
and counts only: no narratives, source identifiers, evidence spans or individual group IDs.
They describe complaint-report patterns, not verified failures, defect rates, severity,
causality, exposure-adjusted rates or reliability estimates. Advanced themes remain Phase 8B.

The reader verifies completion provenance, extraction/index hashes, schema and temporal
identities, each row's indexed membership/date/eligibility/sequence and conservation counts.
It opens the membership index read-only and stores counting facts in temporary disk-backed
SQLite with an 8 MiB main cache and disk temporary storage. It streams extraction rows;
memory is bounded by a row plus the fixed taxonomy aggregate output. Disk usage grows with
rows/mentions. The <=2 GB goal and runtime remain unbenchmarked on the historical corpus.

`<summary>.provenance.json` uses `howreliable-owner-report-summary-provenance-1.0`, recording
source extraction, source completion and membership checksums; extraction schema/rule
identities; temporal/counting policies; injected UTC timestamp; code hash/revision/dirty
identity; and output checksum/byte size. Sources are rehashed before publication. Existing
targets are refused, output is staged privately, and completion provenance publishes last.
Caught failures/interrupts remove only this invocation's published files. Hard termination
can leave orphans: readers must require matching complete provenance; inspect orphans
instead of treating them as complete or automatically overwriting them.

F acceptance covers synthetic repeated mentions, duplicate rows/reports, identical text
across distinct reports, status overlap, absent evidence, cutoff denominators, stable sorting,
deterministic bytes, source immutability, checksum/membership disagreement, missing completion,
overwrite refusal and interrupted publication. No manual evaluation or scoring is performed.

```console
python -m pytest tests/test_nlp_summaries.py -q -p no:cacheprovider
```

## Remaining operational decisions

Assign annotators, independent reviewer and held-out custodian before sampling. Confirm
that 200 report selections can satisfy duplicate isolation and practical category coverage;
do not split a duplicate group to meet quotas. Final executable aliases, context windows,
rule precedence, performance measurement tool and cache limits belong to later reviewed
milestones. The 20-prediction support flag and Wilson reporting are v1 specification choices,
not additional user-approved statistical-validation thresholds. Taxonomy/guide changes
after annotation require documented reannotation and versioning, not silent relabeling.
