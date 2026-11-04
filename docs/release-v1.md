# Local v1.0 release and artifact preservation

Release preparation completed 2026-11-04. All planned feature development is finished.
This is the local v1.0 checkpoint; existing Python package metadata remains 0.1.0 and
versioned API/model/evidence contracts retain their own versions. No Git tag, commit or push
is created automatically. Public licensing remains an owner decision; see [licensing](licensing.md).

## Install and run

Use Python 3.12 and the pinned project/development dependencies. Installation can require
package downloads; the provisioned application operates locally without cloud services.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn howreliable.demo.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>; stop with Ctrl+C. See the [local walkthrough](local-demo.md).
The historical SQLite index is required. The official evidence artifact, frozen ML bundle
and global NLP summary are independent optional additions. A Git clone alone does not
include these ignored inputs, and the server never acquires or builds them automatically.

Complaint history, official recall/document evidence, P4 purchase readiness, P5 advertised
asking-price comparisons, historical 2023 ML and experimental global NLP remain separate.
Source snapshot matches do not verify VIN/trim/Canadian applicability or repair completion.
Purchase inputs are unverified; prices are not appraisals; complaint counts are not failure rates.

## Exact artifact inventory

Current source root: `C:\Users\orjue\Documents\HowReliable`.
The ignored file `artifacts/release/v1.0/artifact-inventory.json` enumerates **30 files**,
each with repository-relative path, byte size, SHA-256 and Git-ignore verification.
It records the existing Git HEAD and notes that reviewed source changes are still uncommitted.
Do not mistake that HEAD alone for the complete current source tree.

| Purpose | Paths relative to the source root | Requirement |
| --- | --- | --- |
| Complaint history | `data/processed/demo/history-v1-20261102-v2.sqlite` and `.sqlite.provenance.json` | Required, 317,716,164 bytes combined |
| Official evidence | `data/processed/official/p7-20261104-v1/evidence.sqlite` and `manifest.json` | Optional; 1,943,492,720 bytes combined |
| Frozen historical ML | `artifacts/registry/bundles/howreliable-rf-2022-cutoff-v1/manifest.json`, `manifest.sha256`, and all 12 registered locations | Optional; 14 files, 56,858,044 bytes combined |
| Global older NLP sample | `artifacts/nlp/owner-reports/g1-smoke-20261027-seed-8a01/summary.json` and `.json.provenance.json` | Optional, 2 files |
| Historical regression fixtures | `artifacts/presentation/representative-results.json`; `artifacts/explainability/representative-local-explanations.json`; `artifacts/cloud/{deployment-contract,s3-contract,monitoring-contract}.json` | Needed for the provisioned full regression suite |
| Source/restoration receipts | Both P7 raw `acquisition-manifest.json` files, both processed `ingestion.provenance.json` files, and `artifacts/release/v1.0/fixture-restoration.json` | Preserve source identity and restoration audit trail |

The inventory gives every exact path, including the model's registered data under
`data/processed/modeling/` and `data/processed/targets/`; copying only the model directory is
insufficient. All 30 files are present and ignored by Git. Together they are 2,318,253,746
bytes (approximately 2.16 GiB), excluding the small inventory file itself.

The complaint-index checksum is
`e9e1fb211a6c7b7ac929c7e9deca6a48bc32ce7a818a7372ab028f32f2517948`.
The official database checksum is
`221b27fd825c5e1c47c5c4746c1744feb3402ec55e7bbd64f84ad0cf9fac35a1`.

The clean complaint corpus and P7 raw/canonical data are not required merely to run the
restored demo. They remain valuable reproducibility inputs and must not be deleted:

```text
data/raw/nhtsa/complaints/
data/interim/nhtsa/complaints/
data/processed/nhtsa/complaints/
data/raw/nhtsa/recalls/p7-20261104-v1/
data/raw/nhtsa/manufacturer_communications/p7-20261104-v1/
data/processed/recalls/p7-20261104-v1/
data/processed/manufacturer_communications/p7-20261104-v1/
artifacts/official/p7-20261104-v1/    # processing/resource receipts and temporary-run helper
```

Archive these separately if full research reproducibility is desired. That is a larger copy
than the runtime inventory and requires its own explicit size/scope approval. Annotation
worksheets/private mappings are not demo prerequisites. No data, provenance, helper script
or backup was deleted as part of release preparation.

