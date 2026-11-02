# Development-only local annotation editor (G2A.1)

The editor uses existing FastAPI/Uvicorn dependencies and local HTML/CSS/JavaScript.
No installation, network model, prediction service or product API change is needed.
Working schema: `howreliable-development-review-1.0`. The frozen annotation/extraction
schemas and evaluation partitions remain unchanged.

## Launch and resume

From the repository root with the project Python environment:

```powershell
$source = 'artifacts/nlp/owner-reports/g2a-annotation-20261027-v2/development/worksheet.jsonl'
$working = 'artifacts/nlp/owner-reports/annotation-work/development-review.json'
python -m howreliable.nlp.review_app --source $source --working $working
```

Open `http://127.0.0.1:8765` in a local browser. Stop with Ctrl+C. `--port` can select
another local port; there is deliberately no host option. The command always binds to
`127.0.0.1`. It does not open the browser automatically or create annotations on launch.
The working file is first created on Save. Restart with the same paths to resume saved
work; the UI opens the first in-progress report, otherwise the first pending report.
Use the report selector for any other saved report. Progress counts represent saved states.

The source must be an empty `development/worksheet.jsonl` and every unit must belong to
development. Held-out/private/prediction/mapping/manifest paths are refused, including
resolved aliases into those paths. The browser receives only taxonomy options, progress
metadata and one development report at a time. There is no file browser, upload route,
prediction display or static-directory mount. No held-out worksheet, private mapping,
prediction file, or partition manifest is read by the application.

The destination must be a separate `.json` path under an `annotation-work` directory,
outside the frozen source run. Repository destinations must be in Git-ignored
`artifacts/nlp` or `data/processed/nlp`. Separate outside-repository scratch directories
with the same marker are supported for synthetic tests. Do not put working files in a
synced/public directory. Development narratives may contain incidental personal information;
keep the browser and all files local. This editor intentionally cannot be used for holdout
annotation; that requires a separately approved custodian workflow.

## Annotate one report

1. Enter your annotator ID. Read every original narrative variant. Metadata shows dates
   and source-row multiplicity; source IDs and structured component/severity are hidden.
2. Select the shortest complete component or symptom phrase in the read-only narrative,
   using the mouse or keyboard. The selection panel shows original text and `[start,end)`.
   Select kind, taxonomy code, and assertion explicitly. Explain the interpretation or
   ambiguity; even clear mentions need a reason because the frozen mention schema requires
   `ambiguity_reason`. Candidate codes are optional and come from the same approved taxonomy.
3. Click **Add selected evidence**. This creates only your selected annotation. IDs are
   deterministic from annotation ID, variant ID, kind and initial offsets. Repeated mentions
   receive their own spans. Editing keeps the existing mention ID; deletion/recreation of
   the same initial span/kind gives the same ID. No labels or assertion values are suggested.
4. To edit, click **Edit / highlight**, change fields, optionally select new evidence,
   then **Update selected mention**. To add a negation/uncertainty cue, select its text and
   use **Add selected text as cue** on the selected mention. Cues can be removed individually.
   Commit mention-editor fields with Add/Update before saving the report; uncommitted form
   fields are not annotations. **Clear editor** discards those form fields explicitly.
5. To link a component and symptom, select your two endpoint mentions, select the supporting
   clause, and add an association. The clause must cover both endpoints in the same variant;
   unresolved endpoints cannot be linked. Proximity is not evidence of a relationship.
   Remove/recreate a link to change its evidence or endpoints. Removing an endpoint with
   links asks before removing those links too. Changed endpoint spans may require rebuilding
   their links before Save passes validation.
6. Mark the variant finished. For a genuinely empty-label review, explicitly confirm
   **no component or symptom mentions**; do not create an artificial absence span. Confirm
   every variant, including missing/empty variants. These confirmations are human actions.
