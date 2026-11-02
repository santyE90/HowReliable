# Licensing status and owner decision

As of the H4B documentation checkpoint, the repository has no explicit license file and
`pyproject.toml` declares no project license. No license has been selected or added by this
milestone. Final selection requires owner approval; public visibility is not itself an
explicit project license grant.

## Separate considerations

- **Source code and documentation:** the owner must choose intended permissions and any
  attribution requirements after considering contributors and third-party code/assets.
- **Dependencies:** installed libraries retain their own licenses. A future distribution,
  container, or bundled demo should review relevant dependency notices and obligations.
- **Upstream NHTSA data:** identify the exact source and applicable source-specific terms
  before redistributing snapshots or excerpts. Do not assume a future repository license
  automatically covers upstream data or removes privacy considerations in owner narratives.
- **Generated artifacts:** model bundles, derived indexes, charts, and summaries need an
  explicit distribution decision considering their inputs and any included third-party
  content. A checksum proves identity, not permission to redistribute.
- **Annotation/recovery materials:** private mappings, narratives, credentials, local state,
  and evaluation materials are not approved public-release assets. Keep them excluded.

H4C screenshots should show aggregate dashboard outputs without raw narratives, personal
details, credentials, or local filesystem information. Actual captures must retain accurate
historical-model and global-NLP limitations.

This document records unresolved project decisions, not a replacement for an approved license
or a determination of every upstream data/dependency term. No new public artifact download is
authorized by documenting these considerations.