## Backup procedure and verified release copy

Executed with owner approval on 2026-11-04 at the destination below: all 30 artifacts
(2,318,253,746 bytes) and the inventory copy passed SHA-256 verification. No existing backup
was overwritten. The saved inventory SHA-256 is
`3c637c993d3fb7d54b2e134c79e529256613e343d6dcc880725f472102306515`.
The inventory records the pre-release source HEAD; the separately reviewed release commit
preserves the final source. Its artifact hashes remain authoritative for this backup.

Recommended new destination:
`C:\Users\orjue\Documents\HowReliable-Backups\v1.0-20261104`.
This is a same-laptop staging/rollback copy; an owner-selected external drive is preferable
for protection against laptop/disk loss. No large copy is authorized by this document alone.
Stop local writers first. Preserve reviewed source separately through the owner's eventual
Git commit or a complete source copy including untracked P7 files; do not back up only HEAD.

After explicit copy approval, define this helper in PowerShell. It validates every source
and destination conflict before copying, enforces directory containment, refuses different
existing bytes, and verifies each copied file. It never overwrites an existing file.

```powershell
function Copy-VerifiedReleaseFiles {
    param([string]$From, [string]$To, [string]$InventoryPath)
    $fromRoot = [IO.Path]::GetFullPath($From).TrimEnd('\') + '\'
    $toRoot = [IO.Path]::GetFullPath($To).TrimEnd('\') + '\'
    $index = Get-Content -LiteralPath $InventoryPath -Raw | ConvertFrom-Json
    $pending = @()
    foreach ($item in $index.files) {
        if ([IO.Path]::IsPathRooted($item.path)) { throw 'Absolute inventory path rejected' }
        $source = [IO.Path]::GetFullPath((Join-Path $fromRoot $item.path))
        $target = [IO.Path]::GetFullPath((Join-Path $toRoot $item.path))
        if (-not $source.StartsWith($fromRoot, [StringComparison]::OrdinalIgnoreCase) -or
            -not $target.StartsWith($toRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Inventory path leaves its allowed root'
        }
        if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or
            (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $item.sha256) {
            throw "Missing or mismatched source: $($item.path)"
        }
        if (Test-Path -LiteralPath $target) {
            if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or
                (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $item.sha256) {
                throw "Conflicting destination: $($item.path)"
            }
        } else {
            $pending += [pscustomobject]@{ Source=$source; Target=$target; Hash=$item.sha256 }
        }
    }
    foreach ($item in $pending) {
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($item.Target)) | Out-Null
        [IO.File]::Copy($item.Source, $item.Target, $false)
        if ((Get-FileHash -LiteralPath $item.Target -Algorithm SHA256).Hash -ne $item.Hash) {
            throw "Post-copy checksum mismatch: $($item.Target)"
        }
    }
}

$repoRoot = 'C:\Users\orjue\Documents\HowReliable'
$backupRoot = 'C:\Users\orjue\Documents\HowReliable-Backups\v1.0-20261104'
$inventoryPath = Join-Path $repoRoot 'artifacts/release/v1.0/artifact-inventory.json'
if (Test-Path -LiteralPath $backupRoot) { throw 'Choose a new backup destination' }
Copy-VerifiedReleaseFiles -From $repoRoot -To $backupRoot -InventoryPath $inventoryPath
$savedInventory = Join-Path $backupRoot 'artifacts/release/v1.0/artifact-inventory.json'
[IO.File]::Copy($inventoryPath, $savedInventory, $false)
if ((Get-FileHash -LiteralPath $inventoryPath).Hash -ne
    (Get-FileHash -LiteralPath $savedInventory).Hash) { throw 'Inventory copy mismatch' }
```

Restoration, after approval: provision the source checkout/dependencies first, define the
same helper, set `$repoRoot` to the new repository, and use the saved inventory:

