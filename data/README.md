# Local data layout

Downloaded and generated data are intentionally excluded from Git.

```text
data/
  raw/nhtsa/complaints/       # immutable official ZIP artifacts
  interim/nhtsa/complaints/   # deterministic JSON Lines and provenance
  processed/nhtsa/complaints/ # accepted clean rows, exclusions, and provenance
  processed/modeling/        # frozen as-of feature data and split
  processed/targets/         # historical complaint-activity targets and provenance
  processed/demo/            # narrative-free SQLite history index and completion marker
  processed/nlp/             # bounded exploratory extraction outputs; not full-corpus coverage
```

Never edit or overwrite a raw artifact. Retrieve a newly published artifact under its
official filename and use its SHA-256 checksum and provenance sidecar to distinguish it.

The installed browser demo requires the generated historical index and its provenance sidecar.
The separately restored canonical model bundle and P7 official-evidence SQLite/manifest pair
are optional panels. These ignored artifacts are not delivered by a clean Git clone.
See the [v1.0 inventory and backup guide](../docs/release-v1.md), [reproducibility](../docs/reproducibility.md) and
[local demo setup](../docs/local-demo.md). Do not commit datasets, indexes, models, or private
annotation materials. Source terms and artifact distribution remain separate owner decisions.

