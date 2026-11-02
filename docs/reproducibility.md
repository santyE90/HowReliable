# Reproducibility and local artifacts

There are three distinct setup levels. Git contains application code, tests, documentation,
and infrastructure templates, not the data or canonical model bundle. No public download
location for the exact frozen bundle is currently provided. An owner-approved distribution
or restoration process remains unresolved; do not substitute an invented URL or a retrained model.

## A. Clean clone: inspect, install, and test code

Use Python 3.12 (the configured CI version is 3.12.11). From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -m "not full_artifacts"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

These commands match package metadata and pytest configuration. Installation needs package
downloads; "offline demo" means no network service at runtime after dependencies/artifacts
are installed. Pinned direct dependencies include PyTorch, so installation is not a minimal
FastAPI-only download. No clean-environment install was performed during the H4B docs update.

`tests/conftest.py` classifies canonical-artifact test modules as `full_artifacts` and skips
them when the manifest is absent. A code-only pass is not verification of the real model or
complete demo. Tests create synthetic temporary fixtures; they do not need the complaint corpus.
Some Node/Windows Edge checks skip when their tools are unavailable. See [CI](ci.md).

## B. Historical corpus and SQLite index

### Inputs and provenance

The historical index builder needs:

```text
data/processed/nhtsa/complaints/complaints-clean.jsonl
data/processed/nhtsa/complaints/complaints-clean.jsonl.provenance.json
```

The restored snapshot contains 412,866 accepted source rows. The original ingestion had
418,884 rows; 6,018 exclusions are retained separately as
`complaints-clean.jsonl.excluded.jsonl`. The index does not require reading exclusions.

Its source files originate from the official NHTSA received-date archive documented in
[data sources](data-sources.md). Raw ZIP and interim JSONL/provenance live under
`data/raw/nhtsa/complaints/` and `data/interim/nhtsa/complaints/`, respectively. The ingestion
CLI supports `--artifact` with an actual acquisition timestamp, or `--download`; cleaning uses
`python -m howreliable.data.cleaning`. See [cleaning rules](cleaning-rules.md) for its command
and conservation policy. Do not invent acquisition dates to regenerate historical provenance.

Retrieving the same upstream URL later does not guarantee the same bytes or records. Exact
historical restoration requires the preserved source/provenance, not merely the current URL.
Fresh acquisition is external data work, not a side effect of startup or tests.

### Explicit index build

With the clean input pair restored, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m howreliable.demo.index --input data/processed/nhtsa/complaints/complaints-clean.jsonl --output data/processed/demo/history-v1-20261102-v2.sqlite --generation-utc 2026-11-02T18:00:00Z
```

The timestamp is an explicit reproducibility input, not an automatically inferred current
build time. The default demo reads that exact index path. If the database or its completion
marker already exists, the command refuses to overwrite it. Do not delete an existing index
to rerun this example; choose a new destination for an independent build instead.

The builder streams validated records, verifies canonical vehicle IDs and input conservation,
hashes the source and cleaning provenance, and records code/schema identities and grouping/date
policies. It checks SQLite integrity and accounting before atomic publication; completion
provenance includes the database SHA-256. The API checks that checksum on startup.
Malformed dates/identities fail closed. Missing/conflicting dates have explicit accounting.
There is no separate index `validate` CLI; see [index behavior](local-demo.md).

On the restored snapshot, the index has 290,634 unique reports and 10,670 vehicle identities.
Byte-identical reproduction depends on the same input, code, timestamp, and SQLite environment.
No narratives are copied into the index. All generated outputs remain Git-ignored.

**This level now supports browser purchase assessments and historical browsing.** The P2
demo permits missing/invalid model bundles and reports explicit unavailable predictions; the
original API-only factory remains fail-closed. See [purchase workflow](purchase-assessment.md).

## C. Complete browser demo: canonical model plus historical index

Restore the original manifest pair:

```text
artifacts/registry/bundles/howreliable-rf-2022-cutoff-v1/manifest.json
artifacts/registry/bundles/howreliable-rf-2022-cutoff-v1/manifest.sha256
```

Also restore all 12 manifest-referenced artifacts at their registered repository-relative
paths. These include the trusted sklearn model, as-of feature data, targets/provenance,
split, preferred-model handoff, evaluation/explainability outputs, presentation contracts,
and API contract. They are not all stored beside the manifest. The manifest, not an informal
file copy list, is authoritative. See the [registry roles and trust boundary](model-registry.md).

The documented canonical manifest SHA-256 is:

```text
831ecaa2cf31102bb13d2e414a380465cb948b07c45f9a4acb225e40aa2159cc
```

Validate the restored local bundle:

```powershell
.\.venv\Scripts\python.exe -m howreliable.modeling.registry validate howreliable-rf-2022-cutoff-v1
```

This command checks manifest/sidecar integrity, every registered artifact checksum, compatible
contracts, and model loading. Only trusted owner-provided model artifacts should be loaded;
checksums do not make arbitrary pickle/joblib files safe. Stop on mismatch; do not change
frozen metadata or accepted checksums to accommodate replacement files.

The package includes training and artifact-generation implementations, but no documented
one-command path recreates the complete exact historical bundle from a clean clone. Fixed
random seeds do not guarantee identical model bytes across platforms/library builds.
Restoration and retraining are different operations. No training is required or authorized
by this setup guide.

### Optional global G1 sample panel

Restore these existing outputs only if available:

```text
artifacts/nlp/owner-reports/g1-smoke-20261027-seed-8a01/summary.json
artifacts/nlp/owner-reports/g1-smoke-20261027-seed-8a01/summary.json.provenance.json
```

The reader verifies completion and output checksum. The 1,000-row / 691-report sample
predates current rules and is not independently validated or vehicle-specific. The extraction
corpus, annotations, challenge materials, and hidden predictions are not needed to display it.
Absent sample outputs produce an unavailable panel; do not run NLP to satisfy startup.

### Run and test the provisioned application

```powershell
.\.venv\Scripts\python.exe -m uvicorn howreliable.demo.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/** and stop with **Ctrl+C**. The factory explicitly uses local
artifacts, regardless of S3 settings used for other tools. See [demo walkthrough](local-demo.md).

For the complete regression suite, additional historical test fixtures can be required,
including `artifacts/presentation/representative-results.json` and
`artifacts/cloud/monitoring-contract.json`. Their original bytes were restored locally;
the registry bundle alone is not a promise that every historical fixture is present.
With all fixtures provisioned:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Neither level requires AWS/Terraform operations. No artifact access credentials or private
download instructions should be committed. Review distribution permissions separately for
code, upstream data, models, and annotation materials; see [licensing status](licensing.md).