```powershell
$savedInventory = Join-Path $backupRoot 'artifacts/release/v1.0/artifact-inventory.json'
Copy-VerifiedReleaseFiles -From $backupRoot -To $repoRoot -InventoryPath $savedInventory
$restoredInventory = Join-Path $repoRoot 'artifacts/release/v1.0/artifact-inventory.json'
if (Test-Path -LiteralPath $restoredInventory) {
    if ((Get-FileHash -LiteralPath $restoredInventory).Hash -ne
        (Get-FileHash -LiteralPath $savedInventory).Hash) { throw 'Inventory conflict' }
} else {
    [IO.File]::Copy($savedInventory, $restoredInventory, $false)
}
```

The helper checks all conflicts before writing; matching existing files are left intact.
Retain the inventory and its SHA-256 separately with the backup. It validates byte identity,
not trust in a downloaded model: restore only the owner's trusted model bundle. After copying,
run the registry validator if the optional ML bundle was restored, then launch the demo and
check both reference cohorts. No ingestion/index reconstruction is needed for restoration.

## Test cleanup and fixture provenance

All previous 5 failures and 7 setup errors are resolved without changing source data or
frozen artifacts. The three formerly absent fixtures were also absent at their exact paths
in the named recovery folder. Their legitimate local recovery methods are:

- Deployment contract: existing `generate_deployment_contract_artifact()`, timestamp
  `2026-09-19T12:00:00Z`; historical SHA-256
  `c4e6806743421eb1e0feebf27522aec5caa1e9fc87675daaee18c1e5b30b71e4` matched exactly.
- S3 contract: existing `generate_s3_contract_artifact()`, timestamp
  `2026-09-15T20:00:00Z`; historical SHA-256
  `8f55b5164ef35c3a7758c4867af784b6ea27d4e3a4e28bbf7b779948b1e0163a` matched exactly.
- Local explanations: the original JSON writer serializes
  `{"examples": verified_report["representative_local_explanations"]}` from the registered
  `explainability-report.json`. All six examples are copied without recomputation. The
  restored file hash is `11c8e56d9947f4b2d9b16a8bde4542469f152abae1ea96c33eb4bc2d46b8d183`.
  Its original standalone historical checksum is unknown; byte-identical historical recovery
  is not claimed. Registered report checksum and semantic identity were verified.

Existing targets were checked absent and not overwritten. Independent temporary candidates
were verified first; no expected checksum, source report or model was changed. The ignored
`fixture-restoration.json` records this provenance. Contract generators only write local JSON;
they make no AWS calls. Explanation extraction does not run training, NLP or dataset pipelines.

The neural test restores identical weights but evaluates in batches of 8 versus the training
helper's 64. On this CPU, float32 matrix rounding changes logits by at most
`2.9802322387695312e-08`, probabilities by `7.350069108902346e-09`, and Brier score by
`5.682015968844212e-11`. Only the recomputed Brier comparison now permits `abs=1e-10, rel=0`.
Exact histories, checkpoint weights, discrete/other metrics and existing loss checks remain.
No production numerical code, model training pipeline or unrelated test coverage was changed.

## Final validation and remaining limits

The provisioned full suite passes **956 tests**, with **one skipped** optional full-corpus
PyTorch pipeline test because its separate Phase 3B research inputs are absent. Synthetic
PyTorch coverage still runs. This is not an application defect and does not affect the
frozen random forest or local demo. The existing Starlette/AnyIO deprecation warning remains.
Ruff, strict mypy across 155 files, dependency checks, JavaScript syntax and documentation
links pass. Real/synthetic desktop/mobile Edge smoke tests and native keyboard checks pass;
spoken screen-reader and cross-browser certification are not claimed.

| Reference cohort | Complaint reports / rows | Recall campaigns | Communication documents |
| --- | --- | ---: | ---: |
| 2011 BMW 335i | 22 / 35 | 7 | 8 |
| 2011 Toyota Corolla | 23 / 32 | 9 | 101 (10-record preview) |

Official loading, corrupt/missing-source fallback, model-free startup, P4/P5 independence,
safe rendering and stale-response protection are covered. The historical index hash remains
unchanged. Clean clones need the documented artifacts to reproduce the provisioned results.
No large backup, data acquisition/rebuild, model retraining, cloud operation, commit or push
was performed during release cleanup. Local v1.0 is ready; review the combined P7/cleanup
source, tests and docs before an explicitly requested commit. Keep every generated artifact,
environment, private annotation/recovery material and Terraform state out of that commit.
