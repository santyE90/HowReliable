# HowReliable?

**Evidence-based used-car purchase context from NHTSA data.** HowReliable is a local
Python/FastAPI dashboard combining historical complaint evidence, official U.S. recall and
manufacturer-communication records, transparent purchase-readiness guidance and manually
entered Canadian asking-price comparisons. Its historical ML experiment remains a separate view.

## What it does

- Select a vehicle make, model, and year from **10,670 historical vehicle identities**.
- Explore **290,634 unique reports / 412,866 accepted source rows**, report-date timelines,
  structured components, missing information, and provenance from the restored 2020–2024 snapshot.
- Enter mileage, maintenance, condition, accident and inspection context for explainable,
  conditional purchase-readiness guidance based on user-supplied, unverified information.
- Compare permitted manual Canadian advertisements using deterministic eligibility rules and
  selected-sample asking-price summaries, without an appraisal or external listing retrieval.
- Load vehicle problem profiles with exact-cohort NHTSA recall/communication evidence when
  the optional verified local artifact is installed; unavailable sources remain explicit.
- Inspect a frozen random-forest experiment for **8,416 supported cohorts**, including
  explanations and explicit unsupported-vehicle states.
- Explore a separate **1,000-row / 691-report** global NLP sample, never presented as vehicle-specific.

## Engineering highlights

- Source-faithful NHTSA ingestion, deterministic cleaning, quality flags, and exclusion accounting.
- Canonical vehicle identities with Unicode normalization and exact matching rather than fuzzy joins.
- Streaming, duplicate-aware SQLite indexing: source rows are preserved while report counts avoid inflation.
- Typed FastAPI endpoints and a responsive HTML/CSS/JavaScript dashboard with tested
  keyboard controls, focus behavior, safe text rendering and stale-response protection.
- Checksum-first model registry, immutable artifact contracts, frozen inference, and model explanations.
- Conservative offline component/symptom extraction with evidence spans, assertion rules, and provenance.
- Synthetic tests, artifact-dependent regression tests, Ruff, strict mypy, and existing GitHub Actions CI.

## Technology

Python 3.12 (CI uses 3.12.11), pandas, NumPy, scikit-learn, SQLite, Pydantic, FastAPI/Uvicorn,
and plain HTML/CSS/JavaScript. PyTorch research tooling and historical Docker/AWS/Terraform
materials are also retained; they are not required services for the local demo.

## Architecture

```text
Official NHTSA complaint ZIP
  -> lossless ingestion + provenance
  -> validated clean records
  -> narrative-free SQLite index -> historical FastAPI queries --+
                                                               |
Verified official NHTSA snapshots -> optional evidence SQLite ---+
                                                               |
User purchase context + manual comparables -> separate rules ----+
                                                               |
Restored canonical model bundle -> validated frozen inference ---+-> local browser dashboard
                                                               |
Existing bounded G1 extraction -> global descriptive summary ----+
```

Complaint history, regulatory/document evidence, purchase readiness, asking-price positioning,
the model experiment and the global NLP sample retain distinct meanings and provenance.
See [architecture](docs/architecture.md) and [API contracts](docs/api.md).

## Local setup and demo

From the repository root, using Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

**A clean clone can run code-only tests, but purchase/history browsing needs the ignored
historical index. The canonical model bundle is optional for the separate ML experiment.** No public canonical-bundle download is currently
provided. See [reproducibility and artifact requirements](docs/reproducibility.md).

After provisioning the validated artifacts:

