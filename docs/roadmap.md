# Roadmap

## Current direction

H2/H3/H3.1 deliver the local historical index/API and browser demo. H4A completed the
repository audit; H4B documents presentation and reproducibility; actual screenshots and a
short walkthrough are next in H4C. See [local demo](local-demo.md),
[reproducibility](reproducibility.md), and [historical project overview](project-history.md).

Further NLP research and the G2C.2 20-report challenge annotation are deferred indefinitely;
retain all artifacts. Five development reports informed rule design, so exploratory NLP
scores do not establish independent accuracy. No full-corpus NLP run is implied.

AWS is not required for the local demo. The last reported state is stopped ECS and retired
ALB, with S3/ECR artifacts preserved; Terraform state recovery is complete but reconciliation
is deferred. See the [historical deployment status](local-demo.md#deferred-work-and-infrastructure-boundary).
No live cloud or hosted CI verification was performed for H4B.

## Implementation history

The phase entries below preserve their original validation checkpoints. Older statements
about unexecuted deployment/CI steps apply to those checkpoints, not to current resource status.

Status markers: **complete** means implemented and validated; **planned** means no
implementation exists yet.

- **Phase 0 — Foundation: complete** — packaging, dependency configuration,
  centralized settings and logging, tests, and initial documentation.
- **Phase 1A — Vehicle Data Model: complete** — immutable canonical vehicle
  representation, validation, normalization, serialization, and stable identities.
- **Phase 1B — Structured Data Ingestion: complete** — official NHTSA ODI
  complaint retrieval, immutable raw artifacts, source-faithful parsing, deterministic JSON
  Lines output, and provenance.
- **Phase 1C — Reliability Event Schema: complete** — immutable canonical
  events, cross-source taxonomies, source traceability, and conservative NHTSA complaint
  mapping.
- **Phase 2A — Exploratory Data Analysis: complete** — reproducible full-corpus
  pandas/NumPy analysis, mapping diagnostics, data-quality visualizations, and documented
  findings without dataset mutation.
- **Phase 2B — Data Cleaning: complete** — deterministic clean JSON Lines,
  evidence-preserving quality flags, explicit exclusions and conservation accounting,
  versioned provenance, and full-corpus validation.
- **Phase 2C — Feature Engineering: complete** — target-agnostic event and broad
  vehicle-cohort tables, stable schemas, versioned provenance, and full-corpus accounting.
- **Phase 2D — NHTSA EWR Production Data Ingestion & Cohort Matching: complete** — official
  public production snapshots, immutable provenance, cumulative-safe aggregation, and
  conservative full-cohort exposure matching diagnostics.
- **Phase 2E — Manufacturer Communications / TSB Ingestion & Cohort Matching: complete** —
  official rich-TSV ingestion, compact-view overlap audit, document/applicability identity,
  structured-only classification, conservative cohort matching, and cross-source coverage.
- **Phase 2F — NHTSA Recall Ingestion & Cohort Matching: complete** — official complete flat
  corpus ingestion, campaign/applicability identity, product-aware filtering, conservative
  cohort matching, and four-source coverage diagnostics.
- **Phase 2G — Multi-Source Integration & Dataset Review: complete** — deterministic
  10,670-row four-source cohort artifact, explicit missingness, cross-source diagnostics,
  temporal feasibility analysis, and evidence-based Phase 3A direction.
- **Phase 3A — Define ML Target: complete** — versioned cohort-level future complaint-
  activity targets, explicit eligibility/censoring, full cutoff/horizon diagnostics, leakage
  audit, and a selected 2022 year-end/12-month/at-least-one-report target.
- **Phase 3B — Baseline ML Models: complete** — leakage-safe cutoff reconstruction,
  frozen stratified split, trivial rules, traditional sklearn models, family/identity
  ablations, persisted artifacts, and age/support/source diagnostics.
- **Phase 3B checkpoint decision.** Phase 3C was justified only as a controlled comparison
  against the frozen random-forest baseline; sparse and old-cohort behavior must improve
  rather than being hidden by aggregate metrics.
- **Phase 3C — PyTorch Dataset Pipeline: complete** — exact Phase 3B input validation,
  training-only preprocessing, deterministic feature manifest, float32 Dataset objects,
  portable seeded DataLoaders, and reproducible metadata without model training.
- **Phase 3D — First Neural Network: complete** — bounded small-MLP comparison,
  validation-only selection, early stopping, deterministic checkpoint/history/results,
  five-seed robustness, calibration, and subgroup diagnostics. The selected MLP did not
  meaningfully improve upon the random forest.
- **Phase 3E — Training Infrastructure: complete** — immutable validated configuration,
  lineage-derived run IDs, atomic run artifacts, exact epoch-boundary resume, explicit
  train/evaluate separation, reproducibility manifests, and automatic forest comparison.
- **Phase 3F — Evaluation: complete** — aligned frozen prediction artifacts, deterministic
  aggregate and paired bootstrap intervals, calibration, fixed-threshold sensitivity,
  subgroup uncertainty, error/agreement analysis, and preferred-model handoff.
- **Phase 4A — Explainability: complete** — deterministic feature mapping, exact local
  tree-path probability contributions, global family/source summaries, validation permutation
  cross-check, representative explanations, reconstruction and terminology guards.
- **Phase 4B — Complaint-Activity Presentation and Decision Contract: complete** — immutable
  versioned result schema, literal probability/classification labels, compact Phase 4A
  explanations, factual evidence profiles, evaluated limitation flags, deterministic
  serialization, representative results, and a constrained Phase 5A handoff.
- **Phase 4B rename history.** The original planned milestone was **Phase 4B — Risk
  Scoring**. It was formally reframed after target/evaluation validation because observed
  future complaint activity cannot support a reliability or repair-risk score.
- **Phase 5A — FastAPI: complete** — explicit application factory, fail-fast frozen-artifact
  validation, application-lifetime resource loading, indexed deterministic cohort discovery,
  typed complaint-activity retrieval, structured errors, OpenAPI, and versioned API artifact.
- **Phase 5B — Model Registry / Loading: complete** — immutable portable manifest, explicit
  bundle selection, path-safe local artifact store, checksum-first loading, cross-artifact
  compatibility validation, typed read-only inference bundle, and unchanged API behavior.
- **Phase 6A — AWS S3: complete** — explicit local/S3 backend selection, safe relative-key
  object mapping, downloaded-byte checksum validation, deterministic fail-closed/idempotent
  publication, least-privilege reader policy, and validated local/S3 inference equivalence.
- **Phase 6B — AWS Deployment: complete** — non-root versioned container, ECR image contract,
  ECS Fargate task/service definitions, distinct least-privilege roles, ALB health/network
  design, and deterministic deployment contract. Implementation and local/static validation
  are complete; live AWS deployment was not executed.
- **Phase 6C — Monitoring: complete** — structured local/container logging, bounded request
  correlation, lifecycle/request events, ECS CloudWatch Logs routing with finite retention,
  four native-metric alarm specifications, and a deterministic monitoring contract.
  Implementation and local/static validation are complete; live CloudWatch validation was
  not executed.
- **Phase 7A — CI: complete** — one least-privilege GitHub Actions workflow with separate
  quality, test, deterministic-contract, and non-publishing Docker jobs; explicit clean-runner
  versus full-artifact test handling; and a versioned CI contract. Local implementation and
  structural validation are complete; no live GitHub Actions run was executed.
- **Phase 7B — CD: complete** — manual trusted-SHA deployment workflow, GitHub OIDC,
  least-privilege deployment-role templates, build-once immutable ECR images, validated ECS
  task revisions, bounded stability/smoke, and failure-preserving rollback. Implementation
  and local/static validation are complete; live CD/ECR/ECS/smoke were not executed.
- **Phase 7C — Terraform: complete** — one production-oriented Terraform root for the
  established network, protected S3, immutable ECR, ECS/ALB foundation, distinct IAM roles,
  GitHub OIDC identity, logs, and four alarms. Static implementation validation is complete;
  Terraform CLI validation, live plan, apply, and all AWS acceptance remain unexecuted.
- **Historical Phase 7C checkpoint:** Terraform implementation was complete at that stage.
  Current demo and deployment boundaries are described above; infrastructure reconciliation
  is deliberately deferred.
- **Phase 8A — Owner Report NLP: Milestones A through F implemented** — standalone offline
  deterministic extraction scope, taxonomy v1, and annotation/evaluation protocol are defined
  in the [specification](owner-report-nlp.md) and
  [annotation guide](owner-report-nlp-annotation-guide.md). The synthetic-tested input adapter
  provides streaming accounting, grouping, date controls, provenance and a local CLI.
  C adds a versioned component lexicon and original-text mention spans. D adds a versioned
  symptom lexicon, bounded assertion scope and conservative local associations, with legacy
  NLP-schema compatibility. E persists disk-backed memberships, transitive duplicate-safe
  evaluation keys and explicit temporal/eligible accounting. F adds verified, deterministic
  descriptive summaries with distinct-report denominators and separate completion provenance.
  Full-corpus NLP processing and independent quality evaluation remain deferred. See the
  specification for the Milestone F acceptance boundary and bounded G1 performance evidence.
  G1 completed a bounded real-data smoke benchmark. G2A prepares reproducible blinded
  100/100 development/held-out worksheets with global duplicate isolation; see the
  [review workflow](owner-report-nlp-review-workflow.md). At the G2A checkpoint, human annotation, custody assignment
  and scoring were outstanding; G2A did not run full-corpus NLP. Subsequently, five development
  reports were manually reviewed and scored, and targeted rules were improved. G2C.2 prepared
  20 fresh challenge reports, whose annotation is now deferred; no independent quality claim follows.
- **Phase 8B — Source Normalization: planned**
- **Phase 8C — NLP Integration: planned**
- **Phase 9 — Component-Level Prediction: planned**
- **Phase 10 — Minimal Frontend: local scope delivered in H3/H3.1**, without a cloud frontend deployment.
- **Phase 11 — Production Readiness: planned**