7. Use **in_progress** while drafting, **annotated** after all variants are complete, or
   **needs_adjudication** with notes for a dispute. Save. A different human reviewer can later
   enter their ID and set **reviewed** after checking the evidence. The tool rejects an
   identical annotator/reviewer ID, but cannot establish actual human independence.

Assertions and ambiguity follow the [annotation guide](owner-report-nlp-annotation-guide.md).
Use unresolved/ambiguous outcomes when justified, rather than forcing a diagnosis. Enter
review notes without consulting predictions. `human-guide-1.0` is saved as manual rule
provenance; it is not an extraction rule or automatic gold label. Independent review and
adjudication remain required human work. This editor does not implement final adjudication
or quality scoring.

## Saving, validation and recovery

Save performs structural and semantic validation before publishing anything. Valid drafts
may have incomplete report/variant review, but every added mention or link must already be
structurally and semantically valid. A draft cannot persist half-filled mention forms;
finish the form or clear it first. Edits invalidate variant completion and return completed
reports to in-progress. Choose the final status after finishing those edits.

The working file stores the source checksum, a revision counter, review state, completion
and explicit-empty confirmations, and annotation records. The original source never changes.
Working JSON is UTF-8 with LF and a trailing newline; arrays retain the working order.
Each later Save preserves the previous saved file in `annotation-work/backups/` using a
unique revision filename. Backup and current-file publication use same-volume atomic rename
and flushed file contents. Unsaved browser edits are not autosaved. Save before pausing;
navigation/close prompts warn about unsaved work. Restarting resumes the last successful Save.

Stale browser tabs are rejected using revision checks. A short exclusive `.lock` file also
prevents concurrent saves across processes. On a save error the old current file remains
valid; your unsaved edits stay in the tab. Reloading discards them. After a hard kill, stop
all editor processes and inspect any stale lock or `.review-*`/`.backup-stage-*` orphan
before removing it. Do not treat temporary files as completed saves. To recover an older
backup, stop the server, preserve the current file, copy the desired backup to a new
working `.json` path, and validate it before launching with that new path. Never restore
over the frozen source. Backups contain narratives and must remain private/Git-ignored.

Read-only CLI validation:

```powershell
python -m howreliable.nlp.annotation_review --source $source --working $working
python -m howreliable.nlp.annotation_review --source $source --working $working --require-complete
```

The first command accepts valid pending/draft/disputed states. The second requires every
report to be annotated or independently reviewed, with all variants completed and explicit
confirmation for empty-label variants. Both exit nonzero on failure and write no files.
Errors contain report positions and fixed codes, not narratives or validation input dumps.

The reusable `validate_working(source, WorkingFile, require_complete=...)` checks source
checksum and ordered identities, immutable variant text/hash/metadata, taxonomy/schema,
explicit assertions, Unicode evidence/cue slicing, unique report-local mention IDs,
association endpoint references/evidence, completion flags and status consistency.
It does not infer whether a human chose the correct label, negation scope, or relationship.
Those decisions still require independent review. Browser selections convert UTF-16 DOM
positions to Python Unicode code-point offsets; the server checks the original string
again before saving, including emoji/combining characters and line breaks.

The localhost service also checks Host/Origin, rejects cross-site writes, requires a custom
JSON request header, disables access logs/caching, uses local assets only, and prevents
embedding. It is a local single-workstation tool, not a multi-user authentication system.
Do not expose it with a tunnel or reverse proxy. No browser-based filesystem API or model
integration is present.

## Validation coverage

Synthetic tests cover offsets, cues, references, immutable identities, completion/empty
review, independent reviewer IDs, save/resume/backups, interrupted replacement, stale edits,
read-only CLI behavior, forbidden paths/routes, host/origin checks and loopback binding.
An installed Node runtime tests browser/Python code-point conversion; an installed headless
Edge optionally exercises real DOM selection, save, reload and immutable-field rejection.
These browser tools are optional test dependencies; no downloads are required by the editor.