```powershell
.\.venv\Scripts\python.exe -m uvicorn howreliable.demo.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**. Choose make, model, and year, add optional purchase context,
and select **Assess this vehicle**.
Try **2011 BMW 335i** or **2011 Toyota Corolla**. Stop with **Ctrl+C**.
No AWS credentials, Docker, frontend build system, or NLP processing is needed to use the dashboard.
See the [walkthrough and troubleshooting](docs/local-demo.md).

Screenshots, recordings and further portfolio polish remain deferred.

## Data and reproducibility

[NHTSA sources](docs/data-sources.md) document the official received-date archive and schema.
Downloaded data, generated indexes, models, and annotation materials stay outside Git.
Upstream records may be revised: the exact historical snapshot requires preserved bytes and provenance.

| Level | Available from Git? | Additional requirements |
|---|---|---|
| Code inspection and code-only tests | Yes | Installed project/development dependencies |
| Historical data/index rebuilding | Code and commands only | Original clean corpus + provenance, or external data acquisition and preparation |
| Model-free purchase/history demo | Application code only | Historical SQLite index + checksum/provenance sidecar |
| Official recall/communication panel | Reader code only | Separate verified evidence SQLite + manifest |
| Optional frozen ML panel | Reader code only | Canonical manifest/checksum pair + 12 registered artifacts |
| Optional NLP sample panel | Reader code only | Existing G1 summary and completion provenance |

The demo attempts validated model loading at startup; missing or invalid bundles leave
purchase assessments and historical browsing available, with explicit unavailable predictions. Exact artifact restoration is distinct from
rerunning training, which is not promised to reproduce frozen binary checksums.

See the [v1.0 release and artifact backup guide](docs/release-v1.md) for exact local paths,
the SHA-256 inventory, restoration procedure and required versus optional artifacts.
No large backups are created automatically. [Official evidence](docs/official-evidence.md)
documents snapshot scope and permissions. Purchase inputs/comparables stay in page memory;
the app does not persist submissions, retrieve listing URLs or send telemetry. Request
metadata may be logged locally; avoid entering personal information.

## Testing and validation

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not full_artifacts"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

With all canonical regression fixtures restored, run `python -m pytest` in the activated environment.
The final provisioned local run passed **956 tests**, with one optional research-artifact skip
and one existing dependency deprecation warning. A clean clone has additional artifact/browser
skips; this result is not a claim about the latest hosted CI run.
[CI documentation](docs/ci.md) explains artifact-dependent skips. Browser tests use installed
Windows Edge and skip when unavailable; they are not equivalent to cross-browser certification.
The existing CI workflow checks quality, tests, packaging, static contracts, and a non-publishing
Docker build. Its configuration does not establish that the latest hosted run passed.

## Scientific limitations

- The frozen model uses information through **December 2022** to estimate whether a vehicle
  cohort has complaint activity during **January–December 2023**. It is not a current forecast,
  reliability score, repair prediction, or individual mechanical-failure probability.
- NHTSA complaints are selectively reported and lack a suitable exposure denominator here
  for estimating vehicle failure rates. Multiple component categories can overlap within a report.
- Recall and communication counts measure campaigns/documents within a source snapshot,
  not failure frequency. U.S. broad cohort matches do not verify VIN, trim, Canadian-market
  applicability, open recalls or repair completion. Communication coverage is received years 2020–2024.
- Purchase readiness is conditional on unverified supplied context; a favorable asking-price
  comparison cannot establish mechanical condition or a fair market value.
- NLP extraction accuracy has **not been independently validated**. Five development reports
  informed rule design; exploratory results do not establish generalization.
- The global NLP sample predates the latest rules and represents neither the full corpus nor
  the selected vehicle. Further NLP research and challenge annotation are deferred.

See [limitations](docs/limitations.md) and [model evaluation](docs/model-evaluation.md).

## Project status and documentation

**Local v1.0 release preparation is complete; planned feature development is finished.**
P4–P7 supply purchase context, price comparisons and optional official-evidence profiles.
AWS is not required; no live deployment is assumed. The [checkpoint](docs/local-demo.md)
records last reported ALB retirement/ECS stoppage and deferred Terraform reconciliation.

- [Reproducibility and artifacts](docs/reproducibility.md)
- [Local demo, prerequisites, and checkpoint](docs/local-demo.md)
- [v1.0 release and artifact preservation](docs/release-v1.md)
- [Purchase assessments](docs/purchase-assessment.md) · [Manual pricing](docs/pricing-evidence.md)
- [Vehicle problem profiles](docs/vehicle-problem-profile.md) · [Official sources](docs/official-evidence.md)
- [Model registry](docs/model-registry.md) · [NLP scope](docs/owner-report-nlp.md)
- [Roadmap](docs/roadmap.md) · [Historical project overview](docs/project-history.md)
- [Licensing status](docs/licensing.md): no explicit repository license is currently declared;
  code, upstream data, and generated artifacts require separate consideration. Owner selection is pending.
