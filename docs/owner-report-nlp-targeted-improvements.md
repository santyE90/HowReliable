# G2C.1 targeted development rule improvements

This milestone is exploratory. Five development reports were used for rule design and
evaluation; they cannot establish generalization or the 90% held-out precision target.
The baseline annotations, original prediction file, previous results, extraction schema 1.3,
taxonomy v1, frozen predictive model and API contracts remain unchanged.

## Rule changes

- Component lexicon/matcher 1.1 recognizes the explicit phrases `brake hold system`,
  `steering column` and `steering wheel column`, preserving longest-phrase precedence.
- Body filtering rejects direct building modifiers and narrowly anchored local coreference:
  garage door, door of the garage, garage with the door, and analogous building references.
  A garage elsewhere does not suppress vehicle-door/window mentions. This is bounded
  lexical context, not general entity or pronoun resolution.
- Symptom lexicon 1.1 adds explicit automatic-restart failure variants, a self-contained
  no-other-way-to-turn-on-car/vehicle construction, command-failed predicates, and bounded
  dashboard warning appearance patterns. App/software/command subjects are not physical
  no-start evidence. No generic standalone `failed` or `warning` matcher is added.
- Rolling and delayed abrupt-stop phrases require brake-hold/auto-hold/parking-brake context
  in the same bounded sentence. Explicitly released, inactive or absent hold contexts are
  excluded. HOLD status alone is not a warning. Hypothetical hold problems retain uncertainty
  even across a contrast boundary.
- Assertion rules 1.1 stop using clause length alone to abstain on explicit named component
  referents. Distant uncertainty cues still cause abstention; local suspicion, ambiguity,
  indicator names and negation handling remain conservative. An affirmed engine referent
  never asserts an engine defect.
- `will sometimes not restart automatically` can express a recurring observed failure,
  while explicit hypothetical cues prevent affirmation. Future dashboard-warning wording
  remains uncertain unless bounded explicit recurrence supports a habitual interpretation.
  Repair context and ordinary deliberate shutdown handling remain unchanged.

Offsets still refer to original Unicode code points. Text is never repaired or trimmed.
Existing mention IDs/rule IDs remain stable for unchanged spans/aliases. New rule identities
and lexicon hashes are recorded in provenance. Association rules remain version 1.0; adding
new eligible mentions can nevertheless expose existing association constructions.

## Development-only prediction generation

The original G2A prediction file contains both partitions. G2C.1 does **not** open it or
private mappings. It generates new packets using only completed development identities and
original narrative variants from the frozen development worksheet. Gold labels determine
eligibility only; their codes, spans and assertions are never extraction inputs.

The dedicated `howreliable-development-predictions-1.0` packet schema stores one prediction
per narrative variant with its stable variant ID, source narrative hash and source-row
multiplicity. It does not fabricate source event IDs or pretend to be a full clean-corpus
extraction run. The existing evaluator has a minimal explicit branch for this format,
checking packet/variant identities, text offsets, references, multiplicity and provenance.
The original row-based format and scoring definitions remain supported unchanged. A
synthetic equivalence test scores the same evidence through both formats.

```powershell
$source = 'artifacts/nlp/owner-reports/g2a-annotation-20261027-v2/development/worksheet.jsonl'
$working = 'artifacts/nlp/owner-reports/annotation-work/development-review.json'
$new = 'artifacts/nlp/owner-reports/g2c1-development-20261102-v1'
$results = 'artifacts/nlp/owner-reports/g2c1-development-eval-20261102-v1'
python -m howreliable.nlp.development_predictions --source $source --working $working --output-dir $new --expected-reports 5 --generation-utc 2026-11-02T18:00:00Z
python -m howreliable.nlp.development_evaluation --source $source --working $working --predictions "$new/development-predictions.jsonl" --output-dir $results --generation-utc 2026-11-02T18:00:00Z
```

These commands refuse existing destinations; use new directories for reruns. Generator
provenance binds source, exact working snapshot, prediction bytes and extraction identities.
Evaluation refuses a different working snapshot. Outputs stage privately and publish as a
new directory with completion provenance. No browser prediction display or gold-writing
operation is introduced.

## Validation and limitations

Synthetic cases cover valid vehicle doors near garages, nonvehicle doors/windows/latches,
actual/hypothetical/negated restart, commands versus physical start, normal status versus
warning, active versus released/absent hold, long named referents, uncertainty preservation,
Unicode offsets and repeatability. Generator/evaluator tests cover legacy-equivalent scoring,
gold-value independence, duplicate-row multiplicity, immutable source files, deterministic
bytes, overwrite refusal, interrupted generation and incorrect identities/offsets.

Scope rules remain lexical and bounded. Generic pronouns, long or conflicting statements,
unmapped concepts, complex command/app narratives and distant hold context can still require
abstention. No automatic detection of arbitrary unmapped symptoms was added. The five-report
reference retains its existing span choices, including Report 2 whitespace. Do not alter gold
to improve scores. Review a separate local result/comparison artifact for the measured run;
improved development scores are evidence of fit to these examples, not independent quality.
